# Watchdog

Monitor de seguridad continuo para esta maquina Kali (WSL2), corriendo por
cron: escaneo liviano cada 15 minutos, escaneo pesado cada hora que termina
con una auditoria de integridad (procesos vs paquetes instalados,
certificados de confianza). Hallazgos se enriquecen con VirusTotal,
AlienVault OTX y AbuseIPDB, y se resuelven segun una politica de
cuarentena/borrado configurable.

## Que es y que NO es

**Es:**
- Un pipeline de deteccion heuristica (rutas sospechosas, binarios no
  empaquetados, cambios en el cert store, puertos/hosts nuevos) +
  enriquecimiento con threat intel real (VT/OTX/AbuseIPDB).
- Un detector de anomalias de comportamiento **de este equipo especifico**:
  un IsolationForest entrenado sobre la linea base de metricas de *tu*
  sistema (numero de procesos, conexiones, CPU, etc.), exportado a ONNX.
  Esto SI aprende, pero aprende "como es normal que se vea esta maquina",
  no "el modus operandi de atacantes en general".
- Memoria local de IOCs (SQLite): si el mismo hash o IP reaparece, lo
  reconoce mas rapido sin volver a pegarle a las APIs externas.
- Triage opcional asistido por LLM (via OpenRouter): lee el hallazgo + la
  intel ya recolectada y te da una explicacion en espanol. No entrena nada,
  no "aprende ciberseguridad" - es un resumen, no un cerebro autonomo.

**No es:**
- Un agente de IA autonomo que aprende tacticas de atacantes reales y se
  vuelve mas inteligente con cada ataque. Eso es un proyecto de
  investigacion de meses/anos, no un cron de Python. Si en algun momento
  quieren ir en esa direccion, el punto de partida real seria
  fine-tuning sobre datasets publicos de IOCs/TTPs (MITRE ATT&CK,
  MalwareBazaar, etc.), no "bajar un agente" y ya.
- Un sistema que borra cosas a ciegas. Ver "Politica de respuesta" abajo.

## Arquitectura

```
watchdog/
├── config/config.yaml       # intervalos, exclusiones, umbrales de politica
├── src/watchdog/
│   ├── main.py               # orquestador (--mode light|heavy)
│   ├── scanners/
│   │   ├── network_scan.py   # ss (liviano) + nmap (pesado), diff vs corrida anterior
│   │   ├── host_scan.py      # procesos sospechosos + captura forense (pipeline) + metricas
│   │   ├── os_scan.py        # wrappers de rkhunter / chkrootkit / clamscan
│   │   ├── integrity_scan.py # procesos vs dpkg, certificados vs baseline
│   │   └── persistence_scan.py # authorized_keys, sudoers.d, crontab, self-integrity (cierre del ciclo pesado)
│   ├── intel/                # VirusTotal, AlienVault OTX, AbuseIPDB
│   ├── anomaly/               # IsolationForest -> ONNX (baseline.py entrena, detector.py evalua)
│   ├── response/
│   │   ├── policy.py          # decide: alert_only | quarantine | auto_delete
│   │   └── quarantine.py      # mueve+chmod 000, mata proceso, borra (si corresponde), restaura
│   ├── llm/triage.py          # explicacion opcional via LLM
│   └── storage/db.py          # SQLite: incidents, ioc_memory, metrics_history, cert_baseline, persistence_baseline
├── scripts/
│   ├── install_cron.sh        # crea venv + instala deps + registra los 3 cron jobs
│   ├── train_baseline.py      # entrena el modelo ONNX una vez que hay historial
│   └── offbox_backup.sh       # backup diario (03:30) de db+logs+forense hacia /mnt/c (Windows)
├── data/                      # quarantine/, forensics/, baseline/, watchdog.db (gitignored)
└── logs/watchdog.log
```

## Setup

```bash
cd /watchdog
cp .env.example .env
# Editar .env con tus API keys (todas opcionales, ver abajo de donde sacarlas)

bash scripts/install_cron.sh
```

Esto crea el venv, instala dependencias, y registra 2 lineas en tu crontab
de usuario (no root):

```
*/15 * * * *  PYTHONPATH=/watchdog/src ... watchdog.main --mode light
0 * * * *     PYTHONPATH=/watchdog/src ... watchdog.main --mode heavy
```

### Permisos (necesario para el ciclo pesado)

`rkhunter` y `chkrootkit` necesitan root. Para que el cron no se quede
colgado pidiendo contrasena, dar sudo NOPASSWD **solo** para esos dos
binarios (no para sudo en general):

```bash
sudo visudo -f /etc/sudoers.d/watchdog
```

Contenido a agregar (reemplazar `deamon` si tu usuario es otro):

```
deamon ALL=(root) NOPASSWD: /usr/bin/rkhunter, /usr/sbin/chkrootkit
```

Sin esto, `os_scan.py` simplemente loguea que no pudo correrlos y sigue
con el resto del pipeline (no rompe nada, solo se pierde esa cobertura).

### API keys (todas con free tier, todas opcionales)

| Servicio | Free tier | Link |
|---|---|---|
| VirusTotal | 4 req/min | https://www.virustotal.com/gui/my-apikey |
| AlienVault OTX | gratis | https://otx.alienvault.com/api |
| AbuseIPDB | 1000 req/dia | https://www.abuseipdb.com/account/api |
| OpenRouter (para triage LLM opcional) | segun tu cuenta | ya la tenes en `genomic_agent/.env` si queres reusarla |

Sin ninguna key configurada, el watchdog sigue funcionando en modo
heuristico puro (rutas sospechosas, binarios no empaquetados, diffs de
red/certs) - solo pierde el enriquecimiento externo.

## Politica de respuesta

Elegida explicitamente para minimizar el riesgo de que un falso positivo
(que existen - ver nota abajo) borre algo importante:

1. **Cuarentena siempre.** Cualquier hallazgo con senal real (intel
   positiva o heuristica de proceso/archivo) se mueve a
   `data/quarantine/`, se le pone `chmod 000`, y se mata el proceso si
   sigue vivo. Nunca queda ejecutandose.
2. **Borrado automatico solo con confianza muy alta:** VirusTotal
   `positives >= 15` Y `total >= 70` **Y** AlienVault OTX confirma el
   mismo hash con al menos un pulse. Ajustable en
   `config.yaml -> policy`.
3. **Certificados: nunca accion automatica.** Un cambio en el cert store
   se reporta siempre como alerta para revision humana - borrar un CA
   real a ciegas puede romper TLS en toda la maquina.
4. **Cada accion queda registrada** en `data/watchdog.db` (tabla
   `incidents`) con el hash, el intel recibido, y la ruta del forense
   (`data/forensics/*.json`: cadena de procesos padre, archivos abiertos,
   conexiones de red) guardado ANTES de tocar nada.

## Monitoreo de persistencia y backup off-box

Agregados despues de una revision de "que le falta a esto" - los vectores
clasicos de persistencia post-compromiso no estaban cubiertos por los
scanners originales:

- **`persistence_scan.py`** (corre al final del ciclo pesado, junto con
  `integrity_scan.py`): hashea `~/.ssh/authorized_keys`, todo
  `/etc/sudoers.d/*`, la salida de `crontab -l`, y **el propio codigo
  fuente de watchdog** (`src/watchdog/**/*.py`), y compara contra un
  baseline en `persistence_baseline`. Cualquier cambio es **siempre
  alert_only** - nunca se revierte nada automaticamente, porque "arreglar"
  sudoers o cron mal puede dejarte sin acceso al sistema.
- **Limitacion honesta:** si un atacante ya tiene root, tambien puede
  editar `watchdog.db` (el baseline vive ahi) y este chequeo deja de ser
  confiable por si solo. No es una garantia criptografica, es deteccion
  temprana - por eso existe el backup off-box de abajo.
- **`scripts/offbox_backup.sh`** (cron diario 03:30): copia
  `data/watchdog.db`, `data/forensics/`, `logs/` y `config/config.yaml`
  a `/mnt/c/Users/elanz/watchdog-backups/` (lado Windows, fuera del
  dominio de confianza de Linux) como `.tar.gz` con retencion de 30 dias.
  **No** copia `data/quarantine/` a proposito - son muestras
  potencialmente maliciosas, no tiene sentido replicarlas al lado
  "limpio". Si Kali se compromete y el atacante borra la evidencia local,
  la copia de Windows sigue estando ahi.

### Restaurar un falso positivo

```python
from watchdog.response.quarantine import restore
restore(logger, "/watchdog/data/quarantine/169...._archivo", "/ruta/original")
```

### Nota sobre falsos positivos (de la auditoria manual que motivo este proyecto)

`chkrootkit` marco binarios de un venv de Python (`pip`, `streamlit`,
`flake8`) como "Possible Linux.Xor.DDoS" solo por no venir de un paquete
Debian. `config.yaml -> exclude_paths` ya excluye `venv/`,
`node_modules/`, `site-packages/`, etc. de `integrity_scan.py` y filtra el
ruido de `chkrootkit` que menciona "From Debian package" o rutas
excluidas - pero si agregas nuevos venvs fuera de esos patrones, agrega la
ruta a `exclude_paths`.

## Entrenar el detector de anomalias

Necesita historial real de tu maquina (el cron ya lo va acumulando en cada
corrida, en `metrics_history`). Por defecto pide 200 muestras (~2 dias a
15 min):

```bash
cd /watchdog && .venv/bin/python scripts/train_baseline.py
```

Se puede re-correr periodicamente (ej. una vez por semana via otro cron)
para que el baseline se actualice si tu uso normal de la maquina cambia.

## Tests

```bash
cd /watchdog && .venv/bin/pytest tests/ -v
```

## Logs

- `logs/watchdog.log` - log estructurado de cada corrida.
- `logs/cron.log` - stdout/stderr crudo de cron (por si algo explota antes
  de que el logger de Python arranque).
- `data/watchdog.db` - tabla `incidents` tiene el historial completo
  consultable con cualquier cliente SQLite (`sqlite3 data/watchdog.db`).

## Limitaciones conocidas

- `auditd` no funciona en WSL2 (kernel sin soporte completo de audit) -
  por eso la trazabilidad de procesos usa `psutil` (cadena de padres,
  archivos abiertos, conexiones) en vez de logs de auditoria del kernel.
- El nmap de red pesado escanea el CIDR configurado en `config.yaml`
  (default: la red virtual WSL detectada en la auditoria). Si tu red real
  es otra, ajustar `network.local_cidr`.
- El detector de anomalias es tan bueno como el baseline: en una maquina
  con uso muy irregular (prender/apagar VMs, correr benchmarks, etc.) va
  a tener mas falsos positivos hasta que el modelo vea suficiente
  variedad de "normal".
