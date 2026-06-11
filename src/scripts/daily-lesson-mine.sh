#!/bin/bash
# Daily lesson auto-miner — runs as a no_agent cron job
# Mines session history for bug-fix patterns from the last 24 hours.
# Deduplicates against existing lessons using semantic similarity.
# Validates quality (confidence ≥ 0.7) before saving.
# Reports compound stats at the end.
# Only produces output when it actually saved something (quiet otherwise).
#
# Portable: works on macOS (BSD grep, no -P, no bc required).

set -euo pipefail

# ── Paths ──────────────────────────────────────────────────────────────
# Priority: ~/.hermes/offline/ (install.sh destination) >
#           ~/.hermes/hermes-cortex/ (legacy) >
#           CORTEX_REPO (configurable env var) >
#           ~/Developer/AI/hermes-cortex/ (Titus' path) >
#           ~/hermes-cortex/ (default)
MINE_SCRIPT=""
for candidate in \
  "$HOME/.hermes/offline/session_mine.py" \
  "$HOME/.hermes/hermes-cortex/src/offline/session_mine.py" \
  "${CORTEX_REPO:-}/src/offline/session_mine.py" \
  "$HOME/Developer/AI/hermes-cortex/src/offline/session_mine.py" \
  "$HOME/hermes-cortex/src/offline/session_mine.py"; do
  if [ -f "$candidate" ]; then
    MINE_SCRIPT="$candidate"
    break
  fi
done
[ -n "$MINE_SCRIPT" ] || exit 0  # not installed, stay silent

INDEX_SCRIPT="${MINE_SCRIPT/session_mine.py/offline_knowledge.py}"
[ -f "$INDEX_SCRIPT" ] || INDEX_SCRIPT="${MINE_SCRIPT%/*}/offline_knowledge.py"
[ -f "$INDEX_SCRIPT" ] || exit 0

LESSON_STATS="$HOME/.hermes/cron/output/_lesson_compounds.json"
mkdir -p "$(dirname "$LESSON_STATS")"

# ── Portable grep-like extraction (no -P, no \K) ──────────────────────
_extract_int() {
  # Usage: _extract_int "Label:" < <output>
  # Extracts first integer after "Label:" followed by whitespace
  local label="$1"
  sed -nE "s/.*${label}[[:space:]]+([0-9]+).*/\1/p" | head -1
}

# ── Count existing lessons before mining ──────────────────────────────
COUNT_BEFORE=$(python3 "$INDEX_SCRIPT" lesson stats 2>/dev/null | _extract_int "Total lessons:" || echo 0)
[ -n "$COUNT_BEFORE" ] || COUNT_BEFORE=0

# ── Mine last 24 hours ─────────────────────────────────────────────────
OUTPUT=$(python3 "$MINE_SCRIPT" mine --auto --days 1 --limit 20 2>&1)
NUM_SAVED=$(echo "$OUTPUT" | grep -c "✅" || true)

if [ "$NUM_SAVED" -gt 0 ]; then
    echo "📚 Daily Lesson Mining — $(echo "$OUTPUT" | grep "Saved:" | wc -l | tr -d ' ') new lessons"
    echo "$OUTPUT"
    echo ""

    # Rebuild the search index
    python3 "$INDEX_SCRIPT" lesson index 2>&1 | tail -2
    echo ""
fi

# ── Count existing lessons after mining ───────────────────────────────
COUNT_AFTER=$(python3 "$INDEX_SCRIPT" lesson stats 2>/dev/null | _extract_int "Total lessons:" || echo 0)
[ -n "$COUNT_AFTER" ] || COUNT_AFTER=0
NEW_COUNT=$((COUNT_AFTER - COUNT_BEFORE))

# ── Compound stats — python for portability ───────────────────────────
# Use python3 instead of bc for floating-point arithmetic
COMPOUND_DATA=$(python3 -c "
import json, os, glob
total = 0
lessons_dir = os.path.expanduser('~/brain/lessons')
for f in glob.glob(os.path.join(lessons_dir, '*.md')):
    try:
        with open(f) as fh:
            for line in fh:
                if line.startswith('success_count:'):
                    total += int(line.split(':')[1].strip())
                    break
    except: pass
hours = round(total * 0.25, 1)
print(json.dumps({'total': total, 'hours': hours}))
" 2>/dev/null || echo '{"total":0,"hours":0}')

TOTAL_APPLIED=$(echo "$COMPOUND_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
EST_HOURS=$(echo "$COMPOUND_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin)['hours'])")

# ── Language count ─────────────────────────────────────────────────────
LANG_COUNT=$(python3 "$INDEX_SCRIPT" lesson stats 2>/dev/null | _extract_int "Languages:" || echo 0)
[ -n "$LANG_COUNT" ] || LANG_COUNT=0

# ── Update compound stats file ────────────────────────────────────────
cat > "$LESSON_STATS" <<EOF
{
  "last_run": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "total_lessons": $COUNT_AFTER,
  "new_this_run": $NEW_COUNT,
  "total_applications": $TOTAL_APPLIED,
  "estimated_hours_saved": $EST_HOURS,
  "languages_covered": $LANG_COUNT
}
EOF

# ── Report if anything happened ────────────────────────────────────────
if [ "$NUM_SAVED" -gt 0 ] || [ "$NEW_COUNT" -gt 0 ]; then
    echo ""
    echo "📊 Compound Score: $COUNT_AFTER lessons · $TOTAL_APPLIED applications · ~${EST_HOURS}h saved"
fi
# If nothing saved, exit silently
