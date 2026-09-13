"""Messaging — AlertService unificado + ConsensoVigilante (Padre)."""
from .alert_service import AlertService, AlertTemplates, Severity, FormattedMessage
from .consenso_vigilante import ConsensoVigilante, get_vigilante, reset_vigilante
__all__=["AlertService","AlertTemplates","Severity","FormattedMessage","ConsensoVigilante","get_vigilante","reset_vigilante"]
