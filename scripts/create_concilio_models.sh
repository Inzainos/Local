#!/usr/bin/env bash
# Create robust Concilio Ollama models (anti-injection + memory pack + score format).
# Thin by default; Sentinel corpus opt-in via inject_sentinel_architecture: true.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MF="$ROOT/modelfiles"

echo "== ollama list (before) =="
ollama list || true

echo "== Creating concilio-worker LIGHTEST (FROM nemotron-mini) =="
if ollama create concilio-worker -f "$MF/Modelfile.concilio-worker"; then
  echo "OK concilio-worker"
else
  echo "FAIL concilio-worker — need base nemotron-mini"
fi

# Alias lightest
ollama create concilio-lightest -f "$MF/Modelfile.lightest" 2>/dev/null || true
ollama create sentinel-concilio-worker -f "$MF/Modelfile.sentinel-concilio-worker" 2>/dev/null || true

echo "== Creating concilio-medium MEDIUM coder (FROM deepseek-r1:8b) =="
if ollama create concilio-medium -f "$MF/Modelfile.medium"; then
  echo "OK concilio-medium"
else
  echo "FAIL concilio-medium — need base deepseek-r1:8b"
fi

echo "== Unload before arbiter create =="
ollama stop nemotron-mini 2>/dev/null || true
ollama stop deepseek-r1:8b 2>/dev/null || true
ollama stop concilio-worker 2>/dev/null || true
ollama stop concilio-medium 2>/dev/null || true
ollama stop sentinel-concilio-worker 2>/dev/null || true
sleep 2

echo "== Creating concilio-arbitro HEAVY (FROM gemma3:4b) =="
if ollama create concilio-arbitro -f "$MF/Modelfile.concilio-arbitro"; then
  echo "OK concilio-arbitro"
else
  echo "FAIL concilio-arbitro — likely RAM; retry later:"
  echo "  ollama create concilio-arbitro -f $MF/Modelfile.concilio-arbitro"
fi
ollama create concilio-heavy -f "$MF/Modelfile.heavy" 2>/dev/null || true
ollama create sentinel-concilio-arbitro -f "$MF/Modelfile.sentinel-concilio-arbitro" 2>/dev/null || true

echo "== ollama list (after) =="
ollama list || true
