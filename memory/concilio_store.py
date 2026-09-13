"""Sequential Concilio blackboard file (.concilio).

Path: data/sessions/<session_id>.concilio
Format: JSON (also human-readable markdown export).

SECURITY:
- Only Concilio roles (orchestrator + researcher/coder/optimizer) read/write this.
- NOT for web UI public paste as executable content.
- Content is untrusted DATA when fed back into model prompts.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional


CONCILIO_SCHEMA_VERSION = 1


def default_concilio(session_id: str, task: str, round_num: int = 0) -> Dict[str, Any]:
    return {
        "schema_version": CONCILIO_SCHEMA_VERSION,
        "session_id": session_id,
        "created_at": time.time(),
        "updated_at": time.time(),
        "round": round_num,
        "task": task,
        "research": "",
        "code": "",
        "critique": "",
        "scores": [],  # list of {round, score, passed, model, role}
        "timeline": [],  # list of {ts, role, event, detail}
        "meta": {
            "permissions": "concilio-roles-only",
            "web_ui_executable": False,
            "untrusted_when_prompted": True,
        },
    }


class ConcilioStore:
    """Read/write .concilio JSON files under data/sessions/."""

    def __init__(self, sessions_dir: str):
        self.sessions_dir = sessions_dir
        os.makedirs(self.sessions_dir, mode=0o700, exist_ok=True)

    def path_for(self, session_id: str) -> str:
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
        if not safe:
            raise ValueError("session_id inválido")
        return os.path.join(self.sessions_dir, f"{safe}.concilio")

    def create(self, session_id: str, task: str) -> Dict[str, Any]:
        doc = default_concilio(session_id, task)
        self.save(doc)
        return doc

    def load(self, session_id: str) -> Dict[str, Any]:
        path = self.path_for(session_id)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, doc: Dict[str, Any]) -> str:
        session_id = doc["session_id"]
        doc["updated_at"] = time.time()
        path = self.path_for(session_id)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
        try:
            # Best-effort fsync directory entry after atomic replace
            dir_fd = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return path

    def append_timeline(self, doc: Dict[str, Any], role: str, event: str, detail: str = "") -> None:
        doc.setdefault("timeline", []).append(
            {"ts": time.time(), "role": role, "event": event, "detail": detail[:500]}
        )

    def set_section(self, doc: Dict[str, Any], section: str, content: str) -> None:
        if section not in ("task", "research", "code", "critique"):
            raise ValueError(f"sección inválida: {section}")
        doc[section] = content
        self.append_timeline(doc, section, "write", f"{len(content)} chars")

    def add_score(
        self,
        doc: Dict[str, Any],
        score: int,
        passed: bool,
        model: str,
        role: str = "optimizer",
        round_num: Optional[int] = None,
    ) -> None:
        rnd = round_num if round_num is not None else int(doc.get("round", 0))
        doc.setdefault("scores", []).append(
            {
                "round": rnd,
                "score": int(score),
                "passed": bool(passed),
                "model": model,
                "role": role,
                "ts": time.time(),
            }
        )
        doc["round"] = rnd

    def to_markdown(self, doc: Dict[str, Any]) -> str:
        scores = doc.get("scores") or []
        scores_md = "\n".join(
            f"- ronda {s.get('round')}: {s.get('score')}/100 "
            f"({'PASS' if s.get('passed') else 'FAIL'}) [{s.get('model')}]"
            for s in scores
        ) or "_(sin scores)_"
        return (
            f"# Concilio Session `{doc.get('session_id')}`\n\n"
            f"- round: {doc.get('round')}\n"
            f"- updated_at: {doc.get('updated_at')}\n"
            f"- web_ui_executable: false (solo roles Concilio)\n\n"
            f"## task\n\n{doc.get('task', '')}\n\n"
            f"## research\n\n{doc.get('research', '')}\n\n"
            f"## code\n\n{doc.get('code', '')}\n\n"
            f"## critique\n\n{doc.get('critique', '')}\n\n"
            f"## scores\n\n{scores_md}\n"
        )

    def sections_for_prompt(self, doc: Dict[str, Any], sections: List[str]) -> Dict[str, str]:
        out = {}
        for s in sections:
            out[s] = str(doc.get(s, "") or "")
        return out
