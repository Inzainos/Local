"""Memory pack builder for Sequential Concilio.

Reads DEV Sentinel docs (AGENTS.md, CLAUDE.md, README.md + hard-rules
excerpts) from workspaces-dev first. Never reads .env or dumps secrets.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HOME = Path("/home/deamon")

# Prefer DEV → TEST → PROD docs roots (prod last, never DB).
DOC_ROOTS: Tuple[Path, ...] = (
    HOME / "workspaces-dev",
    HOME / "workspaces-test",
    HOME / "workspaces",
    HOME,  # fallback AGENTS.md / README.md at $HOME
)

PRIORITY_DOCS = (
    "AGENTS.md",
    "CLAUDE.md",
    "sentinel_omega/CLAUDE.md",
    "sentinel_omega/README.md",
    "README.md",
)

SECRET_NAME = re.compile(
    r"(?i)(\.env|\.pem|\.key|credentials|secret|token|password|api[_-]?key)"
)
REDACT = re.compile(
    r"(?i)(token|api[_-]?key|password|secret|authorization)\s*[:=]\s*\S+"
)
BEARER = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._\-]+")


def _safe_read(path: Path, max_chars: int) -> str:
    if not path.is_file():
        return ""
    # Hard skip anything that looks like a secret file.
    name = path.name.lower()
    if name.startswith(".env") or name.endswith((".pem", ".key")):
        return ""
    if SECRET_NAME.search(str(path)) and path.suffix.lower() in {".env", ".json", ".yml", ".yaml"}:
        # Allow markdown/docs even if path mentions "token" in prose; block env-like.
        if path.suffix.lower() != ".md":
            return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    text = REDACT.sub(r"\1=[REDACTED]", text)
    text = BEARER.sub("Bearer [REDACTED]", text)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…[truncated]…"
    return text


HARD_RULES_FALLBACK = """\
=== REGLAS DURAS SENTINEL OMEGA (pack canónico) ===
0. Regla Cero: nunca asumas, siempre revisa (flujo punta a punta).
1. Secretos SOLO por entorno (os.environ). NUNCA hardcodear. .env en .gitignore.
2. Cero datos sintéticos. Faltante = NULL. LOCF solo desde reales. Derived ≠ sensor.
3. sentinel_omega/data/ en .gitignore — mkdir(parents=True, exist_ok=True).
4. Reportes versionados (estado/historial/), no sobrescribir historial.
5. Migración forward-only (EXPECTED_COLUMNS + _migrate_add_missing_columns).
6. Tests deben pasar antes de commitear.
7. Umbral de consenso del Concilio = 85 (sin zona intermedia 80–84).
8. No tocar DB de producción desde remaps/auditorías del Concilio.
9. Fast path Gente/Estado (/api/ask) queda FUERA del Concilio secuencial.
"""


def build_memory_pack(
    max_total_chars: int = 12000,
    max_file_chars: int = 3500,
    include_hard_rules: bool = True,
) -> str:
    """Assemble a redacted memory pack from DEV Sentinel docs."""
    parts: List[str] = []
    used: set[str] = set()
    budget = max_total_chars

    if include_hard_rules:
        parts.append(HARD_RULES_FALLBACK)
        budget -= len(HARD_RULES_FALLBACK)

    for root in DOC_ROOTS:
        if budget <= 500:
            break
        if not root.exists():
            continue
        for rel in PRIORITY_DOCS:
            if budget <= 500:
                break
            path = root / rel
            key = str(path.resolve()) if path.exists() else ""
            if not key or key in used:
                continue
            # Prefer first hit per basename (DEV first).
            base_key = path.name
            if any(base_key == Path(u).name and "workspaces-dev" in u for u in used):
                continue
            chunk = _safe_read(path, min(max_file_chars, budget))
            if not chunk:
                continue
            used.add(key)
            header = f"\n===== DOC: {path} =====\n"
            parts.append(header + chunk)
            budget -= len(header) + len(chunk)

    pack = "\n".join(parts).strip()
    return pack[:max_total_chars]


def memory_pack_metadata() -> Dict[str, object]:
    found: List[str] = []
    for root in DOC_ROOTS:
        for rel in PRIORITY_DOCS:
            p = root / rel
            if p.is_file():
                found.append(str(p))
    return {
        "doc_roots": [str(r) for r in DOC_ROOTS],
        "found_docs": found,
        "secrets_policy": "no_.env_no_tokens",
    }
