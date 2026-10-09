#!/usr/bin/env python3
"""Reproduction: the titus/pi lock-release failure, PRE-FIX vs CURRENT.

Drives the real scenario against BOTH revisions of the server module:
  pre-fix  = `git show HEAD:mcp-servers/loop-gov-mcp.py` (git HEAD, i.e. the
             revision the report came in against)
  current  = the working-tree module

Scenario (exactly the reported one): a NON-Hermes caller (no injected repo —
pi / Claude Code / the CLI) prompts begin_change while sitting in a project repo
on a host that also holds the canonical ~/hermes-cortex; the work lands in the
project repo; the cycle is scored; end_change is called.

Reported symptom: the close is refused as a "wrong repo" and the lock file is
left behind — only an operator can remove it.

Usage:  python3 tests/run_non_hermes_lock_release_repro.py
        (prints a transcript; makes no change to the repo)
"""
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path.home() / "hermes-cortex"
MCP_REL = "mcp-servers/loop-gov-mcp.py"


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
        }
    finally:
        os.chdir(prev)


def main():
    pre_src = subprocess.run(["git", "-C", str(REPO), "show", "HEAD:" + MCP_REL],
                             capture_output=True, text=True).stdout
    tmp = Path(tempfile.mkdtemp(prefix="rg-prefix-"))
    pre_file = tmp / "loop-gov-mcp.prefix.py"
    pre_file.write_text(pre_src)

    print("Reproduction: end_change on a NON-Hermes host (titus / pi)")
    print("=" * 68)
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    print(f"pre-fix revision : HEAD ({head})")
    print(f"current          : working tree ({MCP_REL})")
    print(f"re-run with      : python3 {Path(__file__).relative_to(Path.home())}")
    print()
    results = {}
    for label, path in (("PRE-FIX (HEAD)", pre_file),
                        ("CURRENT (working tree)", REPO / MCP_REL)):
        try:
            results[label] = scenario(_load(path, "lg_" + label.split()[0].lower()))
        except Exception as e:  # noqa: BLE001
            results[label] = {"error": f"{type(e).__name__}: {e}"}
    for label, res in results.items():
        print(f"── {label} ──")
        for k, v in res.items():
            print(f"   {k:24} : {v}")
        print()


if __name__ == "__main__":
    main()
