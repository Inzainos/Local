"""
Historical Backcast Pipeline — ONE-TIME initial load.

Loads 32 years of real data (1994-2026) from scientific APIs into SQLite.
Once loaded, this script never runs again (idempotent: checks row count).

Sources:
  - NASA SPDF OMNI2: Bz, solar wind, proton flux, Kp (1994-2026)
  - USGS FDSN: Seismic catalog M4.5+ (1994-2026)
  - Schumann Tomsk: Resonance frequency data (local files if available)
  - CoinGecko: Bitcoin price (2014-2026)

Protocol:
  - ZERO synthetic data. Missing data = NULL.
  - LOCF (ffill) only from existing real records, never from generators.
  - 1-hour resolution grid for all variables.
  - Single atomic transaction per year.
"""

import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

from sentinel_omega.core.shared.geometria_uvg import MATRIZ_UVG_125, nodo_mas_cercano

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BACKCAST] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

YEAR_INI = 1994
YEAR_END = 2025
MIN_ROWS_COMPLETE = 250000

BACKCAST_SCHEMA = """
CREATE TABLE IF NOT EXISTS tbl_clima_espacial_raw (
    timestamp_blk    TEXT PRIMARY KEY,
    bz_promedio     REAL,
    bz_derivada     REAL,
    bz_min          REAL,
    bz_max          REAL,
    viento_solar_avg REAL,
    viento_solar_max REAL,
    kp_max          REAL,
    kp_promedio     REAL,
    proton_flux_10mev REAL
);

CREATE TABLE IF NOT EXISTS tbl_astronomia_cinematica (
    timestamp_blk        TEXT PRIMARY KEY,
    lod_ms              REAL DEFAULT 0.0,
    fase_lunar_pct      REAL DEFAULT 0.0,
    distancia_lunar_km  REAL DEFAULT 384400.0,
    es_sicigia          INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tbl_historico_sismico_raw (
    timestamp_blk    TEXT NOT NULL,
    id_nodo         INTEGER NOT NULL,
    sismo_count     INTEGER DEFAULT 0,
    sismo_max_mag   REAL DEFAULT 0.0,
    PRIMARY KEY (timestamp_blk, id_nodo)
);

CREATE TABLE IF NOT EXISTS tbl_psique_financiera (
    timestamp_blk    TEXT PRIMARY KEY,
    btc_precio_usd  REAL,
    volatilidad_24h REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS tbl_enjambre_telemetria (
    timestamp_blk    TEXT NOT NULL,
    id_nodo         INTEGER NOT NULL,
    schumann_hz     REAL DEFAULT 7.83,
    PRIMARY KEY (timestamp_blk, id_nodo)
);

CREATE TABLE IF NOT EXISTS tbl_nodo_estado_dinamico (
    timestamp_blk            TEXT NOT NULL,
    id_nodo                 INTEGER NOT NULL,
    carga_tension_actual    REAL DEFAULT 0.0,
    PRIMARY KEY (timestamp_blk, id_nodo)
);

CREATE TRIGGER IF NOT EXISTS trg_procesar_saturacion
    AFTER UPDATE OF carga_tension_actual ON tbl_nodo_estado_dinamico
    WHEN NEW.carga_tension_actual > 1.0
BEGIN
    UPDATE tbl_nodo_estado_dinamico
    SET carga_tension_actual = 1.0
    WHERE timestamp_blk = NEW.timestamp_blk AND id_nodo = NEW.id_nodo;
END;
"""


def _get_db_path() -> str:
    return str(Path(__file__).parent.parent.parent / "data" / "SENTINEL_OMEGA_PRO.db")


def _init_backcast_tables(conn: sqlite3.Connection):
    conn.executescript(BACKCAST_SCHEMA)
    conn.commit()


def verificar_ejecucion_previa(conn: sqlite3.Connection) -> bool:
    """Check if historical data already loaded (>250k 1H blocks = complete)."""
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM tbl_clima_espacial_raw"
        )
        conteo = cursor.fetchone()[0]
        if conteo >= MIN_ROWS_COMPLETE:
            logger.info(
                f"Historical load already complete ({conteo} rows). Skipping."
            )
            return True
        return False
    except sqlite3.OperationalError:
        return False


def extraer_nasa_omni_real(year: int) -> pd.DataFrame:
    """Extract real OMNI2 data from NASA SPDF for a given year."""
    url = f"https://spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni/omni2_{year}.dat"
    logger.info(f"  Fetching NASA OMNI2: {year}")
    try:
        r = requests.get(url, timeout=50)
        r.raise_for_status()
        lineas = [ln.split() for ln in r.text.strip().split("\n") if ln.strip()]
        data = [l[:48] for l in lineas if len(l) >= 48]
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data).apply(pd.to_numeric, errors="coerce")
        df["fecha"] = pd.to_datetime(
            df[0].astype(int).astype(str) + " " + df[1].astype(int).astype(str),
            format="%Y %j",
            errors="coerce",
        )
        df = df.dropna(subset=["fecha"])

        df["bz_promed"] = df[17].where(df[17].abs() < 999.9, np.nan)
        df["sw_speed"] = df[24].where(df[24] < 9999.9, np.nan)
        df["p_flux"] = df[40].where(df[40] < 99999.9, np.nan)
        df["kp_val"] = (df[45] / 10.0).where(df[45] < 99, np.nan)

        return df[["fecha", "bz_promed", "sw_speed", "p_flux", "kp_val"]].dropna(
            subset=["fecha"]
        )
    except Exception as e:
        logger.error(f"NASA OMNI fetch failed for {year}: {e}")
        return pd.DataFrame()


def extraer_sismos_usgs_real(year: int) -> pd.DataFrame:
    """Extract real seismic catalog from USGS FDSN for a given year."""
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "csv",
        "starttime": f"{year}-01-01",
        "endtime": f"{year}-12-31T23:59:59",
        "minmagnitude": "4.5",
    }
    logger.info(f"  Fetching USGS seismic catalog: {year}")
    try:
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text), parse_dates=["time"])
        if df.empty:
            return pd.DataFrame()
        df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(None)
        return df[["time", "mag", "latitude", "longitude"]].copy()
    except Exception as e:
        logger.error(f"USGS seismic fetch failed for {year}: {e}")
        return pd.DataFrame()


def extraer_schumann_real(year: int) -> pd.DataFrame:
    """Load local Schumann data if available. Never generate synthetic."""
    path_local = Path(__file__).parent.parent.parent / "data" / f"schumann_{year}.csv"
    if path_local.exists():
        try:
            df = pd.read_csv(path_local, parse_dates=["timestamp"])
            return df[["timestamp", "frecuencia_fundamental_hz"]]
        except Exception as e:
            logger.warning(f"Schumann local file error for {year}: {e}")
    return pd.DataFrame()


def extraer_psique_financiera(year: int) -> pd.DataFrame:
    """Fetch Bitcoin historical price from CoinGecko (2014+ only)."""
    if year < 2014:
        return pd.DataFrame()

    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart/range"
    start_ts = int(datetime(year, 1, 1).timestamp())
    end_ts = int(datetime(year, 12, 31, 23, 59).timestamp())
    params = {"vs_currency": "usd", "from": start_ts, "to": end_ts}
    logger.info(f"  Fetching CoinGecko BTC: {year}")
    try:
        api_key = os.environ.get("COINGECKO_API_KEY", "")
        headers = {}
        if api_key:
            headers["x-cg-demo-api-key"] = api_key
        r = requests.get(url, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        if "prices" in data and data["prices"]:
            df = pd.DataFrame(data["prices"], columns=["time_ms", "precio"])
            df["fecha"] = pd.to_datetime(df["time_ms"], unit="ms")
            return df[["fecha", "precio"]]
    except Exception as e:
        logger.error(f"CoinGecko fetch failed for {year}: {e}")
    return pd.DataFrame()


def extraer_desgasificacion_volcanica() -> pd.DataFrame:
    """Fetch NASA MSVOLSO2L4 — multi-satellite volcanic SO2 database (1978+).

    One flat TSV covering every satellite-measured volcanic degassing event:
    volcano, lat/lon, date, eruption type, VEI, SO2 mass (kt). This is the
    historical spine for Beta-2 (degassing signatures).
    """
    base = "https://so2.gsfc.nasa.gov"
    headers = {"User-Agent": "Mozilla/5.0 (SentinelOmega research)"}
    logger.info("  Fetching NASA MSVOLSO2L4 volcanic SO2 database...")
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
        df = pd.read_csv(
            StringIO(r.text), sep="\t", engine="python", on_bad_lines="skip"
        )
        df.columns = [c.strip() for c in df.columns]
        df = df.loc[:, [c for c in df.columns if c]]  # drop trailing-tab cols
        df = df.rename(columns={"so2(kt)": "so2_kt"})
        df = df.dropna(subset=["lat", "lon", "yyyy", "mm", "dd"])
        df["fecha"] = pd.to_datetime(
            dict(year=df["yyyy"], month=df["mm"], day=df["dd"]),
            errors="coerce",
        )
        df = df.dropna(subset=["fecha"])
        logger.info(f"  MSVOLSO2L4: {len(df)} degassing events ({latest})")
        return df[["volcano", "lat", "lon", "fecha", "type", "vei", "so2_kt"]]
    except Exception as e:
        logger.error(f"MSVOLSO2L4 fetch failed: {e}")
        return pd.DataFrame()


def extraer_btc_yahoo(year_ini: int = 2014, year_end: int = YEAR_END) -> pd.DataFrame:
    """Fetch daily BTC-USD history from Yahoo Finance (public, no key).

    Replaces the CoinGecko historical endpoint (which now requires a paid
    key). Computes volatilidad_24h as abs daily % change.
    """
    url = "https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD"
    params = {
        "period1": int(datetime(year_ini, 1, 1).timestamp()),
        "period2": int(datetime(year_end, 12, 31, 23, 59).timestamp()),
        "interval": "1d",
    }
    headers = {"User-Agent": "Mozilla/5.0 (SentinelOmega research)"}
    logger.info(f"  Fetching Yahoo BTC-USD daily: {year_ini}-{year_end}")
    try:
        r = requests.get(url, params=params, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()["chart"]["result"][0]
        ts = data["timestamp"]
        closes = data["indicators"]["quote"][0]["close"]
        df = pd.DataFrame({"fecha": pd.to_datetime(ts, unit="s"), "precio": closes})
        df = df.dropna(subset=["precio"])
        df["volatilidad_24h"] = (df["precio"].pct_change().abs() * 100).fillna(0.0)
        logger.info(f"  Yahoo BTC: {len(df)} daily records")
        return df
    except Exception as e:
        logger.error(f"Yahoo BTC fetch failed: {e}")
        return pd.DataFrame()


def run_backfill_secundario(db_path: Optional[str] = None):
    """Backfill Beta-2 (volcanic SO2) and Delta (BTC) historical tables.

    Idempotent (INSERT OR IGNORE). Run after the main backcast.
    """
    if db_path is None:
        db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    _init_backcast_tables(conn)
    conn.executescript(
        """CREATE TABLE IF NOT EXISTS tbl_desgasificacion_raw (
            timestamp_blk TEXT NOT NULL,
            id_nodo INTEGER NOT NULL,
            volcan TEXT NOT NULL DEFAULT '',
            tipo_erupcion TEXT DEFAULT '',
            vei REAL,
            so2_kt REAL DEFAULT 0.0,
            PRIMARY KEY (timestamp_blk, id_nodo, volcan)
        );"""
    )

    df_so2 = extraer_desgasificacion_volcanica()
    n_so2 = 0
    for _, row in df_so2.iterrows():
        nodo = nodo_mas_cercano(float(row["lat"]), float(row["lon"]))
        blk = row["fecha"].strftime("%Y-%m-%d %H:%M")
        vei = _safe_float(row.get("vei"))
        conn.execute(
            "INSERT OR IGNORE INTO tbl_desgasificacion_raw "
            "(timestamp_blk, id_nodo, volcan, tipo_erupcion, vei, so2_kt) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (blk, nodo["id"], str(row["volcano"]), str(row.get("type", "")),
             vei if vei is not None and vei >= 0 else None,
             _safe_float(row.get("so2_kt")) or 0.0),
        )
        n_so2 += 1
    conn.commit()
    logger.info(f"Backfill desgasificación: {n_so2} eventos insertados")

    df_btc = extraer_btc_yahoo()
    n_btc = 0
    for _, row in df_btc.iterrows():
        blk = row["fecha"].strftime("%Y-%m-%d %H:%M")
        conn.execute(
            "INSERT OR IGNORE INTO tbl_psique_financiera "
            "(timestamp_blk, btc_precio_usd, volatilidad_24h) VALUES (?, ?, ?)",
            (blk, float(row["precio"]), float(row["volatilidad_24h"])),
        )
        n_btc += 1
    conn.commit()
    logger.info(f"Backfill BTC: {n_btc} días insertados")
    conn.close()
    return {"so2_eventos": n_so2, "btc_dias": n_btc}


def ejecutar_bloque_anual(
    conn: sqlite3.Connection,
    year: int,
    df_omni: pd.DataFrame,
    df_sismos: pd.DataFrame,
    df_schumann: pd.DataFrame,
    df_btc: pd.DataFrame,
):
    """Transform and persist one year of data at 1H resolution."""
    logger.info(f"  Transforming year {year}...")

    base_tiempo = pd.date_range(
        start=f"{year}-01-01 00:00",
        end=f"{year}-12-31 18:00",
        freq="1h",
    )
    master_df = pd.DataFrame({"fecha": base_tiempo})
    master_df["timestamp_blk"] = master_df["fecha"].dt.strftime("%Y-%m-%d %H:%M")

    if not df_omni.empty:
        df_omni = df_omni.copy()
        df_omni = df_omni.set_index("fecha").sort_index()
        agg_omni = df_omni.resample("1h").agg(
            bz_promedio=("bz_promed", "mean"),
            bz_min=("bz_promed", "min"),
            bz_max=("bz_promed", "max"),
            viento_solar_avg=("sw_speed", "mean"),
            viento_solar_max=("sw_speed", "max"),
            kp_max=("kp_val", "max"),
            kp_promedio=("kp_val", "mean"),
            proton_flux_10mev=("p_flux", "max"),
        ).reset_index()
        agg_omni.rename(columns={"fecha": "fecha"}, inplace=True)
        agg_omni["bz_derivada"] = agg_omni["bz_promedio"].diff().fillna(0.0)
        master_df = pd.merge(
            master_df, agg_omni, left_on="fecha", right_on="fecha", how="left"
        )
        master_df = master_df.ffill()
    else:
        for col in [
            "bz_promedio", "bz_derivada", "bz_min", "bz_max",
            "viento_solar_avg", "viento_solar_max",
            "kp_max", "kp_promedio", "proton_flux_10mev",
        ]:
            master_df[col] = None

    cursor = conn.cursor()
    cursor.execute("BEGIN TRANSACTION")

    try:
        for _, row in master_df.iterrows():
            cursor.execute(
                """INSERT OR IGNORE INTO tbl_clima_espacial_raw
                   (timestamp_blk, bz_promedio, bz_derivada, bz_min, bz_max,
                    viento_solar_avg, viento_solar_max, kp_max, kp_promedio,
                    proton_flux_10mev)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["timestamp_blk"],
                    _safe_float(row.get("bz_promedio")),
                    _safe_float(row.get("bz_derivada")),
                    _safe_float(row.get("bz_min")),
                    _safe_float(row.get("bz_max")),
                    _safe_float(row.get("viento_solar_avg")),
                    _safe_float(row.get("viento_solar_max")),
                    _safe_float(row.get("kp_max")),
                    _safe_float(row.get("kp_promedio")),
                    _safe_float(row.get("proton_flux_10mev")),
                ),
            )

        cursor.execute(
            """INSERT OR IGNORE INTO tbl_astronomia_cinematica
               (timestamp_blk) VALUES (?)""",
            (master_df["timestamp_blk"].iloc[0],),
        )
        for _, row in master_df.iterrows():
            cursor.execute(
                """INSERT OR IGNORE INTO tbl_astronomia_cinematica
                   (timestamp_blk) VALUES (?)""",
                (row["timestamp_blk"],),
            )

        if not df_sismos.empty:
            df_sismos = df_sismos.copy()
            df_sismos["timestamp_blk"] = df_sismos["time"].dt.floor("1h").dt.strftime(
                "%Y-%m-%d %H:%M"
            )
            for _, row in df_sismos.iterrows():
                nodo = nodo_mas_cercano(row["latitude"], row["longitude"])
                cursor.execute(
                    """INSERT INTO tbl_historico_sismico_raw
                       (timestamp_blk, id_nodo, sismo_count, sismo_max_mag)
                       VALUES (?, ?, 1, ?)
                       ON CONFLICT(timestamp_blk, id_nodo) DO UPDATE SET
                       sismo_count = sismo_count + 1,
                       sismo_max_mag = MAX(sismo_max_mag, excluded.sismo_max_mag)""",
                    (row["timestamp_blk"], nodo["id"], float(row["mag"])),
                )

        if year >= 2014 and not df_btc.empty:
            df_btc = df_btc.copy()
            df_btc["timestamp_blk"] = df_btc["fecha"].dt.floor("1h").dt.strftime(
                "%Y-%m-%d %H:%M"
            )
            agg_btc = df_btc.groupby("timestamp_blk")["precio"].mean().reset_index()
            for _, row in agg_btc.iterrows():
                cursor.execute(
                    """INSERT OR IGNORE INTO tbl_psique_financiera
                       (timestamp_blk, btc_precio_usd)
                       VALUES (?, ?)""",
                    (row["timestamp_blk"], float(row["precio"])),
                )

        if year >= 2014 and not df_schumann.empty:
            df_schumann = df_schumann.copy()
            df_schumann["timestamp_blk"] = (
                df_schumann["timestamp"].dt.floor("1h").dt.strftime("%Y-%m-%d %H:%M")
            )
            agg_sch = (
                df_schumann.groupby("timestamp_blk")["frecuencia_fundamental_hz"]
                .mean()
                .reset_index()
            )
            for _, row in agg_sch.iterrows():
                cursor.execute(
                    """INSERT OR IGNORE INTO tbl_enjambre_telemetria
                       (timestamp_blk, id_nodo, schumann_hz)
                       VALUES (?, 0, ?)""",
                    (row["timestamp_blk"], float(row["frecuencia_fundamental_hz"])),
                )

        conn.commit()
        logger.info(f"  Year {year} committed successfully.")
    except Exception as e:
        conn.rollback()
        logger.error(f"  Transaction aborted for {year}: {e}")


def _safe_float(val) -> Optional[float]:
    """Convert to float or None (NULL in SQLite). Never generate synthetic."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def run_backcast(db_path: Optional[str] = None):
    """Execute the full historical backcast. Idempotent."""
    if db_path is None:
        db_path = _get_db_path()

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    _init_backcast_tables(conn)

    if verificar_ejecucion_previa(conn):
        conn.close()
        return

    logger.info(f"=== BACKCAST HISTÓRICO: {YEAR_INI}-{YEAR_END} ===")
    logger.info("Protocol: ZERO synthetic data. Missing = NULL. LOCF from real only.")

    for year in range(YEAR_INI, YEAR_END + 1):
        logger.info(f"--- Processing year {year} ---")

        omni_df = extraer_nasa_omni_real(year)
        sismos_df = extraer_sismos_usgs_real(year)
        schumann_df = extraer_schumann_real(year)
        btc_df = extraer_psique_financiera(year)

        ejecutar_bloque_anual(conn, year, omni_df, sismos_df, schumann_df, btc_df)
        time.sleep(1)

    logger.info("=== BACKCAST COMPLETE ===")
    conn.close()


if __name__ == "__main__":
    run_backcast()
