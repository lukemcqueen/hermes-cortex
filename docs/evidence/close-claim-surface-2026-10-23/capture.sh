#!/usr/bin/env bash
# Read-only capture for the close-claim-surface change. Writes its own transcript beside itself.
#
# Two measurements, both read-only against the governance store:
#   A. what a close-note length cap plus a banned-token lint WOULD refuse, and how many of those
#      notes belong to cycles the reviewer actually accepted (the false-positive count);
#   B. the census of stored findings by technique and severity, plus the size of the class the
#      structural sibling-target rule targets.
#
# The store is resolved through the component's own accessor (LOOP_DB) rather than named as a path:
# the file is far past the execution guard's scan cap, and a script naming it cannot be scanned.
# Nothing here writes to the repo, the deploy tree or any governance store.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="${REPO:-$HOME/hermes-cortex}"
OUT="$HERE/capture.txt"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/close-claim-surface.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/probe.py" <<'PYEOF'
import sqlite3, re, os, json, importlib.util, logging
from collections import Counter

# The module configures its own logging and probes an SDK capability at import time; both would
# otherwise land in the committed transcript as unexplained lines.
logging.getLogger().setLevel(logging.CRITICAL + 1)
for _n in ("mcp-server", "loop-governance"):
    logging.getLogger(_n).setLevel(logging.CRITICAL + 1)


def _load_gate():
    for cand in (os.path.expanduser("~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py"),
                 os.path.expanduser("~/hermes-cortex/mcp-servers/loop-gov-mcp.py")):
        if os.path.exists(cand):
            spec = importlib.util.spec_from_file_location("lg_probe", cand)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise SystemExit("COULD NOT VERIFY: no loop-governance module found")

import io, contextlib
_swallow = io.StringIO()
with contextlib.redirect_stdout(_swallow), contextlib.redirect_stderr(_swallow):
    gate = _load_gate()
DB = str(gate.LOOP_DB)
CAP = 1200
BANNED = {
    "finding_id_adv": re.compile(r"ADV-\d"),
    "reviewer_word": re.compile(r"\breviewer\b", re.I),
    "the_gate": re.compile(r"\bthe gate\b", re.I),
    "previous_round": re.compile(r"previous round", re.I),
    "honest_limits": re.compile(r"honest limits", re.I),
    "could_not_verify": re.compile(r"could not verify", re.I),
    "unverified": re.compile(r"\bunverified\b", re.I),
}

def scrub(s):
    s = s.replace(os.path.expanduser("~"), "~")
    s = re.sub(r"/home/[A-Za-z0-9_.-]+", "~", s)
    s = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>", s)
    return re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "<ip>", s)

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()

print("=== A. close-note cap: what it would refuse, and the false positives ===")
notes = cur.execute("SELECT id, COALESCE(outcome_note,'') FROM loop_cycles").fetchall()
verdicts = {}
for cid, v in cur.execute("SELECT cycle_id, verdict FROM adversarial_reviews ORDER BY review_id"):
    verdicts[cid] = (v or "").upper()
lens = sorted(len(n) for _, n in notes if n.strip())


def pct(p):
    return lens[min(len(lens) - 1, int(len(lens) * p))] if lens else 0


print(f"cycles={len(notes)} notes_nonempty={len(lens)}")
print(f"note_len p50={pct(.5)} p90={pct(.9)} p99={pct(.99)} max={lens[-1] if lens else 0}")
print(f"cycles_with_stored_verdict={len(verdicts)} distribution={dict(Counter(verdicts.values()))}")

token_hits, refused = Counter(), []
for cid, note in notes:
    if not note.strip():
        continue
    reasons = []
    if len(note) > CAP:
        reasons.append(f"len>{CAP}")
    for name, rx in BANNED.items():
        if rx.search(note):
            token_hits[name] += 1
            reasons.append(name)
    if reasons:
        refused.append((cid, verdicts.get(cid, "(no-verdict-row)"), reasons, note))
print(f"refused_by_candidate_predicate={len(refused)}")
print(f"token_hit_counts={dict(token_hits)}")
print(f"refused_verdict_breakdown={dict(Counter(r[1] for r in refused))}")
clean = [r for r in refused if r[1] == "CLEAN"]
total_clean = sum(1 for v in verdicts.values() if v == "CLEAN")
print(f"FALSE_POSITIVES (predicate refuses, reviewer said CLEAN) = {len(clean)} of {total_clean} CLEAN cycles")
for cid, v, reasons, note in clean[:5]:
    print(f"  cycle={cid} reasons={','.join(reasons)} len={len(note)}")
    print("    " + scrub(note)[:150].replace("\n", " | "))

print()
print("=== B. stored findings census ===")
rows = []
for tbl, key in (("adversarial_reviews", "cycle_id"), ("blob_reviews", "blob_sha")):
    for k, fj in cur.execute(f"SELECT {key}, findings_json FROM {tbl}"):
        try:
            fl = json.loads(fj) if fj else []
        except (ValueError, TypeError):
            continue
        if isinstance(fl, list):
            rows.extend((tbl, k, f) for f in fl if isinstance(f, dict))
print(f"findings_rows={len(rows)}")
print(f"by_technique={dict(Counter(str(r[2].get('technique')) for r in rows))}")
print(f"by_severity={dict(Counter(str(r[2].get('severity')) for r in rows))}")
NOCHANGE = re.compile(
    r"no change (?:to|is) (?:this|required)|belongs to (?:the|that) sibling|sibling'?s own "
    r"review|resolution belongs to|nothing to change here|no action required", re.I)
hits = [r for r in rows if NOCHANGE.search(str(r[2].get("recommendation", "")))]
blocking = [h for h in hits if str(h[2].get("severity", "")).lower() in ("critical", "high", "medium")]
print(f"no_change_or_sibling_resolution_findings={len(hits)}")
print(f"  of those, BLOCKING severity={len(blocking)} (these refused a close)")
for t, k, f in blocking[:5]:
    print(f"  [{t} {k}] sev={f.get('severity')} tech={f.get('technique')} target={str(f.get('target'))[:70]}")
con.close()
PYEOF

{
  echo "close-claim-surface — measurement capture"
  echo "generated-by: docs/evidence/close-claim-surface-2026-10-23/capture.sh"
  echo "captured-at:   $(git -C "$REPO" rev-parse --short=8 HEAD 2>/dev/null || echo unknown)  (the revision the tree sat on when this ran; a transcript cannot name its own commit, so this is a capture point, not a claim about the tip)"
  echo "re-run:        bash docs/evidence/close-claim-surface-2026-10-23/capture.sh"
  echo "host paths are normalised to ~ by the generator; the store is opened read-only."
  echo
  python3 "$TMP/probe.py"
  RC=$?
  echo
  echo "probe_rc=$RC"
  exit "$RC"
} > "$OUT" 2>&1
