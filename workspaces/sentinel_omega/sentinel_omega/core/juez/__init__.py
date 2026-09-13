"""
Juez — cold auditor, separate from the Padre.

The Juez never predicts and never joins the consensus. It compares what
each bot (and the Padre) said against the observed truth, records
ACIERTO / FALLO / FALSO_POSITIVO with recidivism-scaled severity, and
feeds offline recalibration — it does not touch predictor weights hot.
"""

from sentinel_omega.core.juez.juez import Juez
