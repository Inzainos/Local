import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json
import asyncio
import os
from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from engine.orchestrator import ConsensusOrchestrator
from memory.shared_context import SharedMemory

app = FastAPI(title="Consenso de Expertos Ollama")
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

orchestrator = ConsensusOrchestrator(config_path="config.yaml")
shared_memory = SharedMemory(db_path=orchestrator.db_path)
task_executor = ThreadPoolExecutor(max_workers=1)
task_jobs = {}

class QueryRequest(BaseModel):
    prompt: str
    session_id: str = "default"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Consenso de Expertos Multi-Modelo</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        .agent-card { transition: all 0.3s ease; }
        .agent-active { border-color: #3b82f6; box-shadow: 0 0 15px rgba(59, 130, 246, 0.5); }
        pre code { border-radius: 0.375rem; }
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col font-sans">

    <!-- Header -->
    <header class="bg-slate-900 border-b border-slate-800 px-6 py-4 flex items-center justify-between shadow-lg">
        <div class="flex items-center space-x-3">
            <div class="bg-blue-600 p-2.5 rounded-xl text-white text-xl">
                <i class="fa-solid fa-brain"></i>
            </div>
            <div>
                <h1 class="text-xl font-bold text-white tracking-wide">Consenso de Expertos Multi-Agente</h1>
                <p class="text-xs text-slate-400">Nemotron (Investigación) + DeepSeek (Código) + Gemma (Consenso & Optimización)</p>
            </div>
        </div>
        <div class="flex items-center space-x-3">
            <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">
                <span class="w-2 h-2 mr-2 bg-emerald-400 rounded-full animate-pulse"></span> Ollama Conectado
            </span>
        </div>
    </header>


    <nav class="max-w-7xl w-full mx-auto px-6 pt-4">
        <div class="flex items-center space-x-3">
            <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-blue-950 text-blue-400 border border-blue-800">
                <span class="w-2 h-2 mr-2 bg-blue-400 rounded-full animate-pulse"></span> Agente Local — Uso General
            </span>
            <span class="text-xs text-slate-400">Personalidad: Capitán (Deamon-X)</span>
        </div>
    </nav>

    <!-- Main Content Grid -->
    <main class="flex-1 max-w-7xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">

        <!-- Left Column: Expert Agents Status & Blackboard -->
        <div class="lg:col-span-4 space-y-6">
            
            <!-- Expert Agents Grid -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-md">
                <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3 flex items-center">
                    <i class="fa-solid fa-users-gear mr-2 text-blue-400"></i> Expertos del Concilio
                </h2>
                
                <div class="space-y-3">
                    <!-- Researcher -->
                    <div id="card-researcher" class="agent-card bg-slate-950/70 border border-slate-800 rounded-lg p-3">
                        <div class="flex items-center justify-between">
                            <div class="flex items-center space-x-2.5">
                                <span class="p-2 rounded-md bg-amber-950 text-amber-400 text-sm"><i class="fa-solid fa-magnifying-glass"></i></span>
                                <div>
                                    <div class="text-xs font-semibold text-white">Nemotron-Mini</div>
                                    <div class="text-[11px] text-slate-400">Búsqueda & Requisitos</div>
                                </div>
                            </div>
                            <span id="badge-researcher" class="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400">Listo</span>
                        </div>
                    </div>

                    <!-- Coder -->
                    <div id="card-coder" class="agent-card bg-slate-950/70 border border-slate-800 rounded-lg p-3">
                        <div class="flex items-center justify-between">
                            <div class="flex items-center space-x-2.5">
                                <span class="p-2 rounded-md bg-blue-950 text-blue-400 text-sm"><i class="fa-solid fa-code"></i></span>
                                <div>
                                    <div class="text-xs font-semibold text-white">DeepSeek-R1</div>
                                    <div class="text-[11px] text-slate-400">Ingeniería & Código</div>
                                </div>
                            </div>
                            <span id="badge-coder" class="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400">Listo</span>
                        </div>
                    </div>

                    <!-- Optimizer -->
                    <div id="card-optimizer" class="agent-card bg-slate-950/70 border border-slate-800 rounded-lg p-3">
                        <div class="flex items-center justify-between">
                            <div class="flex items-center space-x-2.5">
                                <span class="p-2 rounded-md bg-purple-950 text-purple-400 text-sm"><i class="fa-solid fa-scale-balanced"></i></span>
                                <div>
                                    <div class="text-xs font-semibold text-white">Gemma-2</div>
                                    <div class="text-[11px] text-slate-400">Auditoría & Consenso</div>
                                </div>
                            </div>
                            <span id="badge-optimizer" class="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400">Listo</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Blackboard / Shared Memory Viewer -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-md">
                <div class="flex items-center justify-between mb-3">
                    <h2 class="text-sm font-semibold text-slate-300 uppercase tracking-wider flex items-center">
                        <i class="fa-solid fa-database mr-2 text-emerald-400"></i> Memoria Compartida (Blackboard)
                    </h2>
                    <span id="consensus-score-badge" class="text-xs font-bold px-2.5 py-1 rounded bg-slate-800 text-slate-300">
                        Score: --
                    </span>
                </div>
                
                <div id="blackboard-feed" class="bg-slate-950 rounded-lg p-3 text-xs font-mono text-slate-400 h-64 overflow-y-auto space-y-2 border border-slate-800/80">
                    <div class="text-slate-600 text-center py-8">La memoria compartida se actualizará en tiempo real con cada ronda de los expertos...</div>
                </div>
            </div>
        </div>

        <!-- Right Column: Interactive Query & Synthesis Output -->
        <div class="lg:col-span-8 flex flex-col space-y-6">
            
            <!-- Input Area -->
            <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-md">
                <label class="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                    Ingresa tu tarea o requerimiento para el concilio de expertos:
                </label>
                <div class="flex space-x-3">
                    <textarea id="prompt-input" rows="3" class="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 resize-none" placeholder="Ej: Crea un scraper asíncrono en Python con control de concurrencia y reintentos exponenciales..."></textarea>
                    <button id="send-btn" onclick="sendTask()" class="bg-blue-600 hover:bg-blue-500 text-white font-medium px-5 rounded-lg flex flex-col items-center justify-center space-y-1 transition duration-200 shadow-md">
                        <i class="fa-solid fa-paper-plane text-lg"></i>
                        <span class="text-xs font-semibold">Ejecutar</span>
                    </button>
                </div>
            </div>

            <!-- Output Display -->
            <div class="flex-1 bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-md flex flex-col min-h-[420px]">
                <div class="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
                    <h2 class="text-base font-semibold text-white flex items-center">
                        <i class="fa-solid fa-sparkles text-yellow-400 mr-2"></i> Solución Final Consensuada
                    </h2>
                    <div id="status-indicator" class="text-xs text-slate-400 flex items-center">
                        <span class="w-2 h-2 rounded-full bg-slate-600 mr-2"></span> En espera
                    </div>
                </div>

                <div id="output-content" class="flex-1 overflow-y-auto prose prose-invert prose-sm max-w-none text-slate-200">
                    <div class="text-slate-500 text-center py-20">
                        Escribe una tarea arriba y presiona "Ejecutar" para ver la colaboración y el consenso de los tres modelos en tiempo real.
                    </div>
                </div>
            </div>

        </div>

    </main>

    <script>
        async function sendTask() {
            const prompt = document.getElementById('prompt-input').value.trim();
            if (!prompt) return;

            const sendBtn = document.getElementById('send-btn');
            const statusInd = document.getElementById('status-indicator');
            const outputDiv = document.getElementById('output-content');
            const bbFeed = document.getElementById('blackboard-feed');
            const scoreBadge = document.getElementById('consensus-score-badge');

            sendBtn.disabled = true;
            sendBtn.classList.add('opacity-50', 'cursor-not-allowed');
            statusInd.innerHTML = '<span class="w-2 h-2 rounded-full bg-blue-500 animate-ping mr-2"></span> Coordinando expertos...';
            outputDiv.innerHTML = '<div class="text-slate-400 text-center py-16"><i class="fa-solid fa-spinner fa-spin text-3xl mb-3 text-blue-500"></i><br>El concilio de modelos está investigando y escribiendo la solución...</div>';
            bbFeed.innerHTML = '<div class="text-blue-400">[INICIO] Petición registrada en memoria compartida.</div>';

            try {
                const response = await fetch('/api/task', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: prompt })
                });
                
                let data = await response.json();
                if (!response.ok) {
                    throw new Error(data.detail || data.error || `El servidor respondió HTTP ${response.status}`);
                }
                if (response.status === 202) {
                    const jobId = data.job_id;
                    const deadline = Date.now() + 330000;
                    do {
                        await new Promise(resolve => setTimeout(resolve, 2000));
                        const statusResponse = await fetch(`/api/task/${jobId}`);
                        const jobData = await statusResponse.json();
                        if (!statusResponse.ok && statusResponse.status !== 202) {
                            throw new Error(jobData.detail || jobData.error || `El servidor respondió HTTP ${statusResponse.status}`);
                        }
                        if (jobData.status === 'COMPLETED') {
                            data = jobData.result;
                            break;
                        }
                        if (jobData.status === 'TIMED_OUT') {
                            throw new Error(jobData.error || 'La tarea excedió el tiempo máximo de espera');
                        }
                        data = jobData;
                    } while (Date.now() < deadline);
                    if (!data.final_synthesis && Date.now() >= deadline) {
                        throw new Error('La tarea excedió el tiempo máximo de espera');
                    }
                }
                
                // Actualizar badges
                // La via directa no pasa por el concilio: mismos desenlaces que
                // el bot y el CLI, para que ninguna pantalla diga algo falso.
                const via = (data.shared_notes || {}).via || '';
                const verde = 'text-xs font-bold px-2.5 py-1 rounded bg-emerald-950 text-emerald-400 border border-emerald-800';
                const ambar = 'text-xs font-bold px-2.5 py-1 rounded bg-amber-950 text-amber-400 border border-amber-800';
                if (via === 'directa_verificada') {
                    scoreBadge.textContent = `Verificado por ejecución · vía directa (${data.consensus_score ?? 0}%)`;
                    scoreBadge.className = verde;
                } else if (via === 'directa_sin_verificar') {
                    scoreBadge.textContent = 'SIN VERIFICAR · vía directa — revisar antes de usar';
                    scoreBadge.className = ambar;
                } else {
                    scoreBadge.textContent = `Score: ${data.consensus_score ?? 0}/100`;
                    scoreBadge.className = data.consensus_reached ? verde : ambar;
                }

                // Render Markdown
                const synthesis = data.final_synthesis || 'El agente no produjo una síntesis final.';
                outputDiv.innerHTML = typeof marked === 'undefined' ? '' : marked.parse(synthesis);
                if (typeof marked === 'undefined') outputDiv.textContent = synthesis;
                
                // Blackboard Feed
                let bbHtml = `<div class="text-slate-300 font-bold mb-2">Resumen de Pizarra (Tarea ${data.task_id ?? 'sin ID'}):</div>`;
                (data.execution_timeline || []).forEach(event => {
                    bbHtml += `<div class="text-slate-400 border-l-2 border-blue-500 pl-2 my-1"><span class="text-blue-400 font-semibold">[${event.agent}]</span> ${event.message}</div>`;
                });
                bbFeed.innerHTML = bbHtml;

                statusInd.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-500 mr-2"></span> Consenso Finalizado';
            } catch (err) {
                outputDiv.innerHTML = `<div class="text-red-400 p-4 bg-red-950/50 rounded-lg border border-red-800">Error al ejecutar la tarea: ${err}</div>`;
                statusInd.innerHTML = '<span class="w-2 h-2 rounded-full bg-red-500 mr-2"></span> Error';
            } finally {
                sendBtn.disabled = false;
                sendBtn.classList.remove('opacity-50', 'cursor-not-allowed');
            }
        }

    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def read_root():
    return HTMLResponse(content=HTML_TEMPLATE)

def _run_task(job_id: str, prompt: str) -> None:
    task_jobs[job_id].update(status="RUNNING", updated_at=time.time())
    try:
        blackboard = orchestrator.run_consensus(user_prompt=prompt, shared_memory=shared_memory)
        task_jobs[job_id].update(status="COMPLETED", result=blackboard.model_dump(), updated_at=time.time())
    except Exception as exc:
        task_jobs[job_id].update(status="FAILED", error=str(exc), updated_at=time.time())


@app.post("/api/task")
async def execute_task_endpoint(request: Request, req: QueryRequest):
    if not _mini_autorizado(request):
        return JSONResponse(status_code=401, content={"error": "clave no valida"})
    prompt = req.prompt.strip()
    if not prompt:
        return JSONResponse(status_code=400, content={"error": "La tarea no puede estar vacía"})
    if any(job["status"] == "RUNNING" for job in task_jobs.values()):
        return JSONResponse(status_code=409, content={"error": "Ya hay una tarea en ejecución"})
    job_id = f"job-{uuid4().hex[:12]}"
    task_jobs[job_id] = {"status": "QUEUED", "prompt": prompt, "created_at": time.time(), "updated_at": time.time()}
    task_executor.submit(_run_task, job_id, prompt)
    return JSONResponse(status_code=202, content={"job_id": job_id, "status": "QUEUED", "message": "Tarea aceptada; consulta su estado."})


@app.get("/api/task/{job_id}")
def task_status(job_id: str):
    job = task_jobs.get(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": "Tarea no encontrada"})
    if job["status"] == "RUNNING" and time.time() - job.get("updated_at", job.get("created_at", time.time())) > orchestrator.timeout + 30:
        job.update(status="TIMED_OUT", updated_at=time.time(), error="El job excedió el tiempo máximo")
    if job["status"] == "COMPLETED":
        return {"job_id": job_id, "status": "COMPLETED", "result": job["result"]}
    if job["status"] == "TIMED_OUT":
        return JSONResponse(status_code=504, content={"error": job["error"], "job_id": job_id})
    if job["status"] == "FAILED":
        return JSONResponse(status_code=502, content={"error": f"Falló el pipeline de consenso: {job['error']}"})
    return {"job_id": job_id, "status": job["status"]}

@app.get("/api/health")
def health():
    return {"status": "ok", "ollama_host": orchestrator.ollama_host}


# ─── CHAT DEL CONCILIO EN LA MINI APP ────────────────────────────────────────
# Dos modos, igual que el bot de Telegram: rapido (fast_ask, un modelo,
# segundos) y tarea (run_consensus completo, via /api/task). La rapida se
# bloquea si hay una tarea en curso: fast_ask haria ensure_exclusive y
# desalojaria el modelo que la tarea esta usando (ping-pong en Ollama).

# Clave opcional para el tunel publico: si se define MINI_APP_KEY, /api/task
# y /api/mini/chat exigen el header X-Mini-Key. La Mini App la toma del
# parametro ?k= de SU URL (el boton de Telegram la lleva), asi el tunel no
# queda abierto a cualquiera con el enlace. Sin clave definida, todo funciona
# como hasta hoy (local sin tunnel, o decision explicita del operador).
MINI_APP_KEY = os.environ.get("MINI_APP_KEY", "")


def _mini_autorizado(request: Request) -> bool:
    if not MINI_APP_KEY:
        return True
    return request.headers.get("X-Mini-Key", "") == MINI_APP_KEY


def _hay_tarea_en_curso() -> bool:
    return any(job["status"] in ("QUEUED", "RUNNING") for job in task_jobs.values())


@app.post("/api/mini/chat")
def mini_chat(request: Request, req: QueryRequest):
    """Consulta rapida al Concilio (fast_ask): un modelo, segundos.

    Es la via LIGERA de siempre (/task del bot): va FUERA del pipeline de
    consenso, con el pack thin de Sentinel y sin memoria de sesiones.
    """
    if not _mini_autorizado(request):
        return JSONResponse(status_code=401, content={"error": "clave no valida"})
    prompt = req.prompt.strip()
    if not prompt:
        return JSONResponse(status_code=400, content={"error": "La consulta no puede estar vacia"})
    if _hay_tarea_en_curso():
        return JSONResponse(status_code=409, content={
            "error": "Hay una tarea del Concilio en curso; espera a que termine "
                     "para consultar. (fast_ask desalojaria su modelo en Ollama)"})
    try:
        reply = orchestrator.fast_ask(prompt)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": f"fast_ask fallo: {exc}"})
    return {"reply": reply, "mode": "rapida"}



# ─── Telegram Mini App: SENTINEL PIPELINE (el foco del operador) ────────────

@app.get("/mini", response_class=HTMLResponse)
def mini_app_page():
    """Mini App — pipeline de Sentinel Omega (foco) + Concilio (secundario)."""
    mini = STATIC_DIR / "mini.html"
    if not mini.is_file():
        return HTMLResponse(
            "<h1>mini.html missing</h1><p>Create static/mini.html</p>",
            status_code=404,
        )
    return HTMLResponse(mini.read_text(encoding="utf-8"))


# ── Los endpoints de ESTADO de Sentinel se RETIRARON con el corte del
# 2026-10-26 (/api/mini/estado y /api/mini/sentinel leían el snapshot y
# la DB de Sentinel): el estado de Sentinel lo sirve el EXPERTO
# (web.py, :8003, @SismoBio_Bot). El CONCILIO GENERAL es consenso y
# verificación — su mini es el CHAT y no consume estado de Sentinel.

@app.get("/api/mini/status")
def mini_status():
    """Safe JSON for Mini App — no .env secrets."""
    try:
        from telegram_bot import status_payload_json


        return status_payload_json()
    except Exception as e:
        import yaml

        cfg_path = Path(__file__).resolve().parent / "config.yaml"
        cfg = {}
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
        consensus = cfg.get("consensus") or {}
        concilio = cfg.get("concilio") or {}
        sdir = Path(__file__).resolve().parent / (
            (concilio.get("sessions_dir") or "data/sessions")
        )
        sessions = list(sdir.glob("*.concilio")) if sdir.is_dir() else []
        return {
            "ok": False,
            "error": str(e)[:120],
            "concilio": {
                "threshold": consensus.get("threshold_score", 85),
                "sequential": bool(concilio.get("sequential", True)),
                "worker_model": concilio.get("worker_model"),
                "arbiter_model": concilio.get("arbiter_model"),
                "sessions_count": len(sessions),
                "last_session": None,
            },
            "ollama": {"loaded": [], "unloaded_note": "fallback"},
            "alert_queue": {
                "nota": ("el despacho vive en el EXPERTO "
                         "(sentinel-experto.service, @SismoBio_Bot)")
            },
            "dashboard_url": os.environ.get(
                "CONSENSUS_DASHBOARD_URL", "http://127.0.0.1:8000"
            ),
            "webapp_url": "",
            "alert_policy": {
                "hourly_digest": "always",
                "immediate": "unprecedented_only",
            },
        }


def start_server(host: str = None, port: int = 8000):
    import os
    if host is None:
        host = os.environ.get("CONSENSUS_HOST", "127.0.0.1")
    if host == "0.0.0.0":
        print("⚠️  Web expuesta en 0.0.0.0 (todas las interfaces) — usa solo en red confiable")
    print(f"🚀 Servidor Web de Consenso de Expertos iniciado en http://localhost:{port}")
    uvicorn.run(app, host=host, port=port)




@app.get("/api/concilio/health")
def concilio_health_api():
    """Public health for miniapp /status — no tokens or .env."""
    info = orchestrator.health()
    sessions_dir = (info.get("concilio") or {}).get("sessions_dir") or str(STATIC_DIR.parent / "data" / "sessions")
    try:
        n = len(list(Path(sessions_dir).glob("*.concilio"))) if Path(sessions_dir).is_dir() else 0
    except Exception:
        n = 0
    # Strip potentially noisy injector metadata; keep models/threshold/sequential
    return {
        "status": "ok",
        "consensus_threshold": info.get("consensus_threshold", 85),
        "sessions_count": n,
        "concilio": {
            "sequential": (info.get("concilio") or {}).get("sequential"),
            "worker_model": (info.get("concilio") or {}).get("worker_model"),
            "arbiter_model": (info.get("concilio") or {}).get("arbiter_model"),
            "loaded_now": (info.get("concilio") or {}).get("loaded_now"),
            "inject_sentinel_architecture": (info.get("concilio") or {}).get("inject_sentinel_architecture"),
        },
        "agents": {
            role: {
                "name": (info.get("agents") or {}).get(role, {}).get("name"),
                "model": (info.get("agents") or {}).get(role, {}).get("model"),
                "available": (info.get("agents") or {}).get(role, {}).get("available"),
            }
            for role in ("researcher", "coder", "optimizer")
        },
    }


@app.get("/api/alerts/stats")
def alerts_stats_api():
    """Agente de uso general local — sin cola de alertas de Sentinel."""
    return {
        "nota": "Agente local de uso general (Deamon-X / Capitán)",
        "modo": "uso_general_local",
        "personalidad": "Capitan (Deamon-X)",
    }


@app.get("/api/sentinel/health")
def sentinel_health_disabled():
    """Endpoint retirado: el agente es de uso general local, no de Sentinel."""
    return JSONResponse(
        status_code=404,
        content={"error": "Endpoint retirado: agente de uso general local"},
    )
