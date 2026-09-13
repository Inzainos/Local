#!/bin/bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run with sudo"; exit 1; fi
MODE=${1:-bootstrap}
if [[ "$MODE" == "harden" ]]; then
  SRC=/home/deamon/bridge/sshd_deamonx.conf
else
  SRC=/home/deamon/bridge/sshd_bootstrap.conf
fi
install -m 644 "$SRC" /etc/ssh/sshd_config.d/99-deamonx.conf
sshd -t
systemctl enable --now ssh
systemctl --no-pager --full status ssh | head -15
ss -ltn | grep :22 || true
echo "MODE=$MODE"
