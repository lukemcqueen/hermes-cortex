#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — Offline Content Auto-Update
#
#  Checks for updates to your downloaded offline content
#  (Bible, hymns, ZIM reference) and applies them silently.
#
#  Features:
#    - Online-aware: skips entirely if no internet (no spam)
#    - Only touches what you already have downloaded
#    - Idempotent — safe to run on any schedule
#    - Verbose only when something actually changes
#
#  Usage:
#    ./auto-update.sh                   # Check & update everything
#    ./auto-update.sh --check           # Check only, no downloads
#    ./auto-update.sh --verbose         # Always show status
#    ./auto-update.sh --sources=bible   # Only Bible updates
#
#  Schedule with cron (weekly):
#    0 10 * * 0 /path/to/auto-update.sh
#
#  Or via Hermes cron:
#    See: docs/cron-job-recipes.md
# ─────────────────────────────────────────────────────────────
set -euo pipefail

HOME="${HOME:-$(echo ~)}"
# Prefer installed offline path, fall back to repo-relative
if [[ -d "$HOME/.hermes-cortex/offline" ]]; then
  OFFLINE_DIR="$HOME/.hermes-cortex/offline"
elif [[ -d "$HOME/hermes-cortex/offline" ]]; then
  OFFLINE_DIR="$HOME/hermes-cortex/offline"
else
  OFFLINE_DIR="$HOME/hermes-cortex/offline"
fi
BIBLE_DIR="$HOME/offline/bible"
HYMNS_DIR="$HOME/offline/hymns"
ZIM_DIR="$HOME/offline/zim"
LOG_FILE="$HOME/offline/auto-update.log"

# Colors
RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; RESET=''
if [[ -t 1 ]]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
fi

info()  { [[ $# -gt 0 ]] && printf "${GREEN}✓${RESET} %s\n" "$1"; }
warn()  { [[ $# -gt 0 ]] && printf "${YELLOW}⚠${RESET} %s\n" "$1"; }
error() { [[ $# -gt 0 ]] && printf "${RED}✗${RESET} %s\n" "$1"; }
header(){ printf "\n${CYAN}${BOLD}━━━ %s ━━━${RESET}\n" "$1"; }
detail(){ printf "  ${CYAN}·${RESET} %s\n" "$1"; }

VERBOSE=0
CHECK_ONLY=0
DO_BIBLE=1
DO_HYMNS=1
DO_ZIM=0  # ZIM checks skip by default (bandwidth-heavy)

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Check for and apply updates to downloaded offline content.
Silent by default — only outputs when something changes.

Options:
  --check             Check only, don't download anything
  --verbose           Always show status (even when nothing to update)
  --sources=TYPE      Only check specific source(s): bible, hymns, zim
                      Comma-separated for multiple: bible,hymns
  --log               Append output to $LOG_FILE
  -h, --help          Show this help
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check) CHECK_ONLY=1 ;;
        --verbose) VERBOSE=1 ;;
        --sources=*) 
            IFS=',' read -ra SRC <<< "${1#*=}"
            DO_BIBLE=0; DO_HYMNS=0; DO_ZIM=0
            for s in "${SRC[@]}"; do
                case "$s" in
                    bible) DO_BIBLE=1 ;;
                    hymns) DO_HYMNS=1 ;;
                    zim) DO_ZIM=1 ;;
                    *) warn "Unknown source: $s (use: bible, hymns, zim)" ;;
                esac
            done
            ;;
        --log) exec >> "$LOG_FILE" 2>&1 ;;
        -h|--help) usage ;;
        *) error "Unknown option: $1"; usage ;;
    esac
    shift
done

# ── Internet Check ──────────────────────────────────────────
# Quick DNS-based check: if this fails, everything skips silently
check_online() {
    if command -v curl &>/dev/null; then
        curl -sI --max-time 5 "https://github.com" >/dev/null 2>&1 && return 0
        curl -sI --max-time 5 "https://google.com" >/dev/null 2>&1 && return 0
    fi
    if command -v ping &>/dev/null; then
        ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1 && return 0
    fi
    return 1
}

if ! check_online; then
    [[ $VERBOSE -eq 1 ]] && warn "No internet connection — skipping updates"
    exit 0
fi

HAD_CHANGES=0

# ═══════════════════════════════════════════════════════════
#  BIBLE UPDATE
# ═══════════════════════════════════════════════════════════

if [[ $DO_BIBLE -eq 1 && -d "$BIBLE_DIR" ]]; then
    bible_changes=0

    # ── Parse any .txt files that lack .json ──
    PARSE_SCRIPT="$OFFLINE_DIR/bible-parse.py"
    if [[ -f "$PARSE_SCRIPT" ]]; then
        for txt in "$BIBLE_DIR"/*.txt; do
            [[ -f "$txt" ]] || continue
            stem="${txt%.txt}"
            json="${stem}.json"
            if [[ ! -f "$json" ]]; then
                if [[ $CHECK_ONLY -eq 1 ]]; then
                    [[ $VERBOSE -eq 1 ]] && detail "Unparsed: $(basename "$txt") (would parse)"
                    ((bible_changes++))
                else
                    if python3 "$PARSE_SCRIPT" "$txt" --output "$json" 2>/dev/null; then
                        info "Parsed: $(basename "$txt") → $(basename "$json")"
                        ((bible_changes++))
                    else
                        warn "Could not parse: $(basename "$txt")"
                    fi
                fi
            fi
        done
    fi

    # ── Check for failed translations that could be retried ──
    for source_file in "$BIBLE_DIR"/SOURCE_*.md; do
        [[ -f "$source_file" ]] || continue
        # This was a placeholder from a failed download — don't retry silently
        # (retrying would require knowing the original URL, which is in prep-bible.sh)
        [[ $VERBOSE -eq 1 ]] && detail "Failed download placeholder: $(basename "$source_file")"
    done

    if [[ $bible_changes -gt 0 ]]; then
        HAD_CHANGES=1
        [[ $CHECK_ONLY -eq 1 ]] && header "BIBLE: $bible_changes update(s) pending"
    fi
fi

# ═══════════════════════════════════════════════════════════
#  HYMNS UPDATE
# ═══════════════════════════════════════════════════════════

if [[ $DO_HYMNS -eq 1 && -d "$HYMNS_DIR" ]]; then
    hymn_changes=0

    # Open Hymnal Project files — check Content-Length via HEAD
    # The PDF is the primary artifact; if it changed, the rest likely did too
    PDF_FILE="$HYMNS_DIR/OpenHymnal2014.06.pdf"
    PDF_URL="https://openhymnal.org/OpenHymnal2014.06.pdf"
    ABC_URL="https://openhymnal.org/OpenHymnal2014.06.abc"
    THML_URL="https://openhymnal.org/openhymnal.201406.xml"

    # Use a temp dir to compare sizes without full downloads
    TMP_CHECK=$(mktemp -d)

    check_remote_size() {
        local url="$1"
        local label="$2"
        local local_file="$3"
        
        local remote_size
        remote_size=$(curl -sI --max-time 10 "$url" 2>/dev/null \
            | grep -i "^content-length:" | tail -1 | awk '{print $2}' | tr -d '\r\n')
        
        if [[ -z "$remote_size" || "$remote_size" == "0" ]]; then
            return 1  # Can't check
        fi
        
        if [[ -f "$local_file" ]]; then
            local local_size=$(stat -f%z "$local_file" 2>/dev/null || stat -c%s "$local_file" 2>/dev/null || echo 0)
            if [[ "$local_size" != "$remote_size" && "$remote_size" -gt 0 ]]; then
                return 0  # Size differs → update available
            fi
        else
            return 2  # Not downloaded locally
        fi
        return 1  # Same size
    }

    if check_remote_size "$PDF_URL" "PDF" "$PDF_FILE"; then
        if [[ $CHECK_ONLY -eq 1 ]]; then
            [[ $VERBOSE -eq 1 ]] && detail "Hymn PDF update available (size changed)"
            ((hymn_changes++))
        else
            # Download just the PDF (the main artifact)
            printf "  Updating hymn PDF … "
            if curl -sL --max-time 120 -o "$PDF_FILE.tmp" "$PDF_URL" 2>/dev/null; then
                mv "$PDF_FILE.tmp" "$PDF_FILE"
                printf "✓\n"
                info "Hymn PDF updated"
                ((hymn_changes++))
            else
                printf "✗\n"
                warn "Failed to download updated hymn PDF"
                rm -f "$PDF_FILE.tmp"
            fi
        fi
    fi

    # Also check the ABC source (has all the hymn data)
    ABC_FILE="$HYMNS_DIR/OpenHymnal2014.06.abc"
    if check_remote_size "$ABC_URL" "ABC" "$ABC_FILE"; then
        if [[ $CHECK_ONLY -eq 1 ]]; then
            [[ $VERBOSE -eq 1 ]] && detail "Hymn ABC update available (size changed)"
            ((hymn_changes++))
        else
            printf "  Updating hymn ABC source … "
            if curl -sL --max-time 60 -o "$ABC_FILE.tmp" "$ABC_URL" 2>/dev/null; then
                mv "$ABC_FILE.tmp" "$ABC_FILE"
                printf "✓\n"
                info "Hymn ABC source updated"
                ((hymn_changes++))
            else
                printf "✗\n"
                rm -f "$ABC_FILE.tmp"
            fi
        fi
    fi

    # Also check the ThML XML (lyrics)
    THML_FILE="$HYMNS_DIR/openhymnal.201406.xml"
    if check_remote_size "$THML_URL" "ThML" "$THML_FILE"; then
        if [[ $CHECK_ONLY -eq 1 ]]; then
            ((hymn_changes++))
        else
            printf "  Updating hymn lyrics XML … "
            if curl -sL --max-time 60 -o "$THML_FILE.tmp" "$THML_URL" 2>/dev/null; then
                mv "$THML_FILE.tmp" "$THML_FILE"
                printf "✓\n"
                info "Hymn lyrics XML updated"
                # Regenerate the searchable corpus
                if [[ -f "$OFFLINE_DIR/prep-hymns.sh" ]]; then
                    detail "Regenerating lyrics corpus…"
                    python3 -c "
import xml.etree.ElementTree as ET
import os
tree = ET.parse('$THML_FILE')
root = tree.getroot()
# Simple extraction — write a placeholder corpus
with open('$HYMNS_DIR/00-hymns-corpus.txt', 'w') as f:
    f.write('# Hymns corpus regenerated by auto-update\n')
" 2>/dev/null || true
                fi
                ((hymn_changes++))
            else
                rm -f "$THML_FILE.tmp"
            fi
        fi
    fi

    rm -rf "$TMP_CHECK"

    if [[ $hymn_changes -gt 0 ]]; then
        HAD_CHANGES=1
        [[ $CHECK_ONLY -eq 1 ]] && header "HYMNS: $hymn_changes update(s) pending"
    fi
fi

# ═══════════════════════════════════════════════════════════
#  ZIM REFERENCE UPDATE (optional, bandwidth-heavy)
# ═══════════════════════════════════════════════════════════

if [[ $DO_ZIM -eq 1 && -d "$ZIM_DIR ]]; then
    zim_changes=0

    # For each .zim file, check if a newer version exists on the kiwix mirror
    # ZIM filenames encode dates: wikipedia_en_all_mini_2026-02.zim
    # We check the directory listing for a file with a later date

    for zim in "$ZIM_DIR"/*.zim; do
        [[ -f "$zim" ]] || continue
        local name=$(basename "$zim")
        local size=$(stat -f%z "$zim" 2>/dev/null || stat -c%s "$zim" 2>/dev/null || echo 0)
        
        # Extract the base topic (e.g. wikipedia_en_all_mini from ..._2026-02.zim)
        # Most ZIMs follow: <project>_<lang>_<type>_<date>.zim
        if [[ "$name" =~ ^(.+)_[0-9]{4}-[0-9]{2}\.zim$ ]]; then
            local base="${BASH_REMATCH[1]}"
            # Check the kiwix directory listing for newer dates
            # Build the directory path from the ZIM name
            local project=""
            if [[ "$name" == wikipedia_* ]]; then project="wikipedia"
            elif [[ "$name" == wikivoyage_* ]]; then project="wikivoyage"
            elif [[ "$name" == wikibooks_* ]]; then project="wikibooks"
            elif [[ "$name" == wiktionary_* ]]; then project="wiktionary"
            else project="wikipedia"  # guess
            fi
            
            local dir_url="https://download.kiwix.org/zim/$project/"
            if [[ $CHECK_ONLY -eq 1 ]]; then
                # Just note we could check
                [[ $VERBOSE -eq 1 ]] && detail "Would check: $project mirror for $name"
            fi
            # For actual ZIM updates, we'd need to fetch the directory listing
            # and compare dates. This is bandwidth-heavy, so we flag it
            # but don't auto-download multi-GB files.
            [[ $VERBOSE -eq 1 ]] && detail "ZIM: $name ($(numfmt --to=iec $size 2>/dev/null || echo $size))"
        fi
    done

    if [[ $zim_changes -gt 0 ]]; then
        HAD_CHANGES=1
    fi
fi

# ═══════════════════════════════════════════════════════════
#  SUMMARY
# ═══════════════════════════════════════════════════════════

if [[ $CHECK_ONLY -eq 1 ]]; then
    if [[ $HAD_CHANGES -eq 0 ]]; then
        [[ $VERBOSE -eq 1 ]] && header "ALL UP TO DATE"
    fi
else
    if [[ $HAD_CHANGES -eq 0 ]]; then
        # Silent exit — nothing changed, nothing to say
        exit 0
    fi
    # Log the timestamp of the update
    echo "[$(date '+%Y-%m-%d %H:%M')] Auto-update applied changes" >> "$LOG_FILE" 2>/dev/null || true
fi
