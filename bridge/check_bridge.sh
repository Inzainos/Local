#!/bin/bash
set -euo pipefail
echo "== sshd =="; systemctl is-active ssh; systemctl is-enabled ssh
echo "== listen =="; ss -ltn | grep :22 || echo "22 not listening"
echo "== ssh sessions =="; ss -tnp | grep :22 || echo none
echo "== ollama local =="
code=$(curl -s -o /tmp/ollama_tags.json -w "%{http_code}" --max-time 3 http://127.0.0.1:11434/api/tags || echo fail)
echo "http=$code"
if [[ "$code" == "200" ]]; then
  if command -v jq >/dev/null 2>&1; then
    jq -r '.models[]?.name' /tmp/ollama_tags.json | head -20
  else
    echo "(jq missing — only http code)"
  fi
fi
echo "== auth keys =="; wc -l /home/deamon/.ssh/authorized_keys 2>/dev/null || echo none
echo "== lan ip =="; ip -4 -o addr show eth1 | awk '{print $4}'