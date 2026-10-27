#!/usr/bin/env bash
# Evidence generator — does a non-Hermes harness give two agents in ONE repo
# the same governance session id (and therefore the same lock file)?
#
# PROVENANCE (read this, not a conclusion): this script writes its own output
# file. It drives the DEPLOYED loop-gov-mcp.py with every path redirected to a
# sandbox (state dir, loop DB, HOME, cwd) — nothing in the live governance
# store is read or written. Re-run it to reproduce the transcript:
#
#   bash docs/evidence/shared-session-id-non-hermes-2026-10-27/run.sh [outfile]
#
# Fields that are volatile by design: the module sha256 (changes on every
# deploy), the mktemp sandbox paths, and the generated sess_* ids. The
# transcript is normalised by ONE filter: $HOME -> ~ , ANSI colour stripped.
#
# Two processes are used per case (`python3 driver.py <mode>`) so each case
# exercises the real per-process code path a Pi / Claude Code / CLI session
# takes, not an in-process simulation.
#
# WHERE THE FINDING IS RECORDED (pointer, not an assertion): governance task
# 'verify-session-id-scoping-across-agents', cycle 13849, task_events event 254
# on the host that produced this transcript.
#
# DEPENDENCY POINTER: this file WRITES the file it is run against —
# docs/evidence/shared-session-id-non-hermes-2026-10-27/transcript.txt is this
# script's own output, committed in the same range. It reads nothing else of
# this range; the module it probes is the deployed loop-gov-mcp.py named below.
#
# PORTABILITY: POSIX sh constructs only, no bash-4 syntax, no `declare -A`, no
# unconditional `timeout`, no GNU-only flag; the hash helper falls back to
# `shasum -a 256` when `sha256sum` is absent (macOS). Requires git, python3,
# sed, awk, grep. Absent python3 the script fails loudly rather than emitting a
# partial transcript.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$HERE/transcript.txt}"
MCP="${PROBE_MCP:-$HOME/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/sessid-probe.XXXXXX")"

_sha() {  # GNU and BSD
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  else shasum -a 256 "$1" | awk '{print $1}'; fi
}

_norm() {
  # `\x1b` is a GNU sed extension; build the escape portably so BSD sed works too.
  sed -e "s|${HOME}|~|g" -e "s/$(printf '\033')\[[0-9;]*[a-zA-Z]//g"
}
# Redirect the FILTER too: `exec > >(norm)` alone leaves no file (the process
# substitution's stdout is the inherited one).
exec > >( _norm > "$OUT" ) 2>&1

cat <<EOF
# Evidence: governance session id / lock scoping for NON-Hermes harnesses
# generated-by: docs/evidence/shared-session-id-non-hermes-2026-10-27/run.sh
# captured-at:  $(git -C "$HERE" rev-parse --short=12 HEAD 2>/dev/null || echo unknown)
# module-probed: $MCP
# module-sha256: $(_sha "$MCP")
# volatile: module sha256, sandbox paths, generated sess_* ids
# normalised: \$HOME -> ~, ANSI colour stripped (one filter, applied to every line)
# record: governance task 'verify-session-id-scoping-across-agents', cycle 13849,
#         task_events event 254 — the finding itself is recorded there, not here
EOF

# ── driver: imports the DEPLOYED module with every path redirected ──────────
cat > "$WORK/driver.py" <<'PYEOF'
import importlib.util, json, os, sqlite3, sys
from pathlib import Path

MCP = Path(os.environ["PROBE_MCP"]); STATE = Path(os.environ["PROBE_STATE"])
LOOPDB = Path(os.environ["PROBE_LOOPDB"]); HOME = Path(os.environ["PROBE_HOME"])
REPO = Path(os.environ["PROBE_REPO"])
spec = importlib.util.spec_from_file_location("lgm_probe", MCP)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.GOVERNANCE_STATE_DIR = STATE; m.LOOP_DB = LOOPDB; m.HOME = HOME
m.GOVERNANCE_REPO_PATH = MCP; m.GOVERNANCE_DEPLOY_PATH = MCP  # hermetic dogfood check
os.chdir(REPO)

mode = sys.argv[1]; task = sys.argv[2] if len(sys.argv) > 2 else ""
def _p(label, text, n=300): print(f"{label}={text.replace(chr(10), ' | ')[:n]}")

if mode == "id":
    print("SESSION_ID=" + m.get_session_id(None))
elif mode == "idarg":
    print("SESSION_ID=" + m.get_session_id({"session_id": task}))
elif mode == "begin":
    print("SESSION_ID=" + m.get_session_id(None))
    _p("BEGIN_RESULT", m._begin_change({"task_id": task, "description": "probe " + task}).content[0].text, 400)
elif mode == "beginarg":
    _p("BEGIN_RESULT", m._begin_change({"task_id": task, "description": "probe " + task,
        "session_id": os.environ["PROBE_SID"]}).content[0].text, 300)
elif mode == "beginarg2":
    _p("BEGIN_RESULT", m._begin_change({"task_id": task, "description": "probe " + task,
        "session_id": os.environ["PROBE_SID"], "repo_path": str(REPO)}).content[0].text, 300)
elif mode == "score":
    _p("SCORE_RESULT", m._feedback_accept({"task_id": task, "note": "probe score",
        "completeness": 8, "quality": 8, "progress": 8}).content[0].text, 200)
elif mode == "end":
    _p("END_RESULT", m._end_change({"task_id": task}).content[0].text, 250)
elif mode == "age":
    f = next(iter(STATE.glob(".governance-*.json"))); d = json.loads(f.read_text())
    d["heartbeat_at"] = "2026-01-01T00:00:00Z"; d["started_at"] = "2026-01-01T00:00:00Z"
    f.write_text(json.dumps(d, indent=2))
    print(f"AGED {f.name} heartbeat={d['heartbeat_at']} ttl={d.get('ttl_seconds')}")
elif mode == "cycles":
    c = sqlite3.connect(LOOPDB)
    for r in c.execute("SELECT id, task_id, session_id, decision, user_overrode, "
                       "substr(coalesce(unscored_reason,''),1,70) FROM loop_cycles ORDER BY id"):
        print("CYCLE " + " | ".join(str(x) for x in r))
elif mode == "locks":
    for f in sorted(STATE.glob(".governance-*.json")):
        d = json.loads(f.read_text())
        print(f"LOCK {f.name} session_id={d.get('session_id')} task={d.get('task_id')} repo={d.get('repo_path')}")
    print("PERSISTED=" + ", ".join(f"{f.name}={f.read_text().strip()}"
          for f in sorted(STATE.glob(".session-*.id"))))
PYEOF

newcase() {
  CASE="$WORK/$1"; mkdir -p "$CASE/state" "$CASE/home"; REPO="$CASE/repo"; mkdir -p "$REPO"
  git init -q "$REPO"
  git -C "$REPO" -c core.hooksPath=/nonexistent -c user.email=t@t.t -c user.name=t \
      commit -q --allow-empty -m init
  export PROBE_MCP="$MCP" PROBE_STATE="$CASE/state" PROBE_LOOPDB="$CASE/loop.db" \
         PROBE_HOME="$CASE/home" PROBE_REPO="$REPO"
  echo; echo "### $1   repo=$REPO"
}
run() { python3 "$WORK/driver.py" "$@" 2>&1 | grep -v 'mcp-server\]' | sed 's/^/    /'; }

echo; echo "## A. two separate processes, ONE repo, no injected session id"
newcase A-two-processes-same-repo
echo "  [p1 id]";  run id
echo "  [p2 id]";  run id
echo "  [p1 begin task-a]"; run begin task-a
echo "  [locks after p1]";  run locks
echo "  [p2 begin task-b]"; run begin task-b
echo "  [locks after p2]";  run locks

echo; echo "## B. A scores its cycle, then B begins (lock still held)"
newcase B-scored-then-peer
echo "  [p1 begin task-a]"; run begin task-a
echo "  [p1 score task-a]"; run score task-a
echo "  [p2 begin task-b]"; run begin task-b

echo; echo "## C. cross-session close: can B score and end A's cycle?"
newcase C-cross-session-close
echo "  [p1 begin task-a]"; run begin task-a
echo "  [p2 score task-a]"; run score task-a
echo "  [p2 end task-a]";   run end task-a
echo "  [locks]";           run locks

echo; echo "## D. explicit per-call session_id -> a separate lock"
newcase D-explicit-sid
echo "  [default id]";                 run id
echo "  [explicit sid]";               run idarg sess_pi_probe123
echo "  [p1 begin task-a (default)]";  run begin task-a
echo "  [p2 begin task-b (explicit)]"; PROBE_SID=sess_pi_probe123 run beginarg task-b
echo "  [locks]";                      run locks

echo; echo "## E. explicit session_id without repo_path: what the lock records"
newcase E-explicit-sid-repo-identity
echo "  [explicit sid, no repo_path]";  PROBE_SID=sess_pi_probe_aaa run beginarg task-a
echo "  [explicit sid + repo_path]";    PROBE_SID=sess_pi_probe_bbb run beginarg2 task-b
echo "  [locks]";                       run locks

echo; echo "## F. holder goes quiet past its TTL, peer begins -> same lock path"
newcase F-aged-out-holder
echo "  [p1 begin task-c]";     run begin task-c
echo "  [age p1 lock]";         run age
echo "  [p2 begin task-d]";     run begin task-d
echo "  [locks after p2]";      run locks
echo "  [cycles]";              run cycles
echo "  [p1 end task-c]";       run end task-c

echo; echo "## sandbox (deleted on reboot): $WORK"
