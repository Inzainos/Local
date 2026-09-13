"""
Firmas — per-bot pattern memory and signature engine.

A "firma" is the multi-variable state of the 1-2 weeks preceding a real
event, extracted from the 30-year backcast. Signatures are promoted by
recurrence (nueva -> observada -> recurrente -> consolidada) and compared
against the live state in operation. Only consolidated signatures are
enforceable knowledge (punishable by the Juez when missed).
"""

from sentinel_omega.core.firmas.signature_engine import (
    FEATURE_KEYS,
    FirmaMemoria,
    extraer_features_ventana,
    similitud,
)
