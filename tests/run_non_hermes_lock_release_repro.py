#!/usr/bin/env python3
"""Reproduction: the titus/pi lock-release failure — PRE-FIX vs CURRENT vs DEPLOYED.

Drives the real scenario against THREE revisions of the server module:
  PRE-FIX   `git show <base>:mcp-servers/loop-gov-mcp.py` where <base> is
            LOOP_GOV_PRE_FIX_REV (default HEAD~1) — name it explicitly so the
            comparison cannot silently drift to the wrong revision.
  CURRENT   the working-tree module.
  DEPLOYED  ~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py — the copy a
            harness actually runs. A green check on the repo copy proves nothing
            about the deployed one, so it is checked separately (and reported as
            SKIPPED, not passed, when this host has nothing deployed).

Scenario (exactly the reported one): a NON-Hermes caller (no injected repo —
pi / Claude Code / the CLI) calls begin_change while sitting in a project repo on
a host that also holds the canonical ~/hermes-cortex; the work lands in the
project repo; the cycle is scored; end_change is called.

The tool ASSERTS, and exits non-zero when an expectation is violated, so a
failing run cannot be mistaken for a passing artifact:
  PRE-FIX  must reproduce the report — canonical-repo tag, refusal, lock LEFT BEHIND.
  CURRENT / DEPLOYED  must tag the session's own repo, close, and release the lock.

Usage:
  python3 tests/run_non_hermes_lock_release_repro.py
  python3 tests/run_non_hermes_lock_release_repro.py --write-artifact [--include-doctor]
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MCP_REL = "mcp-servers/loop-gov-mcp.py"
DEPLOYED = Path.home() / ".hermes-cortex" / "tools" / "loop-governance" / "loop-gov-mcp.py"
ARTIFACT = REPO / "tests" / "artifacts" / "non-hermes-repo-identity-repro.txt"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mkrepo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "agent@hermes.local"],
                   capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "agent"], capture_output=True)
    hooks = path / ".nohooks"
    hooks.mkdir(exist_ok=True)
    subprocess.run(["git", "-C", str(path), "config", "core.hooksPath", str(hooks)],
                   capture_output=True)
    return path


def scenario(mod) -> dict:
    """Run the reported flow once against `mod`; return what happened."""
    home = Path(tempfile.mkdtemp(prefix="rg-home-"))
    _mkrepo(home / "hermes-cortex")                     # host-canonical, EMPTY
    proj = _mkrepo(home / "projects" / "proj")
    (proj / "work.txt").write_text("x\n")
    subprocess.run(["git", "-C", str(proj), "add", "work.txt"], capture_output=True)
    subprocess.run(["git", "-C", str(proj), "commit", "-q", "-m", "seed"],
                   capture_output=True)

    state = home / ".hermes-cortex" / "state"
    state.mkdir(parents=True, exist_ok=True)
    mod.HOME = home
    mod.SESSION_FILE = home / ".hermes" / "session.id"
    mod.GOVERNANCE_STATE_DIR = state
    mod.LOOP_DB = home / ".hermes-cortex" / "data" / "loop-governance.db"
    mod._PROCESS_SESSION_ID = ""                        # non-Hermes caller

    prev = os.getcwd()
    os.chdir(proj)
    try:
        slug = mod._derive_slug(None)
        mod._begin_change({"task_id": "rg-1", "description": "pi work in a project repo"})
        lock = json.loads((state / f".governance-{mod.get_session_id(None)}.json").read_text())
        # the work lands INSIDE the window, in the PROJECT repo, trivial (no reviewer)
        (proj / "work.txt").write_text("x\ny\n")
        subprocess.run(["git", "-C", str(proj), "add", "work.txt"], capture_output=True)
        subprocess.run(["git", "-C", str(proj), "commit", "-q", "-m", "pi work"],
                       capture_output=True)
        mod._feedback_accept({"task_id": "rg-1", "note": "done", "completeness": 8,
                              "quality": 8, "progress": 8})
        text = mod._end_change({"task_id": "rg-1"}).content[0].text
        left = sorted(p.name for p in state.glob(".governance-*.json"))
        return {
            "lock.repo_slug": lock.get("repo_slug"),
            "lock.repo_path": lock.get("repo_path") or "(empty)",
            "end_change verdict": text.strip().splitlines()[0],
            "lock file left behind": left or "none — released",
            "_released": not left,
            "_refused": "cannot contain" in text,
        }
    finally:
        os.chdir(prev)


def _git(*args) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True).stdout.strip()


def _doctor() -> str:
    proc = subprocess.run([sys.executable, "ops/scripts/manage/cortex-doctor.py", "--quiet"],
                          cwd=str(REPO), capture_output=True, text=True, timeout=900)
    body = proc.stdout + proc.stderr
    tail = [ln for ln in body.splitlines() if ln.strip()][-6:]
    warns = sum(1 for ln in body.splitlines() if "⚠" in ln)
    return "\n".join(tail) + f"\n  (exit code {proc.returncode}; {warns} warning line(s) in output)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-artifact", action="store_true",
                    help="write tests/artifacts/non-hermes-repo-identity-repro.txt")
    ap.add_argument("--include-doctor", action="store_true",
                    help="append the cortex-doctor transcript to the artifact")
    args = ap.parse_args()

    base_rev = os.environ.get("LOOP_GOV_PRE_FIX_REV", "HEAD~1")
    out: list = []
    failures: list = []

    def emit(line=""):
        print(line)
        out.append(line)

    head = _git("rev-parse", "--short", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    pre_sha = _git("rev-parse", "--short", base_rev)
    pre_src = _git("show", f"{base_rev}:{MCP_REL}")
    if not pre_src:
        print(f"could not read {MCP_REL} at {base_rev} — cannot verify anything")
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="rg-prefix-"))
    pre_file = tmp / "loop-gov-mcp.prefix.py"
    pre_file.write_text(pre_src)

    targets = [
        ("PRE-FIX", f"git {base_rev} ({pre_sha})", pre_file, "refuse"),
        ("CURRENT", "working tree", REPO / MCP_REL, "release"),
        ("DEPLOYED", "harness path", DEPLOYED, "release"),
    ]

    emit("Reproduction — end_change on a NON-Hermes host (titus / pi), 2026-10-09")
    emit("=" * 68)
    emit("Report: a pi session working in a project repo opens a governance lock and the")
    emit("lock is NEVER released — the operator must delete")
    emit("~/.hermes-cortex/state/.governance-sess_*.json by hand.")
    emit()
    emit(f"revision under test   : {head}  (branch {branch}) — HEAD when this ran. The artifact")
    emit("                        is committed BY the change it measures, so the file under")
    emit(f"                        test at the carrying commit is identical (check with")
    emit(f"                        `git diff <carrying-commit> {head} -- {MCP_REL}`).")
    emit(f"pre-fix comparison ref: {base_rev} ({pre_sha})")
    emit("re-run with           : "
         "python3 tests/run_non_hermes_lock_release_repro.py --write-artifact --include-doctor")
    emit()

    for label, desc, path, expectation in targets:
        if label == "DEPLOYED" and not path.exists():
            emit(f"── {label} ({desc}) ──")
            emit(f"   SKIPPED — {path} is not present on this host (nothing deployed to check)")
            emit()
            continue
        emit(f"── {label} ({desc}) ──")
        try:
            res = scenario(_load(path, "lg_" + label.lower()))
        except Exception as e:  # noqa: BLE001 — a scenario error is a FAILURE, never a result
            emit(f"   ERROR : {type(e).__name__}: {e}")
            emit()
            failures.append(f"{label}: scenario raised {type(e).__name__}")
            continue
        for k, v in res.items():
            if not k.startswith("_"):
                emit(f"   {k:24} : {v}")
        emit()
        if expectation == "refuse":
            if not (res["_refused"] and not res["_released"]):
                failures.append(f"{label}: expected the pre-fix refusal WITH the lock left "
                                f"behind, got released={res['_released']} "
                                f"refused={res['_refused']}")
        elif not (res["_released"] and not res["_refused"]):
            failures.append(f"{label}: expected the lock RELEASED, got "
                            f"released={res['_released']} refused={res['_refused']}")

    emit("Reading of the transcript")
    emit("-" * 68)
    emit("PRE-FIX: the lock is tagged with the HOST-CANONICAL repo (hermes-cortex) because a")
    emit("caller with no injector fell through to Priority 1 in _derive_slug(). The close gate")
    emit("then looks for this session's work in ~/hermes-cortex, cannot find it, and REFUSES —")
    emit("a refusal leaves the lock held by design, and the remedy it prints (a governance-")
    emit("enforcer injection) does not exist on a non-Hermes harness. The lock file is left on")
    emit("disk: the reported symptom, in the same file-name shape (sess_<12 hex>) the report cites.")
    emit("CURRENT / DEPLOYED: the session resolves its OWN repo (proj, absolute path recorded in")
    emit("the lock), the close completes, and the lock is released — no operator action.")

    if args.include_doctor:
        emit()
        emit("Post-deploy doctor (this host, after `cortex-dogfood.sh --force`)")
        emit("-" * 68)
        emit(_doctor())

    emit()
    emit("RESULT: " + ("ALL PASS" if not failures else "FAILURES: " + "; ".join(failures)))

    if args.write_artifact:
        ARTIFACT.write_text("\n".join(out) + "\n")
        print(f"\nartifact written: {ARTIFACT}")
    if failures:
        print("RESULT: FAIL")
        return 1
    print("RESULT: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
