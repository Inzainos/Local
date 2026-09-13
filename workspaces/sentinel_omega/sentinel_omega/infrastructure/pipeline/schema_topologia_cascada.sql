-- ═══════════════════════════════════════════════════════════════════
-- Schema: tablas de verdad fundamental para topología en cascada
-- v1.0 — 13 ago 2026
-- ═══════════════════════════════════════════════════════════════════
--
-- PROBLEMA QUE RESUELVE:
-- tbl_historico_sismico_raw y tbl_desgasificacion_raw guardan solo
-- id_nodo (ya resuelto) sin el lat/lon original del evento. Cuando
-- geometria_uvg.py se corrige, no hay forma de re-mapear sin volver a
-- descargar todo de la fuente (USGS / NASA MSVOLSO2L4), porque el dato
-- crudo se perdio en el momento de la primera agregacion.
--
-- SOLUCION:
-- Dos tablas nuevas, INMUTABLES, con una fila por evento individual
-- real (no agregado), que SI guardan lat/lon propio + un id externo
-- unico (usgs_id / volcan+fecha) para upsert idempotente. id_nodo aqui
-- es una columna DERIVADA — se puede recalcular en cualquier momento
-- desde lat/lon sin tocar la red nunca mas.
--
-- Las tablas agregadas existentes (tbl_historico_sismico_raw,
-- tbl_desgasificacion_raw) NO cambian de estructura — siguen
-- alimentando Fase 1/1b de entrenamiento sin tocar esa logica. Se
-- reconstruyen (DELETE + INSERT desde las tablas nuevas) cada vez que
-- corre el ETL en cascada, en vez de editarse a mano.
--
-- NUNCA se guarda el "nombre" del lugar como texto aqui — el nombre
-- siempre se resuelve en vivo contra NODOS_POR_ID (geometria_uvg.py /
-- seed_nodos.py), la unica fuente de verdad para nombres. Guardar el
-- nombre en dos lugares es exactamente el patron que causo el bug
-- original.

CREATE TABLE IF NOT EXISTS tbl_eventos_sismicos_fuente (
    usgs_id         TEXT    PRIMARY KEY,   -- id oficial USGS, estable
    time_utc        TEXT    NOT NULL,      -- ISO 8601, timestamp exacto del evento
    lat             REAL    NOT NULL,
    lon             REAL    NOT NULL,
    mag             REAL    NOT NULL,
    id_nodo         INTEGER NOT NULL,      -- DERIVADO — recalculable desde lat/lon
    topologia_version TEXT NOT NULL,       -- que corrida de geometria_uvg.py lo calculo
    updated_at      TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_eventos_sismicos_fuente_time
    ON tbl_eventos_sismicos_fuente(time_utc);
CREATE INDEX IF NOT EXISTS idx_eventos_sismicos_fuente_nodo
    ON tbl_eventos_sismicos_fuente(id_nodo);
CREATE INDEX IF NOT EXISTS idx_eventos_sismicos_fuente_mag
    ON tbl_eventos_sismicos_fuente(mag);

CREATE TABLE IF NOT EXISTS tbl_eventos_volcanicos_fuente (
    evento_id       TEXT    PRIMARY KEY,   -- volcan+fecha normalizado, estable
    volcan          TEXT    NOT NULL,
    fecha           TEXT    NOT NULL,      -- ISO 8601 date
    lat             REAL    NOT NULL,
    lon             REAL    NOT NULL,
    tipo_erupcion   TEXT    DEFAULT '',
    vei             REAL,
    so2_kt          REAL    DEFAULT 0.0,
    id_nodo         INTEGER NOT NULL,      -- DERIVADO — recalculable desde lat/lon
    topologia_version TEXT NOT NULL,
    updated_at      TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_eventos_volcanicos_fuente_fecha
    ON tbl_eventos_volcanicos_fuente(fecha);
CREATE INDEX IF NOT EXISTS idx_eventos_volcanicos_fuente_nodo
    ON tbl_eventos_volcanicos_fuente(id_nodo);

-- Tabla de control: registra cada corrida del ETL en cascada, para
-- saber que version de topologia produjo el estado actual de las
-- tablas agregadas y de la memoria de patrones.
CREATE TABLE IF NOT EXISTS tbl_topologia_cascada_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    topologia_version   TEXT    NOT NULL,
    ejecutado_at        TEXT    DEFAULT (datetime('now')),
    eventos_sismicos_recalculados   INTEGER DEFAULT 0,
    eventos_volcanicos_recalculados INTEGER DEFAULT 0,
    nodos_cambiaron     INTEGER DEFAULT 0,
    firmas_purgadas     INTEGER DEFAULT 0,
    dry_run             INTEGER DEFAULT 0
);
