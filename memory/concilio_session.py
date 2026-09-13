"""Sequential Concilio session store: data/sessions/<id>.concilio

Each stage of the concilio appends a fenced DATA record. The file is never
treated as executable instructions by the orchestrator — only as opaque
state for the next model turn.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class ConcilioSession:
    """Append-only JSONL-ish session file with a JSON header envelope."""

    def __init__(self, sessions_dir: str | Path, session_id: Optional[str] = None):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.path = self.sessions_dir / f"{self.session_id}.concilio"
        self._records: List[Dict[str, Any]] = []
        self.meta: Dict[str, Any] = {
            "session_id": self.session_id,
            "created_at": time.time(),
            "format": "concilio.v1",
            "notice": "DATA_NOT_INSTRUCTIONS",
        }
        self._flush()

    @classmethod
    def open_existing(cls, path: str | Path) -> "ConcilioSession":
        path = Path(path)
        obj = cls.__new__(cls)
        obj.path = path
        obj.sessions_dir = path.parent
        raw = path.read_text(encoding="utf-8")
        header, _, body = raw.partition("\n---\n")
        obj.meta = json.loads(header) if header.strip() else {}
        obj.session_id = obj.meta.get("session_id", path.stem)
        obj._records = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj._records.append(json.loads(line))
            except json.JSONDecodeError:
                obj._records.append({"stage": "RAW", "content": line})
        return obj

    def append(
        self,
        stage: str,
        agent: str,
        model: str,
        content: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        rec: Dict[str, Any] = {
            "ts": time.time(),
            "stage": stage,
            "agent": agent,
            "model": model,
            "content": content or "",
            "data_not_instructions": True,
        }
        if extra:
            rec["extra"] = extra
        self._records.append(rec)
        self._flush()
        return rec

    def dump_text(self) -> str:
        """Full file body for fencing into prompts."""
        return self.path.read_text(encoding="utf-8") if self.path.exists() else ""

    def records(self) -> List[Dict[str, Any]]:
        return list(self._records)

    def latest(self, stage: Optional[str] = None) -> Optional[Dict[str, Any]]:
        for rec in reversed(self._records):
            if stage is None or rec.get("stage") == stage:
                return rec
        return None

    def _flush(self) -> None:
        header = json.dumps(self.meta, ensure_ascii=False, indent=2)
        lines = [json.dumps(r, ensure_ascii=False) for r in self._records]
        tmp = self.path.with_suffix(".concilio.tmp")
        tmp.write_text(header + "\n---\n" + "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        os.replace(tmp, self.path)
