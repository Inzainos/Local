"""
Pesos de credibilidad por bot — the substrate of hierarchical punishment.

The Padre weighs each bot's vote in consensus by its peso. Training Fase 2
adjusts them: a bot that fails to recognize enforceable knowledge is
punished (hijo x1); the Padre pays double (x2) when its own meta-signature
fails — base_geo protocol. Recognition earns mild reinforcement.

Bounds keep any bot from being silenced or deified: [0.3, 1.5].
"""

import logging
import sqlite3
from typing import Dict

logger = logging.getLogger(__name__)

PESO_DEFAULT = 1.0
PESO_BASELINE = 1.0        # normal reinforcement only RECOVERS up to here
PESO_MIN = 0.3
PESO_MAX = 1.5             # only attention redistribution can push above 1.0

CASTIGO_HIJO = 0.95        # x1 — multiplicative decay per failure
CASTIGO_PADRE = 0.90       # x2 — the Padre pays double
REFUERZO = 1.02            # mild reinforcement per recognition


def cargar_pesos(conn: sqlite3.Connection) -> Dict[str, float]:
    """Load all bot weights (missing bots default to 1.0 at read site)."""
    try:
        rows = conn.execute("SELECT bot_name, peso FROM TBL_PESOS_BOTS").fetchall()
        return {bot: peso for bot, peso in rows}
    except sqlite3.OperationalError:
        return {}


def _ajustar(
    conn: sqlite3.Connection,
    bot: str,
    factor: float,
    es_fallo: bool,
    techo: float = PESO_MAX,
) -> float:
    row = conn.execute(
        "SELECT peso FROM TBL_PESOS_BOTS WHERE bot_name = ?", (bot,)
    ).fetchone()
    peso_actual = row[0] if row else PESO_DEFAULT
    nuevo = max(PESO_MIN, min(PESO_MAX, peso_actual * factor))
    if not es_fallo:
        # Reinforcement respects its ceiling and never LOWERS a weight that
        # is already above it (e.g. earned via attention redistribution).
        nuevo = min(nuevo, max(techo, peso_actual))

    conn.execute(
        "INSERT INTO TBL_PESOS_BOTS (bot_name, peso, aciertos, fallos) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(bot_name) DO UPDATE SET "
        "peso = ?, "
        "aciertos = aciertos + ?, "
        "fallos = fallos + ?, "
        "updated_at = datetime('now')",
        (bot, nuevo, 0 if es_fallo else 1, 1 if es_fallo else 0,
         nuevo, 0 if es_fallo else 1, 1 if es_fallo else 0),
    )
    conn.commit()
    return nuevo


def castigar(
    conn: sqlite3.Connection,
    bot: str,
    es_padre: bool = False,
    gravedad: float = 1.0,
) -> float:
    """Punish a bot for missing enforceable knowledge.

    base_geo protocol: the punishment scales with the gravity of the error —
    missing an M7 hurts far more than missing an M5 (gravedad M5=1, M6=2,
    M7=3; decay factor raised to gravedad). The Padre pays double.
    """
    base = CASTIGO_PADRE if es_padre else CASTIGO_HIJO
    factor = base ** max(1.0, gravedad)
    nuevo = _ajustar(conn, bot, factor, es_fallo=True)
    logger.warning(
        f"CASTIGO {'x2 (PADRE)' if es_padre else 'x1'} a {bot} "
        f"(gravedad={gravedad:.1f}): peso -> {nuevo:.3f}"
    )
    return nuevo


def reforzar(
    conn: sqlite3.Connection,
    bot: str,
    hasta: float = PESO_BASELINE,
) -> float:
    """Mild reinforcement when the bot recognizes a known signature.

    Normal recognition only RECOVERS credibility up to the baseline (1.0) —
    doing your job doesn't earn extra weight, it just repairs punishment.
    Attention redistribution (the bot saw what the Padre missed) may pass
    hasta=PESO_MAX to reward above baseline.
    """
    return _ajustar(conn, bot, REFUERZO, es_fallo=False, techo=hasta)
