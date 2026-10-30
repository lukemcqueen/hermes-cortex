#!/usr/bin/env python3
"""Worker plan-review recording must be sanctioned and lock-free.

WHY (2026-10-30, operator directive + measured deadlock): the plan-review-before-slice
gate (hc-plan-review-check.py) refuses a non-trivial slice unless the active cycle has a
row in `adversarial_reviews`. The ONLY sanctioned writer is adversarial-review.py
--cycle-id N --review, deployed to the SHARED path (~/.hermes-cortex/scripts/) for all
agents. But it writes into ~/.hermes-cortex/data/loop-governance.db — governance DATA, not
a git repo — so the lock gate resolved the write to hermes-cortex and demanded a
hermes-cortex lock, which a worker's pending cycle forbids ("Close out your previous task
... unscored PENDING cycles"). A worker therefore structurally could not satisfy the gate
that gates their OWN commit.

The operator's directive is explicit: adversarial review must NOT be orchestrator-gated; it
must be automatic for the agent and never block real work; a review before building is
always better (and one after to check). So the gate STAYS, and the agent is given the
sanctioned, lock-free way to record the review — same class as the brain-write carve-out.

This test drives the enforcer's OWN predicate (`_is_sanctioned_plan_review_command`) with
controlled inputs in both directions — never live ambient lock/DB state.

Run: python3 -m pytest tests/test_enforcer_plan_review_carveout.py -q
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_ENFORCER = _REPO / "plugins" / "governance-enforcer" / "__init__.py"
_SPEC = importlib.util.spec_from_file_location("enforcer_planreview_under_test", _ENFORCER)
assert _SPEC is not None and _SPEC.loader is not None, f"cannot load {_ENFORCER}"
enf = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(enf)

HOME = Path.home()
DEPLOYED = f"{HOME}/.hermes-cortex/scripts/adversarial-review.py"


def _cmd(material=f"--material-file plan.md", reviewer="--reviewer-id plan-x",
         cycle="--cycle-id 42", script=None, extra=""):
    script = script or DEPLOYED
    return f"python3 {script} {cycle} {material} --review {reviewer} {extra}"


# ── the exact worker invocation is sanctioned ─────────────────────────────

def test_deployed_path_worker_invocation_is_sanctioned():
    assert enf._is_sanctioned_plan_review_command(_cmd()) is True


def test_inline_material_variant_is_sanctioned():
    assert enf._is_sanctioned_plan_review_command(
        _cmd(material="--material 'the plan text'")) is True


def test_relative_or_other_script_path_is_sanctioned():
    assert enf._is_sanctioned_plan_review_command(
        _cmd(script="ops/scripts/orch-bus/adversarial-review.py")) is True
    assert enf._is_sanctioned_plan_review_command(
        _cmd(script="adversarial-review.py")) is True


def test_python_vs_python3_prefix_both_accepted():
    assert enf._is_sanctioned_plan_review_command(_cmd().replace("python3", "python3.11")) is True


# ── what must NOT be sanctioned (fail closed) ─────────────────────────────

@pytest.mark.parametrize("mutator", [
    lambda c: c.replace(" --review ", " --sweep "),       # sweep = cron's job
    lambda c: f"sudo {c}",                                # privilege escalation
    lambda c: c.replace("--material-file plan.md", "--material-file plan.md; rm -rf /"),
    lambda c: c.replace("--material-file plan.md", "--material-file plan.md | cat"),
    lambda c: c + " && echo hi",                          # chained work
    lambda c: c.replace("--reviewer-id plan-x", ""),      # no identity
    lambda c: c.replace("--cycle-id 42", ""),             # no cycle
    lambda c: c.replace("--review ", ""),                 # not recording
    lambda c: c.replace("--material-file plan.md", ""),   # no material
])
def test_anything_else_is_refused(mutator):
    assert enf._is_sanctioned_plan_review_command(mutator(_cmd())) is False


def test_bare_empty_or_malformed_commands_are_refused():
    assert enf._is_sanctioned_plan_review_command("") is False
    assert enf._is_sanctioned_plan_review_command("ls") is False
    assert enf._is_sanctioned_plan_review_command("python3 /tmp/foo.py --review") is False


def test_a_repo_write_command_is_not_exempted():
    assert enf._is_sanctioned_plan_review_command(
        f"git -C {_REPO} commit -m 'x'") is False


# ── the carve-out is wired BEFORE the lock refusals ───────────────────────

def test_the_exemption_is_wired_before_the_lock_refusal():
    """Pin the wiring, not just the helper: an exemption nobody consults is dead code,
    and it must sit in the lock gate BEFORE the no-repo / lock refusal it prevents."""
    source = _ENFORCER.read_text(encoding="utf-8")
    call = source.index("_is_sanctioned_plan_review_command(")
    refusal = source.index("if not _repo_for_gate:")
    assert call < refusal, "the plan-review exemption must be consulted before the refusal"
    assert "_has_governance_lock(" in source