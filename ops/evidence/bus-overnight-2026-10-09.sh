#!/usr/bin/env bash
# Generate the bus-overnight evidence artifact from the COMMITTED, read-only
# bus inspector (ops/scripts/orch-bus/bus-inbox-inspect.py — GET
# /api/pgmq/queues and /api/pgmq/peek only; never consumes a message).
#
# Re-runnable at HEAD: it runs the inspector in both modes, then drives its
# committed _http_get/_norm helpers to peek EVERY non-empty queue on BOTH buses
# and record the per-message retry_count / max_retries / priority / state, the
# workflow_step_result depth, and the queue totals — so every "clean" claim in
# the run note (no DLQ backlog, no stuck pending, no blocked workflow, no
# urgent message) is committed, re-executable proof, not prose.
#
# Writes docs/evidence/bus-overnight-2026-10-09.txt. Host-identifying strings
# (the home dir, every bus endpoint URL, and long numeric ids such as
# chat/phone numbers) are scrubbed at the SOURCE so the committed artifact
# carries no real paths, domains, endpoints or identifiers.
#
# Usage: bash ops/evidence/bus-overnight-2026-10-09.sh
# Read-only: it never sends, archives, or consumes a bus message.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSPECTOR_REL="ops/scripts/orch-bus/bus-inbox-inspect.py"
INSPECTOR="${REPO}/${INSPECTOR_REL}"
[[ -f "${INSPECTOR}" ]] || {
  echo "FATAL: ${INSPECTOR_REL} not found under ${REPO}; cannot generate evidence" >&2
  exit 3
}
ARTIFACT="${REPO}/docs/evidence/bus-overnight-2026-10-09.txt"

scrub() {
  sed -E \
    -e "s#${HOME}#<home>#g" \
    -e 's#https?://[^[:space:]"'"'"'<>]+#<bus-endpoint>#g' \
    -e 's#[0-9]{8,}#<redacted-id>#g'
}

# Record the revision of the INSPECTOR (its last-touching commit), never HEAD:
# an evidence artifact cannot record the hash of the commit that contains it
# (amending the commit would self-invalidate the hash it wrote) — a stable,
# externally-derived revision keeps the artifact reproducible and truthful.
# Fail closed: never write an artifact with an unresolved/empty revision.
if ! REV="$(git -C "${REPO}" log -1 --format=%h -- "${INSPECTOR_REL}")"; then
  echo "FATAL: git log failed resolving the inspector revision for ${INSPECTOR_REL}" >&2
  exit 4
fi
if [[ -z "${REV}" ]]; then
  echo "FATAL: inspector revision empty — pathspec ${INSPECTOR_REL} matched no commit" >&2
  exit 4
fi

OUT_ISSUES="$(python3 "${INSPECTOR}" esther --issues 2>&1)"
RC_ISSUES=$?
OUT_FULL="$(python3 "${INSPECTOR}" esther 2>&1)"
RC_FULL=$?

# Exhaustive, per-message probe reusing the inspector's own committed fetchers.
OUT_PROBE="$(python3 - "${INSPECTOR}" <<'PY' 2>&1
import importlib.util, sys
spec = importlib.util.spec_from_file_location("bii", sys.argv[1])
bii = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bii)

report = bii.build_report("esther")
total_pending = 0
total_stuck = 0
dlq_backlog = 0
for bus in report["buses"]:
    label = bus["label"]
    base = bus["base"]
    print(f"== bus {label}: inspection_error={bus.get('inspection_error')} "
          f"queue_total={bus.get('queue_total')}")
    for d in bus.get("dlq", []):
        if d.get("depth") or d.get("processing"):
            dlq_backlog += 1
            print(f"   DLQ BACKLOG {d['name']} depth={d['depth']} "
                  f"processing={d['processing']}")
    for q in bus.get("nonempty", []):
        if q.get("dlq"):
            continue
        raw = bii._http_get(base, f"/api/pgmq/peek/{q['name']}?limit=200")
        if not isinstance(raw, dict) or raw.get("_http_error") or raw.get("_error"):
            print(f"   {q['name']} depth={q['depth']} PEEK-ERROR {raw}")
            continue
        msgs = raw.get("messages", [])
        print(f"   {q['name']} depth={q['depth']} processing={q['processing']} "
              f"peeked={len(msgs)}")
        for m in msgs:
            total_pending += 1
            b = bii._norm(m.get("body")) or {}
            subj = b.get("subject") if isinstance(b, dict) else None
            rc = m.get("retry_count")
            mx = m.get("max_retries")
            if isinstance(rc, int) and isinstance(mx, int) and rc >= mx:
                total_stuck += 1
            print(f"     state={m.get('state')} subj={subj} "
                  f"priority={m.get('priority')} retry={rc}/{mx} "
                  f"read_ct={m.get('read_ct')} enq={m.get('enqueued_at')}")
    # Blocked-workflow queue depth, read from the authoritative queue list
    # (a non-empty workflow_step_result would also raise an "undated pending"
    # issue in fleet_issues(), so issues_exit=0 and this depth=0 agree).
    ql = bii._http_get(base, "/api/pgmq/queues")
    ws_depth = ws_proc = None
    if isinstance(ql, dict) and not (ql.get("_http_error") or ql.get("_error")):
        for row in ql.get("queues", []):
            if row.get("name") == "workflow_step_result":
                ws_depth, ws_proc = row.get("depth"), row.get("processing")
    print(f"   workflow_step_result depth={ws_depth} processing={ws_proc}")
print(f"SUMMARY pending_peeked={total_pending} stuck(retry>=max)={total_stuck} "
      f"dlq_backlog={dlq_backlog}")
PY
)"
RC_PROBE=$?

# Fail closed: never emit a "successful" artifact from a failed probe.
if [[ ${RC_ISSUES} -ne 0 || ${RC_FULL} -ne 0 || ${RC_PROBE} -ne 0 ]]; then
  echo "FATAL: inspector/probe failed (issues=${RC_ISSUES} full=${RC_FULL} probe=${RC_PROBE})" >&2
  exit 1
fi

{
  echo "# Bus overnight inspection — GENERATED artifact (not hand-written)"
  echo "# generated_at: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "# inspector_last_commit: ${REV}"
  echo "# generator: ops/evidence/bus-overnight-2026-10-09.sh"
  echo "# inspector: ${INSPECTOR_REL} (committed, read-only, never consumes)"
  echo "# command: python3 ${INSPECTOR_REL} esther --issues"
  echo "# command: python3 ${INSPECTOR_REL} esther"
  echo "# command: per-queue peek probe via ${INSPECTOR_REL} helpers"
  echo "# scrubbed at source: <home>, <bus-endpoint>, <redacted-id>."
  echo ""
  echo "## --issues (empty stdout + exit 0 == no-action / silent condition)"
  echo "issues_exit=${RC_ISSUES}"
  printf '%s\n' "${OUT_ISSUES}" | scrub
  echo ""
  echo "## per-message probe (probe_exit=${RC_PROBE})"
  printf '%s\n' "${OUT_PROBE}" | scrub
  echo ""
  echo "## full JSON transcript (inspector output is scrubbed/truncated at source)"
  echo "transcript_exit=${RC_FULL}"
  printf '%s\n' "${OUT_FULL}" | scrub
  echo ""
} > "${ARTIFACT}"

echo "wrote ${ARTIFACT} ($(wc -c < "${ARTIFACT}") bytes) issues_exit=${RC_ISSUES} probe_exit=${RC_PROBE}"
