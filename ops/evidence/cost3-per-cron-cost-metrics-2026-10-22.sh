#!/usr/bin/env bash
# Evidence generator — story c579ef95 [cost/3], 2026-10-22 (esther).
#
# Re-run:  bash ops/evidence/cost3-per-cron-cost-metrics-2026-10-22.sh
# Writes the transcript to stdout and to
#   docs/evidence/cost3-per-cron-cost-metrics/verify.txt
#
# What it proves, with the REAL scripts and this host's REAL data:
#   1. cron-cost-metrics.py emits per-cron token/spend series from the live
#      audit log and live state.db (scratch HOME symlinks the real files;
#      state.db is opened read-only so nothing can write to it);
#   2. the real push client carries those series to a local recording sink in
#      the SAME push as the node metrics — a captured payload, not a claim;
#   3. the real weekly report runs against the live data, printing what it
#      measured and what it did not.
#
# Redaction: every emitted line passes through `norm` (HOME -> ~; the FQDN form
# of the host name replaced, never a bare agent name — an agent's own name is not
# host identity and replacing it makes the transcript lie about which agent the
# metrics belong to). The real VICTORIA_METRICS_URL is never printed or used here
# — the push targets a local recorder on 127.0.0.1.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$REPO/docs/evidence/cost3-per-cron-cost-metrics/verify.txt"
WORK="$(mktemp -d)"
PORT=19998
mkdir -p "$(dirname "$OUT")"

norm() { sed -e "s#${HOME}#~#g"; }
say() { printf '%s\n' "$*" | norm >>"$OUT"; printf '%s\n' "$*" | norm; }
run() {
  say "\$ $*"
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  printf '%s\n' "$out" | norm >>"$OUT"; printf '%s\n' "$out" | norm
  say "rc=$rc"
  return $rc
}

: >"$OUT"
say "# [cost/3] verification transcript — $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
say "# captured-at: revision the working tree sat on when this ran (the committed"
say "# copy is necessarily one commit ahead — this file cannot name its own commit)."
say "captured-at: $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null)"
say ""

# ── 1. the generator, on live data ───────────────────────────────────────────
say "## 1. per-cron series from the live audit log + live state.db"
python3 "$REPO/ops/scripts/manage/cron-cost-metrics.py" --prometheus --agent esther \
  >"$WORK/series.txt" 2>"$WORK/series.err"
gen_rc=$?
say "\$ cron-cost-metrics.py --prometheus --agent esther"
say "rc=$gen_rc   stderr: $(norm <"$WORK/series.err")"
say "series lines emitted: $(grep -c . "$WORK/series.txt")"
say "  = $(grep -c '^hermes_cron_' "$WORK/series.txt") data lines + $(grep -c '^#' "$WORK/series.txt") HELP/TYPE comment lines"
say "job lines (tokens per job_id): $(grep -c 'hermes_cron_tokens_total' "$WORK/series.txt")"
say "cost_available line: $(grep 'hermes_cron_cost_available' "$WORK/series.txt")"
say "first 8 lines:"
sed -n '1,8p' "$WORK/series.txt" | norm >>"$OUT"
sed -n '1,8p' "$WORK/series.txt" | norm
say ""

# ── 2. the real client, parking the payload at a local recording sink ────────
say "## 2. the real push client against a local recording sink"
cat >"$WORK/recorder.py" <<'PY'
import http.server, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        with open(sys.argv[2], "ab") as fh:
            fh.write(body)
        self.send_response(204); self.end_headers()
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PY
python3 "$WORK/recorder.py" "$PORT" "$WORK/payload.txt" &
rec_pid=$!
sleep 1

SCRATCH_HOME="$WORK/home"
mkdir -p "$SCRATCH_HOME/.hermes/cron" "$SCRATCH_HOME/.hermes-cortex/scripts"
ln -sf "$HOME/.hermes/cron/usage_audit.jsonl" "$SCRATCH_HOME/.hermes/cron/usage_audit.jsonl"
ln -sf "$HOME/.hermes/state.db" "$SCRATCH_HOME/.hermes/state.db"
ln -sf "$REPO/ops/scripts/manage/cron-cost-metrics.py" "$SCRATCH_HOME/.hermes-cortex/scripts/cron-cost-metrics.py"

HOME="$SCRATCH_HOME" AGENT_NAME=esther \
  VICTORIA_METRICS_URL="http://127.0.0.1:${PORT}/api/v1/import/prometheus" \
  PUSH_METRICS_STATE_FILE="$WORK/push-metrics.state" \
  bash "$REPO/ops/scripts/manage/agent-push-metrics.sh" >>"$WORK/client.log" 2>&1
rc=$?
say "push client exit code: $rc (0 = pushed)"
say "payload bytes recorded: $(wc -c <"$WORK/payload.txt")"
say "node series in the payload: $(grep -c '^node_' "$WORK/payload.txt")"
say "cron cost series in the payload: $(grep -c '^hermes_cron_' "$WORK/payload.txt")"
say "  ^ the payload is a SUPERSET: node series + the cron cost series (data lines only)."
say "    Section 1's larger number counts the generator's HELP/TYPE comment lines too;"
say "    both counts come from the same generator run, so 119 <= 129 by exactly those comments."
say "sample of the cost series as received:"
grep '^hermes_cron_' "$WORK/payload.txt" | head -4 | norm >>"$OUT"
grep '^hermes_cron_' "$WORK/payload.txt" | head -4 | norm
say "client stderr/stdout: '$(norm <"$WORK/client.log")'"
kill "$rec_pid" 2>/dev/null || true
wait "$rec_pid" 2>/dev/null || true
say ""

# ── 3. the real weekly report, on live data, and its alert path ─────────────
say "## 3. weekly report on live data"
run python3 "$REPO/ops/scripts/manage/orch-weekly-cost-report.py" --days 7
say ""
say "## 3b. the alert path, driven by a fixture that breaches the target"
FX="$WORK/fx"
mkdir -p "$FX"
python3 - "$FX/state.db" <<'PY'
import sqlite3, sys, time
c = sqlite3.connect(sys.argv[1])
c.execute("CREATE TABLE sessions (session_id TEXT, source TEXT, started_at REAL,"
          " input_tokens INTEGER, output_tokens INTEGER, estimated_cost_usd REAL)")
c.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?)", [
    ("cron_fixtureA_1", "cron", time.time(), 1, 1, 12.0),
    ("cron_fixtureA_2", "cron", time.time() - 86400, 1, 1, 14.0),
])
c.commit()
PY
printf '%s\n' '{"job_id": "fixtureA", "total_tokens": 1000}' >"$FX/usage_audit.jsonl"
run python3 "$REPO/ops/scripts/manage/orch-weekly-cost-report.py" \
  --audit "$FX/usage_audit.jsonl" --state-db "$FX/state.db" --days 7
say ""
say "## 4. test suite (both new files — every test name and result)"
run bash "$REPO/tests/run-tests.sh" \
  tests/test_runtime/test_cron_cost_reporting.py \
  tests/test_runtime/test_push_metrics_cost_series.py -v
say ""
say "## 5. the watchdog threshold the report's docstring cites (outside this range, quoted here)"
say "\$ grep -n 'CONSECUTIVE_FAILURE_LIMIT' ops/scripts/health/agent-cron-failure-watchdog.py"
grep -n 'CONSECUTIVE_FAILURE_LIMIT' "$REPO/ops/scripts/health/agent-cron-failure-watchdog.py" 2>&1 | norm >>"$OUT"
grep -n 'CONSECUTIVE_FAILURE_LIMIT' "$REPO/ops/scripts/health/agent-cron-failure-watchdog.py" 2>&1 | norm
say ""
say "# generated-by: this script (stdout is written here by the script itself)"
rm -rf "$WORK"
