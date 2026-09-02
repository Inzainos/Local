# 🧠 Consenso de Expertos Multi-Modelo con Memoria Compartida

Sistema multi-agente local impulsado por **Ollama**, donde tres modelos de IA especializados colaboran mediante una **Memoria Compartida (Blackboard Architecture)** y un **Protocolo de Consenso con Refinamiento Iterativo**.

---

## 🏛️ Arquitectura del Concilio de Expertos

```mermaid
flowchart TD
    User([👤 Usuario / Petición]) --> Router[🧭 Router de Tareas]
    
    subgraph SharedMemory ["🧠 MEMORIA COMPARTIDA UNIFICADA (Blackboard + SQLite)"]
        direction TB
        B_Prompt["📌 Petición & Casos de Uso"]
        B_Research["🔍 Hallazgos & Algoritmos (Nemotron)"]
        B_Code["💻 Código Desarrollado (DeepSeek)"]
        B_Critique["⚖️ Auditoría & Consenso (Gemma)"]
        B_History["🗄️ Historial Persistente & Hechos"]
    end
    
    Router -->|1. Inicia Blackboard| SharedMemory
    
    subgraph Agents ["🤖 Expertos Especializados"]
        Nemotron["🔍 Investigador & Búsqueda\n(nemotron-mini)"]
        DeepSeek["💻 Ingeniero & Coder\n(deepseek-r1:1.5b)"]
        Gemma["⚖️ Auditor & Optimizador\n(gemma2:2b)"]
    end
    
    SharedMemory <-->|Lectura/Escritura| Nemotron
    Nemotron -->|2. Reporte Técnico| SharedMemory
    
    SharedMemory <-->|Lee Investigación| DeepSeek
    DeepSeek -->|3. Propuesta de Código| SharedMemory
    
    SharedMemory <-->|Audita Código & Requisitos| Gemma
    Gemma -->|4. Calificación (0-100)| Decision{¿Puntaje >= 85?}
    
    Decision -- No (Requiere Mejora) -->|Feedback de Optimización| DeepSeek
    Decision -- Sí (Consenso Aprobado) --> Synthesis[✨ Síntesis Final Consensuada]
    
    Synthesis --> Output([🚀 Respuesta Definitiva al Usuario])
```

---

## 👥 Especialización de los Modelos

| Rol | Modelo Ollama | Responsabilidad Clave |
| :--- | :--- | :--- |
| **🔍 Investigador** | `nemotron-mini` | Búsqueda, análisis minucioso de requisitos, selección de algoritmos óptimos, casos borde y arquitectura. |
| **💻 Programador** | `deepseek-r1:1.5b` | Implementación de código modular, tipado, manejo de excepciones y refactorizaciones según las críticas. |
| **⚖️ Optimizador / Árbitro** | `gemma2:2b` | Auditoría de rendimiento, seguridad, cálculo de la Puntuación de Consenso (0-100) y síntesis final aprobada. |

---

## 🚀 Inicio Rápido

### 1. Activar el entorno virtual
```bash
source /home/deamon/consensus-expert-agent/.venv/bin/activate
```

### 2. Verificar estado de los modelos
```bash
python main.py --check
```

### 3. Modo Terminal Interactivo (CLI)
```bash
python main.py
```

### 4. Modo Ejecución Directa de una Tarea
```bash
python main.py --task "Crea una función en Python para calcular la ruta más corta usando Dijkstra con optimización de cola de prioridad."
```

### 5. Modo Interfaz Web Gráfica (Dashboard)
```bash
python main.py --web --port 8000
```
Luego abre tu navegador en: `http://localhost:8000`

### 6. Bot de Telegram — Consensus + Sentinel Omega Bridge
```bash
# Configurar credenciales (una sola vez)
cp .env.example .env
# Editar .env con TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID

# Ejecutar bot
./run_telegram_bot.sh
# O directamente:
python telegram_bot.py
```

**Comandos disponibles en Telegram (@IngZainos_bot):**
| Comando | Función |
|---------|---------|
| `/start` | Menú principal con botones inline |
| `/task <prompt>` | Enviar tarea al Concilio (Nemotron → DeepSeek → Gemma) |
| `/audit [foco]` | Auditar Sentinel Omega (tests, secrets, migrations, automation) |
| `/status` | Estado Sentinel Omega (ciclos, precursores, Juez) |
| `/blackboard` | Ver pizarra de consenso activa |
| `/cancel` | Cancelar tarea en curso |

**Flujo bidireccional:**
- **Sentinel Omega → Usuario**: Alertas de precursores via `tg.send_alert()`
- **Usuario → Consenso**: Comandos `/task`, `/audit`, `/status` procesados por el bot

**Concilio en acción (verificado en logs):**
1. Usuario envía `/task "Puedes revisar la seguridad"` o usa botón "🚀 Nueva Tarea"
2. Bot muestra: `🔄 Iniciando Concilio... 🔍 Nemotron investigando... 💻 DeepSeek codificando... ⚖️ Gemma auditando...`
3. **Nemotron** (investigador): Analiza requerimientos, busca patrones, propone arquitectura → escribe en Blackboard
4. **DeepSeek** (coder): Lee investigación, implementa código modular tipado → escribe en Blackboard
5. **Gemma** (optimizador): Audita código+requisitos, calcula score (0-100), sintetiza → resultado final
6. Si score < 85: Gemma envía feedback a DeepSeek → refinamiento iterativo (máx 3 rondas)
7. Resultado final: Bot edita mensaje original con síntesis completa + teclado principal

**Ejemplo real (02/09/2026 07:30-07:35):**
- Usuario: "Puedes revisar la seguridad"
- 4 llamadas Ollama secuenciales (Nemotron → DeepSeek → Gemma → Síntesis)
- Respuesta final entregada via `editMessageText` en <5 min

---

### 7. Dashboard Web (Streamlit)
```bash
cd /home/deamon/workspaces/sentinel_omega
python -m streamlit run sentinel_omega/infrastructure/dashboard/app.py --server.port 8502 --server.address 0.0.0.0
```
Acceso: `http://localhost:8502` (local) | `http://192.168.1.144:8502` (red LAN)

Tabs: Precursor Risk (Fantasma) | Muro 5 Eventos | SNT Engine | Alerts & Charts | Database | Agent Tab

---

## ⚙️ Configuración (`config.yaml`)

Puedes personalizar los modelos, umbrales de consenso y temperaturas en `config.yaml`:

```yaml
consensus:
  threshold_score: 85         # Puntaje mínimo para aprobar la solución
  max_refinement_rounds: 3    # Rondas máximas de mejora entre Coder y Optimizador

roles:
  researcher:
    model: "nemotron-mini"
  coder:
    model: "deepseek-r1:1.5b"
  optimizer:
    model: "gemma2:2b"
```
