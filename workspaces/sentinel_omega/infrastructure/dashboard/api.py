"""
Sentinel Omega — FastAPI read-only dashboard API.

Never calls init_database. Opens SQLite with file:?mode=ro only.
DB path follows the tree that contains this file (dev/test/prod),
overridable with SENTINEL_DB.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

_DASH_DIR = Path(__file__).resolve().parent
_PKG_DIR = _DASH_DIR.parent.parent  # .../sentinel_omega (python package)
_REPO_ROOT = _PKG_DIR.parent  # workspaces-dev OR nested repo root
for _p in (_REPO_ROOT,):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from sentinel_omega.infrastructure.database.repository import SentinelRepository

from sentinel_omega.infrastructure.dashboard.ask_faq import answer_question

PHI = 1.6180339887
TLAXCALA_LAT = 19.31
TLAXCALA_LON = -98.23
STALE_SECONDS = 600.0


def _resolve_db() -> Path:
    """Prefer SENTINEL_DB, then prod DB, then this tree's data/. Never default to Dev."""
    env = os.environ.get("SENTINEL_DB")
    if env:
        return Path(env)
    prod = Path("/home/deamon/workspaces/sentinel_omega/data/SENTINEL_OMEGA_PRO.db")
    for cand in (
        prod,
        _PKG_DIR / "data" / "SENTINEL_OMEGA_PRO.db",
        _REPO_ROOT / "data" / "SENTINEL_OMEGA_PRO.db",
    ):
        # Skip any path under workspaces-dev unless explicitly set via SENTINEL_DB
        if "workspaces-dev" in str(cand):
            continue
        if cand.exists():
            return cand
    return prod



DB_PATH = _resolve_db()
DB_URI = f"file:{DB_PATH}?mode=ro"

app = FastAPI(
    title="Sentinel Omega Dashboard API",
    version="0.2.0",
    description="Read-only command dashboard API (React). Defaults to Prod DB.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "http://127.0.0.1:4174",
        "http://localhost:4174",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class ReadOnlyRepository(SentinelRepository):
    """SentinelRepository with forced URI read-only connections."""

    def __init__(self, db_path: Optional[str] = None):
        super().__init__(db_path=db_path or str(DB_PATH))

    @property
    def _conn_safe(self) -> sqlite3.Connection:
        if not hasattr(self, "_tls"):
            self._tls = threading.local()
        if getattr(self._tls, "conn", None) is not None:
            return self._tls.conn
        conn = sqlite3.connect(
            DB_URI,
            uri=True,
            timeout=30.0,
            check_same_thread=False,
            isolation_level=None,
        )
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.row_factory = sqlite3.Row
        except Exception:
            pass
        self._tls.conn = conn
        return conn

    def _ro_execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn_safe.execute(sql, params)

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._ro_execute(sql, params)

    def get_aciertos(self, limit: int = 100) -> Dict[str, Any]:
        pesos = [
            dict(r)
            for r in self._ro_execute(
                "SELECT bot_name, peso, aciertos, fallos, updated_at "
                "FROM TBL_PESOS_BOTS ORDER BY aciertos DESC"
            ).fetchall()
        ]
        recent = [
            dict(r)
            for r in self._ro_execute(
                """SELECT id, timestamp, bot_name, prediccion, confianza,
                          verdad, resultado, fase, severidad, resuelto_at
                   FROM TBL_JUEZ_AUDITORIA
                   WHERE resultado IN ('ACIERTO','FALLO','FALSO_POSITIVO')
                   ORDER BY COALESCE(resuelto_at, created_at) DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        ]
        counts = {
            r["resultado"]: r["n"]
            for r in self._ro_execute(
                """SELECT resultado, COUNT(*) AS n
                   FROM TBL_JUEZ_AUDITORIA
                   WHERE resultado IN ('ACIERTO','FALLO','FALSO_POSITIVO')
                   GROUP BY resultado"""
            ).fetchall()
        }
        aciertos = int(counts.get("ACIERTO", 0))
        fallos = int(counts.get("FALLO", 0))
        fps = int(counts.get("FALSO_POSITIVO", 0))
        total = max(aciertos + fallos + fps, 1)
        return {
            "pesos": pesos,
            "recent": recent,
            "summary": {
                "aciertos": aciertos,
                "fallos": fallos,
                "falsos_positivos": fps,
                "asertividad": aciertos / total,
                "total_resueltos": aciertos + fallos + fps,
            },
        }

    def get_alertas(self, limit: int = 50) -> Dict[str, Any]:
        cycles = self.get_ciclos(limit=limit)
        alert_cycles = [c for c in cycles if c.get("geo_signal") == "alert"]
        breaches = self.get_muro_breaches(limit=limit)
        dets = self.get_detecciones(limit=limit)
        hot = [d for d in dets if float(d.get("confidence") or 0) >= 0.5]
        precs = self.get_precursores_cosmicos(limit=20)
        hot_risk = [
            p
            for p in precs
            if str(p.get("nivel_riesgo", "")).upper() in ("HIGH", "CRITICAL")
            or float(p.get("fantasma") or 0) >= 5.0
        ]
        return {
            "geo_alerts": alert_cycles,
            "muro_breaches": breaches,
            "hot_detections": hot,
            "hot_fantasma": hot_risk,
        }


_repo = ReadOnlyRepository()


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _table_exists(name: str) -> bool:
    try:
        row = _repo._ro_execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=? LIMIT 1",
            (name,),
        ).fetchone()
        return bool(row)
    except Exception:
        return False


def _rows(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    try:
        return [dict(r) for r in _repo._ro_execute(sql, params).fetchall()]
    except Exception:
        return []


def _scalar(sql: str, params: tuple = (), default: Any = 0) -> Any:
    try:
        row = _repo._ro_execute(sql, params).fetchone()
        if row is None:
            return default
        return row[0]
    except Exception:
        return default


def _overview_payload() -> Dict[str, Any]:
    precs = _repo.get_precursores_cosmicos(limit=1) if _table_exists("TBL_PRECURSORES_COSMICOS") else []
    cycles = _repo.get_ciclos(limit=1) if _table_exists("TBL_CICLOS") else []
    muro = _repo.get_muro_all(limit=1) if _table_exists("TBL_MURO_EVENTOS") else []
    nodos = _repo.get_nodos() if _table_exists("TBL_NODOS_TOPOLOGIA") else []
    sismos_n = _repo.count_sismos(min_magnitude=4.5) if _table_exists("TBL_HISTORICO_SISMICO") else 0
    dets = _repo.get_detecciones(limit=1) if _table_exists("TBL_DETECCIONES") else []
    try:
        risk = _repo.risk_distribution()
    except Exception:
        risk = {}
    try:
        alert_rate = _repo.cycle_alert_rate()
    except Exception:
        alert_rate = {}
    latest_prec = precs[0] if precs else None
    latest_ciclo = cycles[0] if cycles else None
    latest_muro = muro[0] if muro else None
    last_cycle_ts = latest_ciclo.get("timestamp") if latest_ciclo else None
    now = time.time()
    stale = True if last_cycle_ts is None else (now - float(last_cycle_ts)) > STALE_SECONDS
    return {
        "ts": now,
        "fantasma": {
            "value": latest_prec.get("fantasma") if latest_prec else None,
            "nivel_riesgo": latest_prec.get("nivel_riesgo") if latest_prec else None,
            "schumann_hz": latest_prec.get("schumann_hz") if latest_prec else None,
            "kp": latest_prec.get("kp") if latest_prec else None,
            "bz_nT": latest_prec.get("bz_nT") if latest_prec else None,
            "viento_km_s": latest_prec.get("viento_km_s") if latest_prec else None,
        },
        "muro": {
            "walls_active": latest_muro.get("walls_active") if latest_muro else (
                latest_ciclo.get("muro_walls_active") if latest_ciclo else None
            ),
            "muro_breach": bool(latest_muro.get("muro_breach")) if latest_muro else (
                bool(latest_ciclo.get("muro_breach")) if latest_ciclo else False
            ),
            "correlation_score": latest_muro.get("correlation_score") if latest_muro else None,
            "risk_label": latest_muro.get("risk_label") if latest_muro else None,
        },
        "ciclo": latest_ciclo,
        "counts": {
            "nodos": len(nodos),
            "sismos_m45": sismos_n,
            "detecciones_latest": bool(dets),
        },
        "risk_distribution": risk,
        "cycle_alert_rate": alert_rate,
        "health": {
            "last_cycle_ts": last_cycle_ts,
            "stale": stale,
            "stale_seconds": STALE_SECONDS,
        },
    }


@app.get("/api/health")
def health() -> Dict[str, Any]:
    ok = DB_PATH.exists()
    last_cycle_ts = _scalar("SELECT timestamp FROM TBL_CICLOS ORDER BY timestamp DESC LIMIT 1", default=None)
    now = time.time()
    stale = True if last_cycle_ts is None else (now - float(last_cycle_ts)) > STALE_SECONDS
    fuente = int(_scalar("SELECT COUNT(*) FROM tbl_eventos_sismicos_fuente", default=0) or 0)
    detail: Dict[str, Any] = {
        "status": "ok" if ok else "degraded",
        "db_path": str(DB_PATH),
        "db_exists": ok,
        "mode": "ro",
        "ts": now,
        "last_cycle_ts": last_cycle_ts,
        "stale": stale,
        "stale_seconds": STALE_SECONDS,
        "fuente_sismos": fuente,
        "remap_aplicado": fuente > 0,
        "tree": str(_REPO_ROOT),
    }
    if ok:
        try:
            row = _repo._ro_execute("SELECT COUNT(*) AS n FROM TBL_CICLOS").fetchone()
            detail["ciclos"] = int(row[0]) if row else 0
            detail["db_readable"] = True
        except Exception as exc:
            detail["status"] = "degraded"
            detail["db_readable"] = False
            detail["error"] = str(exc)
    if stale:
        detail["lectura"] = "no hay lectura reciente"
    else:
        detail["lectura"] = "el sistema está leyendo ahora"
    return detail


@app.get("/api/overview")
def overview() -> Dict[str, Any]:
    return _jsonable(_overview_payload())


@app.get("/api/precursores")
def precursores(limit: int = Query(50, ge=1, le=500)) -> List[Dict[str, Any]]:
    if not _table_exists("TBL_PRECURSORES_COSMICOS"):
        return []
    return _jsonable(_repo.get_precursores_cosmicos(limit=limit))


@app.get("/api/muro")
def muro(
    limit: int = Query(50, ge=1, le=500),
    breaches_only: bool = Query(False),
) -> List[Dict[str, Any]]:
    if not _table_exists("TBL_MURO_EVENTOS"):
        return []
    data = _repo.get_muro_breaches(limit=limit) if breaches_only else _repo.get_muro_all(limit=limit)
    return _jsonable(data)


@app.get("/api/nodos")
def nodos(tipo: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    if not _table_exists("TBL_NODOS_TOPOLOGIA"):
        return []
    rows = _jsonable(_repo.get_nodos(tipo=tipo))
    # Overlay coords if a row is missing lat/lon (do not remap ids).
    for r in rows:
        if r.get("lat") is None or r.get("lon") is None:
            name = str(r.get("nombre") or "").lower()
            if "tlaxcala" in name:
                r["lat"] = TLAXCALA_LAT
                r["lon"] = TLAXCALA_LON
                r["coord_source"] = "spec-tlaxcala"
            else:
                r["coord_source"] = "missing"
        else:
            r["coord_source"] = "TBL_NODOS_TOPOLOGIA"
    return rows


@app.get("/api/sismos")
def sismos(
    min_magnitude: float = Query(4.5, ge=0.0),
    limit: int = Query(200, ge=1, le=2000),
    region: Optional[str] = Query(None),
) -> Dict[str, Any]:
    if not _table_exists("TBL_HISTORICO_SISMICO"):
        return {"min_magnitude": min_magnitude, "count": 0, "total_matching": 0, "items": []}
    rows = _repo.get_sismos(min_magnitude=min_magnitude, limit=limit, region=region)
    return _jsonable(
        {
            "min_magnitude": min_magnitude,
            "count": len(rows),
            "total_matching": _repo.count_sismos(min_magnitude=min_magnitude),
            "items": rows,
        }
    )


@app.get("/api/ciclos")
def ciclos(limit: int = Query(50, ge=1, le=500)) -> List[Dict[str, Any]]:
    if not _table_exists("TBL_CICLOS"):
        return []
    return _jsonable(_repo.get_ciclos(limit=limit))


@app.get("/api/detecciones")
def detecciones(
    limit: int = Query(100, ge=1, le=1000),
    tipo: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    if not _table_exists("TBL_DETECCIONES"):
        return []
    return _jsonable(_repo.get_detecciones(limit=limit, tipo=tipo))


@app.get("/api/aciertos")
def aciertos(limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
    return _jsonable(_repo.get_aciertos(limit=limit))


@app.get("/api/alertas")
def alertas(limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
    return _jsonable(_repo.get_alertas(limit=limit))


@app.get("/api/agente")
def agente() -> Dict[str, Any]:
    try:
        from sentinel_omega.infrastructure.messaging.agent_bridge import agent_health

        data = agent_health() or {}
        data["available"] = True
        return _jsonable(data)
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


@app.post("/api/ask")
def ask(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    q = str(payload.get("question") or "")
    live = _overview_payload()
    return answer_question(q, live)


@app.get("/api/cimatica")
def cimatica(
    limit: int = Query(50, ge=1, le=200),
    ambito: Optional[str] = Query(None),
) -> Dict[str, Any]:
    if not _table_exists("tbl_cimatica_patrones"):
        return {"total": 0, "limit": limit, "ambito": ambito, "by_ambito": [], "items": []}
    total = int(_scalar("SELECT COUNT(*) FROM tbl_cimatica_patrones") or 0)
    by_ambito = _rows(
        "SELECT ambito, COUNT(*) AS n, SUM(frecuencia) AS freq FROM tbl_cimatica_patrones GROUP BY ambito"
    )
    if ambito:
        items = _rows(
            """SELECT patron_id, substr(clave,1,120) AS clave, ambito, id_nodo, event_class,
                      frecuencia, primera_vez, ultima_vez
               FROM tbl_cimatica_patrones WHERE ambito=?
               ORDER BY ultima_vez DESC LIMIT ?""",
            (ambito, limit),
        )
    else:
        items = _rows(
            """SELECT patron_id, substr(clave,1,120) AS clave, ambito, id_nodo, event_class,
                      frecuencia, primera_vez, ultima_vez
               FROM tbl_cimatica_patrones
               ORDER BY ultima_vez DESC LIMIT ?""",
            (limit,),
        )
    return _jsonable({"total": total, "limit": limit, "ambito": ambito, "by_ambito": by_ambito, "items": items})


@app.get("/api/correlaciones")
def correlaciones() -> Dict[str, Any]:
    def pack(table: str) -> Dict[str, Any]:
        if not _table_exists(table):
            return {"table": table, "present": False, "items": [], "patrones": [], "event_classes": []}
        items = _rows(
            f"SELECT patron, event_class, n, fuerza, actualizada_at FROM {table} ORDER BY fuerza DESC"
        )
        patrones = sorted({str(r["patron"]) for r in items})
        events = sorted({str(r["event_class"]) for r in items})
        return {
            "table": table,
            "present": True,
            "items": items,
            "patrones": patrones,
            "event_classes": events,
        }

    return _jsonable({"padre": pack("tbl_correlaciones_padre"), "omega": pack("tbl_correlaciones_omega")})


@app.get("/api/bots")
def bots() -> Dict[str, Any]:
    rows = _rows("SELECT bot_name, peso, aciertos, fallos, updated_at FROM TBL_PESOS_BOTS ORDER BY bot_name")
    enriched = []
    sum_a = sum_f = 0
    padre = None
    for r in rows:
        a = int(r.get("aciertos") or 0)
        f = int(r.get("fallos") or 0)
        den = a + f
        rate = (a / den) if den else None
        item = {**r, "asertividad_viva_individual": rate, "n": den}
        enriched.append(item)
        sum_a += a
        sum_f += f
        if str(r.get("bot_name") or "").lower() == "padre":
            padre = item
    den = sum_a + sum_f
    return _jsonable(
        {
            "source": "TBL_PESOS_BOTS",
            "snapshot": True,
            "caption": "TBL_PESOS_BOTS es un SNAPSHOT (no serie temporal). Curva de aprendizaje: /api/aprendizaje desde TBL_JUEZ_AUDITORIA fase=viva.",
            "items": enriched,
            "asertividad_viva_global": (sum_a / den) if den else None,
            "aciertos_total": sum_a,
            "fallos_total": sum_f,
            "padre": padre,
            "updated_at": rows[0]["updated_at"] if rows else None,
        }
    )


@app.get("/api/sesgo")
def sesgo() -> Dict[str, Any]:
    if not _table_exists("tbl_sesgo_aprendizaje"):
        return {"present": False, "items": [], "source": "tbl_sesgo_aprendizaje"}
    items = _rows(
        "SELECT bot, n, recon_insample, recon_causal, sesgo, castigos, evaluada_at FROM tbl_sesgo_aprendizaje ORDER BY bot"
    )
    return _jsonable(
        {
            "present": True,
            "source": "tbl_sesgo_aprendizaje",
            "caption": "Asertividad HISTÓRICA de entrenamiento. insample=dentro del set; causal=fuera. sesgo=insample-causal.",
            "items": items,
        }
    )


@app.get("/api/aprendizaje")
def aprendizaje() -> Dict[str, Any]:
    """Honest per-bot learning curve from Juez viva daily buckets. No interpolation."""
    if not _table_exists("TBL_JUEZ_AUDITORIA"):
        return {"present": False, "series": [], "source": None}
    daily = _rows(
        """SELECT bot_name,
                  date(timestamp, 'unixepoch') AS dia,
                  SUM(CASE WHEN resultado='ACIERTO' THEN 1 ELSE 0 END) AS aciertos,
                  SUM(CASE WHEN resultado IN ('FALLO','FALSO_POSITIVO') THEN 1 ELSE 0 END) AS no_aciertos,
                  COUNT(*) AS n
           FROM TBL_JUEZ_AUDITORIA
           WHERE fase='viva' AND resultado IN ('ACIERTO','FALLO','FALSO_POSITIVO')
           GROUP BY bot_name, dia
           ORDER BY dia, bot_name"""
    )
    if not daily:
        return {
            "present": False,
            "series": [],
            "source": "TBL_JUEZ_AUDITORIA",
            "caption": "no hay historial por ciclo aún",
        }
    cum: Dict[str, List[int]] = {}
    series: Dict[str, List[Dict[str, Any]]] = {}
    for r in daily:
        bot = str(r["bot_name"])
        a, n = int(r["aciertos"] or 0), int(r["n"] or 0)
        ca, cn = cum.get(bot, [0, 0])
        ca += a
        cn += n
        cum[bot] = [ca, cn]
        series.setdefault(bot, []).append(
            {
                "dia": r["dia"],
                "aciertos_dia": a,
                "n_dia": n,
                "aciertos_cum": ca,
                "n_cum": cn,
                "asertividad_cum": (ca / cn) if cn else None,
            }
        )
    return _jsonable(
        {
            "present": True,
            "source": "TBL_JUEZ_AUDITORIA WHERE fase='viva' (vista viva_real)",
            "caption": "Curva REAL diaria (sin interpolar). TBL_PESOS_BOTS es solo snapshot.",
            "series": series,
        }
    )


@app.get("/api/firmas")
def firmas() -> Dict[str, Any]:
    if not _table_exists("TBL_FIRMAS"):
        return {"present": False, "by_clase": [], "total": 0}
    by_clase = _rows("SELECT event_class AS clase, COUNT(*) AS n FROM TBL_FIRMAS GROUP BY event_class ORDER BY n DESC")
    total = int(_scalar("SELECT COUNT(*) FROM TBL_FIRMAS") or 0)
    return _jsonable({"present": True, "source": "TBL_FIRMAS", "total": total, "by_clase": by_clase})


@app.get("/api/lag")
def lag() -> Dict[str, Any]:
    return _jsonable(
        {
            "factores": _rows("SELECT feature, media_rapidas, media_lentas, diferencia_norm, updated_at FROM tbl_factores_lag ORDER BY ABS(diferencia_norm) DESC")
            if _table_exists("tbl_factores_lag")
            else [],
            "anticipacion": _rows(
                "SELECT event_class, lag_promedio_h, lag_max_h, lag_min_h, n_eventos, updated_at FROM tbl_lag_anticipacion ORDER BY lag_promedio_h DESC"
            )
            if _table_exists("tbl_lag_anticipacion")
            else [],
        }
    )


@app.get("/api/juez")
def juez(
    limit: int = Query(100, ge=1, le=500),
    bot: Optional[str] = Query(None),
    fase: str = Query("viva"),
) -> Dict[str, Any]:
    if not _table_exists("TBL_JUEZ_AUDITORIA"):
        return {"items": [], "counts": {}, "source": "TBL_JUEZ_AUDITORIA"}
    counts = _rows(
        "SELECT fase, resultado, COUNT(*) AS n FROM TBL_JUEZ_AUDITORIA GROUP BY fase, resultado"
    )
    if bot:
        items = _rows(
            """SELECT id, timestamp, bot_name, prediccion, confianza, verdad, resultado,
                      fase, severidad, resuelto_at
               FROM TBL_JUEZ_AUDITORIA WHERE fase=? AND bot_name=?
               ORDER BY timestamp DESC LIMIT ?""",
            (fase, bot, limit),
        )
    else:
        items = _rows(
            """SELECT id, timestamp, bot_name, prediccion, confianza, verdad, resultado,
                      fase, severidad, resuelto_at
               FROM TBL_JUEZ_AUDITORIA WHERE fase=?
               ORDER BY timestamp DESC LIMIT ?""",
            (fase, limit),
        )
    return _jsonable({"source": "TBL_JUEZ_AUDITORIA", "fase": fase, "counts": counts, "items": items})


@app.get("/api/layers")
def layers() -> Dict[str, Any]:
    try:
        filas = _repo.get_ultima_prediccion_por_bot()
    except Exception as exc:
        return {"present": False, "reason": str(exc), "agents": [], "padre": None}
    DISPLAY = {
        "alfa1": "Alfa-1 (Bz/OMNI)",
        "alfa2": "Alfa-2 (Satellite)",
        "beta1": "Beta-1 (Kp/FFT+Schumann)",
        "beta2": "Beta-2 (Atmospheric)",
        "delta": "Delta (Financial)",
        "omega": "Omega (Dual-Ask)",
        "loki": "Loki (Campo Unificado)",
        "jupiter": "Jupiter",
        "padre": "Padre",
    }
    agents = []
    padre = None
    for fila in filas:
        bot = str(fila.get("bot_name") or "").lower()
        rec = {
            "bot": bot,
            "label": DISPLAY.get(bot, bot),
            "prediccion": fila.get("prediccion"),
            "confianza": fila.get("confianza"),
            "timestamp": fila.get("timestamp"),
        }
        if bot == "padre":
            padre = rec
        else:
            agents.append(rec)
    return _jsonable(
        {
            "present": bool(filas),
            "source": "viva_real / TBL_JUEZ_AUDITORIA última predicción por bot",
            "agents": agents,
            "padre": padre,
        }
    )


@app.get("/api/reportes")
def reportes(name: Optional[str] = Query(None), limit: int = Query(25, ge=1, le=80)) -> Dict[str, Any]:
    estado = _REPO_ROOT / "estado"
    if not estado.is_dir():
        return {"present": False, "dir": str(estado), "files": [], "content": None}
    files = sorted(
        [p for p in estado.glob("*.md") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    listing = [{"name": p.name, "bytes": p.stat().st_size, "mtime": p.stat().st_mtime} for p in files[:limit]]
    content = None
    chosen = None
    if name:
        safe = Path(name).name
        target = estado / safe
        if target.is_file() and target.suffix == ".md":
            chosen = safe
            raw = target.read_text(encoding="utf-8", errors="replace")
            content = raw[:12000]
    return {"present": True, "dir": str(estado), "files": listing, "name": chosen, "content": content}



def _fmt_ts(v):
    if v is None or v == "":
        return None
    try:
        fv = float(v)
        if fv > 1e9:
            return fv
    except (TypeError, ValueError):
        pass
    return str(v)


def _src(sid, label, inbound_table, inbound_ts, inbound_count, processed_table, processed_value, note, inbound_status=None):
    ts = _fmt_ts(inbound_ts)
    if inbound_status is None:
        if inbound_count == 0:
            inbound_status = "tabla vacía"
        elif ts is None:
            inbound_status = "sin marca de tiempo"
        else:
            inbound_status = "ok"
    locf_n = int(_scalar("SELECT COUNT(*) FROM tbl_locf_cache WHERE source_key=?", (sid,), default=0) or 0) if _table_exists("tbl_locf_cache") else 0
    return {
        "id": sid,
        "label": label,
        "inbound": {
            "table": inbound_table,
            "ts": ts,
            "count": inbound_count,
            "status": inbound_status,
            "locf": "LOCF" if locf_n else "sin LOCF cacheado",
        },
        "processed": {
            "table": processed_table,
            "value": processed_value,
            "note": note,
        },
    }


@app.get("/api/telemetry")
def telemetry() -> Dict[str, Any]:
    """Así entra de la API vs así lo usa Sentinel. Sin relojes inventados."""
    prec = _rows(
        "SELECT timestamp, bz_nT, viento_km_s, protones, kp, lod_ms, schumann_hz, schumann_activity, fantasma, nivel_riesgo "
        "FROM TBL_PRECURSORES_COSMICOS ORDER BY timestamp DESC LIMIT 1"
    )
    p0 = prec[0] if prec else {}
    ciclo = _rows("SELECT timestamp, geo_signal, fantasma, muro_walls_active FROM TBL_CICLOS ORDER BY timestamp DESC LIMIT 1")
    c0 = ciclo[0] if ciclo else {}

    usgs_ts = _scalar("SELECT MAX(timestamp) FROM TBL_HISTORICO_SISMICO", default=None)
    usgs_n = int(_scalar("SELECT COUNT(*) FROM TBL_HISTORICO_SISMICO", default=0) or 0)
    usgs_m45 = int(_scalar("SELECT COUNT(*) FROM TBL_HISTORICO_SISMICO WHERE magnitude>=4.5", default=0) or 0)

    clima_ts = _scalar("SELECT MAX(timestamp_blk) FROM tbl_clima_espacial_raw", default=None) if _table_exists("tbl_clima_espacial_raw") else None
    clima_n = int(_scalar("SELECT COUNT(*) FROM tbl_clima_espacial_raw", default=0) or 0) if _table_exists("tbl_clima_espacial_raw") else 0
    clima_last = _rows("SELECT timestamp_blk, bz_promedio, viento_solar_avg, kp_max, proton_flux_10mev FROM tbl_clima_espacial_raw ORDER BY timestamp_blk DESC LIMIT 1") if clima_n else []
    cl0 = clima_last[0] if clima_last else {}

    sch_ts = _scalar("SELECT MAX(timestamp_blk) FROM tbl_schumann_vivo", default=None) if _table_exists("tbl_schumann_vivo") else None
    sch_n = int(_scalar("SELECT COUNT(*) FROM tbl_schumann_vivo", default=0) or 0) if _table_exists("tbl_schumann_vivo") else 0
    sch_last = _rows("SELECT timestamp_blk, schumann_hz, schumann_activity FROM tbl_schumann_vivo ORDER BY timestamp_blk DESC LIMIT 1") if sch_n else []
    s0 = sch_last[0] if sch_last else {}

    astro_ts = _scalar("SELECT MAX(timestamp_blk) FROM tbl_astronomia_cinematica", default=None) if _table_exists("tbl_astronomia_cinematica") else None
    astro_n = int(_scalar("SELECT COUNT(*) FROM tbl_astronomia_cinematica", default=0) or 0) if _table_exists("tbl_astronomia_cinematica") else 0

    cob_ts = _scalar("SELECT MAX(timestamp_blk) FROM tbl_cobertura_satelital", default=None) if _table_exists("tbl_cobertura_satelital") else None
    cob_n = int(_scalar("SELECT COUNT(*) FROM tbl_cobertura_satelital", default=0) or 0) if _table_exists("tbl_cobertura_satelital") else 0
    cob_last = _rows("SELECT timestamp_blk, coverage_score, thermal_anomalies, clear_passes FROM tbl_cobertura_satelital ORDER BY timestamp_blk DESC LIMIT 1") if cob_n else []
    cob0 = cob_last[0] if cob_last else {}

    delta_ts = _scalar("SELECT MAX(timestamp_blk) FROM tbl_delta_cross", default=None) if _table_exists("tbl_delta_cross") else None
    delta_n = int(_scalar("SELECT COUNT(*) FROM tbl_delta_cross", default=0) or 0) if _table_exists("tbl_delta_cross") else 0

    psi_ts = _scalar("SELECT MAX(timestamp_blk) FROM tbl_psique_financiera", default=None) if _table_exists("tbl_psique_financiera") else None
    psi_n = int(_scalar("SELECT COUNT(*) FROM tbl_psique_financiera", default=0) or 0) if _table_exists("tbl_psique_financiera") else 0

    locf_n = int(_scalar("SELECT COUNT(*) FROM tbl_locf_cache", default=0) or 0) if _table_exists("tbl_locf_cache") else 0
    locf_items = _rows("SELECT source_key, updated_at FROM tbl_locf_cache ORDER BY source_key") if locf_n else []
    salud = _rows("SELECT ts, version, fantasma, viva, aciertos, fallos, pendientes, creada_at FROM tbl_salud_sistema ORDER BY ts DESC LIMIT 1") if _table_exists("tbl_salud_sistema") else []
    volcado = _rows("SELECT id, ejecutado_at, corte_blk, schumann_movidos, delta_movidos, cobertura_movidos, cascada_ok FROM tbl_volcado_vivo_log ORDER BY id DESC LIMIT 1") if _table_exists("tbl_volcado_vivo_log") else []

    bz2 = None
    try:
        if p0.get("bz_nT") is not None:
            bz2 = abs(float(p0["bz_nT"])) ** 2
    except (TypeError, ValueError):
        pass
    viento_term = None
    try:
        if p0.get("viento_km_s") is not None:
            viento_term = float(p0["viento_km_s"]) * 0.02
    except (TypeError, ValueError):
        pass
    sch_term = None
    try:
        if p0.get("schumann_activity") is not None:
            sch_term = (float(p0["schumann_activity"]) / 100.0) * 1.5
    except (TypeError, ValueError):
        pass

    sources = [
        _src(
            "usgs", "USGS sismos",
            "TBL_HISTORICO_SISMICO", usgs_ts, usgs_n,
            "TBL_HISTORICO_SISMICO magnitud>=4.5",
            usgs_m45,
            "Entra el catálogo USGS. Sentinel ALERTA solo desde M4.5 (el Padre). Mide desde M3.3.",
        ),
        _src(
            "noaa_bz_viento", "NOAA Bz / viento solar",
            "tbl_clima_espacial_raw (OMNI2/backcast)", clima_ts, clima_n,
            "TBL_PRECURSORES_COSMICOS.bz_nT + viento_km_s",
            {"bz_nT": p0.get("bz_nT"), "viento_km_s": p0.get("viento_km_s"), "bz2": bz2, "viento_term": viento_term, "precursor_ts": p0.get("timestamp")},
            "Crudo histórico en clima_espacial_raw. Lo que usa Fantasma es Bz² y viento×0.02 del último precursor. Si el crudo termina en 2025, es backcast, no el loop vivo.",
        ),
        _src(
            "kp", "Kp (NOAA / GFZ Potsdam)",
            "tbl_clima_espacial_raw.kp_max", clima_ts, clima_n,
            "TBL_PRECURSORES_COSMICOS.kp",
            {"kp_precursor": p0.get("kp"), "kp_max_raw": cl0.get("kp_max")},
            "GFZ se consulta en el loop (jupiter) pero no tiene tabla propia: no hay reloj GFZ persistido. El Kp que usa Sentinel está en precursores.",
        ),
        _src(
            "schumann", "Schumann (Tomsk / vivo)",
            "tbl_schumann_vivo", sch_ts, sch_n,
            "TBL_PRECURSORES_COSMICOS.schumann_hz",
            {"hz_vivo": s0.get("schumann_hz"), "activity_vivo": s0.get("schumann_activity"), "hz_precursor": p0.get("schumann_hz"), "sch_term": sch_term},
            "Así entra: tbl_schumann_vivo. Así lo usa Fantasma: Hz + activity (término ≈ activity/100×1.5). Referencia 7.83 Hz.",
        ),
        _src(
            "goes", "GOES X-ray (NOAA SWPC)",
            None, None, 0,
            "sin tabla persistida",
            None,
            "El conector fetch_goes_xray existe (loop Júpiter) pero no hay tabla SQLite de X-ray. Sin marca de tiempo.",
            inbound_status="sin marca de tiempo",
        ),
        _src(
            "lod", "LOD / cinemática terrestre",
            "tbl_astronomia_cinematica", astro_ts, astro_n,
            "TBL_PRECURSORES_COSMICOS.lod_ms",
            p0.get("lod_ms"),
            "LOD entra por astronomía (backcast) y se copia al precursor. Si el crudo para en 2025, no inventamos un reloj vivo.",
        ),
        _src(
            "copernicus", "Copernicus Sentinel-1/2 (Alfa-2)",
            "tbl_cobertura_satelital", cob_ts, cob_n,
            "tbl_cobertura_satelital.coverage_score",
            {"coverage_score": cob0.get("coverage_score"), "thermal_anomalies": cob0.get("thermal_anomalies"), "clear_passes": cob0.get("clear_passes")},
            "Así entra la cobertura satelital; Alfa-2 usa coverage_score / anomalías térmicas, no el JPEG crudo.",
        ),
        _src(
            "jupiter_trends", "Júpiter / Google Trends / GFZ",
            None, None, 0,
            "TBL_PESOS_BOTS + viva_real (bot jupiter)",
            None,
            "Trends y GFZ viven en memoria del ciclo (TTL 6 h para Trends). No hay tabla de crudo: sin marca de tiempo. El bot jupiter sí tiene peso/asertividad.",
            inbound_status="sin marca de tiempo",
        ),
        _src(
            "delta", "Delta / acoplamiento geo-financiero",
            "tbl_delta_cross", delta_ts, delta_n,
            "tbl_delta_cross.composite_score",
            delta_n,
            "Cross-coupling ya procesado. Psique BTC en tbl_psique_financiera (histórico).",
        ),
        _src(
            "btc", "BTC / psique financiera",
            "tbl_psique_financiera", psi_ts, psi_n,
            "tbl_delta_cross.sentiment_coupling",
            psi_n,
            "Precio/volatilidad crudos vs acoplamiento que usa Delta.",
        ),
    ]
    return _jsonable({
        "caption_in": "así entra de la API",
        "caption_out": "así lo usa Sentinel",
        "locf_cache_n": locf_n,
        "locf_items": locf_items,
        "salud": salud[0] if salud else None,
        "volcado": volcado[0] if volcado else None,
        "ciclo": c0 or None,
        "precursor": {"timestamp": p0.get("timestamp"), "fantasma": p0.get("fantasma"), "nivel_riesgo": p0.get("nivel_riesgo")} if p0 else None,
        "sources": sources,
    })


@app.get("/api/unificado")
def unificado() -> Dict[str, Any]:
    ov = _overview_payload()
    nodos = _rows(
        "SELECT node_id, nombre, lat, lon, tipo, region FROM TBL_NODOS_TOPOLOGIA "
        "WHERE lower(nombre) LIKE '%tlaxcala%' OR node_id=0 OR node_id=11"
    )
    tlax = None
    for n in nodos:
        if "tlaxcala" in str(n.get("nombre") or "").lower() and str(n.get("tipo") or "") == "real":
            tlax = n
            break
    if tlax is None and nodos:
        tlax = nodos[0]
    cim_n = int(_scalar("SELECT COUNT(*) FROM tbl_cimatica_patrones", default=0) or 0)
    sch = ov.get("fantasma", {}).get("schumann_hz")
    return _jsonable(
        {
            "phi": PHI,
            "schumann_ref_hz": 7.83,
            "schumann_hz": sch,
            "schumann_delta": (float(sch) - 7.83) if sch is not None else None,
            "fantasma": ov.get("fantasma"),
            "muro": ov.get("muro"),
            "ciclo": ov.get("ciclo"),
            "tlaxcala": {
                "spec_lat": TLAXCALA_LAT,
                "spec_lon": TLAXCALA_LON,
                "spec_note": "Nodo de observación Sentinel (spec 19.31 N, 98.23 W). En TBL_NODOS_TOPOLOGIA Tlaxcala es node_id=11; no hay fila id=0 y no se inventa.",
                "row": tlax,
            },
            "cimatica_total": cim_n,
            "engine_in_prod": False,
            "caption": "Loki is the Campo Unificado native bot (third act). Not on prod systemd. Beta-1 draws figuritas; Beta-2 looks up the mixed library (no live training).",
        }
    )




@app.get("/api/cimatica/ahora")
def cimatica_ahora() -> Dict[str, Any]:
    """Current cymatic figure vs similar historical library entries. Live lookup only."""
    try:
        from sentinel_omega.core.firmas.biblioteca_cimatica import consultar, ensure_biblioteca
        conn = None
    except Exception as exc:
        return {"present": False, "reason": str(exc)}
    db = DB_PATH
    import sqlite3
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=8)
    con.row_factory = sqlite3.Row
    try:
        ensure_biblioteca(con)
        n_lib = con.execute("SELECT COUNT(*) FROM tbl_cimatica_biblioteca").fetchone()[0]
        n_pat = con.execute("SELECT COUNT(*) FROM tbl_cimatica_patrones").fetchone()[0] if _table_exists("tbl_cimatica_patrones") else 0
        # last viva beta1 details if any
        row = None
        try:
            row = con.execute(
                "SELECT detalles_json, prediccion, confianza, timestamp FROM TBL_JUEZ_AUDITORIA "
                "WHERE bot_name='beta1' AND fase='viva' ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        except Exception:
            pass
        figura, factores, clave = {}, {}, ""
        if row and row[0]:
            try:
                det = json.loads(row[0])
                figura = det.get("figura") or {}
                factores = det.get("factores") or {}
                clave = det.get("clave_figura") or ""
            except Exception:
                pass
        hit = consultar(con, figura, factores, clave_figura=clave) if figura else {
            "similares": [], "n_hits": 0, "best_similarity": 0, "live_train": False,
        }
        by_ec = _rows(
            "SELECT event_class, COUNT(*) n, SUM(n_eventos) eventos FROM tbl_cimatica_biblioteca "
            "GROUP BY 1 ORDER BY 3 DESC LIMIT 20"
        ) if n_lib else []
        return _jsonable({
            "present": True,
            "live_train": False,
            "biblioteca_n": n_lib,
            "patrones_n": n_pat,
            "current_figura": figura,
            "current_clave": clave,
            "library": hit,
            "by_event_class": by_ec,
            "caption": "Live lookup of (figure + factors) against historical library. No live training.",
        })
    finally:
        con.close()


_STATIC_DIR = Path(__file__).resolve().parent / "static"



@app.get("/api/heatmaps")
def heatmaps() -> Dict[str, Any]:
    """Padre+Juez heatmaps from real tables. Empty cells stay empty — no invented metrics."""
    # --- models × models: daily asertividad co-presence (last 30d viva) ---
    models = {"present": False, "bots": [], "matrix": [], "caption": "", "source": "TBL_JUEZ_AUDITORIA"}
    if _table_exists("TBL_JUEZ_AUDITORIA"):
        daily = _rows(
            """SELECT bot_name,
                      date(timestamp, 'unixepoch') AS dia,
                      SUM(CASE WHEN resultado='ACIERTO' THEN 1 ELSE 0 END) * 1.0
                        / NULLIF(SUM(CASE WHEN resultado IN ('ACIERTO','FALLO','FALSO_POSITIVO') THEN 1 ELSE 0 END), 0)
                        AS rate
               FROM TBL_JUEZ_AUDITORIA
               WHERE fase='viva'
                 AND resultado IN ('ACIERTO','FALLO','FALSO_POSITIVO')
                 AND timestamp >= strftime('%s','now','-30 days')
               GROUP BY bot_name, dia"""
        )
        by_bot: Dict[str, Dict[str, float]] = {}
        for r in daily:
            b = str(r.get("bot_name") or "")
            if not b or r.get("rate") is None:
                continue
            by_bot.setdefault(b, {})[str(r["dia"])] = float(r["rate"])
        bots = sorted(by_bot.keys())
        matrix = []
        for a in bots:
            row = []
            days_a = by_bot[a]
            for b in bots:
                if a == b:
                    vals = list(days_a.values())
                    row.append(round(sum(vals) / len(vals), 4) if vals else None)
                    continue
                days_b = by_bot[b]
                common = [days_a[d] for d in days_a if d in days_b]
                common_b = [days_b[d] for d in days_a if d in days_b]
                if len(common) < 3:
                    row.append(None)
                    continue
                # Pearson-lite on shared days
                n = len(common)
                ma = sum(common) / n
                mb = sum(common_b) / n
                num = sum((x - ma) * (y - mb) for x, y in zip(common, common_b))
                da = sum((x - ma) ** 2 for x in common) ** 0.5
                db = sum((y - mb) ** 2 for y in common_b) ** 0.5
                row.append(round(num / (da * db), 4) if da and db else None)
            matrix.append(row)
        models = {
            "present": bool(bots),
            "bots": bots,
            "matrix": matrix,
            "caption": "Correlación de asertividad diaria entre bots (Juez viva, 30 días). Diagonal = media propia. Celdas vacías = <3 días en común.",
            "source": "TBL_JUEZ_AUDITORIA",
        }

    # --- telemetry × telemetry via tbl_patrones_correlacion (feature×event ratios) ---
    telemetry = {"present": False, "features": [], "events": [], "matrix": [], "caption": "", "source": "tbl_patrones_correlacion"}
    if _table_exists("tbl_patrones_correlacion"):
        items = _rows(
            "SELECT event_class, feature, ratio, n_firmas FROM tbl_patrones_correlacion ORDER BY feature, event_class"
        )
        features = sorted({str(r["feature"]) for r in items})
        events = sorted({str(r["event_class"]) for r in items})
        lookup = {(str(r["feature"]), str(r["event_class"])): r.get("ratio") for r in items}
        matrix = [[lookup.get((f, e)) for e in events] for f in features]
        telemetry = {
            "present": bool(items),
            "features": features,
            "events": events,
            "matrix": matrix,
            "caption": "Ratio media(feature|clase) / media global. >1 = elevado antes de esa clase. Fuente tbl_patrones_correlacion.",
            "source": "tbl_patrones_correlacion",
            "n": len(items),
        }

    # --- climatic factors: lag features matching kp/schumann/atmosphere + ciclo KPIs ---
    climatic = {"present": False, "items": [], "caption": "", "source": "tbl_factores_lag + TBL_CICLOS"}
    lag_items = []
    if _table_exists("tbl_factores_lag"):
        lag_items = _rows(
            "SELECT feature, media_rapidas, media_lentas, diferencia_norm, updated_at "
            "FROM tbl_factores_lag ORDER BY ABS(diferencia_norm) DESC"
        )
    keys = ("kp", "schumann", "bz", "wind", "viento", "atm", "press", "temp", "humid", "omni", "dst")
    clim_rows = [
        r for r in lag_items
        if any(k in str(r.get("feature") or "").lower() for k in keys)
    ]
    ciclo_clim = []
    if _table_exists("TBL_CICLOS"):
        # recent fantasma vs muro / precursors — real columns only
        ciclo_clim = _rows(
            """SELECT timestamp, fantasma, nivel_riesgo, muro_walls_active, precursors_count
               FROM TBL_CICLOS ORDER BY timestamp DESC LIMIT 40"""
        )
    climatic = {
        "present": bool(clim_rows or ciclo_clim),
        "lag_climatic": clim_rows,
        "lag_all_n": len(lag_items),
        "ciclos_recent": ciclo_clim,
        "caption": (
            "Factores climáticos/espaciales desde tbl_factores_lag (kp/schumann/bz/viento/atm…) "
            "y últimos ciclos (fantasma/muro). Si lag_climatic está vacío, no hay features con esos nombres."
        ),
        "source": "tbl_factores_lag + TBL_CICLOS",
    }

    # padre/omega correlaciones (may be empty)
    padre_corr = []
    omega_corr = []
    if _table_exists("tbl_correlaciones_padre"):
        padre_corr = _rows(
            "SELECT patron, event_class, n, fuerza FROM tbl_correlaciones_padre ORDER BY fuerza DESC LIMIT 40"
        )
    if _table_exists("tbl_correlaciones_omega"):
        omega_corr = _rows(
            "SELECT patron, event_class, n, fuerza FROM tbl_correlaciones_omega ORDER BY fuerza DESC LIMIT 40"
        )

    return _jsonable(
        {
            "models_x_models": models,
            "telemetry_x_events": telemetry,
            "climatic": climatic,
            "padre_corr": {"present": bool(padre_corr), "items": padre_corr, "source": "tbl_correlaciones_padre"},
            "omega_corr": {"present": bool(omega_corr), "items": omega_corr, "source": "tbl_correlaciones_omega"},
        }
    )




@app.get("/api/consenso")
def consenso(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    """Consensus state: recent cycles + bot weights + latest layer signals."""
    if not _table_exists("TBL_CICLOS"):
        return {"present": False, "cycles": [], "bots": [], "latest": None}
    
    cycles = _rows("""SELECT id, timestamp, geo_signal, geo_confidence, geo_consensus,
                          fantasma, nivel_riesgo, precursors_count, precursor_types,
                          muro_walls_active, muro_breach, alerts_dispatched
                   FROM TBL_CICLOS ORDER BY timestamp DESC LIMIT ?""", (limit,))
    
    bots = _rows("SELECT bot_name, peso, aciertos, fallos, updated_at FROM TBL_PESOS_BOTS ORDER BY bot_name")
    
    # Enrich bots with asertividad
    enriched_bots = []
    for r in bots:
        a = int(r.get('aciertos') or 0)
        f = int(r.get('fallos') or 0)
        den = a + f
        rate = (a / den) if den else None
        enriched_bots.append({**r, 'asertividad_viva': rate, 'n': den})
    
    latest = cycles[0] if cycles else None
    
    return _jsonable({
        'present': True,
        'cycles': cycles,
        'bots': enriched_bots,
        'latest': latest,
        'source': 'TBL_CICLOS + TBL_PESOS_BOTS',
        'caption': 'Consenso jerárquico: ciclos recientes + pesos de credibilidad por bot.'
    })


@app.get("/api/telegram/status")
def telegram_status() -> Dict[str, Any]:
    """Telegram bot configuration and connectivity status."""
    import os
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    webapp_url = os.environ.get('TELEGRAM_WEBAPP_URL', '').strip()
    
    configured = bool(token and chat_id and 'TU_TOKEN' not in token and not token.startswith('REPLACE'))
    
    return _jsonable({
        'configured': configured,
        'has_token': bool(token),
        'has_chat_id': bool(chat_id),
        'has_webapp_url': bool(webapp_url),
        'webapp_url': webapp_url if webapp_url else None,
        'dry_run': os.environ.get('SENTINEL_DRY_RUN', '').lower() in ('1', 'true', 'yes'),
        'cooldown_s': int(os.environ.get('TELEGRAM_COOLDOWN_S', '1800')),
        'heartbeat_s': int(os.environ.get('TELEGRAM_HEARTBEAT_S', '14400')),
    })


@app.post("/api/telegram/test")
def telegram_test(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Send a test Telegram message."""
    from sentinel_omega.infrastructure.api.telegram import send_alert
    
    message = payload.get('message', '🧪 Test desde Sentinel Omega Dashboard')
    ok = send_alert(message)
    
    return _jsonable({
        'sent': ok,
        'message': message,
    })



@app.get("/mini", response_class=HTMLResponse)
@app.get("/mini.html", response_class=HTMLResponse)
def mini_app():
    """Telegram Mini App — Estado. Requires HTTPS public URL (TELEGRAM_WEBAPP_URL)."""
    page = _STATIC_DIR / "mini.html"
    if not page.exists():
        return HTMLResponse("<h1>mini.html missing</h1>", status_code=404)
    return FileResponse(page, media_type="text/html; charset=utf-8")



# === 6-tab dashboard API extensions (RO, capped) ===

@app.get("/api/schumann_vivo")
def schumann_vivo(limit: int = Query(120, ge=1, le=500)) -> Dict[str, Any]:
    """Serie Schumann vivo desde tbl_schumann_vivo."""
    if not _table_exists("tbl_schumann_vivo"):
        return {"present": False, "items": [], "latest": None, "source": "tbl_schumann_vivo", "caption": "Tabla ausente en esta DB."}
    items = _rows(
        "SELECT timestamp_blk, schumann_hz, schumann_activity, creada_at "
        "FROM tbl_schumann_vivo ORDER BY timestamp_blk DESC LIMIT ?",
        (limit,),
    )
    return _jsonable({
        "present": bool(items),
        "items": items,
        "latest": items[0] if items else None,
        "n": len(items),
        "source": "tbl_schumann_vivo",
        "caption": "Hz y actividad WPC vivos. Limite capped. Solo lectura.",
    })


@app.get("/api/delta")
def delta_family(limit: int = Query(80, ge=1, le=400)) -> Dict[str, Any]:
    """Delta cross + psique financiera para Familias/Delta."""
    delta_items = []
    psi_items = []
    sources = []
    if _table_exists("tbl_delta_cross"):
        delta_items = _rows(
            "SELECT timestamp_blk, cross_coupling, geomagnetic_coupling, schumann_coupling, "
            "sentiment_coupling, composite_score, regime_label, confidence, data_completeness, "
            "geo_kp_max_3d, geo_storm_active, geo_schumann_deviation "
            "FROM tbl_delta_cross ORDER BY timestamp_blk DESC LIMIT ?",
            (limit,),
        )
        sources.append("tbl_delta_cross")
    if _table_exists("tbl_psique_financiera"):
        psi_items = _rows(
            "SELECT timestamp_blk, btc_precio_usd, volatilidad_24h, vix, fear_greed, "
            "yield_spread, btc_dominance, fetch_flags "
            "FROM tbl_psique_financiera ORDER BY timestamp_blk DESC LIMIT ?",
            (limit,),
        )
        sources.append("tbl_psique_financiera")
    return _jsonable({
        "present": bool(delta_items or psi_items),
        "delta": delta_items,
        "psique": psi_items,
        "latest_delta": delta_items[0] if delta_items else None,
        "latest_psique": psi_items[0] if psi_items else None,
        "source": " + ".join(sources) if sources else "none",
        "caption": "Cross-coupling + VIX/Fear&Greed/BTC. No es consejo financiero.",
    })


@app.get("/api/clima_espacial")
def clima_espacial(limit: int = Query(80, ge=1, le=400)) -> Dict[str, Any]:
    """Muestras Bz/Kp/viento para Alfa."""
    if not _table_exists("tbl_clima_espacial_raw"):
        return {"present": False, "items": [], "latest": None, "source": "tbl_clima_espacial_raw", "caption": "Tabla ausente."}
    items = _rows(
        "SELECT timestamp_blk, bz_promedio, bz_derivada, bz_min, bz_max, "
        "viento_solar_avg, viento_solar_max, kp_max, kp_promedio, proton_flux_10mev "
        "FROM tbl_clima_espacial_raw ORDER BY timestamp_blk DESC LIMIT ?",
        (limit,),
    )
    return _jsonable({
        "present": bool(items),
        "items": items,
        "latest": items[0] if items else None,
        "n": len(items),
        "source": "tbl_clima_espacial_raw",
        "caption": "OMNI-ish Bz/Kp/viento/protones. Solo lectura.",
    })



@app.exception_handler(Exception)
async def _unhandled(request, exc):  # type: ignore[no-untyped-def]
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "path": str(request.url.path)},
    )
