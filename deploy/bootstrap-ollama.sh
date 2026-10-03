#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${TERRASATCH_REPO_DIR:-/opt/terrasatch/api}"
MODEL="${1:-${TERRASATCH_OLLAMA_MODEL:-qwen3:1.7b}}"

cd "$REPO_DIR"

echo "Starting production Ollama service"
docker compose up -d ollama

echo "Waiting for Ollama"
for attempt in $(seq 1 30); do
  if docker compose exec -T ollama ollama list >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" == "30" ]]; then
    echo "Ollama did not become ready" >&2
    exit 1
  fi
  sleep 2
done

echo "Pulling model: $MODEL"
docker compose exec -T ollama ollama pull "$MODEL"

echo "Verifying model"
docker compose exec -T ollama ollama show "$MODEL" >/dev/null

echo "Production Ollama ready with model: $MODEL"
echo "The intelligence provider is not changed by this script."
