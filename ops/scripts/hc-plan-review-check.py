#!/usr/bin/env python3
"""hc-plan-review-check — the plan-review-before-slice gate.

For a GOVERNED development session making a non-trivial change in ANY repo,
require the active governance cycle to carry a recorded adversarial plan review
(a row in `adversarial_reviews`) BEFORE the implementation commit lands. This
turns Luke's standing rule ("have deepseek pro review the plan before building")
into a commit gate: begin_change -> plan -> adversarial-review.py --cycle-id N
--review -> implement -> commit -> end_change.

A "slice" is a change worth reviewing: it touches a source/config file AND is
either multi-file or >50 added+deleted lines. Trivial single-file edits, docs,
and hermes-cortex's own adversarial-scan commits are exempt (the HC repo is
already covered by the A2/A4 scan; this gate targets project repos).

Skipped (rc 0) when there is no active governance session -- an ungoverned or
human commit has no cycle to have reviewed (Mirrors hc-reflexion-check
--skip-no-session, so it may fire in every repo without blocking manual commits).

EXIT CODES (a shell gate must be able to gate on this):
    0  pass (no slice, no governed session, or the active cycle is reviewed)
    1  refuse -- a slice without a plan review on the active cycle
    2  usage error
    3  cannot verify (DB missing/unreachable, no git) -- fail closed, named
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

GOV_DIR = Path.home() / ".hermes-cortex" / "state"
DEFAULT_DB = Path.home() / ".hermes-cortex" / "data" / "loop-governance.db"

# A change is a "slice" when it touches a source/config file AND (multiple files
# OR > this many added+deleted lines). Single trivial files pass without review.
SOURCE_EXT = {".py", ".sh", ".bash", ".ts", ".tsx", ".js", ".jsx",
              ".go", ".rs", ".rb", ".yaml", ".yml", ".toml", ".json"}
MAX_SLICE_FILES = 1        # more than this many source files => slice
MAX_SLICE_LINES = 50       # more than this many added+deleted lines => slice

EXIT_PASS = 0
EXIT_REFUSE = 1
EXIT_USAGE = 2
EXIT_CANNOT_VERIFY = 3

_HCRC_PATHS = (
    Path(__file__).resolve().parent / "hc-reflexion-check.py",
    Path.home() / ".hermes-cortex" / "scripts" / "hc-reflexion-check.py",
)


def _load_hcrc():
    """Import hc-reflexion-check.py for its repo_slug()/active_session_id()
    so the session identity used here is the SAME one the reflexion gate uses --
    one implementation of 'which session does this repo's commit belong to'."""
    for path in _HCRC_PATHS:
        if path.is_file():
            try:
                spec = importlib.util.spec_from_file_location("hcrc_reflexion", path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    return mod
            except Exception as exc:  # noqa: BLE001
                print(f"hc-plan-review-check: could not load {path}: {exc}",
                      file=sys.stderr)
                return None
    return None


def staged_slice(repo_root: str) -> tuple[bool, str]:
    """(is_slice, detail). Inspect the STAGED change (git diff --cached)."""
    try:
        names = subprocess.run(
            ["git", "-C", repo_root, "diff", "--cached", "--name-only", "-z"],
            capture_output=True, text=True, timeout=10).stdout.split("\0")
        names = [n for n in names if n]
        numstat = subprocess.run(
            ["git", "-C", repo_root, "diff", "--cached", "--numstat"],
            capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        return True, f"could-not-verify staged set: {exc}"

    src = [n for n in names if Path(n).suffix in SOURCE_EXT]
    # Untracked, not-yet-staged files are invisible to --cached; a new file the
    # agent stages first IS seen. Docs-only is not a slice.
    if not src:
        return False, f"{len(names)} non-source file(s), no slice"
    added = removed = 0
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            a, r = parts[0], parts[1]
            if a.isdigit():
                added += int(a)
            if r.isdigit():
                removed += int(r)
    total = added + removed
    if len(src) > MAX_SLICE_FILES or total > MAX_SLICE_LINES:
        return True, f"{len(src)} source file(s), {total} added+deleted lines"
    return False, f"{len(src)} source file(s), {total} lines — trivial"


def active_cycle_id(db_path: Path, session_id: str) -> int | None:
    """The most recent loop_cycles.id for this session (NULL session excluded)."""
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM loop_cycles WHERE session_id = ? "
            "AND session_id IS NOT NULL AND session_id != '' "
            "ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def cycle_reviewed(db_path: Path, cycle_id: int) -> bool:
    """Does adversarial_reviews hold a row for this cycle (a reviewed plan)?"""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM adversarial_reviews WHERE cycle_id = ? "
            "ORDER BY ts DESC LIMIT 1", (cycle_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(prog="hc-plan-review-check",
                                 description=__doc__)
    ap.add_argument("--repo-root", default="",
                    help="git toplevel (default: git rev-parse --show-toplevel)")
    ap.add_argument("--session", default="",
                    help="session id override (default: active governance lock)")
    ap.add_argument("--db", default=str(DEFAULT_DB),
                    help="loop-governance DB path")
    ap.add_argument("--skip-no-session", action="store_true",
                    help="exit 0 when no active governance session (ungoverned/human commit)")
    a = ap.parse_args()

    hcrc = _load_hcrc()
    if hcrc is None:
        print("hc-plan-review-check: cannot load hc-reflexion-check.py "
              "(session resolution) — run cortex-update.sh", file=sys.stderr)
        return EXIT_CANNOT_VERIFY

    repo_sl = a.repo_root.strip() or _git_toplevel()
    slug = hcrc.repo_slug()
    if slug == "hermes-cortex":
        # self-contained HC-repo exemption, matching the pre-commit hook's
        # IS_CORTEX_REPO scope: hermes-cortex is covered by its own close-time
        # adversarial review (A2/A4 on staged scripts), so this gate targets
        # project repos only. Return early regardless of caller.
        print("PASS — hermes-cortex repo (covered by its own close review)")
        return EXIT_PASS
    session_id = a.session.strip() or hcrc.active_session_id(slug)

    if not session_id:
        if a.skip_no_session:
            print(f"NO-SESSION — plan-review gate skipped (no governed session; "
                  f"nothing to review)")
            return EXIT_PASS
        print(f"NO-SESSION — no active governance lock for repo '{slug}'; "
              "call begin_change() before committing", file=sys.stderr)
        return EXIT_REFUSE

    is_slice, detail = staged_slice(repo_sl)
    if not is_slice:
        print(f"PASS — {detail} needs no plan review (cycle {session_id})")
        return EXIT_PASS

    try:
        cycle_id = active_cycle_id(Path(a.db).expanduser(), session_id)
    except Exception as exc:  # noqa: BLE001
        print(f"hc-plan-review-check: cannot read loop-governance DB "
              f"({exc}) — run cortex-update.sh", file=sys.stderr)
        return EXIT_CANNOT_VERIFY

    if cycle_id is None:
        print("hc-plan-review-check: no loop cycle found for the active session "
              "— begin_change() creates it; run it before the slice", file=sys.stderr)
        return EXIT_REFUSE

    try:
        reviewed = cycle_reviewed(Path(a.db).expanduser(), cycle_id)
    except Exception as exc:  # noqa: BLE001
        print(f"hc-plan-review-check: cannot read adversarial_reviews "
              f"({exc}) — run cortex-update.sh", file=sys.stderr)
        return EXIT_CANNOT_VERIFY

    if reviewed:
        print(f"PASS — cycle {cycle_id} has a reviewed plan ({detail})")
        return EXIT_PASS

    print(f"PLAN-REVIEW REQUIRED — this is a non-trivial slice ({detail}) and "
          f"cycle {cycle_id} has no recorded adversarial plan review.", file=sys.stderr)
    print("  Review the plan for this slice BEFORE implementing it:", file=sys.stderr)
    print("    ops/scripts/orch-bus/adversarial-review.py "
          f"--cycle-id {cycle_id} --material \"$(cat <plan>)\" --review \\", file=sys.stderr)
    print("      --reviewer-id plan-<slug>", file=sys.stderr)
    print("  Then re-commit.", file=sys.stderr)
    return EXIT_REFUSE


def _git_toplevel() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "."


if __name__ == "__main__":
    sys.exit(main())
