#!/usr/bin/env sh
# Get the production LLM into Ollama: Qwen3-30B-A3B (qwen3:30b-a3b-q4_K_M, Q4_K_M, ~18.6 GB).
# The Ollama library tag ships Qwen3's chat template with the thinking switch the app uses
# (`think: true/false` per request), so no custom Modelfile or alias is needed.
# Idempotent: re-running only pulls changed layers. See docs/QWEN3_30B.md.
#
#   scripts/setup_ollama_model.sh                    # Ollama on this host (`ollama` on PATH)
#   OLLAMA_BIN=~/.local/ollama/bin/ollama scripts/setup_ollama_model.sh
#   scripts/setup_ollama_model.sh --docker           # the compose `ollama` service (--profile ollama)
#   MODEL=qwen3:30b-a3b-q4_K_M scripts/setup_ollama_model.sh  # the tag to pull (default below)
set -eu

MODEL="${MODEL:-qwen3:30b-a3b-q4_K_M}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ "${1:-}" = "--docker" ]; then
  run() { docker compose -f "$ROOT/docker-compose.yml" exec -T ollama ollama "$@"; }
else
  run() { "${OLLAMA_BIN:-ollama}" "$@"; }
fi

echo "pull   $MODEL"
run pull "$MODEL"
run show "$MODEL"
echo "ready: set OLLAMA_MODEL=$MODEL in .env (the default in docker-compose.yml and .env.example)"
