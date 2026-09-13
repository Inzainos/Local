#!/usr/bin/env bash
set -euo pipefail
BIN=/home/deamon/.local/bin/cloudflared
CEA=/home/deamon/consensus-expert-agent
LOG=$CEA/logs/cloudflared-mini.log
ENVF=$CEA/.env
mkdir -p "$CEA/logs"
: > "$LOG"
# Start tunnel in background
"$BIN" tunnel --url http://127.0.0.1:8002 --no-autoupdate >>"$LOG" 2>&1 &
CFPID=$!
# Wait for trycloudflare URL
URL=""
for i in $(seq 1 60); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)
  if [[ -n "$URL" ]]; then
    break
  fi
  if ! kill -0 "$CFPID" 2>/dev/null; then
    echo "cloudflared died before publishing URL" >&2
    exit 1
  fi
  sleep 1
done
if [[ -z "$URL" ]]; then
  echo "timeout waiting for trycloudflare URL" >&2
  kill "$CFPID" 2>/dev/null || true
  exit 1
fi
WEBAPP="${URL}/mini"
# Update .env
python3 - << PY
from pathlib import Path
url = "${WEBAPP}"
p = Path("${ENVF}")
lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
out, seen = [], False
for line in lines:
    if line.strip().startswith("TELEGRAM_WEBAPP_URL="):
        out.append(f"TELEGRAM_WEBAPP_URL={url}")
        seen = True
    else:
        out.append(line)
if not seen:
    out.append(f"TELEGRAM_WEBAPP_URL={url}")
p.write_text("\n".join(out) + "\n", encoding="utf-8")
print("TELEGRAM_WEBAPP_URL=", url)
PY
# Soft-restart telegram bot so systemd picks new EnvironmentFile
pkill -TERM -f '/telegram_bot.py' 2>/dev/null || true
echo "cloudflared pid=$CFPID url=$WEBAPP"
# Keep tunnel in foreground for systemd
wait "$CFPID"
