#!/usr/bin/env bash
# symlink-audit.sh — check all symlinks in the repo are valid
# Usage: bash scripts/symlink-audit.sh [--check]

echo "=== Symlink Audit ==="
broken=0
total=0
issues=0

echo ""
echo "--- Repo symlinks ---"
find ~/hermes-cortex -type l ! -path '*/__pycache__/*' ! -path '*/.git/*' | while read link; do
  total=$((total + 1))
  target=$(readlink "$link")
  if [ ! -e "$link" ]; then
    echo "  BROKEN: $link -> $target"
    broken=$((broken + 1))
  fi
done

echo ""
echo "--- ~/.local/bin symlinks ---"
for t in score-cycle loop-feedback auto-apply loop-config skill-miner inbox-watch session-cache-build; do
  if [ -L ~/.local/bin/"$t" ]; then
    target=$(readlink ~/.local/bin/"$t")
    if [ -e "$target" ]; then
      echo "  OK: $t -> $target"
    else
      echo "  BROKEN: $t -> $target"
      broken=$((broken + 1))
    fi
  fi
done

echo ""
echo "--- Summary ---"
echo "  $broken broken symlinks"

if [ "$broken" -gt 0 ]; then
  exit 1
fi
