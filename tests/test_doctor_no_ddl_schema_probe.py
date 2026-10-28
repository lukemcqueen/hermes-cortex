#!/usr/bin/env python3
"""The doctor REPORTS the tasks schema version; it must never APPLY it.

Backlog row `72b2c69b` (found 2026-10-27 by the build cycle, cycle 13866). The
defect, measured rather than argued:

  * `cortex_doctor/checks.py` ran `task-db.py --apply-schema` as a HEALTH CHECK
    — on every `agent-message-handler` tick (~5 minutes);
  * `task-db.py`'s `cmd_apply_schema()` resolved `migrate.py` from a candidate
    list whose FIRST entry was `Path(os.environ.get("CORTEX_REPO", ""))/…`, i.e.
    the REPO WORKING TREE when that variable was set, and a *relative* path
    (resolved against the caller's cwd) when it was not. The deployed copy was
    LAST.

So an unattended health check made a host's repo working tree authoritative for
production DDL and bypassed the register-map contract that
`cortex-update.sh:446` states ("the register map IS the deploy"). Measured
consequence: an UNCOMMITTED migration file reached the live `mycortex` database
~50 s after it was written, before it was committed, registered or deployed.

Three properties are pinned here:

  1. the doctor contains no `--apply-schema` call at all (the precedent is
     `tests/test_task_queue_evidence.py`, which pins the same property for the
     acceptance-evidence script);
  2. the version the doctor reports comes from a read-only SELECT, and a version
     behind the DEPLOYED migrations is a WARN naming the deploy path — not a
     silent apply;
  3. `task-db.py` resolves the DEPLOYED runner first and never builds a
     cwd-relative candidate.

`cortex_doctor/checks.py` is a package module (relative imports, import-time
side effects), so properties 1 and 2's call site are asserted against its SOURCE
— the same technique the precedent above uses. Everything testable behaviourally
lives in `task-db.py` and is driven for real below.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
CHECKS = REPO / "ops" / "scripts" / "manage" / "cortex_doctor" / "checks.py"
TASK_DB = REPO / "ops" / "scripts" / "manage" / "task-db.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


task_db = _load("task_db_ddl_probe", TASK_DB)


# ── 1. a health check reports; it does not mutate ───────────────────────────

def test_doctor_check_does_not_call_apply_schema():
    src = CHECKS.read_text()
    assert '"--apply-schema"' not in src and "'--apply-schema'" not in src, (
        "the doctor must REPORT the tasks schema version, never apply it: a "
        "health check that applies DDL makes a repo working tree authoritative "
        "for production schema and bypasses the register map "
        "(cortex-update.sh:446)")


def test_doctor_reads_the_version_read_only():
    src = CHECKS.read_text()
    assert "FROM tasks.schema_version" in src, (
        "the reported version must come from a SELECT on tasks.schema_version")


def test_doctor_warns_when_the_deployed_migrations_are_ahead():
    """Divergence is REPORTED with the deploy path as the remedy."""
    src = CHECKS.read_text()
    assert "deployed_schema_version" in src, (
        "the doctor must compare the live version against the DEPLOYED schema "
        "dir and WARN when it needs raising (row 72b2c69b fix direction (a)); "
        "silently applying the difference is the defect")


# ── 2. the migration authority is the DEPLOYED tree ─────────────────────────

def test_candidates_prefer_the_deployed_tree(tmp_path):
    deploy, repo = tmp_path / "deploy", tmp_path / "repo"
    with patch.dict(os.environ, {"CORTEX_DEPLOY_HOME": str(deploy),
                                 "CORTEX_REPO": str(repo)}, clear=False):
        cands = task_db._migrate_candidates()
    assert cands[0] == deploy / "services/tasks/migrate.py", (
        f"the DEPLOYED runner must be resolved first, got {cands[0]}")
    assert cands[-1] == repo / "ops/services/tasks/migrate.py", (
        f"the repo tree is a fallback, never the authority, got {cands[-1]}")


def test_candidates_are_never_cwd_relative(tmp_path):
    """The second defect in the same function: an unset CORTEX_REPO used to
    produce the RELATIVE path 'ops/services/tasks/migrate.py', so the DDL
    authority depended on the caller's working directory."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("CORTEX_REPO", "CORTEX_DEPLOY_HOME")}
    with patch.dict(os.environ, env, clear=True):
        cands = task_db._migrate_candidates()
    assert all(c.is_absolute() for c in cands), (
        f"a candidate must never be cwd-relative: {cands}")
    assert cands[0] == Path.home() / ".hermes-cortex/services/tasks/migrate.py"


def test_cmd_apply_schema_runs_the_deployed_runner(tmp_path):
    """When both trees carry a runner, the deployed one is what executes — and a
    host with nothing deployed still resolves its repo tree."""
    deploy, repo = tmp_path / "deploy", tmp_path / "repo"
    dep = deploy / "services/tasks/migrate.py"
    rep = repo / "ops/services/tasks/migrate.py"
    dep.parent.mkdir(parents=True)
    rep.parent.mkdir(parents=True)
    dep.write_text("# deployed\n")
    rep.write_text("# repo tree\n")

    seen: list[list[str]] = []

    class _Done:
        returncode = 0
        stdout = "schema now at version 16\n"
        stderr = ""

    with patch.dict(os.environ, {"CORTEX_DEPLOY_HOME": str(deploy),
                                 "CORTEX_REPO": str(repo)}, clear=False), \
         patch.object(task_db.subprocess, "run",
                      side_effect=lambda argv, **kw: (seen.append(argv), _Done())[1]):
        task_db.cmd_apply_schema()
        assert seen and seen[-1][1] == str(dep), (
            f"the DEPLOYED runner must win when both exist, ran {seen[-1][1]}")

        dep.unlink()          # fallback preserved: no deployed copy -> repo tree
        seen.clear()
        task_db.cmd_apply_schema()
        assert seen and seen[-1][1] == str(rep), (
            f"the repo tree must still resolve when nothing is deployed, "
            f"ran {seen[-1][1]}")


# ── 3. the deployed migration level is readable without applying ────────────

def test_deployed_schema_version_reads_the_deployed_dir(tmp_path):
    deploy = tmp_path / "deploy"
    schema = deploy / "services/tasks/schema"
    schema.mkdir(parents=True)
    for name in ("v001__tasks.sql", "v009__task-model-v3.sql",
                 "v016__task-upsert-plan.sql", "README.md"):
        (schema / name).write_text("--\n")
    with patch.dict(os.environ, {"CORTEX_DEPLOY_HOME": str(deploy)}, clear=False):
        assert task_db.deployed_schema_version() == 16


def test_deployed_schema_version_is_none_when_absent(tmp_path):
    """No deployed schema dir -> NO claim (never a fabricated 0)."""
    with patch.dict(os.environ, {"CORTEX_DEPLOY_HOME": str(tmp_path / "nope")},
                    clear=False):
        assert task_db.deployed_schema_version() is None
