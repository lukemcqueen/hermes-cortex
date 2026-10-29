#!/usr/bin/env python3
"""The loop-gov binary is registered as EXACTLY the two role-distinct servers.

Slice B: `loop-governance` (--role loop-governance: lifecycle/lock/scoring/task)
and `review` (--role review: re-review/feedback/cycle-read). The doctor FAILs on
either missing, either carrying the wrong/no --role, or a THIRD registration of
the probe (two processes, two views of one lock store).

Hermetic: fixtures are tmp config files; nothing touches the host's real config.yaml.
"""
import sys
import importlib.util
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "ops/scripts/manage/cortex_doctor"
spec = importlib.util.spec_from_file_location("cortex_doctor_mcp_names_test", BASE / "mcp_names.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["cortex_doctor_mcp_names_test"] = mod
spec.loader.exec_module(mod)

PROBE = "loop-gov-mcp.py"


def _role(argv, role):
    """argv with the --role appended for the probe."""
    if role is None:
        return argv
    return argv + ["--role", role]


class FakeRes:
    def __init__(self):
        self.checks = []

    def add(self, name, status, detail="", fix=""):
        self.checks.append((name, status, detail, fix))


def config_with(tmp_path, servers):
    p = tmp_path / "config.yaml"
    lines = ["mcp_servers:"]
    for name, argv in servers.items():
        lines += [f"  {name}:", "    command: /usr/bin/python3", "    args:"]
        lines += [f"      - {a}" for a in argv]
        lines.append("    enabled: true")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def run(tmp_path, config):
    old_cfg, old_pi = mod.DEFAULT_CONFIG, mod.PI_MCP
    try:
        mod.DEFAULT_CONFIG = config
        mod.PI_MCP = tmp_path / "no-pi-mcp.json"  # isolate: never read the real ~/.pi/agent/mcp.json
        res = FakeRes()
        mod.check_mcp_role_names(res)
        return res.checks
    finally:
        mod.DEFAULT_CONFIG, mod.PI_MCP = old_cfg, old_pi


def test_both_role_names_match_passes(tmp_path):
    cfg = config_with(tmp_path, {
        "loop-governance": _role([PROBE], "loop-governance"),
        "review": _role([PROBE], "review"),
    })
    checks = run(tmp_path, cfg)
    assert len(checks) == 1
    name, status, detail, fix = checks[0]
    assert status == "PASS", (status, detail)
    assert name == "MCP loop-gov role servers"
    assert "loop-governance" in detail and "review" in detail


def test_missing_loop_governance_fails(tmp_path):
    # only `review` present (the pre-Slice-B single-registration host) -> FAIL
    cfg = config_with(tmp_path, {"review": _role([PROBE], "review")})
    name, status, detail, fix = run(tmp_path, cfg)[0]
    assert status == "FAIL", detail
    assert "loop-governance missing" in detail


def test_missing_review_fails(tmp_path):
    cfg = config_with(tmp_path, {"loop-governance": _role([PROBE], "loop-governance")})
    name, status, detail, fix = run(tmp_path, cfg)[0]
    assert status == "FAIL", detail
    assert "review missing" in detail


def test_wrong_role_fails(tmp_path):
    # loop-governance registered with the WRONG --role (or none) -> FAIL
    cfg = config_with(tmp_path, {
        "loop-governance": _role([PROBE], "review"),
        "review": _role([PROBE], "review"),
    })
    name, status, detail, fix = run(tmp_path, cfg)[0]
    assert status == "FAIL", detail
    assert "loop-governance has --role 'review'" in detail


def test_missing_role_arg_fails(tmp_path):
    # a role-less loop-gov registration (full set) cannot satisfy the role contract
    cfg = config_with(tmp_path, {
        "loop-governance": [PROBE],
        "review": _role([PROBE], "review"),
    })
    name, status, detail, fix = run(tmp_path, cfg)[0]
    assert status == "FAIL", detail
    assert "loop-governance has --role '(none)'" in detail


def test_third_registration_runs_probe_fails(tmp_path):
    # two correct plus a THIRD probe registration -> two views of the lock store
    cfg = config_with(tmp_path, {
        "loop-governance": _role([PROBE], "loop-governance"),
        "review": _role([PROBE], "review"),
        "mcp-gov-server-pi-1": _role([PROBE], "review"),
    })
    name, status, detail, fix = run(tmp_path, cfg)[0]
    assert status == "FAIL", detail
    assert "third registration" in detail


def test_no_probe_at_all_fails(tmp_path):
    cfg = config_with(tmp_path, {"agent-bus": ["cortex-bus-mcp.py"]})
    name, status, detail, fix = run(tmp_path, cfg)[0]
    assert status == "FAIL"
    assert "unreachable" in detail


def test_missing_config_file_fails_closed(tmp_path):
    checks = run(tmp_path, tmp_path / "no-such-config.yaml")
    assert checks[0][1] == "FAIL"


def test_pi_mcp_json_dual_registration_is_seen(tmp_path):
    old_cfg, old_pi = mod.DEFAULT_CONFIG, mod.PI_MCP
    try:
        pi = tmp_path / "mcp.json"
        pi.write_text(
            '{"mcpServers": {"loop-governance": {"args": ["%s", "--role", "loop-governance"]}, '
            '"review": {"args": ["%s", "--role", "review"]}}}' % (PROBE, PROBE),
            encoding="utf-8")
        mod.PI_MCP = pi
        # no loop-gov in the hermes config; the Pi json supplies BOTH
        mod.DEFAULT_CONFIG = config_with(tmp_path, {"agent-bus": ["other.py"]})
        res = FakeRes()
        mod.check_mcp_role_names(res)
        assert res.checks[0][1] == "PASS"
    finally:
        mod.DEFAULT_CONFIG, mod.PI_MCP = old_cfg, old_pi