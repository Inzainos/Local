#!/usr/bin/env bash
# Instala el entorno virtual + dependencias, y registra los 2 cron jobs del
# usuario actual (no requiere sudo: es el crontab de $USER, no el de root).
set -euo pipefail

ROOT="/watchdog"
cd "$ROOT"

if [ ! -d ".venv" ]; then
    echo "Creando entorno virtual..."
    python3 -m venv .venv
fi

echo "Instalando dependencias..."
"$ROOT/.venv/bin/pip" install -q --upgrade pip
"$ROOT/.venv/bin/pip" install -q -r requirements.txt

PYTHON="$ROOT/.venv/bin/python"
# PYTHONPATH tiene que ir pegado al comando de python, no antes del "cd &&"
# (en sh, un VAR=val antes de un comando solo aplica a ESE comando).
LIGHT_CMD="cd $ROOT && PYTHONPATH=$ROOT/src $PYTHON -m watchdog.main --mode light >> $ROOT/logs/cron.log 2>&1"
HEAVY_CMD="cd $ROOT && PYTHONPATH=$ROOT/src $PYTHON -m watchdog.main --mode heavy >> $ROOT/logs/cron.log 2>&1"
BACKUP_CMD="bash $ROOT/scripts/offbox_backup.sh >> $ROOT/logs/cron.log 2>&1"

TMP_CRON="$(mktemp)"
crontab -l 2>/dev/null | grep -v -e "watchdog.main" -e "offbox_backup.sh" > "$TMP_CRON" || true
{
    echo "*/15 * * * * $LIGHT_CMD"
    echo "0 * * * * $HEAVY_CMD"
    echo "30 3 * * * $BACKUP_CMD"
} >> "$TMP_CRON"
crontab "$TMP_CRON"
rm -f "$TMP_CRON"

echo "Cron instalado:"
crontab -l | grep "watchdog.main"

echo ""
echo "IMPORTANTE: para que rkhunter/chkrootkit corran en el ciclo pesado sin"
echo "que el cron se quede colgado pidiendo password, hace falta dar sudo"
echo "NOPASSWD acotado a esos 2 binarios. Ver README.md seccion 'Permisos'."
