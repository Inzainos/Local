"""
Shared Data Pipeline Infrastructure
Normalized ingestion framework used by all layers.
Resolution normalization: all sources → 6h blocks (geodynamic) or configurable.
"""

import sqlite3
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


FILL_SENTINEL = 9999.9


@dataclass
class IngestionConfig:
    source_name: str
    db_path: str
    table_name: str
    resolution_hours: int = 6
    max_gap_hours: int = 3
    fill_value: float = FILL_SENTINEL
    year_start: int = 1994
    year_end: int = 2024


class DataSource(ABC):

    def __init__(self, config: IngestionConfig):
        self.config = config
        self.logger = logging.getLogger(f"pipeline.{config.source_name}")

    @abstractmethod
    def fetch(self, start: datetime, end: datetime) -> pd.DataFrame:
        pass

    @abstractmethod
    def validate(self, df: pd.DataFrame) -> bool:
        pass

    def clean(self, df: pd.DataFrame, fill_cols: List[str]) -> pd.DataFrame:
        for col in fill_cols:
            if col in df.columns:
                df[col] = df[col].replace(self.config.fill_value, np.nan)
                gap_mask = df[col].isna()
                if gap_mask.any():
                    df[col] = df[col].interpolate(
                        method='linear', limit=self.config.max_gap_hours
                    )
        return df

    def store(self, df: pd.DataFrame) -> int:
        db_path = Path(self.config.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        try:
            df.to_sql(self.config.table_name, conn, if_exists='append', index=False)
            count = len(df)
            self.logger.info(f"Stored {count} rows → {self.config.table_name}")
            return count
        finally:
            conn.close()


class DatabaseManager:

    def __init__(self, db_path: str):
        self.db_path = db_path

    def query(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        conn = sqlite3.connect(self.db_path)
        try:
            return pd.read_sql_query(sql, conn, params=params)
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple = ()) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def table_count(self, table: str) -> int:
        df = self.query(f"SELECT COUNT(*) as cnt FROM {table}")
        return int(df['cnt'].iloc[0])
