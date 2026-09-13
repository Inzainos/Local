"""
Sentinel Omega — SQLite Schema & Migrations (v11, self-expanding)

Full DDL lives in schema_parts/*.b64 (zlib+base64).
On import, parts are joined, decompressed, and executed in this module namespace.
"""
from __future__ import annotations

import base64
import logging
import zlib
from pathlib import Path

logger = logging.getLogger(__name__)

_PARTS_DIR = Path(__file__).resolve().parent / "schema_parts"

def _load_expanded() -> str:
    parts = sorted(_PARTS_DIR.glob("schema_part_*.b64"))
    if not parts:
        raise RuntimeError(f"schema_parts missing under {_PARTS_DIR}")
    b64 = "".join(p.read_text(encoding="ascii").strip() for p in parts)
    return zlib.decompress(base64.b64decode(b64)).decode("utf-8")

_src = _load_expanded()
exec(compile(_src, "schema_expanded", "exec"), globals())
