#!/usr/bin/env python3
"""Knowledge-brain writes must be sanctioned and lock-free.

WHY (measured 2026-10-27/28): the dream layer's entire output is a file written
into the knowledge brain — ``~/brain/<profile>/dreams/<date>.md`` plus its INDEX
row — and the brain is deliberately NOT a git repo (it is shared data, not code).
``_target_repo_root()`` therefore resolves NO repo for such a call, so the lock
gate refused it outright: "No governed repo could be resolved for this call —
and governance is scoped to a git repo, so no lock could authorise it."

The gate's own words name the flaw: governance is scoped to a repo, and there is
no repo here to bind to. The refusal was an impossible demand, not a control. It
cost the nightly dream its Phase 4 write-back on a host whose dream cron carries
an ``enabled_toolsets`` allowlist, and it is why an unattended session cannot
seed or prune the brain at all.

The exemption is deliberately NARROW: the brain tree only, file-tool path
arguments only. A terminal call is never exempted (its write target is not
path-analysable), and every other security gate (PII, adversarial, bypass-debt)
still applies to a brain write.

Run: python3 -m pytest tests/test_enforcer_brain_write_exempt.py -q
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_ENFORCER = _REPO / "plugins" / "governance-enforcer" / "__init__.py"
_SPEC = importlib.util.spec_from_file_location("enforcer_brain_under_test", _ENFORCER)
assert _SPEC is not None and _SPEC.loader is not None, f"cannot load {_ENFORCER}"
enf = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(enf)

HOME = Path.home()
BRAIN = HOME / "brain"


def test_dream_write_back_path_is_sanctioned():
    """The exact call the nightly dream makes in Phase 4."""
    assert enf._is_sanctioned_brain_write(
        {"path": str(BRAIN / "esther" / "dreams" / "2026-10-28.md")}) is True


def test_index_row_and_file_path_key_are_sanctioned():
    assert enf._is_sanctioned_brain_write(
        {"path": str(BRAIN / "esther" / "dreams" / "INDEX.md")}) is True
    assert enf._is_sanctioned_brain_write(
        {"file_path": str(BRAIN / "lessons" / "some-lesson.md")}) is True


def test_brain_root_itself_is_sanctioned():
    assert enf._is_sanctioned_brain_write({"path": str(BRAIN)}) is True


def test_a_sibling_directory_is_not_sanctioned():
    """`~/brainstorm/` must not match by string prefix."""
    assert enf._is_sanctioned_brain_write(
        {"path": str(HOME / "brainstorm" / "x.md")}) is False


@pytest.mark.parametrize("target", [
    "hermes-cortex/docs/troubleshooting.md",
    ".hermes/cache/scratch/probe.txt",
    ".hermes-cortex/skills.yaml",
    ".hermes/cron/jobs.json",
    "some-repo/plugins/governance-enforcer/__init__.py",
])
def test_everything_else_stays_gated(target):
    assert enf._is_sanctioned_brain_write({"path": str(HOME / target)}) is False


def test_a_terminal_call_is_never_exempted():
    """A command's write target is not path-analysable — `workdir` is not a target."""
    assert enf._is_sanctioned_brain_write(
        {"command": f"rm -rf {BRAIN}", "workdir": str(BRAIN)}) is False


def test_missing_or_malformed_path_args_are_not_exempted():
    assert enf._is_sanctioned_brain_write({}) is False
    assert enf._is_sanctioned_brain_write({"path": ""}) is False
    assert enf._is_sanctioned_brain_write({"path": None}) is False
    assert enf._is_sanctioned_brain_write(None) is False  # type: ignore[arg-type]


def test_the_exemption_is_wired_before_the_no_repo_refusal():
    """Pin the wiring, not just the helper: an exemption nobody consults is dead
    code, and it must sit in the lock gate BEFORE the 'no governed repo' refusal
    it exists to prevent."""
    source = _ENFORCER.read_text(encoding="utf-8")
    call = source.index("if _is_sanctioned_brain_write(args):")
    refusal = source.index("if not _repo_for_gate:")
    assert call < refusal, "the brain exemption must be consulted before the refusal"


def test_the_exemption_does_not_cover_repo_writes():
    """A write inside a governed checkout is still a governed write."""
    assert enf._is_sanctioned_brain_write(
        {"path": str(_REPO / "plugins" / "governance-enforcer" / "__init__.py")}) is False
