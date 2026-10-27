#!/usr/bin/env python3
"""FROZEN window capture for the 2026-10-27 soul-refinement mining pass.

Regenerate with:
    python3 docs/evidence/generate-soul-window-evidence-2026-10-27.py \
        > docs/evidence/soul-refinement-window-2026-10-27.txt

Why the bounds are FROZEN (and why that is not laziness): the pass's window is
resolved from RUN TIME, so a generator re-run twenty minutes later derives
different bounds and prints different counts for the same pass. A transcript
that recomputes them contradicts the cycle note it exists to support. Both
bounds are therefore defaults here, env-overridable via SOUL_NOW / SOUL_START.

Why the start is NOT `now - 24 h`: the skill's own pitfall requires starting
from the PREVIOUS pass's end bound, or the two windows overlap and the same
correction is re-reviewed and re-counted as fresh work. The previous pass
(`..._20261026_231443`) has `last_activity_at` = the start bound below; that
makes this window 23.96 h rather than a nominal 24.00 h, and the difference is
real, not rounding.

Read-only: the session store is opened with mode=ro + PRAGMA query_only. No
session ids, chat ids or host paths are printed (the repo is public).
"""
from __future__ import annotations

import datetime
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

KST = datetime.timezone(datetime.timedelta(hours=9))

# --- FROZEN BOUNDS (env-overridable) -------------------------------------
SOUL_NOW = float(os.environ.get("SOUL_NOW", "1793110521.5995796"))
SOUL_START = float(os.environ.get("SOUL_START", "1793024274.9852538"))

REPO = Path(__file__).resolve().parents[2]

# Frozen pre-fix measurement: the detector's verdict at PASS START. Not
# reproducible by re-running (the fix has landed since), which is exactly why
# it is recorded here rather than recomputed — a generator that recomputed it
# would print PASS and silently erase the pass's own deliverable.
PRE_FIX_STRANDED = (
    "devops/approval-gate-debugging/SKILL.md",
    "devops/cron-job-management/SKILL.md",
    "devops/enforcement-change-safety/SKILL.md",
    "devops/orch-bus-worker/SKILL.md",
    "devops/shell-scripting/SKILL.md",
    "skill-vetting/SKILL.md",
    "software-development/change-checklist/SKILL.md",
)
HERMES_HOME = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
STATE_DB = HERMES_HOME / "state.db"

# Machine-marker heads: a scheduled job's own prompt, or a wrapper the
# transport adds. These read like operator input and are not.
#
# THE TEST IS `startswith` ON THE LSTRIPPED CONTENT — deliberately NOT
# `marker in content[:N]`. A substring test silently drops REAL operator prose
# that quotes a peer's report (measured 2026-10-27: "Time to fix the mycortex
# nightly dream for all agents. Ex: Cronjob Response: ..." — a live operator
# request — was dropped by a `[:200]` substring test, so the pass read 5 prose
# rows instead of 6 and never opened the day's only un-landed-looking request).
# The skill's rule is "drop rows OPENING with a machine marker"; implement that
# rule, not a stricter approximation of it. This generator and any mining
# script must share ONE classifier: two implementations disagreeing produced
# 5-vs-6 prose rows for the same window, i.e. the artifact contradicted the
# pass it documents.
MACHINE = (
    "[IMPORTANT: The user has invoked",
    "[IMPORTANT: You are running as a scheduled cron job",
    "[IMPORTANT: Background process",
    "[INTERNAL NOTIFICATION",
    "[Cron delivery:",
    "Gateway message origin",
    "[OUT-OF-BAND USER MESSAGE",
    "[CRON_FAILURE]",
)
# `subagent` matters as much as `cron`: a fan-out child stores its DISPATCHING
# prompt as role='user' exactly like a cron tick does.
NON_HUMAN_SOURCES = ("cron", "subagent")


def kst(epoch: float) -> str:
    return datetime.datetime.fromtimestamp(epoch, KST).strftime("%Y-%m-%d %H:%M:%S KST")


def classify(content: str) -> str:
    """Return the row's class: a LEADING machine marker, or operator prose.

    The anchor is the contract, and both directions are load-bearing:
      - a marker that LEADS (after lstrip) is machine output, however much
        prose follows it (a cron session's own task prompt is `role='user'`);
      - a marker that appears MID-text is prose, because the operator quotes
        cron deliveries and peer reports constantly.
    A match-anywhere classifier collapses that second class into the first and
    silently deletes real operator requests — measured 2026-10-27, when exactly
    that dropped the window's only still-open-looking request. Both directions
    are pinned in tests/test_soul_refinement_window_evidence.py.
    """
    head = (content or "").lstrip()
    return "machine" if any(head.startswith(m) for m in MACHINE) else "operator_prose"


def scrub(text: str, limit: int = 90) -> str:
    text = re.sub(r"\d{7,}", "<digits>", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def scrub_paths(text: str) -> str:
    """Collapse the operator's home dir to `$HOME` before anything is committed.

    Redaction belongs in the GENERATOR, never in the committed copy: a
    hand-patched artifact would disagree with the command line printed above it,
    and the next regeneration would re-introduce the path. Tool output is the
    live case — the doctor prints absolute paths inside its own messages, so
    every captured line goes through here.
    """
    return (text or "").replace(str(Path.home()), "$HOME")


def main() -> int:
    print("# SOUL refinement — 2026-10-27 mining window (FROZEN bounds)")
    print()
    print("Frozen ON PURPOSE: the window is resolved from RUN TIME, so a generator")
    print("re-run later derives different bounds and would print different counts for")
    print("the same pass. Both bounds are generator defaults (env-overridable via")
    print("SOUL_NOW / SOUL_START) so this artifact never contradicts the cycle note it")
    print("documents. See the skill's Pitfalls on count drift.")
    print()
    print(f"  SOUL_NOW   = {kst(SOUL_NOW)}   (epoch {SOUL_NOW:.3f})")
    print(f"  SOUL_START = {kst(SOUL_START)}   (epoch {SOUL_START:.3f})")
    print(f"  WINDOW     = {(SOUL_NOW - SOUL_START) / 3600:.2f} h ending at SOUL_NOW")
    print()
    print("The start is the PREVIOUS pass's `last_activity_at`, not `now - 24 h`: a full")
    print("24 h lookback at this run time would reach back into the previous window and")
    print("re-count corrections that pass already codified.")
    print()

    if not STATE_DB.exists():
        print(f"CANNOT VERIFY: no session store at {STATE_DB.name}")
        return 3

    con = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    con.execute("PRAGMA query_only=1")
    cur = con.cursor()
    lo, hi = SOUL_START, SOUL_NOW

    # --- sessions, classified by source -----------------------------------
    sess = list(
        cur.execute(
            "SELECT id, title, source FROM sessions "
            "WHERE COALESCE(last_activity_at, started_at) > ? "
            "AND COALESCE(last_activity_at, started_at) <= ? "
            "ORDER BY COALESCE(last_activity_at, started_at)",
            (lo, hi),
        )
    )
    by_source: dict[str, int] = {}
    for _sid, _title, source in sess:
        by_source[source or "(null)"] = by_source.get(source or "(null)", 0) + 1

    # --- user rows, classified BEFORE reading -----------------------------
    rows = list(
        cur.execute(
            "SELECT m.timestamp, s.id, s.source, m.content "
            "FROM messages m JOIN sessions s ON s.id = m.session_id "
            "WHERE m.role='user' AND m.active=1 AND m.timestamp > ? AND m.timestamp <= ? "
            "ORDER BY m.timestamp",
            (lo, hi),
        )
    )
    human_rows = [r for r in rows if (r[2] or "") not in NON_HUMAN_SOURCES]
    prose = [r for r in human_rows if classify(r[3]) == "operator_prose"]
    non_human_rows = len(rows) - len(human_rows)
    machine_in_human = len(human_rows) - len(prose)

    print("## Resolved counts (frozen bounds)")
    print()
    src_desc = ", ".join(f"{k} {v}" for k, v in sorted(by_source.items()))
    print("| Measure | Value |")
    print("|---|---|")
    print(f"| Sessions active in window (source: {src_desc}) | {len(sess)} |")
    print(f"| `role='user'` rows in window (active=1) | {len(rows)} |")
    print(f"| Rows in a NON-human transport (cron/subagent) | {non_human_rows} |")
    print(f"| Human-transport rows | {len(human_rows)} |")
    print(f"|   ↳ of those, machine-marker rows dropped | {machine_in_human} |")
    print(f"|   ↳ operator prose rows actually read | {len(prose)} |")
    print()
    print("A ROW is selected by its own `timestamp`; a SESSION by")
    print("`COALESCE(last_activity_at, started_at)` — different sets by construction,")
    print("so a row can belong to a session whose bound sits outside the window.")
    print()

    print("## Classification (per skill: classify BEFORE reading)")
    print()
    print(f"The window's {len(rows)} user rows split {non_human_rows} machine")
    print(f"(cron/subagent sessions, which store their own task prompt as `role='user'`)")
    print(f"and {len(human_rows)} in a human transport. Of the human rows {machine_in_human}")
    print(f"still carried a machine marker, leaving {len(prose)} prose rows — the actual")
    print("correction candidate set. Raw `role='user'` counting would over-report by")
    print(f"{len(rows) / max(len(prose), 1):.1f}x here.")
    print()
    if prose:
        print("Operator prose rows (scrubbed):")
        print()
        for ts, _sid, source, content in prose:
            print(f"  - [{kst(ts)}] src={source} {scrub(content)}")
    else:
        print("No operator prose rows: a genuinely zero-operator window.")
    con.close()
    print()

    print("## Reconciliation against the pass's OWN count (never silently overwrite)")
    print()
    print("The pass resolved, at its own instant: 28 sessions / 38 user rows / 5 prose")
    print("rows. This regeneration prints 27 / 38 / 6. Both deltas are explained, and")
    print("neither is drift:")
    print()
    print("  - sessions 28 -> 27: the pass's extra session is THIS RUN'S OWN session.")
    print("    A SESSION is bound by `COALESCE(last_activity_at, started_at)`, and at")
    print("    the mining instant this run's own `last_activity_at` was still <= the")
    print("    frozen end bound; it has since advanced past it. (Rows in a session are")
    print("    unaffected: a ROW is selected by its own `timestamp`.)")
    print("  - prose 5 -> 6: a DEFECT in the pass's own classifier, corrected here. The")
    print("    pass tested whether a machine marker appeared ANYWHERE in the first 200")
    print("    chars; the skill's rule is to drop only rows that OPEN with one (after")
    print("    lstrip). The stricter test dropped a real operator request that quotes a")
    print("    peer's report. The skill patch lands with this artifact.")
    print()

    print("## The window's own commits (so 'already landed' is checkable, not narrated)")
    print()
    print("Per the skill, each operator correction is checked against a same-day")
    print("committed artifact before a principle is proposed. Read from the repo:")
    print()
    log = subprocess.run(
        ["git", "-C", str(REPO), "log",
         f"--since={kst(lo)}", f"--until={kst(hi)}",
         "--pretty=format:%h|%ad|%s", "--date=format:%m-%d %H:%M"],
        capture_output=True, text=True,
    )
    for line in log.stdout.splitlines():
        print(f"  {line}")
    print()

    print("## Deliverable — fleet hygiene (all corrections already landed same-day)")
    print()
    print("Each correction in this window already had a same-day committed fix, so a")
    print("new principle would have duplicated landed work. Per the skill, the pass's")
    print("deliverable is instead the hygiene the day's own cycles re-broke. Recorded")
    print("BOTH measurements, because the live capture below can only show the")
    print("POST-fix state and would otherwise hide that anything was re-broken:")
    print()
    print("  BEFORE (frozen, measured at pass start — not reproducible by re-running")
    print("  this generator, since the fix has since landed and the tree changed):")
    print("    check-skill-drift-parity.py -> **Verdict: FAIL**  stranded: 7")
    for s in PRE_FIX_STRANDED:
        print(f"      - {s}")
    print()
    print("  The reconciler's own modes: `--apply` landed the 4 pure-superset files;")
    print("  the remaining 3 printed REVIEW (it would drop N repo lines). Each REVIEW")
    print("  line is a CLAIM, not a fact — measured again here as the same false-")
    print("  positive shape: in all 3 the deployed side reflowed AND extended the repo")
    print("  text, so the 'dropped' lines are superseded in place, not lost. Verified")
    print("  by reading the full `diff -u` of each BEFORE copying anything (the whole")
    print("  drop set was 14/1/4 lines and every one was present, rewritten, in the")
    print("  deployed text).")
    print()
    print("  HAZARD this pass had to check before landing them: a naive `cp` of a")
    print("  deployed skill into the repo would inject the deploy's own SOURCE banner")
    print("  if the file carried one (the parity tool ignores banners by design).")
    print("  Checked first: these 3 deployed copies carry no banner, headers match the")
    print("  repo byte-for-byte, so the copy is content-only.")
    print()
    parity = subprocess.run(
        [sys.executable, str(REPO / "ops/scripts/manage/check-skill-drift-parity.py")],
        capture_output=True, text=True, cwd=REPO,
    )
    pout = parity.stdout
    verdict = next((l for l in pout.splitlines() if l.startswith("**Verdict")), "??")
    counts = [
        l for l in pout.splitlines()
        if l.startswith("| ") and "in sync" not in l
    ]
    print(f"  check-skill-drift-parity.py  -> {scrub_paths(verdict)}   (rc={parity.returncode})")
    for line in counts:
        print(f"    {line}")
    print()
    print("  Parity measures ONE direction (content that exists only deployed). The")
    print("  doctor's `Skill drift` line measures the OTHER (repo ahead of deploy).")
    print("  Both are captured below because a parity PASS is not the deploy being")
    print("  current — reading only one direction is how a stale deploy stays invisible.")
    print()
    print("  This capture is taken AFTER this pass's own skill patch and BEFORE its")
    print("  deploy, so a repo-ahead line for the skill this pass patched is EXPECTED")
    print("  here and is what the deploy following the commit clears. The line is kept")
    print("  rather than filtered: a capture that hid its own pre-deploy state would be")
    print("  the same one-direction reading this section exists to prevent.")
    print()
    doc = subprocess.run(
        [sys.executable, str(REPO / "ops/scripts/manage/cortex-doctor.py")],
        capture_output=True, text=True, cwd=REPO,
    )
    for line in doc.stdout.splitlines():
        if "kill drift" in line.lower() or "SOUL.md" in line:
            print(f"  {scrub_paths(line.strip())}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
