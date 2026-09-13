"""
Sentinel Omega — Data Repository

CRUD operations for all tables. Thread-safe via per-call connections.
All timestamps are Unix epoch floats (time.time()).
"""

import json
import logging
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sentinel_omega.infrastructure.database.schema import get_connection

logger = logging.getLogger(__name__)


class SentinelRepository:

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        self._conn = None
        # Cache column names per table (thread-safe dict)
        self._cols_cache: Dict[str, List[str]] = {}

    @property
    def _conn_safe(self) -> sqlite3.Connection:
        """Thread-safe connection: read-only fast path, no DDL."""
        import threading
        if not hasattr(self, "_tls"):
            import threading as _th
            self._tls = _th.local()
        if hasattr(self._tls, "conn") and self._tls.conn is not None:
            return self._tls.conn
        from pathlib import Path as _P
        # __file__ = sentinel_omega/infrastructure/database/repository.py
        # Need to go up 4 levels: database -> infrastructure -> sentinel_omega -> workspace -> data/
        db = self._db_path or str(_P(__file__).parent.parent.parent.parent / "data" / "SENTINEL_OMEGA_PRO.db")
        # Direct connect without init_database (evita database is locked en dashboard)
        # WAL + busy_timeout para concurrencia con launcher
        conn = sqlite3.connect(str(db), timeout=30.0, check_same_thread=False, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-8000")
            conn.row_factory = sqlite3.Row
        except Exception:
            pass
        self._tls.conn = conn
        return conn

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        # Try thread-safe conn first
        try:
            return self._conn_safe.execute(sql, params)
        except Exception:
            # Fallback to legacy _conn if exists
            if self._conn is not None:
                return self._conn_safe.execute(sql, params)
            raise

    def _executemany(self, sql: str, params_list: List[tuple]) -> None:
        conn = self._conn_safe
        conn.executemany(sql, params_list)
        conn.commit()

    # ── Precursores Cósmicos ──────────────────────────────────────

    def insert_precursor_cosmico(
        self,
        bz: float = 0.0,
        viento: float = 0.0,
        protones: float = 0.0,
        kp: float = 0.0,
        lod_ms: float = 0.0,
        schumann_hz: float = 7.83,
        schumann_activity: float = 0.0,
        fase_lunar: float = 0.0,
        presion_hpa: float = 1013.0,
        fantasma: float = 0.0,
        nivel_riesgo: str = "LOW",
        timestamp: Optional[float] = None,
    ) -> int:
        ts = timestamp or time.time()
        cur = self._execute(
            """INSERT INTO TBL_PRECURSORES_COSMICOS
            (timestamp, bz_nT, viento_km_s, protones, kp, lod_ms,
             schumann_hz, schumann_activity, fase_lunar,
             presion_hpa, fantasma, nivel_riesgo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, bz, viento, protones, kp, lod_ms,
             schumann_hz, schumann_activity, fase_lunar,
             presion_hpa, fantasma, nivel_riesgo),
        )
        self._conn_safe.commit()
        return cur.lastrowid

    def get_precursores_cosmicos(
        self, limit: int = 100, min_riesgo: Optional[str] = None
    ) -> List[Dict]:
        if min_riesgo:
            rows = self._execute(
                """SELECT * FROM TBL_PRECURSORES_COSMICOS
                WHERE nivel_riesgo = ? ORDER BY timestamp DESC LIMIT ?""",
                (min_riesgo, limit),
            ).fetchall()
        else:
            rows = self._execute(
                "SELECT * FROM TBL_PRECURSORES_COSMICOS ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(zip(self._col_names("TBL_PRECURSORES_COSMICOS"), r)) for r in rows]

    def get_ultima_prediccion_por_bot(self) -> List[Dict]:
        """Última predicción real (fase='viva') de cada bot, incluido 'padre'.
        Fuente: viva_real (vista sobre TBL_JUEZ_AUDITORIA, solo fase='viva'),
        alimentada por register_cycle_predictions() en cada ciclo del launcher.
        """
        rows = self._execute(
            """SELECT bot_name, prediccion, confianza, timestamp, detalles_json
               FROM viva_real
               WHERE (bot_name, timestamp) IN (
                   SELECT bot_name, MAX(timestamp) FROM viva_real GROUP BY bot_name
               )
               ORDER BY bot_name"""
        ).fetchall()
        cols = ["bot_name", "prediccion", "confianza", "timestamp", "detalles_json"]
        return [dict(zip(cols, r)) for r in rows]

    # ── Nodos Topología ───────────────────────────────────────────

    def upsert_nodo(
        self,
        node_id: int,
        nombre: str,
        lat: float,
        lon: float,
        tipo: str = "real",
        conductividad: float = 0.0,
        energia: float = 0.0,
        saturacion: float = 0.0,
        region: str = "",
    ) -> None:
        self._execute(
            """INSERT OR REPLACE INTO TBL_NODOS_TOPOLOGIA
            (node_id, nombre, lat, lon, tipo, conductividad_telurica,
             energia_acumulada, saturacion, region, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (node_id, nombre, lat, lon, tipo, conductividad,
             energia, saturacion, region),
        )
        self._conn_safe.commit()

    def bulk_upsert_nodos(self, nodos: List[Dict]) -> int:
        self._executemany(
            """INSERT OR REPLACE INTO TBL_NODOS_TOPOLOGIA
            (node_id, nombre, lat, lon, tipo, conductividad_telurica,
             energia_acumulada, saturacion, region, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            [
                (n["node_id"], n["nombre"], n["lat"], n["lon"],
                 n.get("tipo", "real"), n.get("conductividad", 0.0),
                 n.get("energia", 0.0), n.get("saturacion", 0.0),
                 n.get("region", ""))
                for n in nodos
            ],
        )
        return len(nodos)

    def get_nodos(self, tipo: Optional[str] = None) -> List[Dict]:
        if tipo:
            rows = self._execute(
                "SELECT * FROM TBL_NODOS_TOPOLOGIA WHERE tipo = ? ORDER BY node_id",
                (tipo,),
            ).fetchall()
        else:
            rows = self._execute(
                "SELECT * FROM TBL_NODOS_TOPOLOGIA ORDER BY node_id"
            ).fetchall()
        return [dict(zip(self._col_names("TBL_NODOS_TOPOLOGIA"), r)) for r in rows]

    def update_nodo_energy(self, node_id: int, energia: float, saturacion: float) -> None:
        self._execute(
            """UPDATE TBL_NODOS_TOPOLOGIA
            SET energia_acumulada = ?, saturacion = ?, updated_at = datetime('now')
            WHERE node_id = ?""",
            (energia, saturacion, node_id),
        )
        self._conn_safe.commit()

    # ── Histórico Sísmico ─────────────────────────────────────────

    def insert_sismo(
        self,
        event_id: str,
        timestamp: float,
        lat: float,
        lon: float,
        magnitude: float,
        depth_km: float = 0.0,
        mag_type: str = "",
        region: str = "",
        source: str = "USGS",
    ) -> None:
        self._execute(
            """INSERT OR IGNORE INTO TBL_HISTORICO_SISMICO
            (event_id, timestamp, lat, lon, depth_km, magnitude,
             mag_type, region, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, timestamp, lat, lon, depth_km, magnitude,
             mag_type, region, source),
        )
        self._conn_safe.commit()

    def bulk_insert_sismos(self, sismos: List[Dict]) -> int:
        before = self._execute(
            "SELECT COUNT(*) FROM TBL_HISTORICO_SISMICO"
        ).fetchone()[0]
        self._executemany(
            """INSERT OR IGNORE INTO TBL_HISTORICO_SISMICO
            (event_id, timestamp, lat, lon, depth_km, magnitude,
             mag_type, region, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (s["event_id"], s["timestamp"], s["lat"], s["lon"],
                 s.get("depth_km", 0.0), s["magnitude"],
                 s.get("mag_type", ""), s.get("region", ""),
                 s.get("source", "USGS"))
                for s in sismos
            ],
        )
        after = self._execute(
            "SELECT COUNT(*) FROM TBL_HISTORICO_SISMICO"
        ).fetchone()[0]
        return after - before

    def get_sismos(
        self,
        min_magnitude: float = 0.0,
        limit: int = 1000,
        region: Optional[str] = None,
    ) -> List[Dict]:
        if region:
            rows = self._execute(
                """SELECT * FROM TBL_HISTORICO_SISMICO
                WHERE magnitude >= ? AND region LIKE ?
                ORDER BY timestamp DESC LIMIT ?""",
                (min_magnitude, f"%{region}%", limit),
            ).fetchall()
        else:
            rows = self._execute(
                """SELECT * FROM TBL_HISTORICO_SISMICO
                WHERE magnitude >= ? ORDER BY timestamp DESC LIMIT ?""",
                (min_magnitude, limit),
            ).fetchall()
        return [dict(zip(self._col_names("TBL_HISTORICO_SISMICO"), r)) for r in rows]

    def count_sismos(self, min_magnitude: float = 0.0) -> int:
        return self._execute(
            "SELECT COUNT(*) FROM TBL_HISTORICO_SISMICO WHERE magnitude >= ?",
            (min_magnitude,),
        ).fetchone()[0]

    # ── Detecciones ───────────────────────────────────────────────

    def insert_deteccion(
        self,
        tipo: str,
        display_name: str,
        confidence: float,
        station: str = "",
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        values: Optional[Dict] = None,
        wall_name: str = "",
        cycle_id: Optional[int] = None,
        timestamp: Optional[float] = None,
    ) -> int:
        ts = timestamp or time.time()
        cur = self._execute(
            """INSERT INTO TBL_DETECCIONES
            (timestamp, cycle_id, tipo, display_name, station, lat, lon,
             confidence, values_json, wall_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, cycle_id, tipo, display_name, station, lat, lon,
             confidence, json.dumps(values or {}), wall_name),
        )
        self._conn_safe.commit()
        return cur.lastrowid

    def get_detecciones(
        self, limit: int = 100, tipo: Optional[str] = None
    ) -> List[Dict]:
        if tipo:
            rows = self._execute(
                """SELECT * FROM TBL_DETECCIONES
                WHERE tipo = ? ORDER BY timestamp DESC LIMIT ?""",
                (tipo, limit),
            ).fetchall()
        else:
            rows = self._execute(
                "SELECT * FROM TBL_DETECCIONES ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(zip(self._col_names("TBL_DETECCIONES"), r))
            d["values"] = json.loads(d.pop("values_json", "{}"))
            result.append(d)
        return result

    # ── Ciclos ────────────────────────────────────────────────────

    def insert_ciclo(
        self,
        geo_signal: str = "no_signal",
        geo_confidence: float = 0.0,
        geo_consensus: bool = False,
        fantasma: float = 0.0,
        nivel_riesgo: str = "LOW",
        precursors_count: int = 0,
        precursor_types: Optional[List[str]] = None,
        muro_walls_active: int = 0,
        muro_breach: bool = False,
        alerts_dispatched: int = 0,
        timestamp: Optional[float] = None,
    ) -> int:
        ts = timestamp or time.time()
        types_json = json.dumps(precursor_types or [])
        cur = self._execute(
            """INSERT INTO TBL_CICLOS
            (timestamp, geo_signal, geo_confidence, geo_consensus,
             fantasma, nivel_riesgo, precursors_count, precursor_types,
             muro_walls_active, muro_breach, alerts_dispatched)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, geo_signal, geo_confidence, int(geo_consensus),
             fantasma, nivel_riesgo, precursors_count, types_json,
             muro_walls_active, int(muro_breach), alerts_dispatched),
        )
        self._conn_safe.commit()
        return cur.lastrowid

    def get_ciclos(self, limit: int = 50) -> List[Dict]:
        rows = self._execute(
            "SELECT * FROM TBL_CICLOS ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(zip(self._col_names("TBL_CICLOS"), r)) for r in rows]

    # ── Muro de los 5 Eventos ────────────────────────────────────

    def insert_muro_evento(
        self,
        walls_active: int,
        correlation_score: float,
        muro_breach: bool,
        risk_label: str,
        wall_states: Dict[str, bool],
        active_types: List[str],
        cycle_id: Optional[int] = None,
        timestamp: Optional[float] = None,
    ) -> int:
        ts = timestamp or time.time()
        cur = self._execute(
            """INSERT INTO TBL_MURO_EVENTOS
            (timestamp, cycle_id, walls_active, correlation_score,
             muro_breach, risk_label,
             wall_geofisico, wall_atmosferico, wall_oceanico,
             wall_solar, wall_financiero, active_types_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, cycle_id, walls_active, correlation_score,
             int(muro_breach), risk_label,
             int(wall_states.get("GEOFÍSICO", False)),
             int(wall_states.get("ATMOSFÉRICO", False)),
             int(wall_states.get("OCEÁNICO", False)),
             int(wall_states.get("SOLAR/GEOMAGNÉTICO", False)),
             int(wall_states.get("FINANCIERO/SOCIAL", False)),
             json.dumps(active_types)),
        )
        self._conn_safe.commit()
        return cur.lastrowid

    def get_muro_breaches(self, limit: int = 50) -> List[Dict]:
        rows = self._execute(
            """SELECT * FROM TBL_MURO_EVENTOS
            WHERE muro_breach = 1 ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(zip(self._col_names("TBL_MURO_EVENTOS"), r))
            d["active_types"] = json.loads(d.pop("active_types_json", "[]"))
            result.append(d)
        return result

    def get_muro_all(self, limit: int = 100) -> List[Dict]:
        rows = self._execute(
            "SELECT * FROM TBL_MURO_EVENTOS ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(zip(self._col_names("TBL_MURO_EVENTOS"), r))
            d["active_types"] = json.loads(d.pop("active_types_json", "[]"))
            result.append(d)
        return result

    # ── Analytics ─────────────────────────────────────────────────

    def cimatica_top_patrones(self, limit: int = 20) -> "List[Dict]":
        """Top patrones por frecuencia (dashboard cimatica)."""
        try:
            cur = self.conn.execute(
                "SELECT patron_id, clave, frecuencia, event_class, ambito, id_nodo, primera_vez, ultima_vez "
                "FROM tbl_cimatica_patrones ORDER BY frecuencia DESC, ultima_vez DESC LIMIT ?", (limit,)
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []

    def cimatica_stats(self) -> "Dict[str, Any]":
        """Resumen cimatica."""
        try:
            total = self.conn.execute("SELECT COUNT(*) FROM tbl_cimatica_patrones").fetchone()[0]
            consistentes = self.conn.execute("SELECT COUNT(*) FROM tbl_cimatica_patrones WHERE frecuencia>=3").fetchone()[0]
            por_clase = self.conn.execute("SELECT event_class, COUNT(*) as n FROM tbl_cimatica_patrones GROUP BY event_class ORDER BY n DESC LIMIT 10").fetchall()
            return {"total": total, "consistentes": consistentes, "por_clase": [dict(r) for r in por_clase]}
        except Exception:
            return {"total": 0, "consistentes": 0, "por_clase": []}

    def fantasma_timeline(self, limit: int = 50) -> "List[Dict]":
        """Historial fantasma para timeline."""
        try:
            cur = self.conn.execute("SELECT ts, fantasma, nivel FROM tbl_salud_sistema ORDER BY ts DESC LIMIT ?", (limit,))
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []

    def fantasma_component_breakdown(self, limit: int = 50) -> List[Dict]:
        rows = self._execute(
            """SELECT timestamp, bz_nT, viento_km_s, schumann_hz,
                      schumann_activity, kp, lod_ms, presion_hpa,
                      fase_lunar, protones, fantasma, nivel_riesgo
               FROM TBL_PRECURSORES_COSMICOS
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        cols = ["timestamp", "bz_nT", "viento_km_s", "schumann_hz",
                "schumann_activity", "kp", "lod_ms", "presion_hpa",
                "fase_lunar", "protones", "fantasma", "nivel_riesgo"]
        return [dict(zip(cols, r)) for r in rows]

    def risk_distribution(self) -> Dict[str, int]:
        rows = self._execute(
            """SELECT nivel_riesgo, COUNT(*) as cnt
               FROM TBL_PRECURSORES_COSMICOS
               GROUP BY nivel_riesgo"""
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def precursor_type_frequency(self) -> Dict[str, int]:
        rows = self._execute(
            """SELECT tipo, COUNT(*) as cnt
               FROM TBL_DETECCIONES
               GROUP BY tipo ORDER BY cnt DESC"""
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def precursor_confidence_stats(self) -> Dict[str, Dict[str, float]]:
        rows = self._execute(
            """SELECT tipo, AVG(confidence), MIN(confidence), MAX(confidence), COUNT(*)
               FROM TBL_DETECCIONES
               GROUP BY tipo"""
        ).fetchall()
        return {
            r[0]: {"avg": r[1], "min": r[2], "max": r[3], "count": r[4]}
            for r in rows
        }

    def wall_activation_history(self, limit: int = 100) -> List[Dict]:
        rows = self._execute(
            """SELECT timestamp, wall_geofisico, wall_atmosferico,
                      wall_oceanico, wall_solar, wall_financiero,
                      walls_active, correlation_score, muro_breach
               FROM TBL_MURO_EVENTOS
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        cols = ["timestamp", "wall_geofisico", "wall_atmosferico",
                "wall_oceanico", "wall_solar", "wall_financiero",
                "walls_active", "correlation_score", "muro_breach"]
        return [dict(zip(cols, r)) for r in rows]

    def seismic_magnitude_distribution(self, bins: int = 20) -> List[Dict]:
        rows = self._execute(
            """SELECT CAST(magnitude * 2 AS INT) / 2.0 AS mag_bin,
                      COUNT(*) as cnt
               FROM TBL_HISTORICO_SISMICO
               GROUP BY mag_bin ORDER BY mag_bin"""
        ).fetchall()
        return [{"magnitude": r[0], "count": r[1]} for r in rows]

    def seismic_by_region(self, min_magnitude: float = 4.0, limit: int = 20) -> List[Dict]:
        rows = self._execute(
            """SELECT region, COUNT(*) as cnt, AVG(magnitude) as avg_mag,
                      MAX(magnitude) as max_mag
               FROM TBL_HISTORICO_SISMICO
               WHERE magnitude >= ? AND region != ''
               GROUP BY region ORDER BY cnt DESC LIMIT ?""",
            (min_magnitude, limit),
        ).fetchall()
        return [
            {"region": r[0], "count": r[1], "avg_magnitude": r[2], "max_magnitude": r[3]}
            for r in rows
        ]

    def seismic_depth_vs_magnitude(
        self,
        min_magnitude: float = 4.0,
        limit: int = 500,
    ) -> List[Dict]:
        rows = self._execute(
            """SELECT depth_km, magnitude, lat, lon, region
               FROM TBL_HISTORICO_SISMICO
               WHERE magnitude >= ?
               ORDER BY timestamp DESC LIMIT ?""",
            (min_magnitude, limit),
        ).fetchall()
        return [
            {"depth_km": r[0], "magnitude": r[1], "lat": r[2], "lon": r[3], "region": r[4]}
            for r in rows
        ]

    def node_saturation_ranking(
        self,
        limit: int = 25,
        region: Optional[str] = None,
    ) -> List[Dict]:
        if region:
            rows = self._execute(
                """SELECT node_id, nombre, tipo, saturacion, energia_acumulada,
                          conductividad_telurica, region
                   FROM TBL_NODOS_TOPOLOGIA
                   WHERE saturacion > 0 AND region = ?
                   ORDER BY saturacion DESC LIMIT ?""",
                (region, limit),
            ).fetchall()
        else:
            rows = self._execute(
                """SELECT node_id, nombre, tipo, saturacion, energia_acumulada,
                          conductividad_telurica, region
                   FROM TBL_NODOS_TOPOLOGIA
                   WHERE saturacion > 0
                   ORDER BY saturacion DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {"node_id": r[0], "nombre": r[1], "tipo": r[2], "saturacion": r[3],
             "energia": r[4], "conductividad": r[5], "region": r[6]}
            for r in rows
        ]

    def cycle_alert_rate(self) -> Dict[str, Any]:
        total = self._execute("SELECT COUNT(*) FROM TBL_CICLOS").fetchone()[0]
        alerts = self._execute(
            "SELECT COUNT(*) FROM TBL_CICLOS WHERE geo_signal = 'alert'"
        ).fetchone()[0]
        breaches = self._execute(
            "SELECT COUNT(*) FROM TBL_CICLOS WHERE muro_breach = 1"
        ).fetchone()[0]
        avg_fantasma = self._execute(
            "SELECT AVG(fantasma) FROM TBL_CICLOS"
        ).fetchone()[0]
        return {
            "total_cycles": total,
            "alert_cycles": alerts,
            "breach_cycles": breaches,
            "alert_rate": alerts / max(total, 1),
            "breach_rate": breaches / max(total, 1),
            "avg_fantasma": avg_fantasma or 0.0,
        }

    def schumann_trend(self, limit: int = 100) -> List[Dict]:
        rows = self._execute(
            """SELECT timestamp, schumann_hz, schumann_activity
               FROM TBL_PRECURSORES_COSMICOS
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {"timestamp": r[0], "schumann_hz": r[1], "schumann_activity": r[2]}
            for r in rows
        ]

    # ── v5: Cobertura Satelital alfa2 ────────────────────────────────

    def insert_cobertura_satelital(
        self,
        timestamp_blk: str,
        zona: str,
        coverage_score: float = 0.0,
        thermal_anomalies: int = 0,
        clear_passes: int = 0,
        total_passes: int = 0,
        revisit_days: float = 0.0,
    ) -> None:
        """Persiste datos de cobertura ESA Sentinel para una zona y ciclo."""
        self._execute(
            "INSERT OR REPLACE INTO tbl_cobertura_satelital "
            "(timestamp_blk, zona, coverage_score, thermal_anomalies, "
            " clear_passes, total_passes, revisit_days) "
            "VALUES (?,?,?,?,?,?,?)",
            (timestamp_blk, zona, coverage_score, thermal_anomalies,
             clear_passes, total_passes, revisit_days),
        )
        self._conn_safe.commit()

    def insert_delta_cross(
        self,
        timestamp_blk: str,
        cross_coupling: float = 0.0,
        geomagnetic_coupling: float = 0.0,
        schumann_coupling: float = 0.0,
        sentiment_coupling: float = 0.0,
        composite_score: float = 0.0,
        regime_label: str = "",
        confidence: float = 0.0,
        data_completeness: float = 0.0,
        geo_kp_max_3d: float = None,
        geo_storm_active: int = 0,
        geo_schumann_deviation: float = None,
    ) -> None:
        """Persiste el resultado delta_enriched de un ciclo."""
        self._execute(
            "INSERT OR REPLACE INTO tbl_delta_cross "
            "(timestamp_blk, cross_coupling, geomagnetic_coupling, "
            " schumann_coupling, sentiment_coupling, composite_score, "
            " regime_label, confidence, data_completeness, "
            " geo_kp_max_3d, geo_storm_active, geo_schumann_deviation) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (timestamp_blk, cross_coupling, geomagnetic_coupling,
             schumann_coupling, sentiment_coupling, composite_score,
             regime_label, confidence, data_completeness,
             geo_kp_max_3d, geo_storm_active, geo_schumann_deviation),
        )
        self._conn_safe.commit()

    # ── Helpers ───────────────────────────────────────────────────

    def _col_names(self, table: str) -> List[str]:
        cur = self._execute(f"PRAGMA table_info({table})")
        return [row[1] for row in cur.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        if hasattr(self, "_tls") and hasattr(self._tls, "conn") and self._tls.conn is not None:
            try:
                self._tls.conn.close()
            except Exception:
                pass
            self._tls.conn = None
