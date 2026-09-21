#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# cron-failure-state.sh — Failure state helpers for no_agent crons
#
# Source this file from any bash script that wants throttled failure
# reporting.  On repeat failure with the same error hash, the script
# exits 0 silently (no delivery) until the cooldown expires.
#
# Usage:
#   source cron-failure-state.sh
#   STATE_DIR="${HOME}/.hermes-cortex/state"
#   if ! cron_should_report "my-script" "error-hash" 30; then
#       exit 0  # silent — already reported recently
#   fi
#   ... do work, fail ...
#   cron_record_failure "my-script" "error-hash"
#   exit 1
#
# On success:
#   cron_record_success "my-script"
#
# State file: ~/.hermes-cortex/state/<script-name>.json
# ─────────────────────────────────────────────────────────────────────

: "${CRON_STATE_DIR:=${HOME}/.hermes-cortex/state}"
: "${CRON_DEFAULT_COOLDOWN:=30}"  # minutes

# ── Internal: read a state file as JSON, return fields via env vars ──
_cron_read_state() {
    local script="$1"
    local state_file="${CRON_STATE_DIR}/${script}.json"
    CRON_LAST_HASH=""
    CRON_LAST_REPORT=""
    CRON_ERR_COUNT=0
    if [[ -f "$state_file" ]]; then
        CRON_LAST_HASH=$(python3 -c "
import json,sys
try:
    d=json.load(open('$state_file'))
    print(d.get('last_error_hash','') or '')
except: sys.exit(0)" 2>/dev/null || echo "")
        CRON_LAST_REPORT=$(python3 -c "
import json,sys
try:
    d=json.load(open('$state_file'))
    print(d.get('last_report_at','') or '')
except: sys.exit(0)" 2>/dev/null || echo "")
        CRON_ERR_COUNT=$(python3 -c "
import json,sys
try:
    d=json.load(open('$state_file'))
    print(d.get('error_count',0))
except: sys.exit(0)" 2>/dev/null || echo "0")
    fi
}

# ── Portable SHA-256 (macOS has no coreutils sha256sum) ─────────────
# sha256sum first, shasum -a 256 fallback (macOS ships perl shasum).
# Hashes STDIN only. The bare sha256sum here broke on macOS (titus):
# command-not-found yielded an EMPTY hash, so every error fingerprint
# collapsed to one value and dedup suppressed genuinely NEW failures.
# Fails closed (non-zero, empty stdout) when no hasher exists.
# Constructs are bash-3.2-safe (local, command -v, ${out%% *}).
_sha256_stdin() {
    local out
    if command -v sha256sum >/dev/null 2>&1; then
        out=$(sha256sum 2>&1) || { echo "" >&2; return 1; }
    elif command -v shasum >/dev/null 2>&1; then
        out=$(shasum -a 256 2>&1) || { echo "" >&2; return 1; }
    else
        echo "_sha256_stdin: no sha256sum/shasum available — cannot hash" >&2
        return 1
    fi
    echo "${out%% *}"
}

# ── Compute an error hash from an error string ──────────────────────
# Deterministic: same string → same hash (SHA-256 first 16 chars).
cron_error_hash() {
    local error_msg="$1"
    echo -n "$error_msg" | _sha256_stdin | cut -c1-16
}

# ── Should we report this failure? ──────────────────────────────────
# Returns 0 (report) or 1 (silent — already reported recently).
# Usage: if cron_should_report "script-name" "error-hash" [cooldown-minutes]; then
cron_should_report() {
    local script="$1"
    local error_hash="$2"
    local cooldown="${3:-${CRON_DEFAULT_COOLDOWN}}"

    mkdir -p "$CRON_STATE_DIR"

    _cron_read_state "$script"

    # No prior failure → always report
    if [[ -z "$CRON_LAST_HASH" || -z "$CRON_LAST_REPORT" ]]; then
        return 0
    fi

    # Different error → report (new failure type)
    if [[ "$CRON_LAST_HASH" != "$error_hash" ]]; then
        return 0
    fi

    # Same error — check cooldown
    local now_epoch
    now_epoch=$(date +%s)
    local report_epoch
    # macOS date(1) uses -j -f, Linux uses -d
    if date -d "$CRON_LAST_REPORT" +%s >/dev/null 2>&1; then
        report_epoch=$(date -d "$CRON_LAST_REPORT" +%s 2>/dev/null)
    elif date -j -f '%Y-%m-%dT%H:%M:%S%z' "$CRON_LAST_REPORT" +%s >/dev/null 2>&1; then
        report_epoch=$(date -j -f '%Y-%m-%dT%H:%M:%S%z' "$CRON_LAST_REPORT" +%s 2>/dev/null)
    else
        report_epoch=0
    fi
    local elapsed=$(( (now_epoch - report_epoch) / 60 ))

    if [[ "$elapsed" -ge "$cooldown" ]]; then
        return 0  # Cooldown expired — re-notify
    fi

    return 1  # Same error, within cooldown — stay silent
}

# ── Record a failure (call AFTER cron_should_report returns 0) ──────
cron_record_failure() {
    local script="$1"
    local error_hash="$2"
    local state_file="${CRON_STATE_DIR}/${script}.json"
    mkdir -p "$CRON_STATE_DIR"

    _cron_read_state "$script"
    local new_count=$(( CRON_ERR_COUNT + 1 ))
    local now_iso
    now_iso=$(date '+%Y-%m-%dT%H:%M:%S%z')

    python3 -c "
import json, os
fp = '$state_file'
d = {}
if os.path.isfile(fp):
    try: d = json.load(open(fp))
    except: pass
d['script'] = '$script'
d['version'] = 1
d['last_error_hash'] = '$error_hash'
d['last_error_at'] = '$now_iso'
d['error_count'] = $new_count
d['last_report_at'] = '$now_iso'
d['report_cooldown_minutes'] = ${3:-${CRON_DEFAULT_COOLDOWN}}
json.dump(d, open(fp, 'w'), indent=2)
" 2>/dev/null || true
}

# ── Record success (clears error state) ─────────────────────────────
cron_record_success() {
    local script="$1"
    local state_file="${CRON_STATE_DIR}/${script}.json"
    mkdir -p "$CRON_STATE_DIR"

    local now_iso
    now_iso=$(date '+%Y-%m-%dT%H:%M:%S%z')

    python3 -c "
import json, os
fp = '$state_file'
d = {}
if os.path.isfile(fp):
    try: d = json.load(open(fp))
    except: pass
d['script'] = '$script'
d['version'] = 1
d['last_error_hash'] = ''
d['last_error_at'] = ''
d['error_count'] = 0
d['last_success_at'] = '$now_iso'
json.dump(d, open(fp, 'w'), indent=2)
" 2>/dev/null || true
}
