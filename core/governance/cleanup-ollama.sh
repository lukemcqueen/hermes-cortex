#!/usr/bin/env bash
# cleanup-ollama.sh — remove all Ollama models except the 2 essential ones
# Reads EMBEDDING_MODEL and JUDGE_MODEL from ~/hermes-cortex/.env
# Default: nomic-embed-text:v1.5 + qwen2.5:3b

# Source model configuration
MODELS_ENV="${HOME}/hermes-cortex/.env"
if [ -f "$MODELS_ENV" ]; then
  set -a
  source "$MODELS_ENV"
  set +a
fi
EMBEDDING_MODEL="${EMBEDDING_MODEL:-nomic-embed-text:v1.5}"
JUDGE_MODEL="${JUDGE_MODEL:-qwen2.5:3b}"

KEEP_MODELS=("$EMBEDDING_MODEL" "$JUDGE_MODEL")

echo "=== Ollama Model Cleanup ==="
echo ""

if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "  Ollama not running — skipping"
  exit 0
fi

for model in $(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}'); do
  keep=false
  for keep_model in "${KEEP_MODELS[@]}"; do
    if [ "$model" = "$keep_model" ]; then
      keep=true
      break
    fi
  done
  if ! $keep; then
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
