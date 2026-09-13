#!/usr/bin/env bash
# Respaldo off-box de la DB de Sentinel Omega hacia el lado Windows del host.
#
# Por qué existe (2026-09-13): una limpieza con glob `*.bak*` sobre el árbol
# vivo borró las copias `data/*.db.bak*`. Nunca estuvieron versionadas, así que
# git no podía recuperarlas, y quedó un único snapshot sin historia previa de
# restauración. Este script resuelve las tres causas de golpe:
#
#   1. CONSISTENCIA. Usa `sqlite3 .backup`, no `cp`. Copiar una SQLite en
#      caliente con `cp` puede producir un archivo roto: si el pipeline está
#      escribiendo, la copia se lleva páginas de dos estados distintos y un WAL
#      desincronizado. Esa copia abre bien y falla meses después, justo cuando
#      la necesitas. `.backup` usa la API de respaldo en línea de SQLite, que
#      toma una instantánea coherente aunque haya escrituras en curso.
#   2. FUERA DEL ÁRBOL QUE SE LIMPIA. El destino vive en /mnt/c (Windows), no
#      bajo `data/`. Ningún glob de limpieza del proyecto puede alcanzarlo, ni
#      por accidente ni por patrón mal escrito.
#   3. HISTORIA. Retención de N días en vez de un solo snapshot, para poder
#      volver a un punto anterior si una corrupción se detecta tarde.
#
# Calcado de watchdog/scripts/offbox_backup.sh, que ya está probado en esta
# máquina.
#
# Uso:
#   bash deploy/offbox_backup_db.sh              # respaldo normal
#   bash deploy/offbox_backup_db.sh --verify     # además, integrity_check de la copia
#   bash deploy/offbox_backup_db.sh --dry-run    # muestra qué haría, sin escribir
#
# Cron sugerido (diario 03:45, después del backup de watchdog a las 03:30):
#   45 3 * * *  bash /home/deamon/workspaces/deploy/offbox_backup_db.sh --verify >> /home/deamon/workspaces/logs/offbox_db.log 2>&1

set -euo pipefail

ROOT="${SENTINEL_ROOT:-/home/deamon/workspaces}"
DB_PATH="${SENTINEL_DB_PATH:-$ROOT/sentinel_omega/data/SENTINEL_OMEGA_PRO.db}"
WIN_BACKUP_DIR="${SENTINEL_BACKUP_DIR:-/mnt/c/Users/elanz/sentinel-backups}"
LOG_DIR="${SENTINEL_LOG_DIR:-$ROOT/logs}"
LOG_FILE="$LOG_DIR/offbox_db.log"
RETENTION_DAYS="${SENTINEL_BACKUP_RETENTION_DAYS:-30}"

VERIFY=0
DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --verify)  VERIFY=1 ;;
        --dry-run) DRY_RUN=1 ;;
        -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "Argumento desconocido: $arg (usa --help)" >&2; exit 2 ;;
    esac
done

mkdir -p "$LOG_DIR"

log() {
    # Siempre a stdout y al log; hora local MX para que cuadre con los reportes.
    printf '%s [offbox_db] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

fail() {
    log "ERROR: $*"
    exit 1
}

command -v sqlite3 >/dev/null 2>&1 || fail "sqlite3 no está instalado; es obligatorio (no se usa cp a propósito)"
[ -f "$DB_PATH" ] || fail "no existe la DB en $DB_PATH (ajusta SENTINEL_DB_PATH)"

# Segundos en el sello, no solo minutos: dos corridas en el mismo minuto
# chocaban de nombre y gzip abortaba dejando un .db sin comprimir en el destino
# (en producción, 873 MB de basura silenciosa). Detectado en prueba.
STAMP="$(date +%Y-%m-%d_%H%M%S)"
DEST_DIR="$WIN_BACKUP_DIR"
DEST_DB="$DEST_DIR/SENTINEL_OMEGA_PRO_${STAMP}.db"
DEST_GZ="${DEST_DB}.gz"

DB_BYTES="$(stat -c %s "$DB_PATH" 2>/dev/null || echo 0)"
log "inicio — origen=$DB_PATH ($(numfmt --to=iec "$DB_BYTES" 2>/dev/null || echo "${DB_BYTES}B")) destino=$DEST_GZ retención=${RETENTION_DAYS}d"

if [ "$DRY_RUN" -eq 1 ]; then
    log "DRY-RUN: no se escribe nada. Se habría ejecutado:"
    log "  sqlite3 \"$DB_PATH\" \".backup '$DEST_DB'\""
    log "  gzip -9 \"$DEST_DB\""
    log "  find \"$DEST_DIR\" -name 'SENTINEL_OMEGA_PRO_*.db.gz' -mtime +$RETENTION_DAYS -delete"
    exit 0
fi

mkdir -p "$DEST_DIR" || fail "no se pudo crear $DEST_DIR (¿está montado /mnt/c?)"

if [ -e "$DEST_GZ" ] || [ -e "$DEST_DB" ]; then
    fail "ya existe un respaldo con ese sello ($DEST_GZ) — no se sobrescribe"
fi

# Si algo falla a media copia, no dejamos el .db intermedio ocupando disco en
# el destino: en producción son cientos de MB que nadie volvería a mirar.
limpiar_parcial() {
    if [ -e "$DEST_DB" ]; then
        rm -f "$DEST_DB"
        log "limpieza: se eliminó la copia intermedia incompleta $DEST_DB"
    fi
}
trap limpiar_parcial EXIT

# Espacio libre en destino: exigimos al menos el tamaño de la DB (el gzip
# quedará por debajo, pero la copia intermedia sin comprimir no).
AVAIL_KB="$(df -Pk "$DEST_DIR" | awk 'NR==2{print $4}')"
NEED_KB=$(( DB_BYTES / 1024 + 1 ))
[ "$AVAIL_KB" -ge "$NEED_KB" ] || fail "espacio insuficiente en $DEST_DIR: hay ${AVAIL_KB}KB, se necesitan ${NEED_KB}KB"

# Copia consistente. NO usar cp: ver el encabezado de este archivo.
log "copiando con sqlite3 .backup (instantánea coherente, tolera escrituras en curso)"
sqlite3 "$DB_PATH" ".backup '$DEST_DB'" || fail "sqlite3 .backup falló"

if [ "$VERIFY" -eq 1 ]; then
    log "verificando integridad de la copia"
    RESULT="$(sqlite3 "$DEST_DB" 'PRAGMA integrity_check;' 2>&1 || true)"
    if [ "$RESULT" != "ok" ]; then
        rm -f "$DEST_DB"
        fail "integrity_check de la copia devolvió: $RESULT — copia descartada, el respaldo NO se guardó"
    fi
    log "integrity_check=ok"
fi

gzip -9 "$DEST_DB" || fail "gzip falló"
GZ_BYTES="$(stat -c %s "$DEST_GZ" 2>/dev/null || echo 0)"
log "guardado: $DEST_GZ ($(numfmt --to=iec "$GZ_BYTES" 2>/dev/null || echo "${GZ_BYTES}B"))"

# Poda por retención. Solo toca archivos con nuestro patrón de nombre, nunca
# un glob abierto — es justamente el error que originó este script.
PODADOS="$(find "$DEST_DIR" -maxdepth 1 -name 'SENTINEL_OMEGA_PRO_*.db.gz' -mtime "+$RETENTION_DAYS" -print -delete | wc -l)"
log "poda: $PODADOS respaldo(s) con más de ${RETENTION_DAYS} días eliminados"

RESTANTES="$(find "$DEST_DIR" -maxdepth 1 -name 'SENTINEL_OMEGA_PRO_*.db.gz' | wc -l)"
log "fin — $RESTANTES respaldo(s) disponibles en $DEST_DIR"
