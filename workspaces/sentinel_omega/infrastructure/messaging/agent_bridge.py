"""Agent Bridge — puente entre Sentinel Omega y consensus-expert-agent."""
from __future__ import annotations
import json, sqlite3, subprocess, sys
from pathlib import Path
from typing import Dict, Any, Optional, List

AGENT_ROOT = Path("/home/deamon/consensus-expert-agent")
AGENT_DB = AGENT_ROOT / "data" / "shared_memory.db"
AGENT_CONFIG = AGENT_ROOT / "config.yaml"

def agent_health() -> Dict[str, Any]:
    """Lee estado del agente sin importar Ollama (evita timeout)."""
    info: Dict[str, Any] = {"agent_root": str(AGENT_ROOT), "exists": AGENT_ROOT.exists()}
    try:
        # Config
        if AGENT_CONFIG.exists():
            info["config_exists"] = True
            txt = AGENT_CONFIG.read_text(encoding="utf-8")
            # extraer modelos y threshold sin yaml
            for line in txt.splitlines():
                if "model:" in line and "qwen" in line:
                    info.setdefault("models", []).append(line.strip())
                if "threshold_score" in line:
                    info["threshold"] = line.strip()
        # DB
        if AGENT_DB.exists():
            info["db_exists"] = True
            try:
                conn = sqlite3.connect(str(AGENT_DB))
                conn.row_factory = sqlite3.Row
                # tablas
                tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                info["db_tables"] = tables
                # ultimos blackboards / turnos si existen
                try:
                    rows = conn.execute("SELECT task_id, consensus_score, consensus_reached, refinement_rounds, final_synthesis FROM blackboards ORDER BY rowid DESC LIMIT 5").fetchall()
                    info["recent_blackboards"] = [dict(r) for r in rows]
                except Exception:
                    info["recent_blackboards"] = []
                try:
                    hist = conn.execute("SELECT role, content FROM conversation_history ORDER BY rowid DESC LIMIT 6").fetchall()
                    info["recent_history"] = [dict(r) for r in hist]
                except Exception:
                    info["recent_history"] = []
                conn.close()
            except Exception as e:
                info["db_error"] = str(e)
        else:
            info["db_exists"] = False
        # Ollama check via python sin httpx
        try:
            import httpx
            with httpx.Client(timeout=5.0) as c:
                r = c.get("http://127.0.0.1:11434/api/tags")
                if r.status_code==200:
                    info["ollama_models"] = [m["name"] for m in r.json().get("models",[])]
                    info["ollama_ok"] = True
                else:
                    info["ollama_ok"] = False
        except Exception as e:
            info["ollama_ok"] = False
            info["ollama_error"] = str(e)[:200]
    except Exception as e:
        info["error"] = str(e)
    return info

def agent_run_audit(focus: str = "", timeout_s: int = 600) -> Dict[str, Any]:
    cmd = [sys.executable, str(AGENT_ROOT / "main.py"), "--audit"]
    if focus:
        cmd += ["--focus", focus]
    try:
        proc = subprocess.run(cmd, cwd=str(AGENT_ROOT), capture_output=True, text=True, timeout=timeout_s)
        return {"ok": proc.returncode==0, "returncode": proc.returncode, "stdout": proc.stdout[-8000:], "stderr": proc.stderr[-4000:]}
    except subprocess.TimeoutExpired as e:
        return {"ok": False, "timeout": True, "stdout": (e.stdout or "")[-4000:] if hasattr(e,'stdout') else "", "stderr": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def agent_run_task(prompt: str, timeout_s: int = 400) -> Dict[str, Any]:
    cmd = [sys.executable, str(AGENT_ROOT / "main.py"), "--task", prompt]
    try:
        proc = subprocess.run(cmd, cwd=str(AGENT_ROOT), capture_output=True, text=True, timeout=timeout_s)
        return {"ok": proc.returncode==0, "returncode": proc.returncode, "stdout": proc.stdout[-8000:], "stderr": proc.stderr[-4000:]}
    except subprocess.TimeoutExpired as e:
        return {"ok": False, "timeout": True, "stdout": "", "stderr": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
