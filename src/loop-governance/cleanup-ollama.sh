#!/usr/bin/env bash
# cleanup-ollama.sh — remove all Ollama models except nomic-embed-text
# Only nomic-embed-text is needed for scoring. Other models waste disk.

echo "=== Ollama Model Cleanup ==="
echo ""

if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "  Ollama not running — skipping"
  exit 0
fi

for model in $(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}'); do
  if [ "$model" != "nomic-embed-text:latest" ]; then
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
