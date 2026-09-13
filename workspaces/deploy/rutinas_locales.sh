#!/usr/bin/env bash
# Rutinas locales de Sentinel Omega — corre vía systemd timer cada 15 min.
#
# Replica en hora local (el servidor ya está en America/Mexico_City, sin
# conversión UTC) los mismos ritmos de .github/workflows/roy-vigilante.yml,
# para que ESTE servidor también mantenga estado/ actualizado sin depender
# de que Roy Vigilante corra en GitHub Actions ni de disparos manuales.
#
# NO incluye --disciplina/--barrido: esos flags pasan por el PID-check de
# launcher.py y chocan con el servicio systemd `sentinel-omega` (que corre
# 24/7) — quedan como paso manual documentado en README (§ Ambientes) hasta
# que se decida automatizar el stop/restart del servicio para correrlos.
set -uo pipefail
cd "$(dirname "$0")/.."
VENV=".venv/bin/python"

H=$(date +%-H)
M=$(date +%-M)
DIA=$(date +%-d)
DOW=$(date +%u)  # 1=lunes ... 7=domingo

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Estado general — cada 2h
if [ $((H % 2)) -eq 0 ] && [ "$M" -lt 15 ]; then
    log "generar_reporte.py"
    $VENV deploy/generar_reporte.py
fi

# Juez — se auto-limita a 4h internamente (pipeline/verificacion.py); lo
# llamamos cada 2h y él decide solo si le toca.
if [ $((H % 2)) -eq 0 ] && [ "$M" -lt 15 ]; then
    log "verificacion_juez.py"
    $VENV deploy/verificacion_juez.py
fi

# Reporte ejecutivo — cada 6h
if [ $((H % 6)) -eq 0 ] && [ "$M" -lt 15 ]; then
    log "reporte_ejecutivo.py"
    $VENV deploy/reporte_ejecutivo.py
fi

# Comparativo diario — 12am y 12pm
if { [ "$H" -eq 0 ] || [ "$H" -eq 12 ]; } && [ "$M" -lt 15 ]; then
    log "reporte_periodico.py --comparativo"
    $VENV deploy/reporte_periodico.py --comparativo
fi

# Semanal — domingo 12:15pm
if [ "$DOW" -eq 7 ] && [ "$H" -eq 12 ] && [ "$M" -ge 15 ] && [ "$M" -lt 30 ]; then
    log "reporte_periodico.py --semanal"
    $VENV deploy/reporte_periodico.py --semanal
fi

# Mensual — día 1 del mes, madrugada (cubre el mes recién terminado)
if [ "$DIA" -eq 1 ] && [ "$H" -eq 0 ] && [ "$M" -lt 15 ]; then
    log "reporte_periodico.py --mensual"
    $VENV deploy/reporte_periodico.py --mensual
fi

# Tuning diario — 5am
if [ "$H" -eq 5 ] && [ "$M" -lt 15 ]; then
    log "tuning_db.py --diario"
    $VENV deploy/tuning_db.py --diario
fi

# Despacho de correo — cada corrida (fail-soft, sin SMTP queda PENDIENTE)
log "enviar_correos.py"
$VENV deploy/enviar_correos.py
