#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  capture.sh — evidence for "the pi agent can search the web" (free).
#
#  Re-runnable. Produces, in this directory:
#    01-installer.txt   install-pi-integration.sh add + --check, with exit codes
#    02-audit.txt       audit-pi-integration.sh (Layer 6 = web search)
#    03-age-gate.txt    the pinned version passes the 14-day package age gate
#    04-search-exa.txt  a REAL pi turn: keyless Exa search, real URLs
#    05-search-ddg.txt  a REAL pi turn: explicit DuckDuckGo search + fetch_content
#
#  Normalisation: $HOME -> ~, hostname -> <host>, repo root -> <repo>, so a
#  committed transcript carries no local path or host name. The normaliser runs
#  in the emitter itself — never hand-patch a captured file afterwards.
#
#  Run:  bash docs/evidence/pi-web-search-2026-10-15/capture.sh
#  Exit: 0 = every captured step exited 0 (the probes really ran)
# ─────────────────────────────────────────────────────────────
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
OUT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI="${PI_LAUNCHER:-$HOME/.pi/agent/bin/pi}"
MODEL="${PI_EVIDENCE_MODEL:-openrouter/moonshotai/kimi-k2.6}"
SCRATCH="${TMPDIR:-/tmp}/pi-web-search-evidence"
FAILS=0

norm() {  # ONE normaliser for every emitted line
  sed -e "s|${HOME}|~|g" -e "s|$(hostname)|<host>|g" -e "s|${REPO}|<repo>|g"
}

run() {  # run <outfile> <label> <cmd...>
  local out="$1" label="$2"; shift 2
  :
  local rc
  {
    echo "### $label"
    echo "\$ $*"
    echo
    "$@" 2>&1
    rc=$?
    echo
    echo "rc=$rc"
  } | norm > "$out"
  rc="$(sed -n 's/^rc=//p' "$out" | tail -1)"
  printf '  %-38s rc=%s -> %s\n' "$label" "${rc:-?}" "${out##*/}"
  [[ "${rc:-1}" == "0" ]] || FAILS=$((FAILS + 1))
}

echo "Capture: pi web search evidence -> $OUT"
run "$OUT/01-installer.txt" "installer (add, then --check)" \
    bash -c "bash $REPO/ops/scripts/install/install-pi-integration.sh && \
             bash $REPO/ops/scripts/install/install-pi-integration.sh --check"
run "$OUT/02-audit.txt" "audit-pi-integration.sh" \
    bash "$REPO/ops/scripts/manage/audit-pi-integration.sh"
run "$OUT/03-age-gate.txt" "package age gate (pinned version)" \
    python3 "$REPO/ops/scripts/health/check-package-age.py" npm pi-web-access==0.35.0

# A REAL turn, in a scratch repo, on the same launcher the gateway spawns.
mkdir -p "$SCRATCH" 2>/dev/null
git -C "$SCRATCH" init -q 2>/dev/null
run "$OUT/04-search-exa.txt" "pi turn: keyless Exa search" \
    env CORTEX_SESSION_REPO="$SCRATCH" CORTEX_SESSION_KEY=evidence-exa \
        "$PI" --model "$MODEL" \
        "Use the web_search tool with queries ['pi coding agent earendil']. Report which provider answered and the top 3 titles with URLs. Be brief."

# The explicit keyless fallback plus a fetch — the two things "research" and
# "review this repo" need. Independent of whether Exa's free tier answers.
run "$OUT/05-search-ddg.txt" "pi turn: DuckDuckGo search + fetch_content" \
    env CORTEX_SESSION_REPO="$SCRATCH" CORTEX_SESSION_KEY=evidence-ddg \
        "$PI" --model "$MODEL" \
        "Set provider to duckduckgo on web_search and query 'python asyncio taskgroup'; then fetch_content https://raw.githubusercontent.com/earendil-works/pi/main/README.md and report its first markdown heading. Be brief."

echo
if [[ "$FAILS" -eq 0 ]]; then echo "ALL STEPS rc=0"; exit 0; else echo "$FAILS STEP(S) NON-ZERO"; exit 1; fi
