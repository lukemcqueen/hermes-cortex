"""fix-cron-skills-toolset.py — the skills-toolset repair for cron jobs.

Class (diagnosed 2026-10-26, cycle 13823; recurring since): a Hermes cron job that
carries an EXPLICIT ``enabled_toolsets`` allowlist omitting ``skills`` gets no
skill tool, so the 7 always-section skills can never load, governance gate 1
blocks every write, and the job's write-back silently never happens. Measured on
the dream layer: a host's nightly dream wrote nothing from 2026-10-22 while its
own cron reported success.

The fix is one config field per job — and it cannot be done from the CLI
(`hermes cron edit` has no --enabled-toolsets), so this script edits the store
directly, under the SAME cross-process lock the gateway uses
(``<cron dir>/.jobs.lock``).

Safety properties pinned here:
  * a job with NO allowlist is never given one (it inherits platform_toolsets.cron
    and already has `skills` on a healthy host);
  * a job that already has `skills` is never rewritten;
  * a no_agent job is skipped (no LLM session, so no skills gate to satisfy);
  * an unreadable store is rc 3 (could-not-verify) and writes NOTHING;
  * report mode writes nothing;
  * a second --apply is a no-op (idempotent).

Run: python3 -m pytest tests/test_fix_cron_skills_toolset.py -q
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "ops" / "scripts" / "manage" / "fix-cron-skills-toolset.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("fix_cron_skills_toolset", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _store(tmp_path, jobs):
    p = tmp_path / "jobs.json"
    p.write_text(json.dumps({"jobs": jobs}, indent=2))
    return p


def _job(name, job_id, toolsets, no_agent=False):
    j = {"name": name, "job_id": job_id, "schedule": "0 5 * * *",
         "prompt": "do the thing", "no_agent": no_agent}
    if toolsets is not None:
        j["enabled_toolsets"] = toolsets
    return j


def _run(jobs_file, *args):
    return subprocess.run([sys.executable, str(SCRIPT), "--jobs-file", str(jobs_file), *args],
                          capture_output=True, text=True, timeout=60)


# ── the defect ───────────────────────────────────────────────────────────────

def test_reports_a_job_whose_allowlist_omits_skills(tmp_path):
    f = _store(tmp_path, [_job("agent-mycortex-dream-nightly", "ad77f951f753",
                               ["terminal", "file", "session_search"])])
    r = _run(f)
    assert r.returncode == 1, f"findings must be rc 1: {r.stdout}{r.stderr}"
    assert "agent-mycortex-dream-nightly" in r.stdout
    assert "skills" in r.stdout
    # report mode must not touch the store
    assert json.loads(f.read_text())["jobs"][0]["enabled_toolsets"] == \
        ["terminal", "file", "session_search"]


def test_apply_adds_skills_and_preserves_everything_else(tmp_path):
    f = _store(tmp_path, [_job("agent-mycortex-dream-nightly", "ad77f951f753",
                               ["terminal", "file", "session_search"])])
    r = _run(f, "--apply")
    assert r.returncode == 0, f"{r.stdout}{r.stderr}"
    job = json.loads(f.read_text())["jobs"][0]
    assert "skills" in job["enabled_toolsets"]
    assert set(["terminal", "file", "session_search"]).issubset(set(job["enabled_toolsets"]))
    assert job["name"] == "agent-mycortex-dream-nightly" and job["job_id"] == "ad77f951f753"
    assert job["prompt"] == "do the thing"


def test_second_apply_is_a_no_op(tmp_path):
    f = _store(tmp_path, [_job("j", "id1", ["terminal", "file"])])
    assert _run(f, "--apply").returncode == 0
    first = f.read_text()
    r2 = _run(f, "--apply")
    assert r2.returncode == 0, r2.stdout
    assert f.read_text() == first, "a second apply must not rewrite the store"
    assert "nothing to fix" in r2.stdout.lower()


# ── safety: never invent, never widen, never touch what is fine ──────────────

def test_job_without_an_allowlist_is_left_alone(tmp_path):
    f = _store(tmp_path, [_job("dream-nightly", "id2", None)])
    r = _run(f, "--apply")
    assert r.returncode == 0, r.stdout
    assert "enabled_toolsets" not in json.loads(f.read_text())["jobs"][0]


def test_job_that_already_has_skills_is_untouched(tmp_path):
    f = _store(tmp_path, [_job("dream-nightly", "id3", ["terminal", "skills"])])
    before = f.read_text()
    r = _run(f, "--apply")
    assert r.returncode == 0, r.stdout
    assert f.read_text() == before


def test_no_agent_job_is_skipped(tmp_path):
    """A script job has no LLM session, so there is no skills gate to satisfy."""
    f = _store(tmp_path, [_job("orch-daily-regression-gate", "id4", ["terminal"], no_agent=True)])
    before = f.read_text()
    r = _run(f, "--apply")
    assert r.returncode == 0, r.stdout
    assert f.read_text() == before


def test_mixed_store_fixes_only_the_broken_jobs(tmp_path):
    f = _store(tmp_path, [
        _job("broken", "id5", ["terminal", "web", "file"]),
        _job("fine", "id6", ["terminal", "skills"]),
        _job("inherits", "id7", None),
    ])
    assert _run(f, "--apply").returncode == 0
    jobs = {j["name"]: j for j in json.loads(f.read_text())["jobs"]}
    assert "skills" in jobs["broken"]["enabled_toolsets"]
    assert jobs["fine"]["enabled_toolsets"] == ["terminal", "skills"]
    assert "enabled_toolsets" not in jobs["inherits"]


# ── could-not-verify ────────────────────────────────────────────────────────

def test_missing_store_is_could_not_verify(tmp_path):
    r = _run(tmp_path / "nope.json", "--apply")
    assert r.returncode == 3, f"an unreadable store must be rc 3, not a verdict: {r.stdout}"
    assert not (tmp_path / "nope.json").exists(), "nothing may be created"


def test_corrupt_store_is_could_not_verify_and_unchanged(tmp_path):
    f = tmp_path / "jobs.json"
    f.write_text("{not json")
    r = _run(f, "--apply")
    assert r.returncode == 3, f"{r.stdout}{r.stderr}"
    assert f.read_text() == "{not json"


def test_write_is_atomic_and_lockable(tmp_path):
    """A write must land beside the store (same fs) and leave no temp file behind."""
    f = _store(tmp_path, [_job("broken", "id8", ["terminal"])])
    (tmp_path / ".jobs.lock").write_text("")
    assert _run(f, "--apply").returncode == 0
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".jobs.json.tmp")]
    assert leftovers == [], f"temp files left behind: {leftovers}"
    json.loads(f.read_text())  # still valid JSON


def test_module_import_is_inert(tmp_path):
    """Importing the module must not read or write the live store."""
    mod = _load_module()
    assert hasattr(mod, "plan_fixes")


# ── the STORE's own shape: jobs.json keys the job as `id`, not `job_id` ─────
# Measured 2026-10-28 against the live store: reading only `job_id` rendered every
# job as "?" AND keyed every planned fix on None — an --apply would have rewritten
# the first job in the file instead of the named one. The unit tests missed it
# because their fixtures used the MCP tool's field name; the live report caught it.

def _store_with_disk_shape(tmp_path, jobs):
    p = tmp_path / "jobs.json"
    p.write_text(json.dumps({"jobs": jobs}, indent=2))
    return p


def test_disk_shaped_jobs_report_their_real_id(tmp_path):
    f = _store_with_disk_shape(tmp_path, [
        {"id": "aaaaaaaaaaaa", "name": "first", "enabled_toolsets": ["terminal", "skills"]},
        {"id": "bbbbbbbbbbbb", "name": "second", "enabled_toolsets": ["terminal"]},
    ])
    r = _run(f)
    assert r.returncode == 1, r.stdout
    assert "bbbbbbbbbbbb" in r.stdout
    assert "?" not in r.stdout.split("Jobs needing")[1].split("NOTE:")[0]


def test_apply_with_disk_shaped_ids_rewrites_only_the_named_job(tmp_path):
    f = _store_with_disk_shape(tmp_path, [
        {"id": "aaaaaaaaaaaa", "name": "first", "enabled_toolsets": ["terminal", "skills"]},
        {"id": "bbbbbbbbbbbb", "name": "second", "enabled_toolsets": ["terminal"]},
    ])
    assert _run(f, "--apply").returncode == 0
    jobs = {j["name"]: j for j in json.loads(f.read_text())["jobs"]}
    assert jobs["first"]["enabled_toolsets"] == ["terminal", "skills"], \
        "a job that already has skills must never be rewritten"
    assert "skills" in jobs["second"]["enabled_toolsets"]


def test_a_job_with_no_identity_is_never_a_target(tmp_path):
    """Two id-less jobs must not collapse into one dict key (None) — that is how
    an --apply rewrites the wrong job."""
    f = _store_with_disk_shape(tmp_path, [
        {"name": "no-id-a", "enabled_toolsets": ["terminal"]},
        {"name": "no-id-b", "enabled_toolsets": ["terminal"]},
    ])
    before = f.read_text()
    r = _run(f, "--apply")
    assert r.returncode == 0, f"{r.stdout}{r.stderr}"
    assert f.read_text() == before, "an unidentifiable job must be left untouched"
    # …and they are REPORTED, not silently dropped
    assert "no-id-a" in r.stdout and "no id/job_id" in r.stdout
