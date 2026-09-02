"""
Inyector de contexto del repositorio Sentinel Omega hacia el Concilio de Expertos.

Este módulo resuelve el problema #1 detectado en la auditoría 2026-08-22:
el agente consensus NO conocía las reglas duras, la arquitectura, ni el estado
del proyecto al que dice servir. Ahora cada blackboard se inicializa con un
resumen canónico del proyecto, leídos desde los archivos reales del repo
aguas abajo (/home/deamon/workspaces/{-, -dev, -test}/*).
"""
import pathlib
from pathlib import Path
import re
import os
from typing import List, Tuple

AGENT_ROOT = Path(__file__).resolve().parents[1]
HOME_ROOT = Path("/home/deamon")
SENTINEL_ROOT = HOME_ROOT / "workspaces" / "sentinel_omega"
WORKSPACES_ROOTS: Tuple[Path, ...] = (
    HOME_ROOT / "workspaces",
    HOME_ROOT / "workspaces-dev",
    HOME_ROOT / "workspaces-test",
)

# Resumen canónico (≤ 2000 chars) — sobrevivirá aunque los archivos del repo
# cambien o sean ilegibles. Mantén este resumen corto y útil.
CANONICAL_PROJECT_SUMMARY = """\
=== PROYECTO: SENTINEL OMEGA (resumen canónico para Concilio de Expertos) ===

Misión: detectar **precursores** de eventos naturales (sismos, erupciones, \
tormentas solares, tsunamis). Autor: Elán Zainos Corona (Fractal Core Research). \
Sucesor de la familia TITAN V32/V46/V53. Repo GitHub: Inzainos/workspaces.

Arquitectura (6 agentes + Padre árbitro + Juez auditor, separados):
- alfa1: clima espacial (Bz, viento solar, Kp, protones/electrones) — 30 años
- beta1: resonancia Schumann, "el latido" — 30 años
- alfa2: satélites ESA Sentinel — 14 años
- beta2: desgasificación volcánica / SO₂ — 14 años
- delta: bolsa + cripto + tendencias ("humor de la tierra") — 10 años
- omega: ritmo cósmico (luna + Schumann + solar + acoplamiento Schumann↔mercado) — 30 años
- jupiter (7º): atención colectiva (Google Trends ↔ tormentas solares)
- padre: consenso jerárquico (≥2 familias + ≥2 alertas + corr Schumann > 0.3)
- juez: audita real vs predicción (severidad asimétrica: omitir evento pesa 10×)

Familias: space_weather (alfa1/alfa2/jupiter), schumann_cymatics (beta1/beta2), \
financial_sentiment (delta). Consenso cruzado, pérdida asimétrica \
(prefiere sobre-alertar a sub-alertar).

Entrenamiento 3 fases: Fase 1 (sísmico, sin castigo) → Fase 1b (no-sísmico: \
erupciones VEI≥3 + tormentas Kp≥6 + financiero) → Fase 2 (disciplina del \
Padre + Juez asimétrico). Tras las fases: matriz de correlaciones feature × \
event_class + sesgo PRE (línea base sin castigo) vs POST (disciplinario).

Bases: NOAA SWPC, USGS FDSN, NASA OMNI2/MSVOLSO2L4, Tomsk (Schumann), IERS \
(LOD), Yahoo Finance (BTC keyless), OpenWeatherMap, NASA NEO, ESA Copernicus \
vía eodag>=4.0, Google Trends (pytrends), GFZ Potsdam Kp (CC BY 4.0).

Reglas duras (NO romper):
0. Regla cero: nunca asumas, siempre revisa — corré el flujo de punta a \
punta, no basta con tests unitarios. Antes de decir "ya está": ¿la tabla se \
pobló?, ¿el reporte lee la sección?, ¿el script corre sin error real?
1. Secretos SOLO por entorno (os.environ). NUNCA hardcodear. .env en .gitignore.
2. Cero datos sintéticos. Faltante = NULL. LOCF solo desde registros reales. \
Datos derivados se etiquetan como 'derived', nunca como dato de sensor.
3. sentinel_omega/data/ está en .gitignore — no existe en checkout limpio. \
Crear con mkdir(parents=True, exist_ok=True) antes de escribir ahí.
4. Reportes versionados: estado/REPORTE.md es el último, cada corte se guarda \
en estado/historial/AAAA/MM/ con hora local (UTC-6). NO sobrescribir historial.
5. Migración de esquema forward-only vía EXPECTED_COLUMNS + _migrate_add_missing_columns. \
Nunca borrar columnas.
6. Tests deben pasar antes de commitear código.

DB actual: schema v11 (~35 tablas). Highlights: tbl_locf_cache (LOCF persistente), \
tbl_eventos_catalogo (multi-evento), tbl_locf_cache, TBL_JUEZ_AUDITORIA con \
columna 'fase' (viva/reconocimiento/backtest/observacion/trasfondo) + vista \
viva_real canónica para asertividad. Launcher self-expanding desde \
launcher_hex/h00..h11.hex. Juez ritmo 2h (RITMO_HORAS=2), castigo/reforzar \
a TODOS los bots vía juez_cycle_register.

Patrones self-expanding: archivos grandes (schema.py, launcher.py) viajan en \
parts base64+zlib; tras `git pull` el loader reconstruye en memoria al \
importar. Si el archivo aparece como stub en GitHub, restaurar desde \
tar.gz sentinel_omega_COMPLETO_sesion.

Stack técnico: Python 3.11+, SQLite, pandas, numpy, scipy, ephem (luna), \
opencv-python (Schumann), onnxruntime (modelos ONNX), eodag>=4.0 (Copernicus), \
pytrends (Google Trends), streamlit (dashboard), rich (CLI). ~420-428 tests.

Ramas: main (PROD en /home/deamon/workspaces), dev, test, y un backup \
pre_rebuild_2026-08-22_122650 (rama dev, commit 400c674). PRs siempre como \
draft; el cron roy-vigilante.yml solo dispara en main.

Comandos clave (raíz del repo):
- python -m pytest sentinel_omega/tests/ -q          # ~428 tests
- python sentinel_omega/launcher.py                  # ciclo continuo (300s)
- python sentinel_omega/launcher.py --once           # 1 ciclo y sale
- python sentinel_omega/launcher.py --backcast       # 1994-2025 one-time
- python sentinel_omega/launcher.py --entrenar       # completo
- python deploy/verificacion_juez.py                 # Juez 4h
- python deploy/generar_reporte.py                   # REPORTE.md
- streamlit run sentinel_omega/infrastructure/dashboard/app.py
- python deploy/rebuild_completo.py --push <rama>     # rebuild autónomo
- python deploy/jupiter_correlaciones.py              # → estado/jupiter_correlaciones.json

Alertas: elan.zainos.corona@gmail.com vía tbl_correo_salida (SMTP fail-soft: \
sin SMTP_USER/SMTP_PASS quedan PENDIENTES, nunca finge enviados). Telegram \
Centinela V2 activo (un solo reporte consolidado por ciclo con alerta, no 4 \
mensajes sueltos).
"""

# Patrones prioritarios en orden de importancia para el contexto del concilio.
PRIORITY_PATTERNS = (
    "AGENTS.md", "CLAUDE.md", "README.md",
    "CHANGELOG.md", "CHANGELOG_*.md",
    "SESSION_FIXES_COMPLETO.md", "INFORME_CORRECCIONES.md", "HANDOFF.md",
    "RESTORE_SCHEMA.md",
)
SECONDARY_PATTERNS = ("*.log",)

# Sub-archivos del agente consensus-expert-agent que también merece la pena exponer.
AGENT_FILES = (
    "README.md", "config.yaml", "main.py", "cli.py", "web_ui.py",
    "agents/base_agent.py", "agents/researcher.py", "agents/coder.py",
    "agents/optimizer.py", "engine/orchestrator.py", "engine/router.py",
    "memory/blackboard.py", "memory/shared_context.py",
    "memory/persistent_store.py", "memory/repository_context.py",
)

# Tope total del payload que llega a los modelos. Si se queda corto, los
# agentes trabajan "a ciegas" respecto al proyecto. Si se desborda, el prompt
# se vuelve caro y el modelo pierde foco.
def _load_ctx_budget():
    # Prioridad: env CONSENSUS_CTX_* > config.yaml context_injector > defaults calibrados (8000/2500)
    try:
        import yaml
        cfg_path = pathlib.Path(__file__).resolve().parents[1] / "config.yaml"
        if cfg_path.is_file():
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
            ci = cfg.get("context_injector", {})
            yaml_total = ci.get("max_total_chars")
            yaml_file = ci.get("max_file_chars")
            if yaml_total is not None and "CONSENSUS_CTX_TOTAL" not in os.environ:
                return int(yaml_total), int(yaml_file or 2500)
    except Exception:
        pass
    return int(os.environ.get("CONSENSUS_CTX_TOTAL", "8000")), int(os.environ.get("CONSENSUS_CTX_FILE", "2500"))

MAX_TOTAL_CHARS, MAX_FILE_CHARS = _load_ctx_budget()


def _redact(text: str) -> str:
    """Borra secretos obvios (tokens, keys, passwords) por si un .log los filtra."""
    text = re.sub(r"(?i)(token|api[_-]?key|password|secret)\s*[:=]\s*[^\s]+", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._\-]+", "Bearer [REDACTED]", text)
    return text


def _first_existing(root: Path, candidates: List[str]) -> List[Path]:
    """Devuelve los archivos que existan en root, en el orden dado."""
    found = []
    for name in candidates:
        path = root / name
        if path.is_file():
            found.append(path)
    return found


def _gather(root: Path, patterns: Tuple[str, ...]) -> List[Path]:
    """Recolecta archivos por patrones glob simples (solo '*', sin recursion profunda)."""
    seen = set()
    out: List[Path] = []
    if not root.is_dir():
        return out
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file() and path.resolve() not in seen:
                seen.add(path.resolve())
                out.append(path)
    return out


def _collect_for(root: Path) -> List[Path]:
    """Devuelve la lista priorizada de archivos a incluir desde un workspace."""
    files: List[Path] = []
    # PRIMERO: estado/ (donde están HANDOFF.md, INFORME_CORRECCIONES.md, REPORTE.md - estado real actual)
    estado_dir = root / "estado"
    if estado_dir.is_dir():
        for name in PRIORITY_PATTERNS:
            for path in estado_dir.glob(name):
                if path.is_file():
                    files.append(path)
    # SEGUNDO: archivos root (AGENTS.md, CLAUDE.md, README.md, CHANGELOG, etc.)
    for name in PRIORITY_PATTERNS:
        for path in root.glob(name):
            if path.is_file():
                files.append(path)
    # TERCERO: Secundarios (.log) al final
    for path in _gather(root, SECONDARY_PATTERNS):
        files.append(path)
    return files


def _clip(content: str) -> str:
    if len(content) > MAX_FILE_CHARS:
        head = content[: MAX_FILE_CHARS // 2]
        tail = content[-MAX_FILE_CHARS // 2 :]
        return head + "\n... [recortado por tamaño] ...\n" + tail
    return content


def _format_section(path: Path, content: str) -> str:
    rel = path
    try:
        rel = path.relative_to(HOME_ROOT)
    except ValueError:
        pass
    return f"=== {rel} ===\n{content}"


def load_repository_context() -> str:
    """
    Devuelve un string de contexto del proyecto Sentinel Omega para inyectar
    a la primera etapa (Researcher) del concilio.

    Estructura del payload:
    1) Resumen canónico (sobrevive aunque cambien los archivos).
    2) AGENTS.md / CLAUDE.md del repo aguas abajo (reglas duras + comandos).
    3) CHANGELOG + SESSION_FIXES + INFORME (estado real del proyecto).
    4) Resto de archivos prioritarios hasta agotar MAX_TOTAL_CHARS.
    """
    sections: List[str] = [CANONICAL_PROJECT_SUMMARY.strip()]
    total = len(sections[0])

    # Espacios prioritarios — PROD primero, luego dev/test si faltan piezas
    workspaces_tried: List[Path] = []
    for w in WORKSPACES_ROOTS:
        if w.is_dir():
            workspaces_tried.append(w)

    # Primera pasada: PROD, agregando secciones hasta agotar el presupuesto
    used_files: set = set()
    for ws in workspaces_tried:
        for path in _collect_for(ws):
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            content = _redact(content)
            content = _clip(content)
            section = _format_section(path, content)
            if total + len(section) + 2 > MAX_TOTAL_CHARS:
                # Presupuesto agotado: paramos de agregar, pero NO dejamos al
                # concilio sin reglas duras. El resumen canónico de arriba
                # ya cubre lo crítico.
                continue
            sections.append(section)
            total += len(section) + 2
            used_files.add(path.resolve())

    # Segunda pasada: sub-archivos del propio agente (consensus-expert-agent).
    # Sólo si el modelo va a sugerir cambios sobre sí mismo (modo "auditoría").
    if os.environ.get("CONSENSUS_INCLUDE_SELF", "1") == "1":
        for rel in AGENT_FILES:
            path = AGENT_ROOT / rel
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            content = _redact(content)
            content = _clip(content)
            section = _format_section(path, content)
            if total + len(section) + 2 > MAX_TOTAL_CHARS:
                continue
            sections.append(section)
            total += len(section) + 2

    return "\n\n".join(sections)


def project_metadata() -> dict:
    """Metadatos baratos para inspección (logs, /api/sentinel/health, debugging)."""
    md = {
        "agent_root": str(AGENT_ROOT),
        "sentinel_root": str(SENTINEL_ROOT),
        "sentinel_exists": SENTINEL_ROOT.is_dir(),
        "workspaces_present": [str(w) for w in WORKSPACES_ROOTS if w.is_dir()],
        "max_total_chars": MAX_TOTAL_CHARS,
        "max_file_chars": MAX_FILE_CHARS,
        "consensus_include_self": os.environ.get("CONSENSUS_INCLUDE_SELF", "1") == "1",
    }
    # Tamano agregado de contexto sin recortar
    md["full_untrimmed_chars"] = sum(
        len(_clip(_redact(p.read_text(encoding="utf-8", errors="replace"))))
        for ws in WORKSPACES_ROOTS if ws.is_dir()
        for p in _collect_for(ws)
    )
    return md
