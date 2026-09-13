#!/usr/bin/env bash
# Sentinel Omega — instalador para servidor Linux (systemd + timers)
# Uso:  bash deploy/install.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"
echo ">> Instalando Sentinel Omega en $REPO_DIR"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r sentinel_omega/requirements.txt -q
.venv/bin/pip install "onnxruntime>=1.14" "scikit-learn>=1.3" "skl2onnx>=1.16" "ephem>=4.1" -q 2>/dev/null || true
echo ">> Dependencias instaladas."

if [ ! -f deploy/.env ]; then
    if [ -f deploy/.env.example ]; then
        cp deploy/.env.example deploy/.env
    else
        touch deploy/.env
    fi
    echo ""
    echo "⚠️  EDITA deploy/.env CON TUS KEYS antes de continuar:"
    echo "    nano deploy/.env"
    echo ""
fi

install_unit() {
    local src="$1"
    local name
    name="$(basename "$src")"
    sudo cp "$src" "/etc/systemd/system/$name"
    sudo sed -i "s|__REPO_DIR__|$REPO_DIR|g" "/etc/systemd/system/$name"
    echo "   instalado $name"
}

echo ">> Instalando units systemd..."
install_unit deploy/sentinel-omega.service
install_unit deploy/sentinel-omega-dashboard.service
install_unit deploy/sentinel-omega-mantenimiento.service
install_unit deploy/sentinel-omega-mantenimiento.timer
install_unit deploy/sentinel-omega-disciplina.service
install_unit deploy/sentinel-omega-barrido.service
install_unit deploy/sentinel-omega-scheduler.service
install_unit deploy/sentinel-omega-watchdog.service

sudo systemctl daemon-reload
echo ">> systemd daemon-reload OK."

sudo systemctl enable sentinel-omega-mantenimiento.timer
echo ">> Timer mantenimiento diario habilitado (08:00 UTC)."

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  BOOTSTRAP (una sola vez — carga 30 años y entrena):"
echo "    .venv/bin/python sentinel_omega/launcher.py \\"
echo "        --backcast --entrenar --entrenar-onnx --once --dry-run"
echo ""
echo "  ARRANQUE 24/7:"
echo "    sudo systemctl enable --now sentinel-omega"
echo "    sudo systemctl enable --now sentinel-omega-dashboard   # opcional"
echo "    sudo systemctl enable --now sentinel-omega-scheduler   # reportes 2h/6h"
echo "    sudo systemctl enable --now sentinel-omega-watchdog     # watchdog red/agente"
echo "    sudo systemctl start sentinel-omega-mantenimiento.timer"
echo "    sudo systemctl enable --now sentinel-omega-onnx-retrain.timer  # retrain ONNX domingos 03:00"
echo ""
echo "  MANTENIMIENTO MANUAL:"
echo "    sudo systemctl start sentinel-omega-mantenimiento.service"
echo "    # o: .venv/bin/python sentinel_omega/launcher.py --disciplina --barrido"
echo ""
echo "  VER TIMERS / LOGS:"
echo "    systemctl list-timers 'sentinel-omega*'"
echo "    journalctl -u sentinel-omega-mantenimiento -n 50"
echo "    journalctl -u sentinel-omega -f"
echo ""
echo "  ALTERNATIVA CRON (si no usas timers):"
echo "    sed \"s|__REPO_DIR__|$REPO_DIR|g\" deploy/crontab.example"
echo "    crontab -e   # pegar la línea generada"
echo "═══════════════════════════════════════════════════════════"
