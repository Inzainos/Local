# Despliegue de Sentinel Omega — servidor permanente

Guía para dejar a Roy corriendo 24/7 en tu servidor (Linux) o en la MSI Katana (Windows).

## Linux (recomendado — systemd con auto-restart)

```bash
# 1. Clonar (o git pull si ya existe)
git clone https://github.com/Inzainos/workspaces.git sentinel-omega
cd sentinel-omega

# 2. Instalar (crea venv, dependencias y el servicio)
bash deploy/install.sh

# 3. Poner tus keys
nano deploy/.env

# 4. UNA SOLA VEZ: cargar 30 años + entrenar firmas (tarda ~30-60 min)
.venv/bin/python sentinel_omega/launcher.py --backcast --entrenar --once --dry-run

# 5. Arrancar 24/7
sudo systemctl enable --now sentinel-omega
```

El servicio se reinicia solo si el proceso muere y arranca solo al prender el servidor.

### Operación diaria

| Qué | Comando |
|---|---|
| Estado | `systemctl status sentinel-omega` |
| Logs en vivo | `journalctl -u sentinel-omega -f` |
| Actualizar versión | `git pull && sudo systemctl restart sentinel-omega` |
| Detener | `sudo systemctl stop sentinel-omega` |
| Dashboard | `.venv/bin/streamlit run sentinel_omega/infrastructure/dashboard/app.py` |

## Windows (MSI Katana)

```bat
git clone https://github.com/Inzainos/workspaces.git sentinel-omega
cd sentinel-omega
python -m venv .venv
.venv\Scripts\pip install -r sentinel_omega\requirements.txt
REM Pon tus keys como variables de entorno de Windows (Panel de control
REM → Sistema → Variables de entorno), los nombres están en deploy\.env.example
.venv\Scripts\python sentinel_omega\launcher.py --backcast --entrenar --once --dry-run
deploy\run_windows.bat
```

Para auto-arranque: agrega `deploy\run_windows.bat` al Programador de Tareas
(al iniciar sesión) o a la carpeta de Inicio.

## Desde la iPad (o cualquier dispositivo)

La iPad no corre el servidor, pero es el centro de mando:

```bash
# En el servidor, una vez (dashboard 24/7 en el puerto 8501):
sudo cp deploy/sentinel-omega-dashboard.service /etc/systemd/system/
sudo sed -i "s|__REPO_DIR__|$(pwd)|g" /etc/systemd/system/sentinel-omega-dashboard.service
sudo systemctl daemon-reload && sudo systemctl enable --now sentinel-omega-dashboard
```

| En la iPad | Para qué |
|---|---|
| **Safari** → `http://IP-DEL-SERVIDOR:8501` | Dashboard completo (9 pestañas, mapas, fantasma, muro) |
| **Telegram** | Alertas rojas/amarillas al instante |
| **Termius** (o Blink) → SSH al servidor | `journalctl -u sentinel-omega -f`, reiniciar, actualizar |
| **Working Copy** | Ver/editar el repo, pull de versiones |

> **Fuera de casa**: instala [Tailscale](https://tailscale.com) (gratis) en el
> servidor y en la iPad — te da una IP privada segura para llegar al dashboard
> y SSH desde cualquier red, sin abrir puertos al internet.

## Rutinas 24/7 sin servidor (Roy Vigilante — GitHub Actions)

Si no hay servidor propio, `.github/workflows/roy-vigilante.yml` corre el
sistema completo en Actions (el cron dispara en `main`). Hora MX = UTC-6:

| Ritmo | Tarea |
|---|---|
| Cada 2 h | Ciclo del Padre (status + registro + cimática) |
| Cada 4 h | El Juez verifica real vs predicción (USGS, verdad por fila) |
| Cada 6 h | Reporte ejecutivo → correo |
| 12am/12pm | Comparativo contra el día anterior (con gráfica) |
| Dom 12:15pm | Reporte semanal |
| Fin de mes 12:30pm | Reporte mensual |
| Cada corrida | Despacho del outbox de correo |

**Correo (canal de alertas, sin Telegram)** — secrets del repo
(Settings → Secrets and variables → Actions):
- `SMTP_USER` + `SMTP_PASS` — cuenta emisora (app password de Gmail:
  myaccount.google.com/apppasswords)
- `CORREO_DESTINO` — opcional (default elan.zainos.corona@gmail.com)

Sin credenciales los correos quedan PENDIENTES en `tbl_correo_salida`
(no se pierden ni se fingen enviados); los reportes siguen publicándose
al repo en `estado/` como siempre.

## Notas

- **Telegram está en pausa** (el canal es correo); el código sigue ahí — con
  `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` se reactivan las alertas al celular.
- **La base de datos** vive en `sentinel_omega/data/SENTINEL_OMEGA_PRO.db`.
  Respáldala si re-instalas: contiene el backcast de 30 años, las firmas
  entrenadas y el ledger del Juez.
- El flag `--backcast` también corre el backfill secundario (SO2 volcánico
  NASA + BTC Yahoo). Todo es idempotente: re-correrlo no duplica datos.
- **Nunca** pongas keys en el código ni subas `deploy/.env` a git.
