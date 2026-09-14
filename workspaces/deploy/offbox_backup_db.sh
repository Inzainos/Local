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
#      bajo `data/`. Ningún glob de limpieza del proyecto puede alcanzarlo.
#   3. HISTORIA ACOTADA. Retención por días **y** por número de copias, para
#      tener puntos de retorno sin que el destino crezca sin techo.
#
# Calcado de watchdog/scripts/offbox_backup.sh, que ya está probado aquí.
#
# Uso:
#   bash deploy/offbox_backup_db.sh              # respaldo normal
#   bash deploy/offbox_backup_db.sh --verify     # además, integrity_check
#   bash deploy/offbox_backup_db.sh --dry-run    # simula; no escribe NADA
#
# Cron (si no usas el timer systemd). Sin redirección: el script ya escribe su
# propio log, y redirigir además duplicaría cada línea:
#   45 3 * * *  bash /home/deamon/workspaces/deploy/offbox_backup_db.sh --verify

set -euo pipefail

ROOT="${SENTINEL_ROOT:-/home/deamon/workspaces}"
DB_PATH="${SENTINEL_DB_PATH:-$ROOT/sentinel_omega/data/SENTINEL_OMEGA_PRO.db}"
WIN_BACKUP_DIR="${SENTINEL_BACKUP_DIR:-/mnt/c/Users/elanz/sentinel-backups}"
LOG_DIR="${SENTINEL_LOG_DIR:-$ROOT/logs}"
LOG_FILE="$LOG_DIR/offbox_db.log"
RETENTION_DAYS="${SENTINEL_BACKUP_RETENTION_DAYS:-30}"
# Techo duro de copias. La retención por días sola no acota el disco: varias
# corridas manuales en la misma ventana dejan N snapshots de cientos de MB.
MAX_COPIAS="${SENTINEL_BACKUP_MAX_COPIES:-30}"

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

# En dry-run no se toca el disco: ni el directorio de logs se crea. Antes sí se
# creaba y `tee` escribía el log, contradiciendo el "no se escribe nada".
if [ "$DRY_RUN" -eq 0 ]; then
    mkdir -p "$LOG_DIR"
fi

log() {
    local linea
    linea="$(printf '%s [offbox_db] %s' "$(date '+%Y-%m-%d %H:%M:%S')" "$*")"
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '%s\n' "$linea"
    else
        printf '%s\n' "$linea" | tee -a "$LOG_FILE"
    fi
}

fail() {
    log "ERROR: $*"
    exit 1
}

command -v sqlite3 >/dev/null 2>&1 || fail "sqlite3 no está instalado; es obligatorio (no se usa cp a propósito)"
[ -f "$DB_PATH" ] || fail "no existe la DB en $DB_PATH (ajusta SENTINEL_DB_PATH)"

STAMP="$(date +%Y-%m-%d_%H%M%S)"
DEST_DIR="$WIN_BACKUP_DIR"
DEST_GZ="$DEST_DIR/SENTINEL_OMEGA_PRO_${STAMP}.db.gz"
# Los intermedios llevan sufijo `.tmp`, que NO casa con el patrón de poda
# (`SENTINEL_OMEGA_PRO_*.db.gz`). Así, si el proceso muere de golpe y el trap no
# alcanza a correr, lo que queda nunca se cuenta como un respaldo válido.
TMP_DB="$DEST_DIR/SENTINEL_OMEGA_PRO_${STAMP}.db.tmp"
TMP_GZ="${TMP_DB}.gz"

DB_BYTES="$(stat -c %s "$DB_PATH" 2>/dev/null || echo 0)"
humano() { numfmt --to=iec "$1" 2>/dev/null || echo "${1}B"; }

log "inicio — origen=$DB_PATH ($(humano "$DB_BYTES")) destino=$DEST_GZ retención=${RETENTION_DAYS}d/${MAX_COPIAS} copias"

if [ "$DRY_RUN" -eq 1 ]; then
    log "DRY-RUN: no se escribe nada, ni el log. Se habría ejecutado:"
    log "  sqlite3 \"$DB_PATH\" \".backup '$TMP_DB'\""
    log "  gzip -9 \"$TMP_DB\"  &&  mv \"$TMP_GZ\" \"$DEST_GZ\""
    log "  poda: por edad (>${RETENTION_DAYS}d) y por exceso sobre ${MAX_COPIAS} copias"
    exit 0
fi

mkdir -p "$DEST_DIR" || fail "no se pudo crear $DEST_DIR (¿está montado /mnt/c?)"

# Cerrojo exclusivo para toda la operación. El sello con segundos no evita una
# carrera: dos invocaciones concurrentes pueden pasar cualquier comprobación de
# existencia antes de que la otra haya creado su archivo.
LOCK_FILE="$LOG_DIR/.offbox_db.lock"
exec 9>"$LOCK_FILE"
if command -v flock >/dev/null 2>&1; then
    flock -n 9 || fail "ya hay un respaldo en curso (cerrojo $LOCK_FILE)"
fi

limpiar_parciales() {
    local restos=0
    for f in "$TMP_DB" "$TMP_GZ"; do
        if [ -e "$f" ]; then rm -f "$f"; restos=1; fi
    done
    [ "$restos" -eq 1 ] && log "limpieza: se eliminaron los intermedios incompletos de esta corrida"
    return 0
}
trap limpiar_parciales EXIT

[ -e "$DEST_GZ" ] && fail "ya existe un respaldo con ese sello ($DEST_GZ) — no se sobrescribe"

podar() {
    local motivo_edad motivo_exceso
    motivo_edad="$(find "$DEST_DIR" -maxdepth 1 -name 'SENTINEL_OMEGA_PRO_*.db.gz' -mtime "+$RETENTION_DAYS" -print -delete | wc -l)"
    # Por exceso: conserva las MAX_COPIAS más recientes por nombre (el sello es
    # ordenable lexicográficamente) y borra el resto.
    motivo_exceso=0
    while IFS= read -r viejo; do
        [ -n "$viejo" ] || continue
        rm -f "$viejo"
        motivo_exceso=$((motivo_exceso + 1))
    done < <(find "$DEST_DIR" -maxdepth 1 -name 'SENTINEL_OMEGA_PRO_*.db.gz' | sort | head -n "-$MAX_COPIAS" 2>/dev/null || true)
    log "poda: $motivo_edad por edad (>${RETENTION_DAYS}d), $motivo_exceso por exceso (>${MAX_COPIAS} copias)"
}

# Podar ANTES de copiar: libera espacio para el snapshot nuevo en vez de
# limpiar cuando el disco ya se llenó.
podar

# Espacio: durante el gzip coexisten la copia `.db` y el `.db.gz`, así que el
# peor caso es ~2x el tamaño de la DB. Reservar solo 1x dejaba que `.backup`
# terminara y `gzip` muriera por ENOSPC.
AVAIL_KB="$(df -Pk "$DEST_DIR" | awk 'NR==2{print $4}')"
NEED_KB=$(( (DB_BYTES / 1024) * 2 + 1 ))
[ "$AVAIL_KB" -ge "$NEED_KB" ] || fail "espacio insuficiente en $DEST_DIR: hay $(humano $((AVAIL_KB*1024))), se necesitan $(humano $((NEED_KB*1024))) (2x la DB: copia + comprimido conviven)"

log "copiando con sqlite3 .backup (instantánea coherente, tolera escrituras en curso)"
sqlite3 "$DB_PATH" ".backup '$TMP_DB'" || fail "sqlite3 .backup falló"

if [ "$VERIFY" -eq 1 ]; then
    log "verificando integridad de la copia"
    RESULT="$(sqlite3 "$TMP_DB" 'PRAGMA integrity_check;' 2>&1 || true)"
    if [ "$RESULT" != "ok" ]; then
        fail "integrity_check de la copia devolvió: $RESULT — copia descartada, el respaldo NO se guardó"
    fi
    log "integrity_check=ok"
fi

gzip -9 "$TMP_DB" || fail "gzip falló"
# Renombrado final: hasta este instante nada en el destino casa con el patrón de
# poda, así que un fallo jamás deja un respaldo aparente pero corrupto.
mv "$TMP_GZ" "$DEST_GZ" || fail "no se pudo renombrar $TMP_GZ → $DEST_GZ"

GZ_BYTES="$(stat -c %s "$DEST_GZ" 2>/dev/null || echo 0)"
log "guardado: $DEST_GZ ($(humano "$GZ_BYTES"))"

RESTANTES="$(find "$DEST_DIR" -maxdepth 1 -name 'SENTINEL_OMEGA_PRO_*.db.gz' | wc -l)"
log "fin — $RESTANTES respaldo(s) disponibles en $DEST_DIR"
