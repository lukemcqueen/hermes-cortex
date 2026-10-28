#!/usr/bin/env python3
"""The review-gateway MCP server has ONE canonical registration name: `review`.

Anything else works mechanically (all the tools function) but the agent sees
`mcp__<weirdname>__begin_change` for its whole life, and the name is the thing told
to docs, installers, watchdogs and the enforcer's own instruction text. So the name
is enforced, not documented.

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
        mod.PI_MCP = tmp_path / "no-pi-mcp.json"  # isolate: the real ~/.pi/agent/mcp.json must not leak into fixtures
        res = FakeRes()
        mod.check_mcp_review_name(res)
        return res.checks
    finally:
        mod.DEFAULT_CONFIG, mod.PI_MCP = old_cfg, old_pi


def test_registered_as_review_passes(tmp_path):
    cfg = config_with(tmp_path, {"review": [PROBE]})
    checks = run(tmp_path, cfg)
    assert len(checks) == 1
    name, status, detail, fix = checks[0]
    assert status == "PASS", (status, detail)
    assert name == "MCP review server name"
    assert "exactly 'review'" in detail


def test_old_name_fails_and_names_the_offender(tmp_path):
    cfg = config_with(tmp_path, {"loop-governance": [PROBE]})
    checks = run(tmp_path, cfg)
    name, status, detail, fix = checks[0]
    assert status == "FAIL", detail
    assert "loop-governance" in detail
    assert "hermes mcp remove" in fix and "hermes mcp add review" in fix


def test_weird_name_fails(tmp_path):
    cfg = config_with(tmp_path, {"mcp-gov-server-pi-1": [PROBE]})
    status = run(tmp_path, cfg)[0][1]
    assert status == "FAIL"


def test_review_exists_but_a_second_registration_runs_the_probe_fails(tmp_path):
    """Bootlegging the probe under a second name while `review` points elsewhere is
    worse than a plain rename: two processes, two views of one lock store."""
    cfg = config_with(tmp_path, {
        "review": ["/opt/other.py"],
        "loop-governance": [PROBE],
    })
    name, status, detail, fix = run(tmp_path, cfg)[0]
    assert status == "FAIL"
    assert "loop-governance" in detail


def test_no_review_gateway_at_all_fails(tmp_path):
    cfg = config_with(tmp_path, {"agent-bus": ["cortex-bus-mcp.py"]})
    name, status, detail, fix = run(tmp_path, cfg)[0]
    assert status == "FAIL"
    assert "unreachable" in detail


def test_missing_config_file_fails_closed(tmp_path):
    checks = run(tmp_path, tmp_path / "no-such-config.yaml")
    assert checks[0][1] == "FAIL"


def test_pi_mcp_json_registration_is_seen(tmp_path):
    old_cfg, old_pi = mod.DEFAULT_CONFIG, mod.PI_MCP
    try:
        pi = tmp_path / "mcp.json"
        pi.write_text('{"mcpServers": {"review": {"args": ["%s"]}}}' % PROBE, encoding="utf-8")
        mod.PI_MCP = pi
        mod.DEFAULT_CONFIG = config_with(tmp_path, {"agent-bus": ["other.py"]})
        res = FakeRes()
        mod.check_mcp_review_name(res)
        assert res.checks[0][1] == "PASS"
    finally:
        mod.DEFAULT_CONFIG, mod.PI_MCP = old_cfg, old_pi
