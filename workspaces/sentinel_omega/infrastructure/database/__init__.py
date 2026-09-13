"""Sentinel Omega — Database layer (SQLite)."""

# Persistent LOCF (tbl_locf_cache) — patches SentinelRepository on import
try:
    from sentinel_omega.infrastructure.database import locf_store  # noqa: F401
except Exception:
    pass
