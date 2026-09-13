#!/usr/bin/env bash
# .devcontainer/postCreate.sh
# Se ejecuta una sola vez al crear el Codespace.

set -e

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Sentinel Omega — preparando entorno en Codespaces"
echo "═══════════════════════════════════════════════════════════"

# 1. Instalar dependencias Jupyter + ML
echo "▶ Instalando dependencias Jupyter..."
pip install --quiet -r sentinel_omega/notebooks/requirements_jupyter.txt

# 2. Instalar dependencias core del sistema (APIs, Streamlit, etc.)
echo "▶ Instalando dependencias core..."
pip install --quiet -r sentinel_omega/requirements.txt

# 3. Crear carpeta de datos (está en .gitignore, no existe en checkout limpio)
echo "▶ Creando carpeta sentinel_omega/data/..."
mkdir -p sentinel_omega/data

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✅ Entorno listo. Comandos disponibles:"
echo ""
echo "  🔬 JupyterLab (puerto 8888):"
echo "     jupyter lab --no-browser --port=8888"
echo "     → abre el notebook: sentinel_omega/notebooks/jupyter_launcher.ipynb"
echo ""
echo "  📊 Streamlit Dashboard (puerto 8501):"
echo "     streamlit run sentinel_omega/infrastructure/dashboard/app.py"
echo ""
echo "  🌍 Un ciclo de vigilancia y reporte:"
echo "     python sentinel_omega/launcher.py --once"
echo "     python deploy/generar_reporte.py"
echo "     cat estado/REPORTE.md"
echo ""
echo "  🔍 Comparar reporte Codespace vs Roy (producción):"
echo "     python deploy/generar_reporte.py . estado/REPORTE_codespace.md"
echo "     diff estado/REPORTE.md estado/REPORTE_codespace.md | head -80"
echo "═══════════════════════════════════════════════════════════"
