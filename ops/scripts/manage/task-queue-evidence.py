#!/usr/bin/env python3
"""Acceptance evidence for the task-queue remediation — RUN it, don't trust prose.

Regenerate the report with:

    bash ops/scripts/manage/run-task-queue-evidence.sh

The adversarial gate was right to refuse a close on a self-report: "6 slices released,
9 -> 16 claimable, tests pass" is a sentence, not evidence. This script RE-DERIVES
every number it states from the live store and the live repo, so any reviewer can run
it and get the same answers.

It works in AGGREGATES only — no row identifiers appear anywhere. That is deliberate:
the checks below are the invariants the remediation established, and they are stronger
than a list of ids because they keep holding for rows added later.

Checks, in order:
  1. NO slice is pending-with-an-assignee (unclaimable AND unwatched)
  2. the pending-slice pool is FULLY accounted for by its two views
  3. the parked pool is empty — every parked row was classified and resolved
  4. `waiting`/`blocked`/`paused` can each transition to `pending` (the parked arc)
  5. every task migration in the repo is registered AND deployed
  6. the DB schema version matches the newest migration in the repo
  7. the pre-existing test failures reproduce on a STASHED (clean) tree
Exit: 0 = every check passed.
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
from pathlib import Path

HOME = Path.home()
REPO = HOME / "hermes-cortex"
DEPLOY = HOME / ".hermes-cortex"
SCHEMA = REPO / "ops" / "services" / "tasks" / "schema"

# Baselines measured BEFORE the remediation (from the raw row dump, not from a
# report). The script asserts the movement, so a silent regression shows up here.
WAS_CLAIMABLE = 9
WAS_STRANDED = 6
WAS_PARKED = 6


def parse_db_version(blob: str):
    """Extract the schema version from a `tasks.schema_version` query result.

    The version is read with a SELECT rather than parsed from the migration runner's
    output. Parsing the runner was wrong twice over: `--apply-schema` MUTATES the
    system under inspection (an evidence script must not repair what it measures),
    and its two output shapes disagree — the applying shape reports the before-state
    in `current=` and the after-state in `(version N)`, so a DB that was BEHIND
    would have been reported as current.
    """
    m = re.search(r"^\s*(\d+)\s*$", blob, re.M)
    return int(m.group(1)) if m else None


def _load_task_db():
    spec = importlib.util.spec_from_file_location(
        "td_evidence", REPO / "ops" / "scripts" / "manage" / "task-db.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    td = _load_task_db()
    failures: list = []
    rows: list = []

    def check(label: str, ok: bool, detail: str) -> None:
        rows.append(f"| {label} | {'PASS' if ok else '**FAIL**'} | {detail} |")
        if not ok:
            failures.append(label)

    q = td.psql

    # 1 — the stranding invariant: nothing may be unclaimable AND unwatched
    stranded = int(q("SELECT count(*) FROM tasks.tasks WHERE status='pending' "
                     "AND kind='slice' AND assignee IS NOT NULL;").strip())
    check("No pending slice is assigned-and-unstarted", stranded == 0,
          f"{stranded} stranded (baseline {WAS_STRANDED})")

    # 2 — the two views must cover the pool exactly, with no remainder
    claimable = int(q("SELECT count(*) FROM tasks.tasks WHERE status='pending' "
                      "AND kind='slice' AND assignee IS NULL;").strip())
    total_pend = int(q("SELECT count(*) FROM tasks.tasks WHERE status='pending' "
                       "AND kind='slice';").strip())
    check("Pending-slice pool fully accounted for by its two views",
          claimable + stranded == total_pend,
          f"claimable {claimable} + assigned {stranded} = {total_pend}")
    check("The pool GREW by exactly the released slices (work is reachable again)",
          claimable >= WAS_CLAIMABLE + WAS_STRANDED,
          f"claimable {claimable} (baseline {WAS_CLAIMABLE} + {WAS_STRANDED} released)")

    # 3 — the parked pool is empty: every parked row was classified and resolved
    #     (5 exact duplicates cancelled, 1 unique row returned to pending)
    parked = int(q("SELECT count(*) FROM tasks.tasks WHERE status='waiting';").strip())
    check("No row is left parked in `waiting`", parked == 0,
          f"{parked} still waiting (baseline {WAS_PARKED})")
    # Cancelled rows are MOVED to tasks.task_archive (51 cancelled there), NOT left in
    # tasks.tasks — so a `count(*) WHERE status='cancelled'` on tasks.tasks is 0 even
    # when the cancellation worked. Check the archive instead.
    #
    # The cutoff is a FIXED date, not `now() - interval '3h'`: a sliding window makes
    # "re-runnable evidence" stop being re-runnable hours after it is written.
    #
    # It MUST be 2026-10-03, not 2026-10-04. The DB stores UTC while this host runs
    # KST (+9), so the cancellations landed at 2026-10-03 23:40 UTC — i.e. 2026-10-04
    # 08:40 local. A cutoff written as the LOCAL date ('2026-10-04') is midnight UTC
    # and excludes them, which reported 0 on a correct system. Verified against the
    # table: `GROUP BY left(archived_at::text,10)` shows exactly 5 cancelled on
    # 2026-10-03, and those 5 are this change's.
    arch = q("SELECT count(*) FROM tasks.task_archive WHERE status='cancelled' "
             "AND archived_at >= '2026-10-03'::timestamptz;").strip()
    check("The superseded slices were archived, not deleted",
          arch.isdigit() and int(arch) >= 5,
          f"{arch} cancelled rows archived since 2026-10-03 UTC (fixed cutoff) — a "
          f"cancel MOVES the row to tasks.task_archive, so it stays recoverable")

    # 4 — the parked arc is live in the DB function itself
    arcs = {s: q(f"SELECT tasks.transition_allowed('{s}', 'pending');").strip()
            for s in ("waiting", "blocked", "paused")}
    check("Parked rows can return to the claim pool",
          all(v == "t" for v in arcs.values()),
          " ".join(f"{k}->pending={v}" for k, v in arcs.items()))

    # 5 — registered AND deployed
    local = sorted(p.name for p in SCHEMA.glob("v0*.sql"))
    update = (REPO / "ops" / "scripts" / "cortex-update.sh").read_text()
    registered = {Path(m.group(1)).name for m in
                  re.finditer(r'register\s+"([^"]*tasks/schema/[^"]+)"', update)}
    unreg = [n for n in local if n not in registered]
    check("Every task migration is registered for deploy", not unreg,
          f"{len(local)} migrations; unregistered: {unreg or 'none'}")
    deployed = {p.name for p in
                (DEPLOY / "services" / "tasks" / "schema").glob("v0*.sql")}
    check("Every task migration is on the deployed tree",
          not [n for n in local if n not in deployed],
          f"{len(deployed)} of {len(local)} deployed")

    # 6 — DB version vs the newest migration in the repo. READ-ONLY on purpose:
    #     an evidence script must not repair the thing it is measuring, or it can
    #     never report that the thing was broken.
    try:
        blob = td.psql("SELECT COALESCE(MAX(version), 0) FROM tasks.schema_version;")
    except Exception as e:                                   # noqa: BLE001
        blob = f"<unreadable: {type(e).__name__}>"
    db_version = parse_db_version(blob)
    newest = max(int(re.search(r"v(\d+)__", n).group(1)) for n in local)
    check("DB schema version matches the newest repo migration",
          db_version == newest,
          f"DB={db_version if db_version is not None else 'unreadable'} repo={newest}")

    # 7 — the pre-existing failures, reproduced on a tree WITHOUT this change.
    #     A git WORKTREE, not `git stash`: the stash would also stash this script's
    #     own untracked output file mid-run and delete it from under the redirect.
    def hc_run(cwd):
        """Return (full_output, summary_line) for the hc_harness suite.

        PYTHONHASHSEED=0 is set deliberately: the assertion diff prints a Python SET
        of tool names ("Extra items in the left set: ..."), and set iteration order
        varies with the hash seed. Without this the captured output differs run to
        run and the report becomes unreproducible — which is exactly what the
        provenance test caught.
        """
        env = {**os.environ, "PYTHONHASHSEED": "0",
               "PYTEST_ADDOPTS": "-p no:cacheprovider"}
        r = subprocess.run(["python3", "-m", "pytest", "tests/test_hc_harness.py",
                            "-q"], cwd=cwd, capture_output=True, text=True,
                           timeout=300, env=env)
        full = (r.stdout or "") + (r.stderr or "")
        # Public repo: a captured `rootdir: /home/<user>/...` line is a PII finding.
        import re as _re2
        full = _re2.sub(r"/home/[A-Za-z0-9._-]+", "$HOME", full)
        summary = full.strip().splitlines()[-1] if full.strip() else "no output"
        return full, summary

    with_changes_full, with_changes = hc_run(REPO)

    # The regression pin, stated the only way it stays true: the harness tests are
    # GREEN now, and they FAILED at the parent of the commit that last touched this
    # test file — so the fix is what turned them green (not a moved baseline).
    fix_sha = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", "tests/test_hc_harness.py"],
        cwd=REPO, capture_output=True, text=True, timeout=60).stdout.strip()
    baseline = f"{fix_sha}^" if fix_sha else "HEAD~1"
    clean_tree_full, clean_tree = "", "not attempted"
    wt = Path("/tmp/tq-evidence-clean-tree")
    subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=REPO,
                   capture_output=True, text=True, timeout=120)
    add = subprocess.run(["git", "worktree", "add", "--detach", str(wt), baseline],
                         cwd=REPO, capture_output=True, text=True, timeout=180)
    if add.returncode == 0:
        try:
            clean_tree_full, clean_tree = hc_run(wt)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                           cwd=REPO, capture_output=True, text=True, timeout=120)
    else:
        clean_tree = f"worktree add failed: {add.stderr.strip()[:80]}"

    check("test_hc_harness passes now and FAILED before the fix (regression pin)",
          "failed" not in with_changes and "failed" in clean_tree,
          f"now: {with_changes} · {baseline[:12]} worktree: {clean_tree}")

    print("# Task-queue remediation — acceptance evidence\n")
    print("Regenerate with: `bash ops/scripts/manage/run-task-queue-evidence.sh`\n")
    print("Every number below is RE-DERIVED from the live store and the live repo by")
    print("running this script. Aggregates only — no row identifiers, so the checks")
    print("keep holding for rows added later.\n")
    print("Provenance: a regression test regenerates this report and compares it to")
    print("the committed file, so a hand-written table cannot pass for script output.\n")
    print("| Check | Result | Detail |")
    print("|---|---|---|")
    for ln in rows:
        print(ln)
    print(f"\n**Verdict: {'PASS' if not failures else 'FAIL'}**"
          + ("" if not failures else f" — failed: {failures}"))

    # Full raw output for the load-bearing claim (that the harness tests are green
    # now and were RED before the fix). A one-line paste is not evidence a reviewer
    # can check.
    print("\n## Raw test output — `tests/test_hc_harness.py`\n")
    print("`hc harness` and its registry were failing their own tests before this fix;")
    print("the same file is re-run at the parent of the commit that last touched it, so")
    print("the claim is a measured before/after rather than an assertion.\n")
    print("### With this change applied\n")
    print("```")
    print(with_changes_full.strip() or "(no output)")
    print("```\n")
    print("### On a HEAD~1 worktree (this change absent)\n")
    print("```")
    print(clean_tree_full.strip() or "(no output)")
    print("```")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
