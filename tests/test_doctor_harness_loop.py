#!/usr/bin/env python3
"""The doctor's per-harness check: one line per DECLARED harness, judged by its own presence.

The registry (ops/install/harnesses/registry.yaml) is the single source of harness
knowledge, and it declares five harnesses on a fleet with more added over time. The
doctor used to judge ONE of them (Pi) with hand-written logic, so every other harness
was invisible: a host whose Claude Code or Codex wiring had rotted reported a clean
doctor, and the knowledge of "what a harness needs" lived in two places.

This check reads the registry, decides presence from what the REGISTRY declares, and
judges the present ones by driving `hc harness verify <name>` — the same command an
operator runs. It is a driver, never a second definition.

Three outcomes, and the distinction between them is the point:
  PRESENT + verify rc 0   -> PASS
  PRESENT + verify rc != 0 -> WARN, carrying the command that decides it
  PRESENT + verify rc 3   -> WARN "could not verify"  (its own outcome: no interpreter
                             could import PyYAML, which is NOT a broken harness)
  ABSENT                  -> SKIP, "not installed on this host" — a host without Codex
                             is not a fault, and SKIP is the un-counted status that keeps
                             it out of the undisposed list
  DECLARED UNSUPPORTED    -> SKIP naming the registry's own reason, never "not installed"
  NO presence declared    -> WARN "could not verify": the check cannot do its job, and
                             that must be visible rather than read as a clean skip

Run: python3 -m pytest tests/test_doctor_harness_loop.py -q
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "ops" / "scripts" / "manage") not in sys.path:
    sys.path.insert(0, str(_REPO / "ops" / "scripts" / "manage"))

from cortex_doctor import checks  # noqa: E402
from cortex_doctor.results import Results  # noqa: E402

DOCTOR = _REPO / "ops" / "scripts" / "manage" / "cortex-doctor.py"

REGISTRY = """\
version: 1
harnesses:
  - name: present-harness
    layer: mcp
    status: shipped
    presence:
      - {present_path}
    install: |
      bash ops/scripts/install/install-present.sh
  - name: absent-harness
    layer: mcp
    status: documented
    presence:
      - {absent_path}
    install: |
      bash ops/scripts/install/install-absent.sh
  - name: blocked-harness
    layer: none
    status: blocked
    why: |
      Its own gateway is not complete, so its surface cannot be designed against it yet.
    presence: []
  - name: undeclared-presence-harness
    layer: mcp
    status: documented
"""


def _registry(tmp_path: Path, *, present: bool = True) -> Path:
    """A registry fixture whose presence points at paths that do and do not exist."""
    present_path = tmp_path / "installed-harness-dir"
    if present:
        present_path.mkdir()
    absent_path = tmp_path / "never-created-dir"
    regdir = tmp_path / "harnesses"
    regdir.mkdir(parents=True, exist_ok=True)
    (regdir / "registry.yaml").write_text(
        REGISTRY.format(present_path=present_path, absent_path=absent_path))
    return regdir


def _registry_view(regdir: Path) -> str:
    """The registry view from the REAL CLI, so no test restates its JSON shape.

    This is the seam that matters: the check must consume what `hc harness list --json`
    actually prints, and a hand-written fixture would test my guess at that shape rather
    than the CLI's output.
    """
    r = subprocess.run(["bash", str(_REPO / "ops" / "scripts" / "hc" / "hc"),
                        "harness", "list", "--json"],
                       capture_output=True, text=True, timeout=120,
                       env={**os.environ, "CORTEX_HARNESS_DIR": str(regdir)})
    assert r.returncode == 0, (
        f"the CLI could not read the fixture registry: rc={r.returncode}\n{r.stderr[-400:]}")
    return r.stdout


def _wire(monkeypatch, tmp_path: Path, *, present: bool = True, rc: int = 0,
          out: str = "artifact: present-harness/x.ts present\n\nresult: PASS\n",
          list_rc: int = 0, list_out: str | None = None):
    """Point the check at the fixture and replace only the CLI's subprocess seam."""
    regdir = _registry(tmp_path, present=present)
    monkeypatch.setattr(checks, "HOME", tmp_path)
    calls = []

    def fake_list():
        return list_rc, (list_out if list_out is not None else _registry_view(regdir))

    def fake_verify(name):
        calls.append(name)
        return rc, out

    monkeypatch.setattr(checks, "_run_harness_list", fake_list)
    monkeypatch.setattr(checks, "_run_harness_verify", fake_verify)
    return calls


def _entry(res, name):
    hits = [c for c in res.checks if c["name"] == f"Harness ({name})"]
    assert len(hits) == 1, f"expected exactly one line for {name}: {[c['name'] for c in res.checks]}"
    return hits[0]


def test_absent_harness_is_skipped_with_a_reason_not_warned(monkeypatch, tmp_path):
    """A host without a harness is not a fault: SKIP says so, and stays out of undisposed."""
    _wire(monkeypatch, tmp_path)
    res = Results()
    checks.check_harness_registry(res)
    e = _entry(res, "absent-harness")
    assert e["status"] == "SKIP", e
    assert "not installed" in e["detail"], e
    # Scoped to THIS harness: the fixture also declares a harness with no `presence:`,
    # which must warn — asserting on the whole result would be asserting my fixture.
    assert not [c for c in res.checks
                if c["status"] == "WARN" and c["name"] == "Harness (absent-harness)"], e


def test_present_harness_that_verifies_passes(monkeypatch, tmp_path):
    calls = _wire(monkeypatch, tmp_path, rc=0)
    res = Results()
    checks.check_harness_registry(res)
    e = _entry(res, "present-harness")
    assert e["status"] == "PASS", e
    assert "artifact: present-harness/x.ts present" in e["detail"], e
    assert calls == ["present-harness"], calls


def test_present_harness_that_fails_is_a_warn_naming_the_deciding_command(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, rc=1, out="artifact: MISSING — /x\n\nresult: FAIL\n")
    res = Results()
    checks.check_harness_registry(res)
    e = _entry(res, "present-harness")
    assert e["status"] == "WARN", e
    assert "result: FAIL" in e["detail"], e
    assert "harness verify present-harness" in e["fix"], e


def test_could_not_verify_is_reported_as_its_own_outcome(monkeypatch, tmp_path):
    """rc 3 means "no interpreter could import PyYAML" — never a broken harness."""
    _wire(monkeypatch, tmp_path, rc=3, out="COULD NOT VERIFY — no interpreter could import PyYAML\n")
    res = Results()
    checks.check_harness_registry(res)
    e = _entry(res, "present-harness")
    assert e["status"] == "WARN", e
    assert "could not verify" in e["detail"].lower(), e


def test_declared_unsupported_harness_is_skipped_with_the_registry_reason(monkeypatch, tmp_path):
    """`layer: none` with a blocked status is DECLARED unsupported, not "not installed"."""
    _wire(monkeypatch, tmp_path)
    res = Results()
    checks.check_harness_registry(res)
    e = _entry(res, "blocked-harness")
    assert e["status"] == "SKIP", e
    assert "not installed" not in e["detail"], e
    assert "gateway" in e["detail"], e


def test_a_harness_with_no_declared_presence_cannot_be_judged_and_says_so(monkeypatch, tmp_path):
    """No presence declared is a REGISTRY gap: visible as could-not-verify, never a clean skip."""
    _wire(monkeypatch, tmp_path)
    res = Results()
    checks.check_harness_registry(res)
    e = _entry(res, "undeclared-presence-harness")
    assert e["status"] == "WARN", e
    assert "could not verify" in e["detail"].lower(), e
    assert "presence" in e["fix"], e


def test_a_registry_the_cli_cannot_read_is_could_not_verify_and_verifies_nothing(monkeypatch, tmp_path):
    """Exit 3 (no interpreter could read the registry) is an outcome, not a crash.

    The doctor runs under a bare `python3` on the deploy path, so this branch is the one
    that decides whether a yaml-less interpreter leaves the check blind or honest. It must
    report could-not-verify and must NOT go on to judge harnesses it never read.
    """
    calls = _wire(monkeypatch, tmp_path, list_rc=3,
                  list_out="COULD NOT VERIFY — no interpreter could import PyYAML\n")
    res = Results()
    checks.check_harness_registry(res)          # must not raise
    hits = [c for c in res.checks if c["name"] == "Harness registry"]
    assert hits, f"the registry-level outcome must be reported: {[c['name'] for c in res.checks]}"
    e = hits[0]
    assert e["status"] == "WARN", e
    assert "could not verify" in e["detail"].lower(), e
    assert "no interpreter" in e["detail"].lower(), e
    assert calls == [], f"nothing can be verified without the registry: {calls}"


def test_a_registry_view_that_is_not_json_is_could_not_verify(monkeypatch, tmp_path):
    """A CLI that answers with prose must not be parsed into a silent empty harness list."""
    calls = _wire(monkeypatch, tmp_path, list_rc=0, list_out="Declared harnesses: 0\n")
    res = Results()
    checks.check_harness_registry(res)
    e = [c for c in res.checks if c["name"] == "Harness registry"][0]
    assert e["status"] == "WARN", e
    assert "could not verify" in e["detail"].lower(), e
    assert calls == [], calls


# ── the uber test: the REAL doctor, through its own dispatch, on THIS host ──────

def _doctor_json(env_extra: dict | None = None) -> dict:
    import os
    env = {**os.environ, **(env_extra or {})}
    r = subprocess.run([sys.executable, str(DOCTOR), "--json"],
                       capture_output=True, text=True, timeout=600, env=env)
    # The doctor's exit code reflects ANY check that fails — a pre-deploy tree reports
    # Deploy-sync FAILs — so asserting 0 would turn this into a probe of the deployed
    # state rather than of the harness check. What must hold: it RAN (not a usage error,
    # which is 3) and emitted parseable machine-readable output.
    assert r.returncode in (0, 1, 2), f"the doctor must run: rc={r.returncode}\n{r.stderr[-600:]}"
    start = r.stdout.find("{")
    assert start >= 0, f"no JSON on stdout:\n{r.stdout[-600:]}"
    return json.loads(r.stdout[start:])


def test_the_real_doctor_reports_one_line_per_declared_harness(tmp_path):
    """End to end through cortex-doctor.py: the registry count and the verdict shape hold.

    This is the system path, not the function: the doctor's own CLI, its own registry
    resolution, and — for a harness that IS installed here — the real `hc harness verify`
    subprocess underneath. It asserts the INVARIANTS that hold on any host (one line per
    declared harness, no FAIL, every status one of the three outcomes) and then the
    host-specific consequence: where a harness's declared presence exists, its line must
    not be SKIP, so a regression in `hc harness verify` fails here rather than in a
    doctor run nobody reads.
    """
    import yaml
    # CORTEX_HOME points at a fixture so this measures the CHECK and the CLI it drives,
    # not whether the tree has been deployed yet: the check prefers the deployed CLI, which
    # only supports the machine-readable view once this change is deployed, and a suite that
    # is red before every deploy is a suite people learn to ignore. The deployed wiring is
    # verified live by the cycle's own deploy, not asserted here.
    report = _doctor_json({"HERMES_CORTEX_HOME": str(tmp_path / "cortex-home")})
    reg = yaml.safe_load((_REPO / "ops" / "install" / "harnesses" / "registry.yaml").read_text())
    declared = [h["name"] for h in reg["harnesses"]]
    lines = {c["name"]: c for c in report["checks"] if c["name"].startswith("Harness (")}
    assert set(lines) == {f"Harness ({n})" for n in declared}, (
        f"the doctor must judge every declared harness exactly once: got {sorted(lines)}")
    for name in declared:
        e = lines[f"Harness ({name})"]
        assert e["status"] in ("PASS", "WARN", "SKIP"), e
        assert e["status"] != "FAIL", f"an absent harness must never FAIL the doctor: {e}"
    # Host-specific consequence, derived from the registry's own presence declarations.
    for h in reg["harnesses"]:
        entries = h.get("presence") or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, str) or entry.startswith("cmd:"):
                continue
            if Path(entry).expanduser().exists():
                e = lines[f"Harness ({h['name']})"]
                assert e["status"] != "SKIP", (
                    f"{h['name']} declares presence {entry}, which exists here, so the "
                    f"doctor must judge it — not skip it: {e}")
                break


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
