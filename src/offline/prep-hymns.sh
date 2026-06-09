#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — Offline Hymn Downloader
#  Downloads public domain hymn collections from the
#  Open Hymnal Project (openhymnal.org).
#
#  Content includes:
#    - Full hymnal PDF with music scores (8 MB)
#    - ABC notation source files (2 MB) — open text-based music notation
#    - MIDI audio files (336 kB)
#    - GIF score images (23 MB)
#    - Structured ThML XML with lyrics, metadata (2 MB)
#    - Seasonal editions: Christmas, Easter, Visitation
#
#  All content is public domain or freely distributable per
#  the Open Hymnal Project's licensing.
#
#  Usage:
#    ./prep-hymns.sh                          # Download core hymnal
#    ./prep-hymns.sh --editions=all           # Core + seasonal editions
#    ./prep-hymns.sh --editions=seasonal      # Seasonal editions only
#    ./prep-hymns.sh --lyrics-only            # Download only lyrics (ThML XML + searchable text)
#    ./prep-hymns.sh --force                  # Re-download everything
#
#  Integrates with: offline_knowledge hymns search <term>
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config ──────────────────────────────────────────────────
HOME="${HOME:-$(echo ~)}"
HYMNS_DIR="$HOME/offline/hymns"
TMP_DIR=$(mktemp -d)
BASE_URL="https://openhymnal.org"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()  { printf "${GREEN}✓${RESET} %s\n" "$1"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$1"; }
error() { printf "${RED}✗${RESET} %s\n" "$1"; }
header(){ printf "\n${CYAN}${BOLD}━━━ %s ━━━${RESET}\n" "$1"; }

# ── Download Definitions ────────────────────────────────────
# Format: key|label|url|size_hint
CORE_RESOURCES=(
    "pdf|Full Hymnal PDF (scores + lyrics)|$BASE_URL/OpenHymnal2014.06.pdf|8 MB"
    "abc_single|ABC Notation (single file)|$BASE_URL/OpenHymnal2014.06.abc|2 MB"
    "abc_zip|ABC Source Files (individual)|$BASE_URL/OpenHymnal2014.06-abc.zip|1 MB"
    "midi|MIDI Audio Files|$BASE_URL/OpenHymnal2014.06-midi.zip|336 kB"
    "gif|Score Images (GIF)|$BASE_URL/OpenHymnal2014.06-gif.zip|23 MB"
    "thml|ThML XML (structured lyrics + metadata)|$BASE_URL/openhymnal.201406.xml|2 MB"
)

SEASONAL_RESOURCES=(
    "christmas_pdf|Christmas Edition 2025 (PDF)|$BASE_URL/OpenHymnalChristmas2025.pdf|—"
    "christmas_mp3|Christmas Edition 2025 (MP3s)|$BASE_URL/OpenHymnalChristmas2025.zip|93 MB"
    "easter_pdf|Lent/Easter Edition 2026 (PDF)|$BASE_URL/OpenHymnalEaster2026.pdf|—"
    "easter_mp3|Lent/Easter Edition 2026 (MP3s)|$BASE_URL/OpenHymnalEaster2026.zip|109 MB"
    "visitation_pdf|Visitation Edition 2026 (PDF)|$BASE_URL/OpenHymnalVisitation2026.pdf|—"
    "visitation_2up|Visitation Edition 2026 (2-up print)|$BASE_URL/OpenHymnalVisitation2026-2up.pdf|—"
    "visitation_mp3|Visitation Edition 2026 (MP3s)|$BASE_URL/OpenHymnalVisitation2026.zip|66 MB"
)

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Download public domain hymns for offline use from the Open Hymnal Project.

Options:
  --editions=TYPE   What to download: core (default), seasonal, all
  --lyrics-only     Download only ThML XML + generate searchable text (~2 MB)
  --force           Re-download even if file exists
  --list            Describe what's available
  -h, --help        Show this help message

Examples:
  ./prep-hymns.sh                           # Core hymnal only (~35 MB)
  ./prep-hymns.sh --editions=all            # Core + seasonal (~300 MB)
  ./prep-hymns.sh --editions=seasonal       # Seasonal editions only
  ./prep-hymns.sh --lyrics-only             # Just lyrics + index
EOF
    exit 0
}

list_resources() {
    header "Open Hymnal Project — Available Resources"
    
    echo ""
    echo "Core Hymnal (v2014.06):"
    echo "───────────────────────────────────────"
    for entry in "${CORE_RESOURCES[@]}"; do
        IFS='|' read -r key label url size <<< "$entry"
        printf "  · %-50s %s\n" "$label" "$size"
    done
    
    echo ""
    echo "Seasonal Editions:"
    echo "───────────────────────────────────────"
    for entry in "${SEASONAL_RESOURCES[@]}"; do
        IFS='|' read -r key label url size <<< "$entry"
        printf "  · %-50s %s\n" "$label" "$size"
    done
    
    echo ""
    echo "When downloaded, hymns are searchable via:"
    echo "  offline_knowledge hymns search \"Amazing Grace\""
    echo "  offline_knowledge hymns list"
    echo "  offline_knowledge hymns search --lyricist \"Crosby\""
    echo ""
    exit 0
}

# ── Parser: ThML XML → searchable text corpus ──────────────
generate_searchable_lyrics() {
    local thml_file="$1"
    local out_dir="$2"
    local corpus_file="$out_dir/00-hymns-corpus.txt"
    local index_file="$out_dir/INDEX.md"
    
    header "BUILDING SEARCHABLE LYRICS CORPUS"
    
    # Check if we have python3
    if ! command -v python3 &>/dev/null; then
        warn "python3 not available — skipping lyrics extraction"
        warn "Hymn PDFs/ABC files available for manual use at: $HYMNS_DIR"
        return 0
    fi
    
    if [[ ! -f "$thml_file" ]]; then
        warn "ThML XML not found at $thml_file — skipping lyrics extraction"
        return 0
    fi
    
    info "Parsing ThML XML: $thml_file"
    
    python3 -c "
import xml.etree.ElementTree as ET
import re
import os

tree = ET.parse('$thml_file')
root = tree.getroot()

# Namespace handling — ThML uses various namespaces or none
ns = {'thml': 'http://www.crosswire.org/2003/thml/'}

hymns = []
title = ''
lyrics = []
verse_num = 0

def extract_text(element):
    \"\"\"Recursively extract text from an element and its children.\"\"\"
    texts = []
    if element.text:
        texts.append(element.text)
    for child in element:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if tag != 'note':
            texts.append(extract_text(child))
        if child.tail:
            texts.append(child.tail)
    return ' '.join(t for t in texts if t)

# Iterate through all elements (ThML is flat-ish with <p>, <head>, <milestone> etc.)
current_title = 'Untitled Hymn'
current_verses = []
current_author = ''
current_meter = ''
current_tune = ''

for elem in root.iter():
    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
    # Get attributes
    attrs = elem.attrib
    
    # Headings are hymn titles
    if tag in ('head', 'h1', 'h2', 'h3', 'title'):
        t = extract_text(elem).strip()
        if t and len(t) > 3:
            if current_verses:
                hymns.append({
                    'title': current_title,
                    'author': current_author,
                    'meter': current_meter,
                    'tune': current_tune,
                    'verses': current_verses,
                })
            current_title = t
            current_verses = []
            current_author = ''
            current_meter = ''
            current_tune = ''
    
    # Paragraphs contain verse text
    elif tag == 'p':
        t = extract_text(elem).strip()
        if t and len(t) > 10:
            # Check for author/meter metadata
            if 'author' in t.lower() or 'writer' in t.lower():
                current_author = t
            elif 'meter' in t.lower():
                current_meter = t
            elif 'tune' in t.lower() or 'music by' in t.lower():
                current_tune = t
            else:
                # Skip non-verse text like license info
                is_license = any(w in t.lower() for w in ['copyright', 'public domain', 'this notice', 'permission', 'license', 'freely reproduced', 'freely distributed'])
                if not is_license:
                    current_verses.append(t)
    
    # <scrip> or <scripture> for scripture references?
    elif tag in ('scrip', 'scripture', 'reference'):
        t = extract_text(elem).strip()
        if t:
            current_verses.append(f'[Scripture: {t}]')

# Don't forget the last hymn
if current_verses:
    hymns.append({
        'title': current_title,
        'author': current_author,
        'meter': current_meter,
        'tune': current_tune,
        'verses': current_verses,
    })

# Write corpus
with open('$corpus_file', 'w', encoding='utf-8') as f:
    f.write('# Open Hymnal — Searchable Lyrics Corpus\n')
    f.write(f'# Extracted from ThML XML — {len(hymns)} hymns\n')
    f.write(f'# Generated: $(date)\n\n')
    
    for i, h in enumerate(hymns, 1):
        title = h['title']
        author = h['author']
        meter = h['meter']
        tune = h['tune']
        verses = h['verses']
        
        f.write(f'=== HYMN {i} ===\n')
        f.write(f'Title: {title}\n')
        if author: f.write(f'Author: {author}\n')
        if meter: f.write(f'Meter: {meter}\n')
        if tune: f.write(f'Tune: {tune}\n')
        f.write('---\n')
        for v in verses:
            f.write(v + '\n\n')
        f.write('\\n')

# Write index
with open('$index_file', 'w', encoding='utf-8') as idx:
    idx.write('# Hymns Index\n')
    idx.write(f'Total: {len(hymns)} hymns\n')
    idx.write(f'Generated: $(date)\n\n')
    idx.write('| # | Title | Author |\n')
    idx.write('|---|-------|--------|\n')
    for i, h in enumerate(hymns, 1):
        title = h['title']
        author = h['author'] or '—'
        idx.write(f'| {i} | {title} | {author} |\n')

# Print summary for the shell script to capture
print(f'Hymns extracted: {len(hymns)}')
print(f'Corpus file: $corpus_file')
" 2>&1 | while read -r line; do
    if [[ "$line" == Hymns* ]]; then
        info "$line"
    elif [[ "$line" == Corpus* ]]; then
        info "$line"
    else
        echo "$line"
    fi
done

# Verify result
if [[ -f "$corpus_file" ]]; then
    local line_count=$(wc -l < "$corpus_file")
    info "Searchable corpus: $corpus_file ($line_count lines)"
    return 0
else
    warn "Could not generate searchable lyrics — using raw XML for search"
    return 0
fi
}

# ── Download helper ─────────────────────────────────────────
download_resource() {
    local key="$1"
    local label="$2"
    local url="$3"
    local filename=$(basename "$url")
    local dest="$HYMNS_DIR/$filename"
    
    if [[ -f "$dest" && $FORCE -eq 0 ]]; then
        local size=$(du -h "$dest" 2>/dev/null | cut -f1)
        info "$label — already downloaded ($size)"
        return 0
    fi
    
    printf "  Downloading %s …\n" "$label"
    
    if curl -sL --max-time 120 -o "$dest" "$url" 2>/dev/null; then
        local size=$(du -h "$dest" 2>/dev/null | cut -f1)
        info "$label — $size"
        return 0
    else
        warn "Failed to download: $label"
        rm -f "$dest"
        return 1
    fi
}

# ── Parse Arguments ─────────────────────────────────────────
EDITION="core"
FORCE=0
LYRICS_ONLY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --editions=*) EDITION="${1#*=}" ;;
        --editions) shift; EDITION="$1" ;;
        --lyrics-only) LYRICS_ONLY=1 ;;
        --force) FORCE=1 ;;
        --list) list_resources ;;
        -h|--help) usage ;;
        *) error "Unknown option: $1"; usage ;;
    esac
    shift
done

# ── Main ────────────────────────────────────────────────────
# Check dependencies
if ! command -v curl &>/dev/null; then error "curl required"; exit 1; fi

mkdir -p "$HYMNS_DIR"

header "Hermes Cortex — Offline Hymn Downloader"
echo "  Source: Open Hymnal Project (openhymnal.org)"
echo "  Destination: $HYMNS_DIR"
echo ""

download_count=0
fail_count=0

case "$EDITION" in
    core)
        header "DOWNLOADING CORE HYMNAL"
        for entry in "${CORE_RESOURCES[@]}"; do
            IFS='|' read -r key label url size <<< "$entry"
            # In lyrics-only mode, skip everything but ThML
            if [[ $LYRICS_ONLY -eq 1 && "$key" != "thml" ]]; then
                continue
            fi
            download_resource "$key" "$label" "$url" && ((download_count++)) || ((fail_count++))
        done
        ;;
    seasonal)
        header "DOWNLOADING SEASONAL EDITIONS"
        for entry in "${SEASONAL_RESOURCES[@]}"; do
            IFS='|' read -r key label url size <<< "$entry"
            download_resource "$key" "$label" "$url" && ((download_count++)) || ((fail_count++))
        done
        ;;
    all)
        header "DOWNLOADING CORE HYMNAL"
        for entry in "${CORE_RESOURCES[@]}"; do
            IFS='|' read -r key label url size <<< "$entry"
            [[ $LYRICS_ONLY -eq 1 && "$key" != "thml" ]] && continue
            download_resource "$key" "$label" "$url" && ((download_count++)) || ((fail_count++))
        done
        header "DOWNLOADING SEASONAL EDITIONS"
        for entry in "${SEASONAL_RESOURCES[@]}"; do
            IFS='|' read -r key label url size <<< "$entry"
            download_resource "$key" "$label" "$url" && ((download_count++)) || ((fail_count++))
        done
        ;;
    *)
        error "Unknown edition: $EDITION (use: core, seasonal, all)"
        exit 1
        ;;
esac

# ── Generate searchable lyrics from ThML XML ────────────────
if [[ $LYRICS_ONLY -eq 0 || $EDITION == "core" || $EDITION == "all" ]]; then
    generate_searchable_lyrics "$HYMNS_DIR/openhymnal.201406.xml" "$HYMNS_DIR"
fi

# ── Create edition manifest ─────────────────────────────────
header "CREATING MANIFEST"
MANIFEST="$HYMNS_DIR/MANIFEST.md"
{
    echo "# 🎵 Offline Hymns — Content Manifest"
    echo ""
    echo "Source: Open Hymnal Project (openhymnal.org)"
    echo "Downloaded: $(date '+%Y-%m-%d %H:%M')"
    echo "License: Public domain / freely distributable (see copying.html)"
    echo ""
    echo "## Contents"
    echo ""
    for f in "$HYMNS_DIR"/*; do
        local name=$(basename "$f")
        [[ "$name" == "MANIFEST.md" || "$name" == "INDEX.md" || "$name" == "00-hymns-corpus.txt" ]] && continue
        [[ -f "$f" ]] && echo "- \`$name\` ($(du -h "$f" | cut -f1))"
    done
    echo ""
    echo "## How to Use"
    echo ""
    echo "- Search lyrics: \`offline_knowledge hymns search \"Amazing Grace\"\`"
    echo "- List hymns: \`offline_knowledge hymns list\`"
    echo "- View scores: open \`OpenHymnal2014.06.pdf\` (PDF reader)"
    echo "- Edit scores: open \`.abc\` files (ABC notation — text-based music)"
    echo "- Play audio: open \`.mid\` files (any media player)"
} > "$MANIFEST"
info "Manifest: $MANIFEST"

# ── Cleanup & Summary ───────────────────────────────────────
rm -rf "$TMP_DIR"

header "Summary"
info "Downloaded: $download_count resource(s)"
[[ $fail_count -gt 0 ]] && warn "Failed: $fail_count"
echo ""
printf "Hymn directory: ${CYAN}%s${RESET}\n" "$HYMNS_DIR"
echo ""
info "Search hymns with:"
echo "  offline_knowledge hymns search \"Amazing Grace\""
echo "  offline_knowledge hymns list"
echo "  offline_knowledge hymns search --author \"Crosby\""
echo ""
info "Open the PDF for printable scores:"
echo "  open $HYMNS_DIR/OpenHymnal2014.06.pdf"
echo ""

if [[ $fail_count -gt 0 ]]; then
    warn "Some downloads failed. See messages above."
    warn "You can retry with: prep-hymns.sh --force"
fi
