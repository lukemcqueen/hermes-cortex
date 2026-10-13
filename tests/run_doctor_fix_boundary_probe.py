#!/usr/bin/env python3
"""Boundary-input probe for the doctor check-accuracy fixes (change-checklist Phase 1.5).

Drives each changed helper with inputs a healthy run never supplies: None, empty, a path that is
a FILE where a DIRECTORY is expected, a malformed `.git`, non-ASCII text, and prose that merely
MENTIONS the score-cycle CLI. Prints every result with an explicit PASS/FAIL verdict.

It found two real crashes on the changed paths, both fixed:
  * `find_script_consumers([None])` raised
    `TypeError: argument should be a str or an os.PathLike object ... not 'NoneType'`
  * a PROSE sentence mentioning `score-cycle` counted as an invocation

Run: python3 tests/run_doctor_fix_boundary_probe.py      (exit 0 = all pass, 1 = a failure)
"""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ops" / "scripts" / "manage"))

from cortex_doctor import checks  # noqa: E402

_spec = importlib.util.spec_from_file_location("mw", REPO / "ops/scripts/manage/mcp_wiring.py")
assert _spec is not None and _spec.loader is not None
mw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mw)
_spec2 = importlib.util.spec_from_file_location(
    "dc", REPO / "ops/scripts/manage/cortex_doctor/config.py")
assert _spec2 is not None and _spec2.loader is not None
dc = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(dc)

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {got!r}")
    if not ok:
        failures.append(f"{label}: got {got!r}, want {want!r}")


print("-- mcp_wiring.repo_rel_script --")
check("None", mw.repo_rel_script(None), "")
check("empty string", mw.repo_rel_script(""), "")
check("bare filename", mw.repo_rel_script("task-mcp.py"), "mcp-servers/task-mcp.py")
check("already relative", mw.repo_rel_script("mcp-servers/task-mcp.py"), "mcp-servers/task-mcp.py")
check("absolute path", mw.repo_rel_script("/opt/x/task-mcp.py"), "/opt/x/task-mcp.py")
check("non-ascii", mw.repo_rel_script("tâsk-mcp.py"), "mcp-servers/tâsk-mcp.py")

print("-- mcp_wiring.audit with boundary config text --")
for label, text in (("None", None), ("empty", ""), ("no mcp_servers key", "model: {}\n"),
                    ("non-ascii", "mcp_servers:\n  t\u00e2sk:\n    command: /x\n")):
    res = mw.audit(text, {"tasks": "task-mcp.py"}, exists=lambda p: True)
    check(f"{label} -> status", res[0][1], "FAIL")

print("-- config.find_script_consumers roots --")
empty_map = {v: [] for v in
             ["JUDGE_MODEL", "EMBEDDING_MODEL", "CODING_MODEL", "CREATIVE_MODEL"]}
check("None root entry", dc.find_script_consumers([None]), empty_map)
check("nonexistent root", dc.find_script_consumers([Path("/nope/nope")])["JUDGE_MODEL"], [])
check("root that is a FILE", dc.find_script_consumers([Path("/etc/hostname")])["JUDGE_MODEL"], [])

print("-- config._reads_env_var --")
check("empty text", dc._reads_env_var("", "JUDGE_MODEL"), False)
check("name only, no read", dc._reads_env_var("JUDGE_MODEL", "JUDGE_MODEL"), False)
check("comment only", dc._reads_env_var("# JUDGE_MODEL is set\n", "JUDGE_MODEL"), False)

print("-- checks._is_git_repo --")
check("no .git", checks._is_git_repo(Path("/tmp")), False)
check("missing dir", checks._is_git_repo(Path("/nope/nope")), False)

print("-- checks._is_cortex_worktree --")
check("no .git", checks._is_cortex_worktree(Path("/tmp")), False)

print("-- checks._invokes_score_cycle --")
check("empty", checks._invokes_score_cycle(""), False)
check("bare token in prose", checks._invokes_score_cycle("the score-cycle tool\n"), False)
check("argv literal", checks._invokes_score_cycle('["score-cycle"]\n'), True)
check("echo mention", checks._invokes_score_cycle('echo "score-cycle"\n'), False)

print("-- checks._score_cycle_consumers --")
check("nonexistent root", checks._score_cycle_consumers([Path("/nope/nope")]), [])

if failures:
    print(f"\nRESULT: FAIL ({len(failures)})")
    for f in failures:
        print("   " + f)
    sys.exit(1)
print("\nRESULT: ALL PASS")
