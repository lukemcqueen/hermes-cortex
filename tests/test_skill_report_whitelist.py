"""Unit tests for orch-skill-report-process.py sender whitelist + hostname aliases.

Covers the 2026-08-13 fix: kustos's host reports as 'cisnet02' (collector
falls back to OS hostname when AGENT_NAME is unset), so the whitelist must
map known hostnames → agents before rejecting unknown senders.
"""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "ops/scripts/manage/orch-skill-report-process.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("orch_skill_report_process", SCRIPT)
    assert spec is not None and spec.loader is not None, f"cannot load {SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _msg(frm: str, subject: str = "Learning Report: 1 skills"):
    return {"msg_id": "m", "body": {"from": frm, "subject": subject, "topic": "reports", "body": "x"}}


def test_hostname_alias_cisnet02_maps_to_kustos():
    mod = _load_module()
    r = mod.extract_skill_report(_msg("cisnet02"))
    assert r is not None
    assert r["from"] == "kustos"


def test_dotted_hostname_alias_normalized():
    mod = _load_module()
    r = mod.extract_skill_report(_msg("cisnet02.local"))
    assert r is not None
    assert r["from"] == "kustos"


def test_all_fleet_agents_accepted():
    mod = _load_module()
    for agent in ["moses", "esther", "joseph", "gisu", "kustos", "titus"]:
        r = mod.extract_skill_report(_msg(agent))
        assert r is not None, f"{agent} should be accepted"
        assert r["from"] == agent


def test_unregistered_hosts_rejected():
    mod = _load_module()
    for host in ["LAM2.local", "lam2", "unknown.host", "cisnet03"]:
        assert mod.extract_skill_report(_msg(host)) is None, f"{host} should be rejected"


def test_non_report_topic_rejected():
    mod = _load_module()
    # topic must be 'reports' (or subject contain 'skill report') — commands are not reports
    msg = {"msg_id": "m", "body": {"from": "esther", "subject": "EXEC: run doctor", "topic": "commands", "body": "x"}}
    assert mod.extract_skill_report(msg) is None
