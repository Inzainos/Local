"""
Legacy Data Loader — imports from CEREBRO_GOD.db and TITAN_MEMORY.db
for SNT backtesting and historical analysis.

CEREBRO_GOD.db schema:
  - historicos: 11,374 rows (1994–2026), daily sismo_max_mag / promedio_kp / promedio_tomsk / so2 / co / temp / presion
  - bitacora: 1,306 rows, real-time monitoring (v_fantasma, kp, bz, tomsk, wind, riesgo_ia, energia_latente)

TITAN_MEMORY.db schema:
  - MELATE/REVANCHA/REVANCHITA/CHISPAZO/TRIS/RETRO: full historical draws (r1–r8)
  - weights_{game}: neural weights per number
  - predictions_{game}: backtesting results
"""

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class LegacyDataLoader:

    def __init__(self, db_path: str):
        self._db_path = Path(db_path)
        if not self._db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    def list_tables(self) -> List[str]:
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    def table_info(self, table: str) -> Dict[str, Any]:
        conn = self._connect()
        try:
            cur = conn.execute(f'PRAGMA table_info("{table}")')
            columns = [(row[1], row[2]) for row in cur.fetchall()]
            cur = conn.execute(f'SELECT COUNT(*) FROM "{table}"')
            count = cur.fetchone()[0]
            return {"table": table, "columns": columns, "row_count": count}
        finally:
            conn.close()

    def load_table(
        self,
        table: str,
        limit: Optional[int] = None,
        where: Optional[str] = None,
    ) -> pd.DataFrame:
        conn = self._connect()
        try:
            query = f'SELECT * FROM "{table}"'
            if where:
                query += f" WHERE {where}"
            if limit:
                query += f" LIMIT {limit}"
            return pd.read_sql_query(query, conn)
        finally:
            conn.close()

    def load_historicos(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load CEREBRO_GOD historicos table with optional date filtering."""
        conn = self._connect()
        try:
            query = "SELECT * FROM historicos"
            conditions = []
            if start_date:
                conditions.append(f"fecha >= '{start_date}'")
            if end_date:
                conditions.append(f"fecha <= '{end_date}'")
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY fecha"

            df = pd.read_sql_query(query, conn)
            if "fecha" in df.columns:
                df["fecha"] = pd.to_datetime(df["fecha"])
            logger.info(f"Loaded {len(df)} historicos records")
            return df
        finally:
            conn.close()

    def load_bitacora(self) -> pd.DataFrame:
        """Load CEREBRO_GOD bitacora (real-time monitoring log)."""
        conn = self._connect()
        try:
            df = pd.read_sql_query(
                "SELECT * FROM bitacora ORDER BY timestamp", conn
            )
            if "fecha" in df.columns:
                df["fecha"] = pd.to_datetime(df["fecha"])
            logger.info(f"Loaded {len(df)} bitacora records")
            return df
        finally:
            conn.close()

    def load_lottery_game(self, game: str) -> pd.DataFrame:
        """Load a lottery game's draw history from TITAN_MEMORY."""
        game = game.upper()
        conn = self._connect()
        try:
            df = pd.read_sql_query(f'SELECT * FROM "{game}" ORDER BY id', conn)
            logger.info(f"Loaded {len(df)} {game} draws")
            return df
        finally:
            conn.close()

    def load_lottery_weights(self, game: str) -> pd.DataFrame:
        """Load neural weights for a lottery game."""
        game = game.lower()
        conn = self._connect()
        try:
            df = pd.read_sql_query(
                f"SELECT * FROM weights_{game} ORDER BY weight DESC", conn
            )
            return df
        finally:
            conn.close()

    def historicos_to_snt_input(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, np.ndarray]:
        """
        Convert historicos to arrays suitable for SNT satellization fitting.
        Returns dict with kp, tomsk, sismo, so2, co, temp, presion arrays.
        """
        df = self.load_historicos(start_date, end_date)
        return {
            "fecha": df["fecha"].values if "fecha" in df.columns else np.array([]),
            "sismo_max_mag": df["sismo_max_mag"].values.astype(float),
            "kp": df["promedio_kp"].values.astype(float),
            "tomsk": df["promedio_tomsk"].values.astype(float),
            "so2": df["so2_mass"].values.astype(float),
            "co": df["co_flux"].values.astype(float),
            "temp": df["temp_max"].values.astype(float),
            "presion": df["presion_atm"].values.astype(float),
        }

    # ── SENTINEL_OMEGA_PRO.db loaders ────────────────────────────────

    def load_fact_sismos(
        self,
        min_mag: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Load seismic events from fact_sismos (424K+ rows)."""
        conn = self._connect()
        try:
            query = "SELECT * FROM fact_sismos"
            if min_mag is not None:
                query += f" WHERE mag >= {min_mag}"
            query += " ORDER BY timestamp_utc"
            if limit:
                query += f" LIMIT {limit}"
            df = pd.read_sql_query(query, conn)
            logger.info(f"Loaded {len(df)} seismic records")
            return df
        finally:
            conn.close()

    def load_fact_clima_espacial(
        self,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Load space weather records from fact_clima_espacial (60K+ rows)."""
        conn = self._connect()
        try:
            query = "SELECT * FROM fact_clima_espacial WHERE timestamp_utc != 'nan'"
            query += " ORDER BY timestamp_utc"
            if limit:
                query += f" LIMIT {limit}"
            df = pd.read_sql_query(query, conn)
            if "timestamp_utc" in df.columns:
                df["timestamp_utc"] = pd.to_datetime(
                    df["timestamp_utc"], errors="coerce"
                )
            logger.info(f"Loaded {len(df)} climate records")
            return df
        finally:
            conn.close()

    def load_backcast_patterns(self) -> pd.DataFrame:
        """Load precursor patterns from backcast analysis (11K+ rows)."""
        conn = self._connect()
        try:
            df = pd.read_sql_query(
                "SELECT * FROM backcast_patterns ORDER BY timestamp_hallazgo",
                conn,
            )
            logger.info(f"Loaded {len(df)} backcast patterns")
            return df
        finally:
            conn.close()

    def load_uvg_nodes(self) -> pd.DataFrame:
        """Load UVG monitoring node definitions (62 nodes)."""
        conn = self._connect()
        try:
            return pd.read_sql_query("SELECT * FROM dim_nodos_uvg", conn)
        finally:
            conn.close()

    def load_padre_audit(self) -> pd.DataFrame:
        """Load Padre model audit trail."""
        conn = self._connect()
        try:
            return pd.read_sql_query(
                "SELECT * FROM tbl_auditoria_padre ORDER BY timestamp_utc",
                conn,
            )
        finally:
            conn.close()

    def load_fact_schumann(self) -> pd.DataFrame:
        """Load Schumann resonance historical measurements (372 rows)."""
        conn = self._connect()
        try:
            df = pd.read_sql_query(
                "SELECT * FROM fact_schumann ORDER BY timestamp_utc", conn
            )
            if "timestamp_utc" in df.columns:
                df["timestamp_utc"] = pd.to_datetime(
                    df["timestamp_utc"], errors="coerce"
                )
            logger.info(f"Loaded {len(df)} Schumann records")
            return df
        finally:
            conn.close()
