-- Esquema de Base de Datos - Padrón de Afiliados
-- SQLite compatible

-- Tabla principal de afiliados
CREATE TABLE IF NOT EXISTS afiliados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dni TEXT UNIQUE NOT NULL,
    nombre TEXT NOT NULL,
    apellido TEXT NOT NULL,
    fecha_nacimiento DATE,
    genero TEXT CHECK (genero IN ('M', 'F', 'O', 'X')),
    provincia TEXT,
    localidad TEXT,
    direccion TEXT,
    codigo_postal TEXT,
    email TEXT,
    telefono TEXT,
    mesa_votacion INTEGER,
    circuito TEXT,
    seccion TEXT,
    fecha_afiliacion DATE DEFAULT (date('now')),
    estado TEXT DEFAULT 'activo' CHECK (estado IN ('activo', 'inactivo', 'baja', 'fallecido')),
    observaciones TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de historial de cambios (auditoría)
CREATE TABLE IF NOT EXISTS historial_cambios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tabla_afectada TEXT NOT NULL,
    registro_id INTEGER NOT NULL,
    accion TEXT NOT NULL CHECK (accion IN ('INSERT', 'UPDATE', 'DELETE')),
    campo_modificado TEXT,
    valor_anterior TEXT,
    valor_nuevo TEXT,
    usuario TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de eventos electorales
CREATE TABLE IF NOT EXISTS eventos_electorales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('eleccion', 'primaria', 'referendum', 'consulta', 'otro')),
    fecha DATE NOT NULL,
    descripcion TEXT,
    activo BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de participación electoral
CREATE TABLE IF NOT EXISTS participacion_electoral (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    afiliado_id INTEGER NOT NULL,
    evento_id INTEGER NOT NULL,
    voto_emitido BOOLEAN DEFAULT 0,
    mesa_asignada INTEGER,
    observaciones TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (afiliado_id) REFERENCES afiliados(id) ON DELETE CASCADE,
    FOREIGN KEY (evento_id) REFERENCES eventos_electorales(id) ON DELETE CASCADE,
    UNIQUE (afiliado_id, evento_id)
);

-- Tabla de alertas/notificaciones
CREATE TABLE IF NOT EXISTS alertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL CHECK (tipo IN ('info', 'warning', 'error', 'success')),
    titulo TEXT NOT NULL,
    mensaje TEXT,
    afiliado_id INTEGER,
    evento_id INTEGER,
    leida BOOLEAN DEFAULT 0,
    enviada_telegram BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (afiliado_id) REFERENCES afiliados(id) ON DELETE SET NULL,
    FOREIGN KEY (evento_id) REFERENCES eventos_electorales(id) ON DELETE SET NULL
);

-- Vista para estadísticas generales rápidas
CREATE VIEW IF NOT EXISTS v_estadisticas_generales AS
SELECT
    COUNT(*) as total_afiliados,
    SUM(CASE WHEN estado = 'activo' THEN 1 ELSE 0 END) as activos,
    SUM(CASE WHEN estado = 'inactivo' THEN 1 ELSE 0 END) as inactivos,
    SUM(CASE WHEN estado = 'baja' THEN 1 ELSE 0 END) as bajas,
    SUM(CASE WHEN estado = 'fallecido' THEN 1 ELSE 0 END) as fallecidos,
    COUNT(DISTINCT provincia) as provincias,
    COUNT(DISTINCT localidad) as localidades,
    COUNT(DISTINCT mesa_votacion) as mesas,
    AVG(CASE
        WHEN fecha_nacimiento IS NOT NULL
        THEN (julianday('now') - julianday(fecha_nacimiento)) / 365.25
    END) as edad_promedio
FROM afiliados;

-- Trigger para actualizar updated_at automáticamente
CREATE TRIGGER IF NOT EXISTS trigger_afiliados_updated_at
AFTER UPDATE ON afiliados
BEGIN
    UPDATE afiliados SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Trigger para registrar INSERT en historial
CREATE TRIGGER IF NOT EXISTS trigger_afiliados_historial_insert
AFTER INSERT ON afiliados
BEGIN
    INSERT INTO historial_cambios (tabla_afectada, registro_id, accion, usuario)
    VALUES ('afiliados', NEW.id, 'INSERT', CURRENT_USER);
END;

-- Trigger para registrar UPDATE en historial
CREATE TRIGGER IF NOT EXISTS trigger_afiliados_historial_update
AFTER UPDATE ON afiliados
BEGIN
    INSERT INTO historial_cambios (tabla_afectada, registro_id, accion, campo_modificado, valor_anterior, valor_nuevo, usuario)
    VALUES ('afiliados', NEW.id, 'UPDATE', 'multiple', 'ver_detalle', 'ver_detalle', CURRENT_USER);
END;

-- Trigger para registrar DELETE en historial
CREATE TRIGGER IF NOT EXISTS trigger_afiliados_historial_delete
AFTER DELETE ON afiliados
BEGIN
    INSERT INTO historial_cambios (tabla_afectada, registro_id, accion, usuario)
    VALUES ('afiliados', OLD.id, 'DELETE', CURRENT_USER);
END;

-- Índices para optimizar consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_afiliados_dni ON afiliados(dni);
CREATE INDEX IF NOT EXISTS idx_afiliados_apellido ON afiliados(apellido);
CREATE INDEX IF NOT EXISTS idx_afiliados_provincia ON afiliados(provincia);
CREATE INDEX IF NOT EXISTS idx_afiliados_localidad ON afiliados(localidad);
CREATE INDEX IF NOT EXISTS idx_afiliados_mesa ON afiliados(mesa_votacion);
CREATE INDEX IF NOT EXISTS idx_afiliados_estado ON afiliados(estado);
CREATE INDEX IF NOT EXISTS idx_afiliados_fecha_afiliacion ON afiliados(fecha_afiliacion);
CREATE INDEX IF NOT EXISTS idx_participacion_afiliado ON participacion_electoral(afiliado_id);
CREATE INDEX IF NOT EXISTS idx_participacion_evento ON participacion_electoral(evento_id);
CREATE INDEX IF NOT EXISTS idx_alertas_leida ON alertas(leida);
CREATE INDEX IF NOT EXISTS idx_alertas_telegram ON alertas(enviada_telegram);
CREATE INDEX IF NOT EXISTS idx_historial_registro ON historial_cambios(tabla_afectada, registro_id);
