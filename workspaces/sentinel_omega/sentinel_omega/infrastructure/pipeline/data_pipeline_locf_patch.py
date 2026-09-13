"""
Upgrade GeodynamicPipeline LOCF to persistent DB (tbl_locf_cache).

Import once (launcher / data_pipeline package) to patch _locf_get/_locf_set
and add bind_repository.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)


def patch_pipeline() -> bool:
    try:
        from sentinel_omega.infrastructure.pipeline.data_pipeline import GeodynamicPipeline
    except Exception as exc:
        logger.warning("patch_pipeline import failed: %s", exc)
        return False

    if getattr(GeodynamicPipeline, "_locf_db_patched", False):
        return True

    _orig_init = GeodynamicPipeline.__init__

    def __init__(self, repository=None, *args, **kwargs):
        _orig_init(self, *args, **kwargs)
        self._repo = repository

    def bind_repository(self, repository) -> None:
        self._repo = repository

    def _locf_get(self, key: str) -> Dict[str, Any]:
        cached = self._cache.get(key)
        if cached:
            age_s = time.time() - self._cache_ts.get(key, 0)
            if age_s > getattr(self, "_LOCF_STALE_S", 86400):
                logger.warning(
                    "LOCF stale for %s (age=%.1fh)", key, age_s / 3600
                )
            else:
                logger.info("LOCF active (memory) for %s (age=%.0fs)", key, age_s)
            return cached
        repo = getattr(self, "_repo", None)
        if repo is not None:
            try:
                dbp = repo.load_locf(key)
                if dbp:
                    data = {k: v for k, v in dbp.items() if not str(k).startswith("_locf_")}
                    if data:
                        self._cache[key] = data
                        updated = float(dbp.get("_locf_updated_at") or time.time())
                        self._cache_ts[key] = updated
                        logger.info("LOCF active (db) for %s", key)
                        return data
            except Exception as exc:
                logger.warning("LOCF db load %s: %s", key, exc)
        logger.warning("LOCF miss for %s — no prior real data", key)
        return {}

    def _locf_set(self, key: str, data: Dict[str, Any]) -> None:
        if data:
            self._cache[key] = data
            self._cache_ts[key] = time.time()
            repo = getattr(self, "_repo", None)
            if repo is not None:
                try:
                    repo.save_locf(key, data)
                except Exception as exc:
                    logger.warning("LOCF db save %s: %s", key, exc)

    GeodynamicPipeline.__init__ = __init__  # type: ignore
    GeodynamicPipeline.bind_repository = bind_repository  # type: ignore
    GeodynamicPipeline._locf_get = _locf_get  # type: ignore
    GeodynamicPipeline._locf_set = _locf_set  # type: ignore
    GeodynamicPipeline._locf_db_patched = True  # type: ignore
    logger.info("GeodynamicPipeline LOCF upgraded to persistent DB")
    return True


try:
    patch_pipeline()
except Exception:
    pass
