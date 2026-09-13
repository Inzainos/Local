#!/usr/bin/env bash
# Backup diario de la evidencia del watchdog hacia el lado Windows del
# host (fuera del dominio de confianza de Linux): si un atacante logra
# root en Kali y borra watchdog.db/logs para tapar sus huellas, esta
# copia sigue estando ahi (Windows es un compromiso separado).
#
# NO se copian los binarios en cuarentena (data/quarantine/*) a proposito:
# son muestras potencialmente maliciosas y no tiene sentido replicarlas
# al lado de confianza. Solo se respalda METADATA (db, logs, forense en
# JSON), que es lo que realmente hace falta para reconstruir que paso.
set -euo pipefail

ROOT="/watchdog"
WIN_BACKUP_DIR="/mnt/c/Users/elanz/watchdog-backups"
RETENTION_DAYS=30

mkdir -p "$WIN_BACKUP_DIR"

STAMP="$(date +%Y-%m-%d_%H%M)"
TMP_TAR="$(mktemp --suffix=.tar.gz)"

tar -czf "$TMP_TAR" \
    -C "$ROOT" \
    data/watchdog.db \
    data/forensics \
    logs \
    config/config.yaml \
    2>/dev/null || true

cp "$TMP_TAR" "$WIN_BACKUP_DIR/watchdog_${STAMP}.tar.gz"
rm -f "$TMP_TAR"

# Poda backups mas viejos que RETENTION_DAYS
find "$WIN_BACKUP_DIR" -name "watchdog_*.tar.gz" -mtime "+$RETENTION_DAYS" -delete

echo "Backup off-box: $WIN_BACKUP_DIR/watchdog_${STAMP}.tar.gz"
