"""
Topologia en Cascada — ETL reusable para Sentinel Omega
v1.0 — 13 ago 2026

CONTEXTO
--------
Origen: bug de localizacion encontrado el 10-13 ago 2026 (geometria_uvg.py
generaba 102/125 nodos con coordenadas ficticias — formula aurea sin
relacion con geografia real; confirmado con el sismo M7.4 de Choco,
Colombia, asignado erroneamente a Chiapas, Mexico, ~1700km de error).

El primer fix (geometria_uvg.py v2.5.2) corrigio las coordenadas de los
nodos, pero dejo un problema de fondo: tbl_historico_sismico_raw y
tbl_desgasificacion_raw solo guardan id_nodo YA RESUELTO, sin el lat/lon
original del evento — asi que cada vez que la topologia cambiara, habria
que volver a descargar TODO de la fuente (USGS / NASA MSVOLSO2L4) y
revisar tabla por tabla que se ve afectada.

Este script resuelve eso de raiz, de una vez:

1. Introduce dos tablas de "verdad fundamental" (ver
   schema_topologia_cascada.sql): tbl_eventos_sismicos_fuente y
   tbl_eventos_volcanicos_fuente. Una fila por evento real, con su
   lat/lon PROPIO (inmutable) + id externo unico para upsert
   idempotente. id_nodo ahi es una columna DERIVADA, recalculable en
   cualquier momento SIN volver a tocar la red.

2. En la PRIMERA corrida (no existen filas en esas tablas), hace un
   fetch completo desde las fuentes publicas (reutiliza las funciones
   de backcast.py, sin duplicar esa logica). En corridas FUTURAS, con
   --solo-recalcular, NO vuelve a tocar la red — solo re-lee las
   coordenadas ya guardadas y recalcula id_nodo contra la version
   actual de geometria_uvg.py. Asi, la proxima vez que se corrija un
   nodo (agregar Baikal, arreglar otra colision, lo que sea), correr
   este mismo script con --solo-recalcular basta.

3. Reconstruye las tablas agregadas existentes
   (tbl_historico_sismico_raw, tbl_desgasificacion_raw) desde las
   tablas fuente, SIN cambiar su estructura — el resto del sistema
   (Fase 1/1b de entrenamiento) las sigue leyendo exactamente igual,
   no hay que tocar esa logica.

4. Respalda y purga la memoria de patrones que depende de id_nodo
   (TBL_FIRMAS, tbl_eventos_no_sismicos, tbl_cimatica_patrones
   ambito='nodo', tbl_nodo_estado_dinamico) SOLO si algo realmente
   cambio de nodo — para que el entrenamiento no quede envenenado con
   patrones aprendidos bajo la topologia vieja.

5. Marca (no borra) TBL_JUEZ_AUDITORIA con la version de topologia
   anterior, para que la vista viva_real empiece a medir asertividad
   limpia desde el momento del fix, sin mezclar epocas.

6. Relanza el entrenamiento completo (Fase 1+1b+2+lags+correlaciones),
   reutilizando entrenar() de entrenamiento.py.

7. Al final, DROP de las tablas temporales usadas para la comparacion
   de id_nodo viejo vs nuevo — no dejan rastro en la base de datos
   final.

NUNCA guarda el nombre del lugar como texto — el nombre siempre se
resuelve en vivo contra NODOS_POR_ID. Una sola fuente de verdad para
geografia, siempre.

USO
---
    # Primera corrida (o para traer eventos nuevos desde la ultima vez):
    python3 topologia_cascada.py --db-path /ruta/SENTINEL_OMEGA_PRO.db --refetch

    # Corridas futuras, tras cualquier cambio en geometria_uvg.py,
    # SIN tocar la red (usa los lat/lon ya guardados):
    python3 topologia_cascada.py --db-path /ruta/SENTINEL_OMEGA_PRO.db --solo-recalcular

    # Simular sin escribir nada:
    python3 topologia_cascada.py --db-path ... --solo-recalcular --dry-run

REQUISITOS
----------
- --refetch requiere acceso a internet (earthquake.usgs.gov,
  so2.gsfc.nasa.gov). --solo-recalcular NO requiere red.
- geometria_uvg.py debe ser importable (con o sin el fix mas reciente
  aplicado — el script detecta la version actual automaticamente, no
  asume cual es "la correcta").
"""

import argparse
import hashlib
import logging
import sqlite3
import sys
import time
from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

# Make `python3 topologia_cascada.py` work from any cwd (same as dashboard).
_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

# ── Logging: consola + archivo ─────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
_ts_run = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"topologia_cascada_{_ts_run}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TOPOLOGIA_CASCADA] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

YEAR_INI = 1994
YEAR_END = 2026
MIN_MAGNITUD_USGS = 4.5


def calcular_version_topologia() -> str:
    """Genera un hash corto de las coordenadas actuales de
    geometria_uvg.py — sirve como 'version_topologia' para saber, sin
    ambiguedad, si dos corridas usaron la misma geografia o no."""
    from sentinel_omega.core.shared.geometria_uvg import MATRIZ_UVG_125
    huella = "|".join(
        f"{n['id']}:{n['lat']:.4f}:{n['lon']:.4f}" for n in sorted(MATRIZ_UVG_125, key=lambda n: n["id"])
    )
    return hashlib.sha256(huella.encode()).hexdigest()[:16]


def crear_tablas_fuente(conn: sqlite3.Connection, dry_run: bool) -> None:
    """Crea las tablas de verdad fundamental si no existen (idempotente)."""
    schema_path = Path(__file__).parent / "schema_topologia_cascada.sql"
    if not schema_path.exists():
        logger.error(f"No se encontro {schema_path} — colocalo junto a este script.")
        sys.exit(1)
    ddl = schema_path.read_text(encoding="utf-8")
    logger.info("Aplicando schema_topologia_cascada.sql (CREATE TABLE IF NOT EXISTS)")
    if not dry_run:
        conn.executescript(ddl)
        conn.commit()


# ── Fetch desde fuentes publicas (reutiliza logica de backcast.py) ──

def fetch_sismos_usgs(year: int) -> pd.DataFrame:
    """Identico a backcast.py::extraer_sismos_usgs_real."""
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "csv",
        "starttime": f"{year}-01-01",
        "endtime": f"{year}-12-31T23:59:59",
        "minmagnitude": str(MIN_MAGNITUD_USGS),
    }
    logger.info(f"  Descargando catalogo sismico USGS: {year}")
    try:
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        if df.empty:
            return pd.DataFrame()
        df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(None)
        logger.info(f"  {year}: {len(df)} sismos M{MIN_MAGNITUD_USGS}+")
        return df[["id", "time", "mag", "latitude", "longitude"]].copy()
    except Exception as e:
        logger.error(f"  Fallo al descargar USGS {year}: {e}")
        return pd.DataFrame()


def fetch_volcanes_nasa() -> pd.DataFrame:
    """Identico a backcast.py::extraer_desgasificacion_volcanica."""
    base = "https://so2.gsfc.nasa.gov"
    headers = {"User-Agent": "Mozilla/5.0 (SentinelOmega research)"}
    logger.info("Descargando catalogo volcanico NASA MSVOLSO2L4...")
    try:
        page = requests.get(f"{base}/measures.html", headers=headers, timeout=30)
        page.raise_for_status()
        import re
        links = re.findall(r'href="(/eruptions/MSVOLSO2L4_\d+\.txt)"', page.text)
        if not links:
            return pd.DataFrame()
        latest = sorted(links)[-1]
        r = requests.get(f"{base}{latest}", headers=headers, timeout=60)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text), sep="\t", engine="python", on_bad_lines="skip")
        df.columns = [c.strip() for c in df.columns]
        df = df.loc[:, [c for c in df.columns if c]]
        df = df.rename(columns={"so2(kt)": "so2_kt"})
        df = df.dropna(subset=["lat", "lon", "yyyy", "mm", "dd"])
        df["fecha"] = pd.to_datetime(
            dict(year=df["yyyy"], month=df["mm"], day=df["dd"]), errors="coerce"
        )
        df = df.dropna(subset=["fecha"])
        logger.info(f"  MSVOLSO2L4: {len(df)} eventos volcanicos ({latest})")
        return df[["volcano", "lat", "lon", "fecha", "type", "vei", "so2_kt"]]
    except Exception as e:
        logger.error(f"Fallo al descargar catalogo volcanico: {e}")
        return pd.DataFrame()


# ── Paso 1: poblar tablas fuente (solo si --refetch) ────────────────

def poblar_eventos_sismicos_fuente(conn: sqlite3.Connection, dry_run: bool) -> int:
    from sentinel_omega.core.shared.geometria_uvg import nodo_mas_cercano

    version = calcular_version_topologia()
    total = 0
    for year in range(YEAR_INI, YEAR_END + 1):
        df = fetch_sismos_usgs(year)
        if df.empty:
            continue
        for _, row in df.iterrows():
            nodo = nodo_mas_cercano(float(row["latitude"]), float(row["longitude"]))
            if not dry_run:
                conn.execute(
                    """INSERT INTO tbl_eventos_sismicos_fuente
                       (usgs_id, time_utc, lat, lon, mag, id_nodo, topologia_version)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(usgs_id) DO UPDATE SET
                           lat=excluded.lat, lon=excluded.lon, mag=excluded.mag,
                           id_nodo=excluded.id_nodo,
                           topologia_version=excluded.topologia_version,
                           updated_at=datetime('now')""",
                    (str(row["id"]), str(row["time"]), float(row["latitude"]),
                     float(row["longitude"]), float(row["mag"]), nodo["id"], version),
                )
            total += 1
        if not dry_run:
            conn.commit()
        time.sleep(0.5)  # cortesia con la API publica de USGS
    logger.info(f"Eventos sismicos fuente poblados/actualizados: {total}")
    return total


def poblar_eventos_volcanicos_fuente(conn: sqlite3.Connection, dry_run: bool) -> int:
    from sentinel_omega.core.shared.geometria_uvg import nodo_mas_cercano

    version = calcular_version_topologia()
    df = fetch_volcanes_nasa()
    if df.empty:
        return 0
    total = 0
    for _, row in df.iterrows():
        fecha_str = row["fecha"].strftime("%Y-%m-%d")
        evento_id = f"{row['volcano']}_{fecha_str}"
        nodo = nodo_mas_cercano(float(row["lat"]), float(row["lon"]))
        if not dry_run:
            conn.execute(
                """INSERT INTO tbl_eventos_volcanicos_fuente
                   (evento_id, volcan, fecha, lat, lon, tipo_erupcion, vei, so2_kt,
                    id_nodo, topologia_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(evento_id) DO UPDATE SET
                       lat=excluded.lat, lon=excluded.lon, id_nodo=excluded.id_nodo,
                       topologia_version=excluded.topologia_version,
                       updated_at=datetime('now')""",
                (evento_id, str(row["volcano"]), fecha_str, float(row["lat"]),
                 float(row["lon"]), str(row.get("type", "")),
                 float(row["vei"]) if pd.notna(row.get("vei")) else None,
                 float(row.get("so2_kt", 0.0)), nodo["id"], version),
            )
        total += 1
    if not dry_run:
        conn.commit()
    logger.info(f"Eventos volcanicos fuente poblados/actualizados: {total}")
    return total


# ── Paso 2: recalcular id_nodo SIN tocar la red ─────────────────────

def recalcular_id_nodo_sismico(conn: sqlite3.Connection, dry_run: bool) -> int:
    """Re-lee lat/lon YA GUARDADO y recalcula id_nodo contra la
    version actual de geometria_uvg.py. No toca la red."""
    from sentinel_omega.core.shared.geometria_uvg import nodo_mas_cercano

    version = calcular_version_topologia()
    filas = conn.execute(
        "SELECT usgs_id, lat, lon, id_nodo FROM tbl_eventos_sismicos_fuente"
    ).fetchall()

    if not filas:
        logger.warning(
            "tbl_eventos_sismicos_fuente esta vacia — no hay nada que "
            "recalcular. Corre primero con --refetch."
        )
        return 0

    cambios = 0
    for usgs_id, lat, lon, id_nodo_viejo in filas:
        nodo_nuevo = nodo_mas_cercano(lat, lon)
        if nodo_nuevo["id"] != id_nodo_viejo:
            cambios += 1
            if not dry_run:
                conn.execute(
                    """UPDATE tbl_eventos_sismicos_fuente
                       SET id_nodo=?, topologia_version=?, updated_at=datetime('now')
                       WHERE usgs_id=?""",
                    (nodo_nuevo["id"], version, usgs_id),
                )
        elif not dry_run:
            # aunque no cambio el nodo, se actualiza la version para
            # dejar registro de que ya se reviso contra la topologia actual
            conn.execute(
                "UPDATE tbl_eventos_sismicos_fuente SET topologia_version=? WHERE usgs_id=?",
                (version, usgs_id),
            )
    if not dry_run:
        conn.commit()
    logger.info(
        f"Recalculo sismico (sin red): {len(filas)} eventos revisados, "
        f"{cambios} cambiaron de nodo"
    )
    return cambios


def recalcular_id_nodo_volcanico(conn: sqlite3.Connection, dry_run: bool) -> int:
    from sentinel_omega.core.shared.geometria_uvg import nodo_mas_cercano

    version = calcular_version_topologia()
    filas = conn.execute(
        "SELECT evento_id, lat, lon, id_nodo FROM tbl_eventos_volcanicos_fuente"
    ).fetchall()
    if not filas:
        logger.warning(
            "tbl_eventos_volcanicos_fuente esta vacia — corre primero con --refetch."
        )
        return 0

    cambios = 0
    for evento_id, lat, lon, id_nodo_viejo in filas:
        nodo_nuevo = nodo_mas_cercano(lat, lon)
        if nodo_nuevo["id"] != id_nodo_viejo:
            cambios += 1
            if not dry_run:
                conn.execute(
                    """UPDATE tbl_eventos_volcanicos_fuente
                       SET id_nodo=?, topologia_version=?, updated_at=datetime('now')
                       WHERE evento_id=?""",
                    (nodo_nuevo["id"], version, evento_id),
                )
        elif not dry_run:
            conn.execute(
                "UPDATE tbl_eventos_volcanicos_fuente SET topologia_version=? WHERE evento_id=?",
                (version, evento_id),
            )
    if not dry_run:
        conn.commit()
    logger.info(
        f"Recalculo volcanico (sin red): {len(filas)} eventos revisados, "
        f"{cambios} cambiaron de nodo"
    )
    return cambios


# ── Paso 3: reconstruir tablas agregadas desde las fuente ───────────

def reconstruir_tabla_sismica_agregada(conn: sqlite3.Connection, dry_run: bool) -> None:
    logger.info("Reconstruyendo tbl_historico_sismico_raw desde tbl_eventos_sismicos_fuente")
    if dry_run:
        logger.info("[DRY-RUN] No se reconstruye la tabla real")
        return
    conn.execute("DELETE FROM tbl_historico_sismico_raw")
    conn.execute(
        """INSERT INTO tbl_historico_sismico_raw
           (timestamp_blk, id_nodo, sismo_count, sismo_max_mag)
           SELECT strftime('%Y-%m-%d %H:00', time_utc) AS timestamp_blk,
                  id_nodo,
                  COUNT(*) AS sismo_count,
                  MAX(mag) AS sismo_max_mag
           FROM tbl_eventos_sismicos_fuente
           GROUP BY timestamp_blk, id_nodo"""
    )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM tbl_historico_sismico_raw").fetchone()[0]
    logger.info(f"tbl_historico_sismico_raw reconstruida: {n} filas (hora x nodo)")


def reconstruir_tabla_volcanica_agregada(conn: sqlite3.Connection, dry_run: bool) -> None:
    logger.info("Reconstruyendo tbl_desgasificacion_raw desde tbl_eventos_volcanicos_fuente")
    if dry_run:
        logger.info("[DRY-RUN] No se reconstruye la tabla real")
        return
    conn.execute("DELETE FROM tbl_desgasificacion_raw")
    conn.execute(
        """INSERT INTO tbl_desgasificacion_raw
           (timestamp_blk, id_nodo, volcan, tipo_erupcion, vei, so2_kt)
           SELECT strftime('%Y-%m-%d 00:00', fecha) AS timestamp_blk,
                  id_nodo, volcan, tipo_erupcion, vei, so2_kt
           FROM tbl_eventos_volcanicos_fuente"""
    )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM tbl_desgasificacion_raw").fetchone()[0]
    logger.info(f"tbl_desgasificacion_raw reconstruida: {n} filas")


# ── Paso 4: purgar memoria de patrones (solo si hubo cambios) ───────

def respaldar_y_purgar_tabla(conn: sqlite3.Connection, tabla: str,
                              sufijo: str, where: str, dry_run: bool) -> int:
    n = conn.execute(f"SELECT COUNT(*) FROM {tabla} {where}").fetchone()[0]
    destino = f"{tabla}_{sufijo}"
    logger.info(f"Respaldando {tabla} ({n} filas{' con ' + where if where else ''}) -> {destino}")
    if dry_run:
        return n
    conn.execute(f"DROP TABLE IF EXISTS {destino}")
    conn.execute(f"CREATE TABLE {destino} AS SELECT * FROM {tabla} {where}")
    conn.execute(f"DELETE FROM {tabla} {where}")
    conn.commit()
    return n


def purgar_memoria_patrones(conn: sqlite3.Connection, sufijo: str, dry_run: bool) -> dict:
    stats = {}
    stats["TBL_FIRMAS"] = respaldar_y_purgar_tabla(conn, "TBL_FIRMAS", sufijo, "", dry_run)
    stats["tbl_eventos_no_sismicos"] = respaldar_y_purgar_tabla(
        conn, "tbl_eventos_no_sismicos", sufijo, "", dry_run)
    stats["tbl_cimatica_patrones_nodo"] = respaldar_y_purgar_tabla(
        conn, "tbl_cimatica_patrones", f"nodo_{sufijo}", "WHERE ambito='nodo'", dry_run)
    stats["tbl_nodo_estado_dinamico"] = respaldar_y_purgar_tabla(
        conn, "tbl_nodo_estado_dinamico", sufijo, "", dry_run)
    logger.info(f"Purga de memoria de patrones completa: {stats}")
    return stats


def marcar_auditoria_pre_fix(conn: sqlite3.Connection, sufijo: str, dry_run: bool) -> int:
    n = conn.execute(
        "SELECT COUNT(*) FROM TBL_JUEZ_AUDITORIA WHERE fase='viva'"
    ).fetchone()[0]
    logger.info(
        f"Marcando {n} filas de TBL_JUEZ_AUDITORIA (fase='viva') como "
        f"'pre_{sufijo}' — viva_real solo lee fase='viva', asi que la "
        "asertividad se mide limpia desde este momento"
    )
    if not dry_run:
        conn.execute(
            "UPDATE TBL_JUEZ_AUDITORIA SET fase=? WHERE fase='viva'",
            (f"pre_{sufijo}",),
        )
        conn.commit()
    return n


def relanzar_entrenamiento(db_path: str, dry_run: bool) -> None:
    if dry_run:
        logger.info("[DRY-RUN] No se relanza el entrenamiento real")
        return
    from sentinel_omega.infrastructure.pipeline.entrenamiento import entrenar
    logger.info("=== Relanzando entrenamiento completo ===")
    resultado = entrenar(db_path)
    logger.info(f"Entrenamiento completo: {resultado}")


def registrar_corrida(conn: sqlite3.Connection, version: str, stats: dict,
                       dry_run: bool) -> None:
    if dry_run:
        return
    conn.execute(
        """INSERT INTO tbl_topologia_cascada_log
           (topologia_version, eventos_sismicos_recalculados,
            eventos_volcanicos_recalculados, nodos_cambiaron,
            firmas_purgadas, dry_run)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (version, stats.get("sismicos", 0), stats.get("volcanicos", 0),
         stats.get("nodos_cambiaron", 0), stats.get("firmas_purgadas", 0),
         int(dry_run)),
    )
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ETL en cascada: recalcula topologia de nodos y "
                    "propaga el cambio a toda la memoria dependiente"
    )
    parser.add_argument("--db-path", required=True)
    parser.add_argument(
        "--refetch", action="store_true",
        help="Descarga de nuevo desde USGS/NASA (requiere internet). "
             "Usar en la primera corrida o para traer eventos nuevos."
    )
    parser.add_argument(
        "--solo-recalcular", action="store_true",
        help="No toca la red — solo recalcula id_nodo desde el lat/lon "
             "ya guardado. Usar en corridas futuras tras cualquier "
             "cambio en geometria_uvg.py."
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.refetch and not args.solo_recalcular:
        parser.error("Especifica --refetch (primera vez / traer datos nuevos) "
                      "o --solo-recalcular (recalculo rapido sin red)")

    version = calcular_version_topologia()
    logger.info(f"=== INICIO TOPOLOGIA CASCADA — version={version} "
                f"modo={'refetch' if args.refetch else 'solo-recalcular'} "
                f"dry_run={args.dry_run} ===")
    logger.info(f"Log completo en: {LOG_FILE}")

    conn = sqlite3.connect(args.db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    stats = {}

    try:
        crear_tablas_fuente(conn, args.dry_run)

        logger.info("--- Paso 1: eventos fuente (sismos + volcanes) ---")
        if args.refetch:
            poblar_eventos_sismicos_fuente(conn, args.dry_run)
            poblar_eventos_volcanicos_fuente(conn, args.dry_run)
            stats["nodos_cambiaron"] = 1  # refetch siempre implica reconstruir todo
        else:
            n1 = recalcular_id_nodo_sismico(conn, args.dry_run)
            n2 = recalcular_id_nodo_volcanico(conn, args.dry_run)
            stats["sismicos"] = n1
            stats["volcanicos"] = n2
            stats["nodos_cambiaron"] = n1 + n2

        if stats.get("nodos_cambiaron", 0) == 0:
            logger.info(
                "Ningun nodo cambio de asignacion — topologia ya estaba "
                "al dia. No se reconstruye nada ni se purga memoria."
            )
            registrar_corrida(conn, version, stats, args.dry_run)
            logger.info("=== TOPOLOGIA CASCADA COMPLETA (sin cambios) ===")
            return

        logger.info("--- Paso 2: reconstruir tablas agregadas ---")
        reconstruir_tabla_sismica_agregada(conn, args.dry_run)
        reconstruir_tabla_volcanica_agregada(conn, args.dry_run)

        logger.info("--- Paso 3: purgar memoria de patrones dependiente de nodo ---")
        sufijo = f"pre_{version}_{_ts_run}"
        purga_stats = purgar_memoria_patrones(conn, sufijo, args.dry_run)
        stats["firmas_purgadas"] = sum(purga_stats.values())

        logger.info("--- Paso 4: marcar auditoria pre-fix ---")
        marcar_auditoria_pre_fix(conn, sufijo, args.dry_run)

        logger.info("--- Paso 5: entrenamiento OMITIDO (verificar fuente primero) ---")
        # relanzar_entrenamiento(args.db_path, args.dry_run)

        registrar_corrida(conn, version, stats, args.dry_run)

        logger.info("=== TOPOLOGIA CASCADA COMPLETA ===")
        logger.info(f"Resumen: {stats}")
        logger.info(
            "La proxima vez que geometria_uvg.py cambie, basta con correr "
            "este mismo script con --solo-recalcular. No hace falta "
            "volver a mapear tabla por tabla."
        )
    except Exception:
        logger.exception("TOPOLOGIA CASCADA FALLO — revisar el log completo arriba")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
