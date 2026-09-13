"""
Persistent LOCF store for Sentinel Omega (tbl_locf_cache).

Wire-up: import this module (or call patch_repository()) so SentinelRepository
gains save_locf / load_locf. data_pipeline can then persist across restarts.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _json_safe(obj: Any) -> Any:
    try:
        import numpy as np
        import pandas as pd
    except ImportError:
        np = pd = None  # type: ignore
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if pd is not None and isinstance(obj, getattr(pd, "DataFrame", ())):
        return {
            "__df__": True,
            "columns": list(obj.columns),
            "data": obj.astype(object).where(obj.notna(), None).values.tolist(),
        }
    if pd is not None and isinstance(obj, getattr(pd, "Series", ())):
        return {
            "__series__": True,
            "data": obj.astype(object).where(obj.notna(), None).tolist(),
        }
    if np is not None and isinstance(obj, np.ndarray):
        return obj.tolist()
    if np is not None and isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    return str(obj)


def save_locf(conn, source_key: str, payload: Dict[str, Any]) -> None:
    if not source_key or not payload:
        return
    try:
        safe = _json_safe(payload)
        conn.execute(
            "INSERT OR REPLACE INTO tbl_locf_cache "
            "(source_key, payload_json, updated_at) VALUES (?, ?, ?)",
            (source_key, json.dumps(safe, default=str), time.time()),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("save_locf(%s) failed: %s", source_key, exc)


def load_locf(conn, source_key: str) -> Optional[Dict[str, Any]]:
    try:
        row = conn.execute(
            "SELECT payload_json, updated_at FROM tbl_locf_cache WHERE source_key = ?",
            (source_key,),
        ).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        if isinstance(data, dict):
            data["_locf_updated_at"] = float(row[1])
        return data
    except Exception as exc:
        logger.warning("load_locf(%s) failed: %s", source_key, exc)
        return None


def patch_repository() -> bool:
    """Attach save_locf/load_locf onto SentinelRepository if missing."""
    try:
        from sentinel_omega.infrastructure.database.repository import SentinelRepository
    except Exception as exc:
        logger.warning("patch_repository import failed: %s", exc)
        return False
    if hasattr(SentinelRepository, "save_locf") and hasattr(SentinelRepository, "load_locf"):
        return True

    def _save(self, source_key: str, payload: Dict[str, Any]) -> None:
        save_locf(self._conn, source_key, payload)

    def _load(self, source_key: str) -> Optional[Dict[str, Any]]:
        return load_locf(self._conn, source_key)

    SentinelRepository.save_locf = _save  # type: ignore[attr-defined]
    SentinelRepository.load_locf = _load  # type: ignore[attr-defined]
    logger.info("SentinelRepository patched with persistent LOCF")
    return True


# Auto-patch on import (safe / idempotent)
try:
    patch_repository()
except Exception:
    pass
