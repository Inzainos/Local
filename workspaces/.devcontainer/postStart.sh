#!/usr/bin/env bash
set -e

echo "============================================"
echo "  SENTINEL OMEGA — Codespace Auto-Launch"
echo "============================================"

# ── Instalar dependencias ───────────────────────────────────────
echo "[1/5] Instalando dependencias..."
pip install --quiet -r sentinel_omega/requirements.txt 2>/dev/null || \
  pip install --quiet requests ephem numpy pandas scikit-learn 2>/dev/null

# ── Backcast + Entrenamiento inicial ───────────────────────────
DB_PATH="sentinel_omega/data/SENTINEL_OMEGA_PRO.db"
mkdir -p sentinel_omega/data

if [ ! -f "$DB_PATH" ] || [ ! -s "$DB_PATH" ]; then
  echo "[2/5] DB no encontrada — corriendo backcast histórico..."
  python sentinel_omega/launcher.py --backcast --entrenar --disciplina --reporte --once \
    >> sentinel_omega/data/codespace_init.log 2>&1
  echo "  Backcast + entrenamiento completado."
else
  echo "[2/5] DB existente — corriendo entrenamiento + reporte inicial..."
  python sentinel_omega/launcher.py --entrenar --reporte --once \
    >> sentinel_omega/data/codespace_init.log 2>&1
  echo "  Entrenamiento + reporte completados."
fi

# ── Scheduler de reportes en background (2h/6h) ──────────────────
echo "[3/5] Arrancando scheduler de reportes (2h/6h)..."
if pgrep -f "scheduler_reportes.py" > /dev/null; then
  SCHEDULER_PID=$(pgrep -f "scheduler_reportes.py" | head -n1)
  echo "  Scheduler YA ACTIVO (PID $SCHEDULER_PID) — no se relanza"
else
  nohup python sentinel_omega/infrastructure/pipeline/scheduler_reportes.py \
    >> sentinel_omega/data/scheduler_reportes.log 2>&1 &
  SCHEDULER_PID=$!
  echo "  Scheduler ONLINE (PID $SCHEDULER_PID)"
fi
echo "  Log: sentinel_omega/data/scheduler_reportes.log"

# ── Arrancar ciclos live continuos en background ──────────────────
echo "[4/5] Arrancando ciclos live continuos..."
if pgrep -f "launcher.py" > /dev/null; then
  LAUNCHER_PID=$(pgrep -f "launcher.py" | head -n1)
  echo "  Sentinel Omega YA ACTIVO (PID $LAUNCHER_PID) — no se relanza"
else
  nohup python sentinel_omega/launcher.py \
    >> sentinel_omega/data/sentinel_omega.log 2>&1 &
  LAUNCHER_PID=$!
  echo "  Sentinel Omega ONLINE (PID $LAUNCHER_PID)"
fi

# ── Resumen final ────────────────────────────────────────────────
echo "[5/5] Sistema completo."
echo ""
echo "  Procesos activos:"
echo "    Launcher      PID $LAUNCHER_PID  — ciclos live"
echo "    Scheduler     PID $SCHEDULER_PID — reportes cada 2h/6h"
echo ""
echo "  Logs disponibles:"
echo "    tail -f sentinel_omega/data/sentinel_omega.log"
echo "    tail -f sentinel_omega/data/scheduler_reportes.log"
echo ""
echo "  Reportes guardados en:"
echo "    sentinel_omega/data/reporte_general_*.txt"
echo "    sentinel_omega/data/reporte_padre_*.txt"
echo "    sentinel_omega/data/reporte_omega_*.txt"
echo "============================================"
