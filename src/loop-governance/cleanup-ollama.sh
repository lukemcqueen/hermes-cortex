#!/usr/bin/env bash
# cleanup-ollama.sh — remove all Ollama models except the embedding model
# Reads EMBEDDING_MODEL from ~/hermes-cortex/.env
# Default: nomic-embed-text:v1.5

# Source model configuration
MODELS_ENV="${HOME}/hermes-cortex/.env"
if [ -f "$MODELS_ENV" ]; then
  set -a
  source "$MODELS_ENV"
  set +a
fi
EMBEDDING_MODEL="${EMBEDDING_MODEL:-nomic-embed-text:v1.5}"

echo "=== Ollama Model Cleanup ==="
echo ""

if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "  Ollama not running — skipping"
  exit 0
fi

for model in $(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}'); do
  if [ "$model" != "$EMBEDDING_MODEL" ]; then
    size=$(ollama list 2>/dev/null | grep "$model" | awk '{print $3}')
    echo "  Removing: $model ($size)"
    ollama rm "$model" 2>/dev/null
  fi
done

echo ""
echo "  Remaining models:"
ollama list 2>/dev/null | tail -n +2 | awk '{print "    " $1 " (" $3 ")"}'
echo ""
echo "  Total Ollama disk: $(du -sh ~/.ollama/models/ 2>/dev/null | awk '{print $1}')"
echo "  Done."
