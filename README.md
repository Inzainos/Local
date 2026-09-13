# Padrón de Afiliados - Sistema de Control Electoral

Sistema para la gestión y análisis del padrón de afiliados con dashboard interactivo en Streamlit.

## Estructura del Proyecto

```
padron_afiliados_app/
├── src/
│   ├── app_afiliados.py           # Dashboard Streamlit principal (11 pestañas)
│   └── analisis_comportamiento.py # Módulo de análisis estadístico y cimático
├── database/
│   └── schema.sql                 # Esquema SQLite completo
├── tests/
│   └── test_analisis.py           # Tests unitarios
├── logs/                          # Logs de ejecución (gitignored)
├── venv/                          # Entorno virtual Python (gitignored)
├── requirements.txt               # Dependencias Python
├── README.md                      # Este archivo
├── CHANGELOG.md                   # Historial de versiones
└── .gitignore                     # Archivos ignorados por Git
```

## Instalación Rápida

```bash
# Clonar e ingresar al directorio
cd /home/deamon/padron_afiliados_app

# Activar entorno virtual
source venv/bin/activate

# Instalar/actualizar dependencias
pip install -r requirements.txt

# Inicializar base de datos (crea padron.db con esquema)
python3 -c "
import sqlite3
from pathlib import Path
sql = Path('database/schema.sql').read_text()
conn = sqlite3.connect('database/padron.db')
conn.executescript(sql)
conn.commit()
conn.close()
print('Base de datos inicializada')
"

# Ejecutar dashboard
streamlit run src/app_afiliados.py
```

El dashboard estará disponible en `http://localhost:8501`

## Funcionalidades Principales

### Dashboard (11 Pestañas)
1. **📊 Dashboard** - Métricas generales, KPIs, gráficos rápidos
2. **👥 Afiliados** - Gestión completa: listar, buscar, filtrar, editar, eliminar
3. **📥 Importar** - Carga masiva CSV/Excel con mapeo de columnas
4. **📈 Análisis** - Análisis demográfico, participación, cohortes, cimática, redes
5. **🗓️ Eventos** - CRUD de eventos electorales (elecciones, primarias, referendums)
6. **✅ Participación** - Registro de voto por DNI y evento
7. **🔔 Alertas** - Centro de notificaciones con estados (pendiente/enviada/leída)
8. **🤖 Telegram** - Configuración bot para alertas automáticas con gráficas
9. **📋 Reportes** - Exportación CSV/Excel/JSON, queries SQL personalizadas
10. **🔍 Auditoría** - Historial de cambios, logs del sistema
11. **⚙️ Config** - Reinicialización BD, ver esquema, info del sistema

### Análisis de Comportamiento Electoral
- **Demográfico**: Edad (promedio, medianas, percentiles, rangos etarios), género, geográfico (provincia/localidad), mesas de votación
- **Participación**: Tasa general, por género, edad, provincia
- **Estadísticas**: Test Chi-cuadrado para independencia
- **Cohortes**: Retención por año de afiliación
- **Cimático**: FFT, autocorrelación, detección de estacionalidad/periodicidad
- **Redes**: Conexiones por mesa, apellido (familias), localidad+apellido
- **Outliers**: Detección IQR para edades y mesas atípicas

### Base de Datos (SQLite)
- `afiliados`: DNI, nombre, apellido, fecha_nacimiento, género, dirección, contacto, mesa_votacion, estado
- `historial_cambios`: Auditoría automática via triggers
- `eventos_electorales`: Elecciones, primarias, referendums
- `participacion_electoral`: Voto por afiliado y evento
- `alertas`: Sistema de notificaciones
- Vista `v_estadisticas_generales` para dashboard rápido
- Índices optimizados

## Tests

```bash
cd /home/deamon/padron_afiliados_app
source venv/bin/activate
python -m pytest tests/ -v
# o directamente
python tests/test_analisis.py
```

## Roadmap (v1.1+)

- [ ] Bot Telegram real con envío de gráficas (Plotly/Altair)
- [ ] Generación de PDFs (WeasyPrint/ReportLab)
- [ ] Mapa de calor geográfico (Folium/Kepler.gl)
- [ ] Autenticación y roles de usuario
- [ ] API REST para integraciones
- [ ] Backup automático programado
- [ ] Migración a PostgreSQL
- [ ] CI/CD con GitHub Actions
- [ ] Dockerfile para despliegue

## Licencia

Proyecto interno - Sistema de Control Electoral
