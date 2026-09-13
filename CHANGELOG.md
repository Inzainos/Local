# Changelog - Padrón de Afiliados

Todos los cambios notables de este proyecto se documentan en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2026-09-13 - H4: symlinks de skills fuera del control de versiones

### Fixed
- `.agents/skills/developing-with-streamlit` y `.claude/skills/developing-with-streamlit`
  eran symlinks a `venv/lib/python3.13/site-packages/streamlit/.agents/skills/`.
  Como `venv/` está en `.gitignore`, quedaban **rotos en cualquier clon limpio**
  hasta crear el entorno con Streamlit instalado. Verificado en un checkout
  fresco: ambos apuntaban a nada.
- Se quitan del índice y se añaden al `.gitignore`. Siguen funcionando en local
  cuando el venv existe; simplemente dejan de viajar en el repo.

### Notes
- Hallazgo H4 de la auditoría del monorepo (2026-09-13). El análogo en
  `local/sentinel-omega` se cerró en `b639aa8`; esta rama quedó pendiente por no
  tener agente asignado en la tabla de owners.

## [1.0.0] - 2026-09-02

### Agregado
- Estructura base del repositorio en `/home/deamon/padron_afiliados_app/`
- Directorios modulares: `/src`, `/database`, `/logs`, `/tests`
- Inicialización de repositorio Git con `.gitignore` configurado
- Entorno virtual Python 3.13 con dependencias: pandas, streamlit, scipy
- Archivo `requirements.txt` con dependencias fijadas

### Base de Datos (`database/schema.sql`)
- Tabla `afiliados` con campos completos (DNI, nombre, apellido, fecha_nacimiento, género, dirección, contacto, mesa de votación, estado)
- Tabla `historial_cambios` para auditoría automática via triggers
- Tabla `eventos_electorales` para gestión de elecciones/primarias/referendums
- Tabla `participacion_electoral` para registro de voto por afiliado y evento
- Tabla `alertas` para sistema de notificaciones
- Vista `v_estadisticas_generales` para dashboard rápido
- Triggers para `updated_at` automático y registro en historial
- Índices optimizados para búsquedas frecuentes

### Aplicación Principal (`src/app_afiliados.py`)
- Dashboard Streamlit con **11 pestañas**:
  1. 📊 **Dashboard** - Métricas generales y KPIs
  2. 👥 **Afiliados** - Gestión y filtrado de padrón
  3. 📥 **Importar** - Carga CSV/Excel con mapeo de columnas
  4. 📈 **Análisis** - Análisis de comportamiento electoral
  5. 🗓️ **Eventos** - CRUD de eventos electorales
  6. ✅ **Participación** - Registro de voto por DNI
  7. 🔔 **Alertas** - Centro de notificaciones con estados
  8. 🤖 **Telegram** - Configuración bot para alertas con gráficas/tablas/cimática
  9. 📋 **Reportes** - Exportación CSV/Excel/JSON con queries personalizadas
  10. 🔍 **Auditoría** - Historial de cambios y logs del sistema
  11. ⚙️ **Config** - Reinicialización BD, esquema, info sistema

### Módulo de Análisis (`src/analisis_comportamiento.py`)
- **Análisis Demográfico**: edad (promedio, medianas, percentiles, rangos etarios), género, geográfico (provincia/localidad), mesas de votación
- **Análisis de Participación**: tasa general, por género, por edad, por provincia
- **Tests Estadísticos**: Chi-cuadrado para independencia (género vs voto, provincia vs voto)
- **Análisis de Cohortes**: retención por año de afiliación
- **Análisis Cimático**: FFT, autocorrelación, detección de estacionalidad/periodicidad en series temporales de afiliación
- **Análisis de Redes**: conexiones por mesa, apellido (familias), localidad+apellido
- **Detección de Outliers**: IQR para edades y mesas atípicas
- **Reporte Completo**: JSON exportable con todos los análisis
- **Resumen Ejecutivo**: KPIs para dashboard

### Tests (`tests/test_analisis.py`)
- Tests unitarios para todas las funciones de análisis
- Tests de conexión a BD con base temporal
- Cobertura: edad, género, geográfico, mesas, cohortes, redes, reporte completo, resumen ejecutivo

### Documentación
- `README.md` con estructura, instalación, uso y roadmap
- `CHANGELOG.md` con historial de versiones
- `requirements.txt` con dependencias fijadas

---

## [Unreleased]

### Planeado
- [ ] Implementación real del bot de Telegram con envío de gráficas (Plotly/Altair)
- [ ] Generación de PDFs con reportes (WeasyPrint/ReportLab)
- [ ] Mapa de calor geográfico interactivo (Folium/Kepler.gl)
- [ ] Autenticación y roles de usuario
- [ ] API REST para integraciones externas
- [ ] Backup automático programado de BD
- [ ] Migración a PostgreSQL para producción
- [ ] Tests de integración con pytest
- [ ] CI/CD con GitHub Actions
- [ ] Dockerfile para despliegue contenerizado

### En Progreso
- [ ] Integración del módulo `analisis_comportamiento.py` en pestaña "Análisis" del dashboard
- [ ] Alertas automáticas basadas en umbrales (nuevos afiliados, participación baja, etc.)

---

## Formato de Versiones

- **MAJOR**: Cambios incompatibles en API/BD
- **MINOR**: Nuevas funcionalidades compatibles hacia atrás
- **PATCH**: Correcciones de bugs compatibles hacia atrás

## Ramas de Trabajo

- `main` / `master`: Versión estable de producción
- `local/alertas-v2.5.3`: Ejemplo de rama de feature (patrón: `local/<feature>-v<version>`)
- `develop`: Rama de integración (si se usa GitFlow)

## Convenciones de Commit

```
feat: nueva funcionalidad
fix: corrección de bug
docs: cambios en documentación
style: formato, linting
refactor: refactorización de código
test: agregar/modificar tests
chore: mantenimiento, dependencias
```
