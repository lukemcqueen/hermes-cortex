#!/bin/bash
# Daily lesson auto-miner — runs as a no_agent cron job
# Mines session history for bug-fix patterns from the last 24 hours.
# Deduplicates against existing lessons using semantic similarity.
# Validates quality (confidence ≥ 0.7) before saving.
# Reports compound stats at the end.
# Only produces output when it actually saved something (quiet otherwise).

set -euo pipefail

# ── Paths ──────────────────────────────────────────────────────────────
MINE_SCRIPT="$HOME/.hermes/offline/session_mine.py"
[ -f "$MINE_SCRIPT" ] || MINE_SCRIPT="$HOME/hermes-cortex/src/offline/session_mine.py"
[ -f "$MINE_SCRIPT" ] || exit 0  # not installed, stay silent

INDEX_SCRIPT="$HOME/.hermes/offline/offline_knowledge.py"
[ -f "$INDEX_SCRIPT" ] || INDEX_SCRIPT="$HOME/hermes-cortex/src/offline/offline_knowledge.py"
[ -f "$INDEX_SCRIPT" ] || exit 0

LESSON_STATS="$HOME/.hermes/cron/output/_lesson_compounds.json"
mkdir -p "$(dirname "$LESSON_STATS")"

# ── Count existing lessons before mining ──────────────────────────────
COUNT_BEFORE=$(python3 "$INDEX_SCRIPT" lesson stats 2>/dev/null | grep -oP 'Total lessons:\s+\K\d+' || echo 0)

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
COUNT_AFTER=$(python3 "$INDEX_SCRIPT" lesson stats 2>/dev/null | grep -oP 'Total lessons:\s+\K\d+' || echo 0)
NEW_COUNT=$((COUNT_AFTER - COUNT_BEFORE))

# ── Compound stats ────────────────────────────────────────────────────
TOTAL_APPLIED=$(python3 -c "
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
print(total)
" 2>/dev/null || echo 0)

EST_HOURS=$(echo "scale=1; $TOTAL_APPLIED * 0.25" | bc)

# ── Update compound stats file ────────────────────────────────────────
cat > "$LESSON_STATS" <<EOF
{
  "last_run": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "total_lessons": $COUNT_AFTER,
  "new_this_run": $NEW_COUNT,
  "total_applications": $TOTAL_APPLIED,
  "estimated_hours_saved": $EST_HOURS,
  "languages_covered": $(python3 "$INDEX_SCRIPT" lesson stats 2>/dev/null | grep -oP 'Languages:\s+\K\d+' || echo 0)
}
EOF

# ── Report if anything happened ────────────────────────────────────────
if [ "$NUM_SAVED" -gt 0 ] || [ "$NEW_COUNT" -gt 0 ]; then
    echo ""
    echo "📊 Compound Score: $COUNT_AFTER lessons · $TOTAL_APPLIED applications · ~${EST_HOURS}h saved"
fi
# If nothing saved, exit silently
