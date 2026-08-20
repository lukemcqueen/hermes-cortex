#!/usr/bin/env bash
# cron_format.sh — Shared output formatter for standard cron format (bash).
#
# Source this file, then use:
#   cron_header "cron-name" "cron-id"
#   cron_phase "Phase Title" "Summary" "bullet1|bullet2|..."
#   cron_result "Verdict line"
#   cron_footer "model-name" "cost"
#   cron_output  # prints the final text
#   cron_silent  # prints [SILENT]
#
# Shortcut:
#   cron_deliver "cron-name" "phase1_title|summary" "bullet1|bullet2" "Phase 2|summary" ... result
#
# Timestamps are auto-added in KST.

CRON_PARTS=()
CRON_STARTED=false

cron_timestamp() {
    if [[ -n "${HERMES_TIMEZONE:-}" ]]; then
        TZ="${HERMES_TIMEZONE}" date +'%Y-%m-%d %H:%M %Z'
    else
        date +'%Y-%m-%d %H:%M %Z'
    fi
}

cron_header() {
    local name="${1:-cron}"
    local id="${2:-JOB_ID}"
    local ts
    ts=$(cron_timestamp)
    CRON_PARTS+=("${name} (${id}) [${ts}]")
    CRON_PARTS+=("-------------")
    CRON_PARTS+=("")
    CRON_STARTED=true
}

cron_phase() {
    local title="$1"
    local summary="$2"
    local bullets="$3"  # pipe-separated list, e.g. "item1|item2|item3"
    local n=0
    # Count existing phases
    for part in "${CRON_PARTS[@]}"; do
        if [[ "$part" == Phase\ * ]]; then
            n=$((n + 1))
        fi
    done
    n=$((n + 1))
    CRON_PARTS+=("Phase ${n} — ${title}: ${summary}")
    if [[ -n "$bullets" ]]; then
        IFS='|' read -ra BULLET_ARRAY <<< "$bullets"
        for b in "${BULLET_ARRAY[@]}"; do
            CRON_PARTS+=("- ${b}")
        done
    fi
    CRON_PARTS+=("")
}

cron_result() {
    CRON_PARTS+=("Result: $1")
    CRON_PARTS+=("")
}

cron_footer() {
    local model="${1:-script}"
    local cost="${2:-\$0}"
    CRON_PARTS+=("📊 ${model} | ${cost}")
}

cron_output() {
    for part in "${CRON_PARTS[@]}"; do
        echo "$part"
    done
}

cron_silent() {
    echo "[SILENT]"
}

cron_deliver() {
    local name="$1"
    local phase1_title phase1_summary phase1_bullets
    local phase2_title phase2_summary phase2_bullets
    local phase3_title phase3_summary phase3_bullets
    local verdict="$2"

    # Simple parse: remaining args are phase|title|summary|bullets
    # This is a simplified version; for complex output, use individual functions
    cron_header "$name"
    local arg_idx=2
    local args=("$@")
    while [[ $arg_idx -lt $# ]]; do
        local section="${args[$arg_idx]}"
        IFS='|' read -ra SECT <<< "$section"
        local stitle="${SECT[0]}"
        local ssummary="${SECT[1]}"
        local sbullets="${SECT[2]:-}"
        cron_phase "$stitle" "$ssummary" "$sbullets"
        arg_idx=$((arg_idx + 1))
    done
    cron_result "$verdict"
    cron_footer "$name"
    cron_output
}

# Auto-export functions
export -f cron_timestamp cron_header cron_phase cron_result cron_footer cron_output cron_silent cron_deliver
