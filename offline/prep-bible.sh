#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — Offline Bible Downloader
#  Downloads Bible translations in plain text for offline use.
#  Integrates with the offline_knowledge cascade.
#
#  Usage:
#    ./prep-bible.sh                         # Interactive menu
#    ./prep-bible.sh --langs=all             # Every available translation
#    ./prep-bible.sh --langs=en,ko,zh        # Specific languages
#    ./prep-bible.sh --langs=en              # Just English (default)
#    ./prep-bible.sh --zim-only              # Only create ZIM (no text)
#
#  Bible text sources (all public domain):
#    - Project Gutenberg (KJV, ASV, WEB, YLT)
#    - eBible.org (multi-language public domain translations)
#
#  Requirements: python3, curl
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config ──────────────────────────────────────────────────
HOME="${HOME:-$(echo ~)}"
BIBLE_DIR="$HOME/offline/bible"
ZIM_DIR="$HOME/offline/zim"
TMP_DIR=$(mktemp -d)

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()  { printf "${GREEN}✓${RESET} %s\n" "$1"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$1"; }
error() { printf "${RED}✗${RESET} %s\n" "$1"; }
header(){ printf "\n${CYAN}${BOLD}━━━ %s ━━━${RESET}\n" "$1"; }

# ── Bible Translation Definitions ───────────────────────────
# Format: code|language|translation_name|source_type:source_id
# source_type: pg=Project Gutenberg, url=direct download URL
BIBLES=(
    "en|English|King James Version (KJV)|pg:10"
    "en|English|World English Bible (WEB)|pg:8294"
    "en|English|American Standard Version (ASV)|pg:30"
    "en|English|Young's Literal Translation (YLT)|pg:7183"
    "af|Afrikaans|Bybel (1953)|url:https://ebible.org/SAL"
    "ar|Arabic|Arabic Bible (Smith & Van Dyke)|url:https://ebible.org/arabicsv"
    "bg|Bulgarian|Библия (1940)|url:https://ebible.org/bul1940"
    "ceb|Cebuano|Bibliya (Bugna)|url:https://ebible.org/cebb"
    "cs|Czech|Bible kralická (1613)|url:https://ebible.org/cskr"
    "da|Danish|Bibelen (1933)|url:https://ebible.org/dan1933"
    "de|German|Lutherbibel (1912)|url:https://ebible.org/deul12"
    "el|Greek|Η Αγία Γραφή (Vamvas)|url:https://ebible.org/grd"
    "es|Spanish|Reina-Valera (1909)|url:https://ebible.org/sp"
    "fa|Persian|کتاب مقدس (Old Persian)|url:https://ebible.org/fas"
    "fi|Finnish|Pyhä Raamattu (1938)|url:https://ebible.org/fi1938"
    "fr|French|Louis Segond (1910)|url:https://ebible.org/frlsg"
    "gu|Gujarati|ગુજરાતી બાઇબલ|url:https://ebible.org/guj"
    "he|Hebrew|תנ״ך (Westminster Leningrad)|url:https://ebible.org/hebl"
    "hi|Hindi|पवित्र बाइबल (IRV)|url:https://ebible.org/hin"
    "hu|Hungarian|Biblia (Karoli)|url:https://ebible.org/hu"
    "id|Indonesian|Alkitab (TB)|url:https://ebible.org/ind"
    "is|Icelandic|Biblían (1912)|url:https://ebible.org/is1912"
    "it|Italian|Giovanni Diodati (1649)|url:https://ebible.org/itdd"
    "ja|Japanese|口語訳聖書 (1955)|url:https://ebible.org/jpn"
    "ko|Korean|개역한글 (1961)|url:https://ebible.org/kor"
    "la|Latin|Biblia Sacra Vulgata|url:https://ebible.org/lav"
    "ml|Malayalam|പരിശുദ്ധ ബൈബിൾ|url:https://ebible.org/mal"
    "mr|Marathi|मराठी बायबल|url:https://ebible.org/mar"
    "my|Burmese|မြန်မာကျမ်းစာ|url:https://ebible.org/my"
    "ne|Nepali|नेपाली बाइबल|url:https://ebible.org/nep"
    "nl|Dutch|Statenvertaling (1637)|url:https://ebible.org/dut"
    "no|Norwegian|Bibelen (1930)|url:https://ebible.org/no1930"
    "pa|Punjabi|ਪੰਜਾਬੀ ਬਾਈਬਲ|url:https://ebible.org/pai"
    "pl|Polish|Biblia Gdańska (1632)|url:https://ebible.org/pbg"
    "pt|Portuguese|João Ferreira de Almeida (1819)|url:https://ebible.org/por"
    "ro|Romanian|Biblia (Cornilescu)|url:https://ebible.org/roc"
    "ru|Russian|Синодальный перевод (1876)|url:https://ebible.org/rus"
    "sk|Slovak|Sväté Písmo|url:https://ebible.org/slo"
    "so|Somali|Kitaabka Quduuska Ah|url:https://ebible.org/som"
    "sq|Albanian|Bibla Shqiptare|url:https://ebible.org/sq"
    "sr|Serbian|Свето Писмо|url:https://ebible.org/sr"
    "sv|Swedish|Bibeln (1917)|url:https://ebible.org/sv1917"
    "sw|Swahili|Biblia Ya Kiswahili|url:https://ebible.org/sw"
    "ta|Tamil|பரிசுத்த வேதாகமம்|url:https://ebible.org/tam"
    "te|Telugu|పరిశుద్ధ గ్రంథము|url:https://ebible.org/tel"
    "th|Thai|พระคัมภีร์ไบเบิล (KJV Thai)|url:https://ebible.org/tha"
    "tl|Tagalog|Ang Biblia (1905)|url:https://ebible.org/tl"
    "tr|Turkish|Kutsal Kitap (TDV)|url:https://ebible.org/tur"
    "uk|Ukrainian|Біблія (Огієнко)|url:https://ebible.org/ukr"
    "ur|Urdu|مقدس کتاب|url:https://ebible.org/urd"
    "vi|Vietnamese|Kinh Thánh (1934)|url:https://ebible.org/vie"
    "zh|Chinese|和合本 (1919)|url:https://ebible.org/chi"
    "zh-hk|Chinese (HK)|新標點和合本|url:https://ebible.org/chih"
    "zh-tw|Chinese (TW)|現代中文譯本|url:https://ebible.org/chi2"
)

# ── Language groups ─────────────────────────────────────────
LANGS_ALL=$(printf '%s\n' "${BIBLES[@]}" | cut -d'|' -f1 | sort -u | tr '\n' ',' | sed 's/,$//')
LANGS_MAJOR="en,es,fr,de,pt,zh,ru,ja,ko,ar,hi,it,nl,pl,id,vi,th,tr"
LANGS_REGIONAL="sw,so,am,tl,gu,ml,te,ta,pa,ne,my,km,ur,fa,he,el,la"

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Download Bible translations for offline use.

Options:
  --langs=LANG_CODES   Language codes to download (comma-separated, e.g. en,es,ko)
                       Special values: all, major, regional
  --list               List all available translations
  --zim-only           Only attempt to fetch/create ZIM (not yet implemented)
  --force              Re-download even if file exists
  -h, --help           Show this help message

Examples:
  ./prep-bible.sh --langs=en              # English translations only
  ./prep-bible.sh --langs=all             # All 55+ translations
  ./prep-bible.sh --langs=major           # 18 major world languages
  ./prep-bible.sh --langs=en,ko,zh,ru     # Specific languages
EOF
    exit 0
}

list_bibles() {
    header "Available Bible Translations"
    printf "%-6s %-12s %-40s %s\n" "Code" "Language" "Translation" "Source"
    printf "%-6s %-12s %-40s %s\n" "────" "───────────" "──────────────────────────" "──────"
    local last_lang=""
    for entry in "${BIBLES[@]}"; do
        IFS='|' read -r code lang name source <<< "$entry"
        if [[ "$code" != "$last_lang" ]]; then
            printf "%-6s %-12s %-40s %s\n" "$code" "$lang" "$name" "$source"
            last_lang="$code"
        else
            printf "%-6s %-12s %-40s %s\n" "" "" "$name" "$source"
        fi
    done
    printf "\nTotal: %d translations in %d languages\n" "${#BIBLES[@]}" "$(printf '%s\n' "${BIBLES[@]}" | cut -d'|' -f1 | sort -u | wc -l)"
    exit 0
}

# ── Parse arguments ─────────────────────────────────────────
LANGS="en"
FORCE=0
ZIM_ONLY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --langs=*) LANGS="${1#*=}" ;;
        --langs) shift; LANGS="$1" ;;
        --list) list_bibles ;;
        --zim-only) ZIM_ONLY=1 ;;
        --force) FORCE=1 ;;
        -h|--help) usage ;;
        *) error "Unknown option: $1"; usage ;;
    esac
    shift
done

# Resolve special language groups
if [[ "$LANGS" == "all" ]]; then
    LANGS="$LANGS_ALL"
elif [[ "$LANGS" == "major" ]]; then
    LANGS="$LANGS_MAJOR"
elif [[ "$LANGS" == "regional" ]]; then
    LANGS="$LANGS_REGIONAL"
fi

IFS=',' read -ra LANG_CODES <<< "$LANGS"

# ── Download Functions ──────────────────────────────────────

download_pg_bible() {
    local pg_id="$1"
    local code="$2"
    local name="$3"
    local out_dir="$4"
    local out_file="$out_dir/pg${pg_id}_${code}.txt"

    if [[ -f "$out_file" && $FORCE -eq 0 ]]; then
        info "Already downloaded: $out_file $(wc -c < "$out_file" 2>/dev/null) bytes"
        return 0
    fi

    info "Downloading $name (PG #$pg_id)..."
    local url="https://www.gutenberg.org/cache/epub/${pg_id}/pg${pg_id}.txt"
    local tmp_txt=$(mktemp)

    if curl -sL --max-time 30 "$url" -o "$tmp_txt" 2>/dev/null; then
        # Strip PG header/footer, extract just the Bible text
        awk '
            /^\\*\\*\\* START OF (THE|THIS) PROJECT/ { found=1; next }
            /^\\*\\*\\* END OF (THE|THIS) PROJECT/ { exit }
            found
        ' "$tmp_txt" > "$out_file" 2>/dev/null || cp "$tmp_txt" "$out_file"
        info "  Saved: $(wc -c < "$out_file") bytes to $(basename "$out_file")"
    else
        warn "  Failed to download PG #$pg_id"
        return 1
    fi
}

download_ebible() {
    local url="$1"
    local code="$2"
    local name="$3"
    local out_dir="$4"
    # eBible.org provides downloadable files. We try a few common patterns.
    # Most have a simple text download at {url}.txt or similar
    local downloaded=0
    local tmp_txt=$(mktemp)

    # Try several known download patterns
    for suffix in ".txt" "/download" "/plain"; do
        local dl_url="${url}${suffix}"
        local out_file="$out_dir/ebible_${code}.txt"
        if [[ -f "$out_file" && $FORCE -eq 0 ]]; then
            info "Already downloaded: $name ($code)"
            downloaded=1
            break
        fi
        if curl -sL --max-time 15 -o "$tmp_txt" "$dl_url" 2>/dev/null; then
            local size=$(wc -c < "$tmp_txt" 2>/dev/null)
            if [[ $size -gt 1000 ]]; then
                cp "$tmp_txt" "$out_file"
                info "  $name ($code): $size bytes"
                downloaded=1
                break
            fi
        fi
    done

    if [[ $downloaded -eq 0 ]]; then
        warn "  Could not download $name ($code) — create placeholder"
        echo "Download for ${name} (${code}) not yet available." > "$out_dir/SOURCE_${code}.md"
        warn "  Created placeholder at SOURCE_${code}.md. You can add the text manually."
    fi
}

# ── Main ─────────────────────────────────────────────────────

# Check dependencies
if ! command -v curl &>/dev/null; then error "curl required"; exit 1; fi

mkdir -p "$BIBLE_DIR"

header "Hermes Cortex — Offline Bible Downloader"

# Check if kiwix-tools is available for ZIM creation
KIWIX_TOOLS=0
if command -v zimwriterfs &>/dev/null; then
    KIWIX_TOOLS=1
fi

total=${#LANG_CODES[@]}
downloaded=0
skipped=0
failed=0

printf "Downloading %d language(s) to %s\n\n" "$total" "$BIBLE_DIR"

for code in "${LANG_CODES[@]}"; do
    code=$(echo "$code" | xargs)  # trim
    [[ -z "$code" ]] && continue

    matches=0
    for entry in "${BIBLES[@]}"; do
        IFS='|' read -r entry_code lang name source <<< "$entry"
        if [[ "$entry_code" == "$code" ]]; then
            ((matches++))

            if [[ "$source" == pg:* ]]; then
                pg_id="${source#pg:}"
                download_pg_bible "$pg_id" "$code" "$name" "$BIBLE_DIR" && ((downloaded++)) || ((failed++))
            elif [[ "$source" == url:* ]]; then
                dl_url="${source#url:}"
                download_ebible "$dl_url" "$code" "$name" "$BIBLE_DIR" && ((downloaded++)) || ((failed++))
            fi
        fi
    done

    if [[ $matches -eq 0 ]]; then
        warn "No translation found for language code: $code"
        ((failed++))
    fi
done

# ── Post-process: Parse to JSON ────────────────────────────
header "PARSING TO STRUCTURED JSON"
PARSE_SCRIPT="$HOME/hermes-cortex/offline/bible-parse.py"
parse_ok=0
parse_fail=0

if [[ ! -f "$PARSE_SCRIPT" ]]; then
    warn "bible-parse.py not found — skipping JSON generation"
else
    for txt_file in "$BIBLE_DIR"/*.txt; do
        [[ -f "$txt_file" ]] || continue
        local json_file="${txt_file%.txt}.json"
        # Skip if JSON already exists and is newer than the txt
        if [[ -f "$json_file" && "$json_file" -nt "$txt_file" ]]; then
            info "JSON already up-to-date: $(basename "$json_file")"
            ((parse_ok++))
            continue
        fi
        printf "  Parsing %s … " "$(basename "$txt_file")"
        if python3 "$PARSE_SCRIPT" "$txt_file" --output "$json_file" 2>/dev/null; then
            printf "✓\n"
            ((parse_ok++))
        else
            printf "✗\n"
            warn "  Failed to parse: $(basename "$txt_file")"
            ((parse_fail++))
        fi
    done
    if [[ $parse_ok -gt 0 ]]; then
        info "Parsed $parse_ok translation(s) to JSON"
    fi
    if [[ $parse_fail -gt 0 ]]; then
        warn "$parse_fail translation(s) could not be parsed — raw .txt still available"
    fi
fi

# ── Create index ────────────────────────────────────────────
header "Creating Bible Index"
INDEX_FILE="$BIBLE_DIR/INDEX.md"
{
    echo "# 📖 Offline Bible Translations"
    echo ""
    echo "Downloaded on $(date '+%Y-%m-%d %H:%M')"
    echo ""
    echo "| Language | Translation | File | Size |"
    echo "|----------|-------------|------|------|"
} > "$INDEX_FILE"

find "$BIBLE_DIR" -name "*.txt" -o -name "SOURCE_*.md" | sort | while read -r f; do
    fname=$(basename "$f")
    size=$(wc -c < "$f" 2>/dev/null | tr -d ' ')
    if [[ $size -gt 1000000 ]]; then
        size_hr=$(echo "scale=1; $size/1000000" | bc)
        size_str="${size_hr} MB"
    elif [[ $size -gt 1000 ]]; then
        size_hr=$(echo "scale=0; $size/1000" | bc)
        size_str="${size_hr} KB"
    else
        size_str="${size} B"
    fi
    echo "| $fname | — | $fname | $size_str |" >> "$INDEX_FILE"
done

echo "" >> "$INDEX_FILE"
echo "Search with: \`offline_knowledge bible search \"query\"\`" >> "$INDEX_FILE"

# ── Create simple HTML for kiwix-serve compatibility (optional) ──
# Bible texts can also be served as plain files. No ZIM conversion needed.

# ── Cleanup & Summary ───────────────────────────────────────
rm -rf "$TMP_DIR"

header "Summary"
info "Downloaded: $downloaded"
[[ $skipped -gt 0 ]] && warn "Skipped: $skipped"
[[ $failed -gt 0 ]] && warn "Failed: $failed"
echo ""
printf "Bible texts:  ${CYAN}%s${RESET}\n" "$BIBLE_DIR"
printf "Index:        ${CYAN}%s${RESET}\n" "$INDEX_FILE"
echo ""
info "Use offline_knowledge to search:"
echo "  offline_knowledge bible search \"John 3:16\""
echo "  offline_knowledge bible search \"faith\" --lang en"
echo "  offline_knowledge bible search --list-languages"
echo ""

if [[ $failed -gt 0 ]]; then
    warn "Some downloads failed. See messages above."
    warn "You can manually add Bible texts to: $BIBLE_DIR"
    exit 1
fi
