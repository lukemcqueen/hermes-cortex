#!/usr/bin/env python3
"""The doctor must DETECT the task-model drift, not just have fixed it once.

Luke's ask (2026-10-04): "make sure update/doctor will detect this issue!"

A check that cannot fail is decoration. These tests drive the real function with a
fake Results and prove it fires in BOTH directions — it flags an unregistered
migration, and it stays quiet when everything is registered.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
DOCTOR_DIR = _REPO / "ops" / "scripts" / "manage" / "cortex_doctor"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ti = _load("task_integrity_under_test", DOCTOR_DIR / "task_integrity.py")


class FakeResults:
    """Minimal stand-in for cortex_doctor.results.Results."""

    def __init__(self):
        self.checks = []

    def add(self, name, status, detail="", fix=""):
        self.checks.append({"name": name, "status": status, "detail": detail,
                            "fix": fix})

    def by_name(self, name):
        return [c for c in self.checks if c["name"] == name]

    def status_of(self, name):
        hits = self.by_name(name)
        return hits[0]["status"] if hits else None


# ── it is actually wired into the doctor's run ──────────────────────────────

def test_the_check_is_registered_in_the_doctor_run_list():
    """A check nobody calls never runs."""
    cli = (DOCTOR_DIR / "cli.py").read_text()
    assert "check_task_model_integrity" in cli, (
        "the task-integrity check is not in cli.py's all_checks — it would never run")
    assert "from .task_integrity import" in cli, "not imported in cli.py"


def test_the_module_is_registered_for_deploy():
    """An unregistered doctor module is absent on the host → ImportError at startup."""
    update = (_REPO / "ops" / "scripts" / "cortex-update.sh").read_text()
    assert "cortex_doctor/task_integrity.py" in update, (
        "task_integrity.py must be in the deploy register or the deployed doctor "
        "cannot import it")


# ── RED direction: it must FIRE ────────────────────────────────────────────

def test_unregistered_migration_is_flagged(monkeypatch, tmp_path):
    """The exact bug: a migration in the repo that the register map never deploys.

    v009/v010 sat like that — the deployed schema dir stopped at v008 and no host
    could apply the v3 task model.
    """
    monkeypatch.setattr(ti, "_registered_schema", lambda: set())
    monkeypatch.setattr(ti, "_deploy", lambda: tmp_path)          # no deployed dir
    res = FakeResults()
    ti.check_task_model_integrity(res)

    assert res.status_of("Task schema deploy") == "FAIL", (
        "an unregistered migration must FAIL — it can never reach a host")
    detail = res.by_name("Task schema deploy")[0]["detail"]
    assert "NOT in the deploy register" in detail
    assert ".sql" in detail, "the failing migrations should be named"


def test_registered_and_deployed_passes(monkeypatch, tmp_path):
    """GREEN direction: with everything registered it must stay quiet.

    Without this the check could pass vacuously for the wrong reason.
    """
    schema_dir = _REPO / "ops" / "services" / "tasks" / "schema"
    all_names = {p.name for p in schema_dir.glob("v0*.sql")}
    monkeypatch.setattr(ti, "_registered_schema", lambda: set(all_names))
    # Point the deploy dir at the repo's schema dir so nothing is "missing".
    monkeypatch.setattr(ti, "_deploy", lambda: tmp_path)
    fake_deploy = tmp_path / "services" / "tasks" / "schema"
    fake_deploy.mkdir(parents=True)
    for n in all_names:
        (fake_deploy / n).write_text("-- stub\n")

    res = FakeResults()
    ti.check_task_model_integrity(res)
    assert res.status_of("Task schema deploy") == "PASS"


def test_a_missing_deployed_copy_is_flagged(monkeypatch, tmp_path):
    """Registered but not deployed: the runner still cannot see it."""
    schema_dir = _REPO / "ops" / "services" / "tasks" / "schema"
    all_names = {p.name for p in schema_dir.glob("v0*.sql")}
    monkeypatch.setattr(ti, "_registered_schema", lambda: set(all_names))
    monkeypatch.setattr(ti, "_deploy", lambda: tmp_path)
    fake_deploy = tmp_path / "services" / "tasks" / "schema"
    fake_deploy.mkdir(parents=True)                                # empty on purpose

    res = FakeResults()
    ti.check_task_model_integrity(res)
    assert res.status_of("Task schema deployed") == "WARN", (
        "registered-but-absent-on-the-host must be flagged")


# ── the stranded-slice invariant ───────────────────────────────────────────

def test_stranded_slices_are_flagged(monkeypatch, tmp_path):
    """pending + assignee = unclaimable AND unwatched. Six hid for six weeks."""
    schema_dir = _REPO / "ops" / "services" / "tasks" / "schema"
    all_names = {p.name for p in schema_dir.glob("v0*.sql")}
    monkeypatch.setattr(ti, "_registered_schema", lambda: set(all_names))
    monkeypatch.setattr(ti, "_deploy", lambda: tmp_path)

    runner = tmp_path / "scripts" / "task-db.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("# stub\n")

    def fake_run(cmd, timeout=25):
        if "--assigned" in cmd:
            return ("ID         PR  ASSIGNEE   PROJECT            CONTENT\n"
                    "72dc920b   2   joseph     hermes-cortex      Phase 1 Foundation\n")
        if "--dry-run" in cmd:
            return "tasks schema: current=12, no pending migrations\n"
        return ""

    monkeypatch.setattr(ti, "_run", fake_run)
    res = FakeResults()
    ti.check_task_model_integrity(res)
    assert res.status_of("Stranded slices") == "WARN", (
        "a pending slice with an assignee must be flagged — nothing is working it")
    assert "unclaim" in res.by_name("Stranded slices")[0]["fix"]


def test_no_stranded_slices_passes(monkeypatch, tmp_path):
    schema_dir = _REPO / "ops" / "services" / "tasks" / "schema"
    all_names = {p.name for p in schema_dir.glob("v0*.sql")}
    monkeypatch.setattr(ti, "_registered_schema", lambda: set(all_names))
    monkeypatch.setattr(ti, "_deploy", lambda: tmp_path)
    runner = tmp_path / "scripts" / "task-db.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("# stub\n")
    monkeypatch.setattr(ti, "_run", lambda cmd, timeout=25:
                        "(no unstarted hand-offs)\n" if "--assigned" in cmd
                        else "tasks schema: current=12, no pending migrations\n")
    res = FakeResults()
    ti.check_task_model_integrity(res)
    assert res.status_of("Stranded slices") == "PASS"


def test_an_unverifiable_check_says_so_rather_than_passing(monkeypatch, tmp_path):
    """SOUL P12: a check that cannot look must not read as 'fine'."""
    schema_dir = _REPO / "ops" / "services" / "tasks" / "schema"
    all_names = {p.name for p in schema_dir.glob("v0*.sql")}
    monkeypatch.setattr(ti, "_registered_schema", lambda: set(all_names))
    monkeypatch.setattr(ti, "_deploy", lambda: tmp_path)
    runner = tmp_path / "scripts" / "task-db.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("# stub\n")
    monkeypatch.setattr(ti, "_run", lambda cmd, timeout=25: "")     # DB unreachable
    res = FakeResults()
    ti.check_task_model_integrity(res)
    assert res.status_of("Stranded slices") == "WARN"
    assert "COULD NOT VERIFY" in res.by_name("Stranded slices")[0]["detail"]
