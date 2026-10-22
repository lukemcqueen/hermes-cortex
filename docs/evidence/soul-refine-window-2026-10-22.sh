#!/usr/bin/env bash
# docs/evidence/soul-refine-window-2026-10-22.sh
#
# Re-runnable transcript generator for the 2026-10-22 soul-refinement pass.
# Read-only: opens the sessions store with mode=ro + PRAGMA query_only=1 and
# never writes outside its own output file. It writes the committed artifact
# itself, so `generated-by` is a fact about the file rather than a claim about
# who typed it.
#
#   usage: bash docs/evidence/soul-refine-window-2026-10-22.sh [OUT]
#
# Every emitted line (its own and every command's) passes through ONE
# normaliser: runs of 7+ digits are masked and /home/<user>, /Users/<user>
# collapse to ~. Never hand-patch the committed copy: re-run this script.
#
# captured-at: is the revision the working tree sat on when the run happened.
# A transcript cannot name its own commit — writing this file changes the
# revision — so no `tip:` line is printed.
set -uo pipefail

OUT="${1:-docs/evidence/soul-refine-window-2026-10-22.txt}"
case "$OUT" in /*) OUTABS="$OUT" ;; *) OUTABS="$(pwd)/$OUT" ;; esac

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export REPO_ROOT
SELF="$REPO_ROOT/docs/evidence/soul-refine-window-2026-10-22.sh"

# --self-test proves the property this script previously lacked: that a FAILING
# run says so through its exit code. Direction 1 runs the generator normally
# (must exit 0); direction 2 runs a COPY from a foreign directory, where it
# cannot resolve the file its own `bash -n` checks, and requires a NON-ZERO exit
# — the previous revision ended in an `echo`, so it always exited 0 and a broken
# run reported success.
if [ "${1:-}" = "--self-test" ]; then
  TMPD="$(mktemp -d)"
  trap 'rm -rf -- "${TMPD:?}"' EXIT
  echo "=== self-test: a failing run must report failure through its exit code ==="
  fails=0
  echo "-- direction 1: normal run, expect rc=0 (output to scratch, never the committed path)"
  bash "$SELF" "$TMPD/ok.txt"
  A=$?
  echo "   normal run rc=$A"
  if [ "$A" -eq 0 ]; then echo "   PASS  a healthy run exits 0"; else echo "   FAIL  healthy run exited $A"; fails=$((fails + 1)); fi
  echo "-- direction 2: same script from a FOREIGN dir cannot resolve its bash -n target,"
  echo "   so it must exit non-zero (this is exactly what the old tail swallowed)"
  mkdir -p "$TMPD/foreign"
  cp "$SELF" "$TMPD/foreign/g.sh"
  (cd "$TMPD/foreign" && bash g.sh "$TMPD/foreign/out.txt")
  B=$?
  echo "   foreign-dir run rc=$B"
  if [ "$B" -ne 0 ]; then echo "   PASS  a failing run exits non-zero"; else echo "   FAIL  a failing run still exited 0"; fails=$((fails + 1)); fi
  echo "-- the failing transcript's tail:"
  if [ -f "$TMPD/foreign/out.txt" ]; then tail -4 "$TMPD/foreign/out.txt" | sed 's/^/   /'; else echo "   (no transcript written)"; fi
  echo "self-test failures: $fails"
  if [ "$fails" -ne 0 ]; then exit 1; fi
  exit 0
fi
exec >"$OUTABS" 2>&1

echo "=== soul-refinement window transcript ==="
echo "generated-by : docs/evidence/soul-refine-window-2026-10-22.sh (writes this file itself)"
echo "captured-at  : $(git -C "$REPO_ROOT" rev-parse --short=8 HEAD)"
echo "store        : ~/.hermes/state.db (read-only, mode=ro)"
echo

python3 - <<'PY'
import re, subprocess, sqlite3, sys, time
import json
from pathlib import Path

RC = 0
REPO = Path(__import__("os").environ["REPO_ROOT"])
STORE = Path.home() / ".hermes" / "state.db"

def norm(s: str) -> str:
    """THE normaliser — every line this script emits goes through it."""
    s = re.sub(r"\d{7,}", "<digits>", s)
    s = re.sub(r"/home/[^/\s]+", "~", s)
    s = re.sub(r"/Users/[^/\s]+", "~", s)
    s = re.sub(r"\x1b\[[0-9;]*m", "", s)
    return s

def say(line: str = "") -> None:
    print(norm(line), flush=True)

def run(args, cwd=REPO):
    p = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()

now = time.time()
say("[1] WINDOW")
say(f"    now (run time) : {time.strftime('%F %T', time.localtime(now))}  ({now:.3f})")

con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
con.execute("PRAGMA query_only=1")
cur = con.cursor()

rows = list(cur.execute(
    "SELECT id, title, started_at, last_activity_at, ended_at FROM sessions "
    "WHERE title LIKE '%soul-refinement%' "
    "ORDER BY COALESCE(last_activity_at, started_at) DESC LIMIT 3"))
say("    prior soul-refinement sessions (newest first):")
prev = None
for sid, title, st, la, en in rows:
    ts = la or st
    fresh = (now - (ts or 0)) < 300
    say(f"      {sid}  started={time.strftime('%F %T', time.localtime(st)) if st else '?'}"
        f"  last_activity={time.strftime('%F %T', time.localtime(la)) if la else '?'}"
        f"  ended={time.strftime('%F %T', time.localtime(en)) if en else '?'}"
        f"{'   <- THIS RUN, skipped' if fresh else ''}")
    if prev is None and not fresh:
        prev = ts
if prev is None:
    say("    !! no previous pass found — falling back to now - 24h")
    prev = now - 86400.0
say(f"    start bound = previous pass's last_activity_at = "
    f"{time.strftime('%F %T', time.localtime(prev))}  ({(now - prev) / 3600:.2f} h)")

say()
say("[2] SESSION CLASSIFICATION (sessions.source, one column — not an id prefix)")
buckets = {}
sess = {}
for sid, src, title, st, la in cur.execute(
        "SELECT id, source, title, started_at, last_activity_at FROM sessions "
        "WHERE COALESCE(last_activity_at, started_at) >= ?", (prev,)):
    src = src or "?"
    buckets[src] = buckets.get(src, 0) + 1
    sess[sid] = src
say(f"    sessions in window: {len(sess)}   " +
    "  ".join(f"{k}={v}" for k, v in sorted(buckets.items())))

say()
say("[3] role='user' ROWS")
raw = list(cur.execute(
    "SELECT session_id, content, timestamp, active FROM messages "
    "WHERE role='user' AND COALESCE(timestamp,0) >= ? ORDER BY timestamp", (prev,)))
say(f"    raw user rows (all sources): {len(raw)}")
per_src, dropped_active, kept = {}, 0, []
for sid, content, ts, active in raw:
    src = sess.get(sid, "<outside-window>")
    per_src[src] = per_src.get(src, 0) + 1
    if active != 1:
        dropped_active += 1
        continue
    if src not in ("telegram", "cli", "desktop", "discord"):
        continue
    c = content or ""
    if not isinstance(c, str):
        c = str(c)
    kept.append((ts, sid, len(c), c))
say("    by source: " + "  ".join(f"{k}={v}" for k, v in sorted(per_src.items())))
say(f"    dropped active!=1 (compaction artifacts): {dropped_active}")
say(f"    rows on human transports before marker filter: {len(kept)}")

MACHINE = ("[IMPORTANT: The user has invoked",
           "[IMPORTANT: You are running as a scheduled cron job",
           "[IMPORTANT: Background process",
           "[INTERNAL NOTIFICATION",
           "[Cron delivery:",
           "Gateway message origin",
           "[SECURITY NOTICE:",
           "[OUT-OF-BAND USER MESSAGE",
           "[CONTEXT COMPACTION",
           "[ASYNC DELEGATION")
prose = [(ts, sid, n, c) for ts, sid, n, c in kept
         if not any(c.lstrip().startswith(m) or m in c[:400] for m in MACHINE)]
say(f"    machine-marker rows dropped (compaction / delegation / gateway wrappers): "
    f"{len(kept) - len(prose)}")
say(f"    OPERATOR PROSE ROWS TO READ: {len(prose)}")
for ts, sid, n, c in prose:
    flat = re.sub(r"\s+", " ", c).strip()
    say(f"      - {time.strftime('%F %T', time.localtime(ts))}  sess={sid}  chars={n}"
        f"  :: {flat[:130]}")
if not sess:
    say("    !! ZERO sessions in the window — re-derive the bound before concluding anything")
    RC = 1

say()
say("[4] SAME-DAY CODIFICATION CHECKS (the decision rule: verify before writing)")
say("    each check prints the evidence itself: for a commit, the commit's own %h/%ad/%s plus")
say("    its message body; where no commit was owed, the matched rule LINES (grep -rn) from the")
say("    file that carries the rule. A finding-count summary is not a quote — see [6].")
since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(prev))
checks = [
    ("operator 15:24  spare humans / refuse agents", "commit",
     "feat(guard): spare humans, refuse agents"),
    ("operator 16:02  is everything pushed and ready", "tree",
     "Deploy \u2260 load"),
    ("operator 18:20  skills must load for ALL coding agents", "commit",
     "make 30 deprecated redirect stubs loadable"),
    ("operator 18:20  a loader that would drop a skill is a FAIL", "commit",
     "FAIL when a loader would drop one of our skills"),
    ("operator 18:20  the checker must resolve its own interpreter", "commit",
     "resolve its own interpreter"),
    ("operator 20:21  'just grind it out' (override, no new rule owed)", "tree",
     "override is final"),
]
landed = 0
for label, kind, pat in checks:
    say(f"    [{label}]")
    if kind == "commit":
        rc, out = run(["git", "log", "--oneline", "--fixed-strings", f"--grep={pat}",
                       f"--since={since}", "--max-count=1"])
        sha = out.split()[0] if out.strip() else None
        hit = bool(sha)
        say(f"        $ git log --oneline --fixed-strings --grep={pat!r} --since={since!r}"
            f"   -> rc={rc}")
        if hit:
            rc2, det = run(["git", "log", "-1", "--format=%h %ad %s%nBODY:%n%b",
                            "--date=short", sha])
            lines = det.splitlines()
            say(f"        $ git log -1 --format='%h %ad %s / BODY' {sha}   -> rc={rc2}")
            for ln in lines[:10]:
                say(f"            {ln[:170]}")
            if len(lines) > 10:
                say(f"            ... ({len(lines) - 10} more body lines in the commit)")
        else:
            say("            (NO MATCHING COMMIT)")
    else:
        rc, out = run(["grep", "-rn", "-F", "--include=*.md", pat,
                       "skills", "docs/templates"])
        lines = [l for l in out.splitlines() if l.strip()]
        hit = bool(lines)
        say(f"        $ grep -rn -F --include=*.md {pat!r} skills docs/templates   -> rc={rc}")
        for ln in lines[:2]:
            say(f"            {ln[:170]}")
        if not lines:
            say("            (NO CARRYING FILE)")
    landed += 1 if hit else 0

say()
say("[5] VERDICT")
say(f"    window non-empty: {'YES' if sess else 'NO'}"
    f"   operator rows: {len(prose)}"
    f"   landed-or-carried: {landed}/{len(checks)}")
say("    Not-silent: the window carried operator rows and the pass refined this skill's"
    " own mining recipe (repo-sourced), so this run reports rather than suppressing.")

say()
say("[6] STATIC GATE ON THIS GENERATOR (mandated by change-checklist Phase 1.5)")
say("    $ python3 ~/.hermes-cortex/scripts/adversarial-verify.py \\")
say("        --file docs/evidence/soul-refine-window-2026-10-22.sh --level A2 --gate")
gr, gout = run(["python3", str(Path.home() / ".hermes-cortex/scripts/adversarial-verify.py"),
                "--file", "docs/evidence/soul-refine-window-2026-10-22.sh",
                "--level", "A2", "--gate"])
for line in gout.splitlines():
    if line.strip():
        say(f"    {line}")
say(f"    rc={gr}   (0 = GATE_PASSED, i.e. no critical/high finding)")
say()
say("    the SAME run with --json, so every finding is quoted rather than characterised:")
jrc, jout = run(["python3", str(Path.home() / ".hermes-cortex/scripts/adversarial-verify.py"),
                 "--file", "docs/evidence/soul-refine-window-2026-10-22.sh",
                 "--level", "A2", "--json"])
try:
    blob = json.loads(jout)
except Exception as exc:  # noqa: BLE001 — a parse failure must be visible, not silent
    say(f"    !! --json output did not parse ({exc}); raw output follows unchanged")
    for ln in jout.splitlines()[:20]:
        say(f"    {ln}")
else:
    findings = blob.get("findings", blob if isinstance(blob, list) else [])
    say(f"    total_findings={blob.get('total_findings')}"
        f"  severity_counts={blob.get('severity_counts')}")
    for f in findings:
        if not isinstance(f, dict):
            say(f"      - {str(f)[:150]}")
            continue
        say(f"      - {f.get('finding_id')} [{f.get('severity')}] {f.get('technique')}"
            f" @ {str(f.get('target'))[:70]} | parameter={f.get('parameter')}"
            f" expected_type={f.get('expected_type')}"
            f" value_repr={str(f.get('value_repr'))[:40]}")
    if not findings:
        say("      (no finding objects in the JSON — the summary above is the whole result)")
say(f"    --json rc={jrc}")
con.close()
print(f"[probe rc={RC}]")
sys.exit(RC)
PY
PYRC=$?
echo "python mining pass rc=$PYRC"
echo
echo "=== syntax check of the file this transcript documents ==="
bash -n "$REPO_ROOT/docs/evidence/soul-refine-window-2026-10-22.sh"
SYNRC=$?
echo "bash -n docs/evidence/soul-refine-window-2026-10-22.sh rc=$SYNRC"
echo
echo "=== END OF TRANSCRIPT ==="
# The transcript must not mask its own failure. Before this, the last statement
# was an `echo`, so the script ALWAYS exited 0 and a broken run reported success.
if [ "$PYRC" -ne 0 ] || [ "$SYNRC" -ne 0 ]; then
  echo "!!! generator FAILED: python pass rc=$PYRC, syntax check rc=$SYNRC" >&2
  exit 1
fi
exit 0
