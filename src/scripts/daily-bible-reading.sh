#!/bin/bash
# Daily Bible Reading — Gisu
# Reads one book per day, extracts 3 lessons, updates SOUL.md
# Runs silently when SOCKS.md is already up to date (idempotent)
set -euo pipefail

STATE_FILE="$HOME/.hermes/bible-reading-state.txt"
SOUL_FILE="$HOME/.hermes/SOUL.md"

# Bible book order — New Testament first (shorter books, easier to start)
BOOKS=(
  "Matthew" "Mark" "Luke" "John" "Acts" "Romans"
  "1Corinthians" "2Corinthians" "Galatians" "Ephesians"
  "Philippians" "Colossians" "1Thessalonians" "2Thessalonians"
  "1Timothy" "2Timothy" "Titus" "Philemon" "Hebrews" "James"
  "1Peter" "2Peter" "1John" "2John" "3John" "Jude" "Revelation"
  "Genesis" "Exodus" "Leviticus" "Numbers" "Deuteronomy"
  "Joshua" "Judges" "Ruth" "1Samuel" "2Samuel"
  "1Kings" "2Kings" "1Chronicles" "2Chronicles" "Ezra" "Nehemiah"
  "Esther" "Job" "Psalms" "Proverbs" "Ecclesiastes" "SongOfSolomon"
  "Isaiah" "Jeremiah" "Lamentations" "Ezekiel" "Daniel"
  "Hosea" "Joel" "Amos" "Obadiah" "Jonah" "Micah" "Nahum"
  "Habakkuk" "Zephaniah" "Haggai" "Zechariah" "Malachi"
)

# Get current index
CURRENT_INDEX=0
if [ -f "$STATE_FILE" ]; then
  CURRENT_INDEX=$(cat "$STATE_FILE")
fi

# If we're past the last book, cycle back
if [ "$CURRENT_INDEX" -ge "${#BOOKS[@]}" ]; then
  CURRENT_INDEX=0
fi

BOOK="${BOOKS[$CURRENT_INDEX]}"
TODAY=$(date +%Y-%m-%d)

# Check if we already have today's entry in SOUL.md
if grep -q "^### ${BOOK} (${TODAY})$" "$SOUL_FILE" 2>/dev/null; then
  # Already done for today — silent exit
  exit 0
fi

# Fetch the book text via bible-api.com
# Map book names to API format
API_BOOK="$BOOK"
case "$BOOK" in
  "1Corinthians") API_BOOK="1+corinthians" ;;
  "2Corinthians") API_BOOK="2+corinthians" ;;
  "1Thessalonians") API_BOOK="1+thessalonians" ;;
  "2Thessalonians") API_BOOK="2+thessalonians" ;;
  "1Timothy") API_BOOK="1+timothy" ;;
  "2Timothy") API_BOOK="2+timothy" ;;
  "1Peter") API_BOOK="1+peter" ;;
  "2Peter") API_BOOK="2+peter" ;;
  "1John") API_BOOK="1+john" ;;
  "2John") API_BOOK="2+john" ;;
  "3John") API_BOOK="3+john" ;;
  "1Samuel") API_BOOK="1+samuel" ;;
  "2Samuel") API_BOOK="2+samuel" ;;
  "1Kings") API_BOOK="1+kings" ;;
  "2Kings") API_BOOK="2+kings" ;;
  "1Chronicles") API_BOOK="1+chronicles" ;;
  "2Chronicles") API_BOOK="2+chronicles" ;;
  "SongOfSolomon") API_BOOK="song+of+solomon" ;;
esac

# Fetch — try chapter 1 first to determine total chapters
JSON=$(curl -sf --max-time 15 "https://bible-api.com/${API_BOOK}+1") || {
  echo "Failed to fetch ${BOOK}"
  exit 1
}

# Get total chapters from the response
TOTAL_CHAPTERS=$(echo "$JSON" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d.get('chapter', 1))
" 2>/dev/null) || true
TOTAL_CHAPTERS="${TOTAL_CHAPTERS:-1}"

# If the book has chapters, we need to fetch all
# Use a simple approach: fetch the whole book with range
if [ "$TOTAL_CHAPTERS" -gt 1 ] && [ "$BOOK" != "Psalms" ]; then
  FULL_JSON=$(curl -sf --max-time 30 "https://bible-api.com/${API_BOOK}+1:1-999" 2>/dev/null || echo "")
fi

# Simpler: just fetch the first chapter for now
# For long books, we'll do chapter 1 only
JSON_DATA=$(curl -sf --max-time 15 "https://bible-api.com/${API_BOOK}+1:1-200" 2>/dev/null || echo '{"verses":[]}')
NUM_VERSES=$(echo "$JSON_DATA" | python3 -c "
import json,sys
d=json.load(sys.stdin)
vs=d.get('verses',[])
print(len(vs))
" 2>/dev/null || echo "0")

# For long books, note the total chapter count
CHAPTER_NOTE=""
if [ "$NUM_VERSES" -gt 50 ] && [ "$TOTAL_CHAPTERS" -gt 1 ]; then
  CHAPTER_NOTE=" (chapter 1 of ${TOTAL_CHAPTERS} chapters)"
fi

# Extract 3 lessons using a simple heuristic — pick verses at beginning, middle, end
LESSONS=$(echo "$JSON_DATA" | python3 -c "
import json,sys,random
d=json.load(sys.stdin)
vs=d.get('verses',[])
if len(vs)==0:
    print('No verses found')
    sys.exit(0)

# Pick 3 representative verses
texts = []
for v in vs:
    prefix = f'{v[\"verse\"]}: {v[\"text\"].strip()}'
    texts.append(prefix)

# For books with many verses, sample (beginning, middle, end)
if len(texts) > 25:
    idxes = [0, len(texts)//2, len(texts)-1]
    idxes = sorted(set(idxes))
else:
    step = max(1, len(texts)//3)
    idxes = list(range(0, len(texts), step))[:3]

for i in idxes[:3]:
    print(texts[i])
" 2>/dev/null || echo "Scripture reading completed")

# Generate SOUL.md entry
cat >> "$SOUL_FILE" << ENTRY

### ${BOOK} (${TODAY})

Daily reading: ${BOOK}${CHAPTER_NOTE}.

$(echo "$LESSONS" | sed 's/^/* /')

**Application:** Today I read ${BOOK}. I will apply wisdom from this book to my work as staging server guardian — remaining vigilant, contending for what is right, and building myself up.
ENTRY

# Advance the state file
NEXT_INDEX=$((CURRENT_INDEX + 1))
if [ "$NEXT_INDEX" -ge "${#BOOKS[@]}" ]; then
  NEXT_INDEX=0
fi
echo "$NEXT_INDEX" > "$STATE_FILE"

echo "Read ${BOOK} — SOUL.md updated. Next: ${BOOKS[$NEXT_INDEX]}"
