#!/usr/bin/env python3
"""MCP wiring must be audited by PATHS, not by whether the server's name appears in a file.

Kustos: "No loop-governance MCP tools in catalog" while the doctor reported
`MCP server (loop-governance): PASS — configured in config.yaml` — the check looked for the
NAME. A registration pointing at a missing venv, wrapper or script loads nothing and says
nothing. These tests pin the parser and the verdicts hermetically (an injected `exists`).

Run: python3 tests/test_mcp_wiring.py
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MOD = REPO / "ops" / "scripts" / "manage" / "mcp_wiring.py"

GOOD = """\
mcp_servers:
  loop-governance:
    command: /opt/venv/bin/python3
    args:
    - /opt/tools/loop-gov-mcp.py
  tasks:
    command: /opt/venv/bin/python3
    args: [/opt/repo/mcp-servers/task-mcp.py]
other_key: 1
"""


def _load():
    spec = importlib.util.spec_from_file_location("mcp_wiring", MOD)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_entries_are_split_by_indent_not_by_child_keys():
    """`command:` sits deeper than the entry and must not start a new entry."""
    blocks = _load()._entry_blocks(GOOD)
    assert set(blocks) == {"loop-governance", "tasks"}, blocks
    assert "command:" in blocks["loop-governance"]
    assert "/opt/repo/mcp-servers/task-mcp.py" in blocks["tasks"]


def test_paths_include_the_command_and_every_argument_form():
    m = _load()
    p = m._paths_of(m._entry_blocks(GOOD)["loop-governance"])
    assert p == ["/opt/venv/bin/python3", "/opt/tools/loop-gov-mcp.py"], p
    q = m._paths_of(m._entry_blocks(GOOD)["tasks"])
    assert "/opt/repo/mcp-servers/task-mcp.py" in q, q


def test_a_healthy_entry_passes():
    res = _load().audit(GOOD, {"loop-governance": "x.py"}, exists=lambda p: True)
    assert res == [("loop-governance", "PASS", "configured and its paths exist", "")], res


def test_an_entry_pointing_at_a_dead_path_FAILS_and_says_which_path():
    """THE regression: present-but-dead used to read as configured-and-fine."""
    res = _load().audit(GOOD, {"loop-governance": "x.py"},
                        exists=lambda p: p == "/opt/venv/bin/python3")
    name, status, detail, fix = res[0]
    assert status == "FAIL", res
    assert "/opt/tools/loop-gov-mcp.py" in detail, detail
    assert "hermes mcp add" in fix and "x.py" in fix, fix


def test_a_dead_args_script_is_caught_too():
    res = _load().audit(GOOD, {"tasks": "task-mcp.py"},
                        exists=lambda p: p != "/opt/repo/mcp-servers/task-mcp.py")
    assert res[0][1] == "FAIL" and "task-mcp.py" in res[0][2], res


def test_a_missing_server_is_a_FAIL_with_the_exact_add_command():
    res = _load().audit(GOOD, {"cortex-context": "mcp-servers/cortex-context-mcp.py"},
                        exists=lambda p: True)
    name, status, detail, fix = res[0]
    assert status == "FAIL" and "not configured" in detail
    assert "hermes mcp add cortex-context" in fix, fix


def test_orchestrator_only_servers_are_judged_by_role():
    m = _load()
    absent = m.audit(GOOD, {"executor": "x.py"}, exists=lambda p: True, is_orch=False)
    assert absent[0][1] == "PASS" and "correct here" in absent[0][2], absent
    present_cfg = GOOD.replace("mcp_servers:", "mcp_servers:\n  executor:\n    command: /opt/venv/bin/python3")
    warn = m.audit(present_cfg, {"executor": "x.py"}, exists=lambda p: True, is_orch=False)
    assert warn[0][1] == "WARN", warn


def test_cli_reports_and_exits_1_on_a_dead_path():
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "config.yaml"
        cfg.write_text(GOOD.replace("/opt/tools/loop-gov-mcp.py", "/opt/gone/loop-gov-mcp.py"))
        r = subprocess.run([sys.executable, str(MOD), "--config", str(cfg),
                            "--expected", "loop-governance", "--json"],
                           capture_output=True, text=True)
        assert r.returncode == 1, r.stdout + r.stderr
        assert "fix:" in r.stdout, r.stdout
        data = json.loads(r.stdout.strip().splitlines()[-1])
        assert data["failures"] == ["loop-governance"], data


def test_cli_is_3_when_there_is_no_config_to_read():
    r = subprocess.run([sys.executable, str(MOD), "--config", "/nope/config.yaml"],
                       capture_output=True, text=True)
    assert r.returncode == 3, f"COULD NOT VERIFY must be its own code: {r.returncode}"
    assert "COULD NOT VERIFY" in r.stderr


def test_a_bare_command_is_resolved_on_PATH_not_as_a_path():
    """`command: python3` is a PATH name. Treating it as a path reported 'python3 does not
    exist', which is wrong; the fleet rule is that it should be the venv, so it WARNS."""
    cfg = "mcp_servers:\n  tasks:\n    command: python3\n    args: [/opt/task-mcp.py]\n"
    m = _load()
    res = m.audit(cfg, {"tasks": "task-mcp.py"}, exists=lambda p: True,
                  which=lambda p: "/usr/bin/python3")
    assert res[0][1] == "WARN" and "bare" in res[0][2], res
    gone = m.audit(cfg, {"tasks": "task-mcp.py"}, exists=lambda p: True, which=lambda p: None)
    assert gone[0][1] == "FAIL" and "python3" in gone[0][2], gone
    print("  a bare command is resolved on PATH, and should be the venv ✓")


def test_the_printed_fix_names_a_path_that_resolves():
    """The doctor calls audit() with a BARE filename ("cortex-bus-mcp.py"), so the printed fix
    used to render `~/hermes-cortex/cortex-bus-mcp.py` — a path that does not exist, i.e. advice
    nobody can run. The fix must name the repo-relative script."""
    m = _load()
    cfg = ("mcp_servers:\n  tasks:\n    command: /opt/hermes-agent/venv/bin/python3\n"
           "    args: [/opt/task-mcp.py]\n")
    res = m.audit(cfg, {"tasks": "task-mcp.py"}, exists=lambda p: True)
    fix = res[0][3]
    arg = next(t for t in fix.split() if t.endswith("task-mcp.py"))
    assert arg.endswith("/mcp-servers/task-mcp.py"), fix
    print("  the printed fix names the repo-relative script ✓")


def test_the_expected_map_agrees_with_the_doctors():
    """One source of truth: this CLI cannot import the doctor's package, so the duplication is
    enforced by comparing the two files rather than hoped for. The VALUES must agree too — a
    key-only check let the doctor pass a bare filename while this module assumed the
    `mcp-servers/` prefix, which is how the unrunnable fix string shipped."""
    import re as _re
    cfg = (REPO / "ops" / "scripts" / "manage" / "cortex_doctor" / "config.py").read_text()
    block = _re.search(r"EXPECTED_MCP_SERVERS\s*=\s*\{(.*?)\}", cfg, _re.DOTALL)
    assert block, "the doctor's EXPECTED_MCP_SERVERS was not found — update this test"
    doctor_map = dict(_re.findall(r'"([a-z][a-z0-9-]*)":\s*"([^"]*)"', block.group(1)))
    orch = _re.search(r"ORCH_ONLY_MCP_SERVERS\s*=\s*\{([^}]*)\}", cfg)
    assert orch, "the doctor's ORCH_ONLY_MCP_SERVERS was not found — update this test"
    doctor_orch = set(_re.findall(r'"([^"]+)"', orch.group(1)))
    m = _load()
    assert set(m.DEFAULT_EXPECTED) == set(doctor_map), (set(m.DEFAULT_EXPECTED), set(doctor_map))
    assert m.DEFAULT_EXPECTED == doctor_map, (m.DEFAULT_EXPECTED, doctor_map)
    assert m.ORCH_ONLY == doctor_orch, (m.ORCH_ONLY, doctor_orch)
    print("  the wiring map matches the doctor's map (keys AND values) ✓")


def test_the_doctor_reports_an_unavailable_audit_instead_of_skipping_it():
    """A check that cannot run must not read as 'nothing wrong'. The doctor loads this module by
    path; if that fails it has to SAY so. (Static assertion: the loaded module's globals make
    exercising that branch in-process impractical, so the guarantee is pinned at the source and
    exercised live in the evidence capture.)"""
    src = (REPO / "ops" / "scripts" / "manage" / "cortex_doctor" / "checks.py").read_text()
    i = src.index("mcp_wiring_for_doctor")
    block = src[i:i + 1200]
    assert "except Exception as _mw_err" in block, block[:300]
    assert "res.add(" in block, "the failure path must REPORT, not pass silently"
    assert "unavailable" in block, "it must say the audit is unavailable"
    print("  the doctor reports an unavailable wiring audit ✓")


def _main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
        except Exception:
            import traceback
            failed.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
    if failed:
        print(f"RESULT: FAIL ({len(failed)}/{len(tests)}): {failed}")
        return 1
    print(f"RESULT: ALL PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
