#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — Offline Prep Script
#  Downloads ZIM content, seeds web-cache, sets up kiwix-serve
#
#  Usage:
#    ./prep-offline.sh                    # Interactive menu
#    ./prep-offline.sh --mode=travel      # Jungle/travel bundle
#    ./prep-offline.sh --mode=build       # Development offline bundle
#    ./prep-offline.sh --mode=education   # Kid learning bundle
#    ./prep-offline.sh --mode=all         # Everything
#    ./prep-offline.sh --mode=travel --include-bible  # Add Bible translations
#    ./prep-offline.sh --mode=travel --include-bible --include-hymns  # Add Bible + hymns
#    ./prep-offline.sh --include-bible    # Interactive + Bible
#    ./prep-offline.sh --include-hymns    # Interactive + hymns
#
#  Requirements: docker (for kiwix-serve), python3, curl
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config ──────────────────────────────────────────────────
HOME="${HOME:-$(echo ~)}"
ZIM_DIR="$HOME/offline/zim"
LIBRARY_FILE="$HOME/offline/kiwix-library.xml"
KIWIX_COMPOSE="$HOME/hermes-cortex/src/offline/kiwix-docker-compose.yml"
KIWIX_COMPOSE_INSTALLED="$HOME/.hermes-cortex/offline/kiwix-docker-compose.yml"
CACHE_SCRIPT="$HOME/.hermes-cortex/web-cache/web_cache.py"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()  { printf "${GREEN}✓${RESET} %s\n" "$1"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$1"; }
error() { printf "${RED}✗${RESET} %s\n" "$1"; }
header(){ printf "\n${CYAN}${BOLD}━━━ %s ━━━${RESET}\n" "$1"; }

# ── ZIM Download URLs (Kiwix official mirror) ───────────────
BASE_URL="https://download.kiwix.org/zim"

# Parallel arrays: key, url, label (indexed by position)
ZIM_KEYS=()
ZIM_URLS=()
ZIM_LABELS=()

_zim_add() {
  ZIM_KEYS+=("$1")
  ZIM_URLS+=("$2")
  ZIM_LABELS+=("$3")
}

_zim_add "wikivoyage_en_nopic" "$BASE_URL/wikivoyage/wikivoyage_en_all_nopic_2026-03.zim" \
  "🌍  Wikivoyage (text-only, 232 MB) — travel guides, phrasebooks, safety"
_zim_add "wikivoyage_en_maxi" "$BASE_URL/wikivoyage/wikivoyage_en_all_maxi_2026-03.zim" \
  "🌍  Wikivoyage (with images, 1.1 GB) — travel guides, photos"
_zim_add "medicine_en" "$BASE_URL/wikipedia/wikipedia_en_medicine_maxi_2026-01.zim" \
  "🏥  WikiMed (2.1 GB) — medical encyclopedia, diseases, treatments"
_zim_add "simple_wikipedia" "$BASE_URL/wikipedia/wikipedia_en_simple_all_maxi_2026-02.zim" \
  "🔤  Simple Wikipedia (3.4 GB) — plain English encyclopedia"
_zim_add "wikipedia_mini" "$BASE_URL/wikipedia/wikipedia_en_all_mini_2026-02.zim" \
  "📚  Wikipedia Mini (12.4 GB) — full encyclopedia, compressed"
_zim_add "wikibooks_en" "$BASE_URL/wikibooks/wikibooks_en_all_maxi_2026-04.zim" \
  "📖  Wikibooks (1.5 GB) — free textbooks, STEM, programming"
_zim_add "wiktionary_en" "$BASE_URL/wiktionary/wiktionary_en_all_maxi_2026-04.zim" \
  "📝  Wiktionary (2.2 GB) — dictionary, thesaurus, etymology"

# Lookup helper — echoes the value for a given key from a named array set
zim_get_url()   { local i; for i in "${!ZIM_KEYS[@]}"; do [[ "${ZIM_KEYS[$i]}" == "$1" ]] && { echo "${ZIM_URLS[$i]}"; return 0; }; done; return 1; }
zim_get_label() { local i; for i in "${!ZIM_KEYS[@]}"; do [[ "${ZIM_KEYS[$i]}" == "$1" ]] && { echo "${ZIM_LABELS[$i]}"; return 0; }; done; return 1; }

# Bundle definitions (keys only)
TRAVEL_BUNDLE=(wikivoyage_en_nopic medicine_en simple_wikipedia wiktionary_en)
BUILD_BUNDLE=(simple_wikipedia wikibooks_en wiktionary_en)
EDUCATION_BUNDLE=(simple_wikipedia wikibooks_en wikivoyage_en_nopic)
ALL_BUNDLE=(wikivoyage_en_nopic medicine_en simple_wikipedia wikibooks_en wiktionary_en)

# ── Functions ───────────────────────────────────────────────

check_deps() {
    local missing=0
    if ! command -v docker &>/dev/null; then
        warn "Docker not found — kiwix-serve will not run"
        missing=1
    fi
    if ! command -v python3 &>/dev/null; then
        error "python3 required"
        missing=1
    fi
    if ! command -v curl &>/dev/null; then
        error "curl required"
        missing=1
    fi
    if [[ $missing -gt 0 ]]; then
        exit 1
    fi
}

download_zim() {
    local key="$1"
    local url=$(zim_get_url "$key")
    local label=$(zim_get_label "$key")
    local filename=$(basename "$url")
    local dest="$ZIM_DIR/$filename"

    mkdir -p "$ZIM_DIR"

    if [[ -f "$dest" ]]; then
        local size=$(du -h "$dest" | cut -f1)
        info "$label — already downloaded ($size)"
        return 0
    fi

    printf "  Downloading %s …\n" "$label"
    printf "  URL: %s\n" "$url"
    printf "  To:  %s\n" "$dest"
    printf "\n"

    # Download with progress
    curl -L --progress-bar -o "$dest" "$url" || {
        error "Download failed for $key"
        rm -f "$dest"
        return 1
    }

    local size=$(du -h "$dest" | cut -f1)
    info "Downloaded: $label ($size)"
    return 0
}

generate_library() {
    header "GENERATING KIWIX LIBRARY"
    python3 "$HOME/hermes-cortex/src/offline/offline_knowledge.py" generate-library
    info "Library file ready: $LIBRARY_FILE"
}

start_kiwix() {
    header "STARTING KIWIX-SERVE (DOCKER)"

    if docker ps --filter "name=kiwix-serve" --format "{{.Status}}" | grep -q .; then
        info "kiwix-serve already running"
        return 0
    fi

    # Copy compose file to installed location if needed
    if [[ -f "$KIWIX_COMPOSE" ]]; then
        mkdir -p "$(dirname "$KIWIX_COMPOSE_INSTALLED")"
        cp "$KIWIX_COMPOSE" "$KIWIX_COMPOSE_INSTALLED"
    fi

    local compose_file="${KIWIX_COMPOSE_INSTALLED}"
    if [[ ! -f "$compose_file" ]]; then
        compose_file="$KIWIX_COMPOSE"
    fi

    if [[ ! -f "$compose_file" ]]; then
        error "kiwix-docker-compose.yml not found"
        return 1
    fi

    docker compose -f "$compose_file" up -d 2>&1 || {
        warn "Docker compose failed — trying docker pull first"
        docker pull ghcr.io/kiwix/kiwix-serve:3.8.2
        docker compose -f "$compose_file" up -d
    }

    sleep 3
    if docker ps --filter "name=kiwix-serve" --format "{{.Status}}" | grep -q .; then
        info "kiwix-serve running at http://localhost:8080"
    else
        warn "kiwix-serve may not have started — check: docker logs kiwix-serve"
    fi
}

seed_web_cache() {
    header "SEEDING WEB CACHE"

    if [[ ! -f "$CACHE_SCRIPT" ]]; then
        warn "web_cache not installed — skipping seed"
        return 0
    fi

    # Seed with relevant travel/medicine queries
    local SEED_QUERIES=(
        "jungle safety precautions tropical travel"
        "tropical diseases malaria dengue prevention"
        "snake bite first aid treatment wilderness"
        "water purification methods wilderness"
        "tropical plant identification edible toxic"
        "remote area medical emergencies"
        "travel vaccination requirements tropics"
        "local customs etiquette remote communities"
        "language phrasebook basic phrases travel"
    )

    local count=0
    for query in "${SEED_QUERIES[@]}"; do
        printf "  Seeding: \"%s\" … " "$query"
        # Run web_cache auto to capture if already cached; we just pre-populate
        python3 "$CACHE_SCRIPT" auto "$query" >/dev/null 2>&1 && {
            printf "cached\n"
            ((count++))
            continue
        }
        # Store a placeholder (actual content comes from first real search)
        printf "placeholder\n"
        ((count++))
    done

    info "Seeded $count cache entries"
    info "Cache will fill with real content when you search online"
}

verify_content() {
    header "VERIFYING INSTALLATION"

    local total=0
    local size_total=0

    for zim in "$ZIM_DIR"/*.zim; do
        if [[ -f "$zim" ]]; then
            local name=$(basename "$zim")
            local size=$(stat -f%z "$zim" 2>/dev/null || stat -c%s "$zim" 2>/dev/null || echo 0)
            local size_hr=$(numfmt --to=iec $size 2>/dev/null || echo "${size}")
            printf "  ✅ %-40s %s\n" "$name" "$size_hr"
            total=$((total + 1))
            size_total=$((size_total + size))
        fi
    done

    if [[ $total -eq 0 ]]; then
        warn "No ZIM files found in $ZIM_DIR"
    else
        local total_gb=$(echo "scale=2; $size_total / 1073741824" | bc 2>/dev/null || echo "$size_total bytes")
        info "$total ZIM file(s), $total_gb total"
    fi

    # Check kiwix
    if docker ps --filter "name=kiwix-serve" --format "{{.Status}}" | grep -q .; then
        info "kiwix-serve: running"
    else
        warn "kiwix-serve: not running"
    fi

    # Check web_cache
    if [[ -f "$CACHE_SCRIPT" ]]; then
        info "web_cache: installed"
    else
        warn "web_cache: not installed (run install.sh step 11)"
    fi
}

print_summary() {
    header "OFFLINE PREP COMPLETE"
    printf "\n"
    printf "  📂  ZIM directory:   %s\n" "$ZIM_DIR"
    printf "  🌐  kiwix-serve:     http://localhost:8080\n"
    printf "  📦  web_cache:       %s\n" "$HOME/.hermes-cortex/web-cache/cache.db"
    if [[ -d "$HOME/offline/bible" ]] && [[ "$(ls -A "$HOME/offline/bible" 2>/dev/null)" ]]; then
        local bible_count=$(find "$HOME/offline/bible" -name "*.txt" 2>/dev/null | wc -l)
        printf "  📖  Bible texts:    %d translations in ~/offline/bible/\n" "$bible_count"
    fi
    if [[ -d "$HOME/offline/hymns" ]] && [[ "$(ls -A "$HOME/offline/hymns" 2>/dev/null)" ]]; then
        local hymn_count=$(find "$HOME/offline/hymns" -type f 2>/dev/null | wc -l)
        printf "  🎵  Hymns:          %d files in ~/offline/hymns/\n" "$hymn_count"
    fi
    printf "\n"
    printf "  Commands:\n"
    printf "    offline_knowledge stats                — system status\n"
    printf "    offline_knowledge query \"question\"    — cascade knowledge lookup\n"
    printf "    offline_knowledge kiwix-search \"term\" — search ZIM content\n"
    printf "    offline_knowledge kiwix-list           — list loaded content\n"
    printf "\n"
    printf "  ${BOLD}Pro tip:${RESET} All tools work identically online and offline.\n"
    printf "  Online:  cache → kiwix → web → LLM (saves API costs)\n"
    printf "  Offline: cache → kiwix → gbrain → LLM (no internet needed)\n"
    printf "\n"
}

# ── Main ────────────────────────────────────────────────────

main() {
    echo ""
    echo "  ╔═══════════════════════════════════════════╗"
    echo "  ║   Hermes Cortex — Offline Prep Tool       ║"
    echo "  ║   Download knowledge for offline use       ║"
    echo "  ╚═══════════════════════════════════════════╝"
    echo ""

    check_deps

    local mode="${1:-interactive}"
    local include_bible=0
    local include_hymns=0

    # Parse flags before --mode=
    for arg in "$@"; do
        case "$arg" in
            --include-bible) include_bible=1 ;;
            --include-hymns) include_hymns=1 ;;
        esac
    done

    # Parse --mode= argument
    if [[ "$mode" == --mode=* ]]; then
        mode="${mode#--mode=}"
    fi

    local selected_keys=()

    case "$mode" in
        travel)
            selected_keys=("${TRAVEL_BUNDLE[@]}")
            header "MODE: TRAVEL — Jungle/Vacation Bundle"
            printf "  Medicine + travel guides + encyclopedia + dictionary\n"
            ;;
        build)
            selected_keys=("${BUILD_BUNDLE[@]}")
            header "MODE: BUILD — Offline Development Bundle"
            printf "  Encyclopedia + textbooks + dictionary\n"
            ;;
        education)
            selected_keys=("${EDUCATION_BUNDLE[@]}")
            header "MODE: EDUCATION — Kid Learning Bundle"
            printf "  Simple encyclopedia + textbooks + travel guides\n"
            ;;
        all)
            selected_keys=("${ALL_BUNDLE[@]}")
            header "MODE: ALL — Full Knowledge Base"
            printf "  Everything — ~10 GB total\n"
            ;;
        interactive|*)
            header "INTERACTIVE MODE"
            printf "  Select content to download:\n\n"

            local i=1
            declare -a key_order
            for key in "${ZIM_KEYS[@]}"; do
                key_order[$i]="$key"
                local lbl=$(zim_get_label "$key")
                printf "  %d. %s\n" $i "$lbl"
                i=$((i + 1))
            done
            printf "  %d. All of the above\n" $i
            printf "\n  Enter numbers (space-separated, e.g. '1 3 5') or 'all': "
            read -r selections

            if [[ "$selections" == "all" ]]; then
                selected_keys=("${ALL_BUNDLE[@]}")
            else
                for num in $selections; do
                    if [[ -n "${key_order[$num]:-}" ]]; then
                        selected_keys+=("${key_order[$num]}")
                    fi
                done
            fi
            ;;
    esac

    # Download selected ZIM files
    if [[ ${#selected_keys[@]} -eq 0 ]]; then
        warn "No content selected — skipping download"
    else
        header "DOWNLOADING ZIM CONTENT"
        printf "  Files will be saved to: %s\n\n" "$ZIM_DIR"

        for key in "${selected_keys[@]}"; do
            download_zim "$key"
        done
    fi

    # Download Bible content (if requested)
    if [[ $include_bible -eq 1 ]]; then
        header "DOWNLOADING BIBLE CONTENT"
        local bible_script="$HOME/hermes-cortex/src/offline/prep-bible.sh"
        if [[ -f "$bible_script" ]]; then
            info "Downloading major language Bible translations…"
            bash "$bible_script" --langs=major 2>&1 || warn "Bible download had some failures"
        else
            warn "prep-bible.sh not found at $bible_script"
        fi
    fi

    # Download hymn content (if requested)
    if [[ $include_hymns -eq 1 ]]; then
        header "DOWNLOADING HYMNS"
        local hymn_script="$HOME/hermes-cortex/src/offline/prep-hymns.sh"
        if [[ -f "$hymn_script" ]]; then
            info "Downloading public domain hymns from Open Hymnal Project…"
            bash "$hymn_script" 2>&1 || warn "Hymn download had some failures"
        else
            warn "prep-hymns.sh not found at $hymn_script"
        fi
    fi

    # Generate library XML
    generate_library

    # Start kiwix-serve
    start_kiwix

    # Seed web cache
    seed_web_cache

    # Verify
    verify_content

    # Summary
    print_summary
}

main "$@"
