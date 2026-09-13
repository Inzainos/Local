#!/usr/bin/env bash
# Create thin Concilio Ollama models (anti-injection + score format only; NO Sentinel corpus).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MF="$ROOT/modelfiles"

echo "== ollama list (before) =="
ollama list || true

echo "== Creating concilio-worker (FROM qwen2.5:1.5b) =="
if ollama create concilio-worker -f "$MF/Modelfile.concilio-worker"; then
  echo "OK concilio-worker"
else
  echo "FAIL concilio-worker — need base qwen2.5:1.5b"
fi

# Compat alias
ollama create sentinel-concilio-worker -f "$MF/Modelfile.sentinel-concilio-worker" 2>/dev/null || true

echo "== Unload before 26b create =="
ollama stop qwen2.5:1.5b 2>/dev/null || true
ollama stop concilio-worker 2>/dev/null || true
ollama stop sentinel-concilio-worker 2>/dev/null || true
sleep 2

echo "== Creating concilio-arbitro (FROM gemma4:26b) =="
if ollama create concilio-arbitro -f "$MF/Modelfile.concilio-arbitro"; then
  echo "OK concilio-arbitro"
else
  echo "FAIL concilio-arbitro — likely RAM; retry later:"
  echo "  ollama create concilio-arbitro -f $MF/Modelfile.concilio-arbitro"
fi
ollama create sentinel-concilio-arbitro -f "$MF/Modelfile.sentinel-concilio-arbitro" 2>/dev/null || true

echo "== ollama list (after) =="
ollama list || true
