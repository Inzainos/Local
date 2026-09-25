#!/usr/bin/env bash
# Create robust Concilio Ollama models (anti-injection + memory pack + score format).
# Thin by default; Sentinel corpus opt-in via inject_sentinel_architecture: true.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MF="$ROOT/modelfiles"

echo "== ollama list (before) =="
ollama list || true

# v1 (2026-09-25): el INVESTIGADOR es concilio-investigador (llama3.2:3b). Este
# script no lo creaba: en una maquina nueva no existiria y el orquestador caeria
# al respaldo sin avisar. El coder (codegemma:7b) y el extractor (qwen2.5-coder:7b)
# se usan como tags base, sin Modelfile: asi se midieron.
echo "== Creating concilio-investigador (FROM llama3.2:3b) --- investigador de la v1 =="
if ollama create concilio-investigador -f "$MF/Modelfile.concilio-investigador"; then
  echo "OK concilio-investigador"
else
  echo "FAIL concilio-investigador — need base llama3.2:3b"
fi
for base in codegemma:7b qwen2.5-coder:7b; do
  if ollama list | grep -q "^${base}"; then echo "OK base $base"; else
    echo "FALTA $base (coder / extractor de la v1): ollama pull $base"; fi
done

echo "== Creating concilio-worker LIGHTEST (FROM nemotron-mini) --- esquema anterior =="
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
