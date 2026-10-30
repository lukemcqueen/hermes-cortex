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


def test_rereview_shape_is_sanctioned():
    """--re-review is the append-only re-judge: same shape, --re-review flag."""
    assert enf._is_sanctioned_plan_review_command(
        _cmd().replace(" --review ", " --re-review ")) is True


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


# ── DB-write gate: adversarial_reviews is append-only (2026-10-30) ──────────

GOV_DB = f"{HOME}/.hermes-cortex/data/loop-governance.db"
DEPLOYED_REVIEWER = f"{HOME}/.hermes-cortex/scripts/adversarial-review.py"


def test_raw_sqlite3_delete_against_gov_db_is_blocked():
    """The exact observed tamper: sqlite3 <db> \"DELETE FROM adversarial_reviews ...\"."""
    cmd = f'sqlite3 "{GOV_DB}" "DELETE FROM adversarial_reviews WHERE cycle_id=8208;"'
    assert enf._is_governance_db_mutation_command(cmd) is True


def test_raw_sqlite3_update_and_drop_are_blocked():
    assert enf._is_governance_db_mutation_command(
        f'sqlite3 "{GOV_DB}" "UPDATE adversarial_reviews SET verdict=\'CLEAN\' WHERE 1;"') is True
    assert enf._is_governance_db_mutation_command(
        f'sqlite3 "{GOV_DB}" "DROP TABLE adversarial_reviews;"') is True


def test_tmp_copy_script_with_db_arg_is_blocked():
    """The copy trick: /tmp/adv-review.py ... --db <gov-db>. The script body is
    not in the command text, so an opaque writer pointing at the store is refused."""
    cmd = (f"python3 /tmp/adv-review.py --cycle-id 8208 "
           f"--material-file /tmp/plan.md --review --reviewer-id plan-x "
           f"--db {GOV_DB}")
    assert enf._is_governance_db_mutation_command(cmd) is True


def test_inline_python_heredoc_with_mutation_is_blocked():
    cmd = (f"python3 - <<'PY'\n"
           f"import sqlite3\n"
           f"c = sqlite3.connect('{GOV_DB}')\n"
           f"c.execute('DELETE FROM adversarial_reviews WHERE cycle_id=8208')\n"
           f"c.commit()\n"
           f"PY")
    assert enf._is_governance_db_mutation_command(cmd) is True


def test_canonical_reviewer_with_any_db_is_not_blocked():
    """The sanctioned writer may point --db at the store (it is the record path)."""
    cmd = (f"python3 {DEPLOYED_REVIEWER} --cycle-id 8208 "
           f"--material-file /tmp/plan.md --review --reviewer-id plan-x "
           f"--db {GOV_DB}")
    assert enf._is_governance_db_mutation_command(cmd) is False
    rereview = cmd.replace(" --review ", " --re-review ")
    assert enf._is_governance_db_mutation_command(rereview) is False


def test_manage_record_review_script_is_not_blocked():
    cmd = (f"python3 {HOME}/hermes-cortex/ops/scripts/manage/record-review.py "
           f"--cycle-id 42 --verdict CLEAN --findings-json '[]' "
           f"--reviewer-id x --reviewer-model m --summary s --db {GOV_DB}")
    assert enf._is_governance_db_mutation_command(cmd) is False


def test_select_only_reads_are_not_blocked_by_the_mutation_gate():
    """Diagnostics (the doctor's own queries) keep working."""
    assert enf._is_governance_db_mutation_command(
        f'sqlite3 "{GOV_DB}" "SELECT verdict FROM adversarial_reviews WHERE cycle_id=8208;"') is False
    assert enf._is_governance_db_mutation_command(
        f"python3 -c \"import sqlite3; "
        f"print(sqlite3.connect('{GOV_DB}').execute('SELECT count(*) FROM loop_cycles').fetchone())\""
    ) is False


def test_unrelated_commands_are_never_blocked():
    assert enf._is_governance_db_mutation_command("git status") is False
    assert enf._is_governance_db_mutation_command("") is False
    assert enf._is_governance_db_mutation_command(
        "grep -rn adversarial_reviews ops/") is False


def test_mutation_gate_wired_between_carveout_and_no_repo_refusal():
    """The DB gate must run AFTER the sanctioned carve-out (so the reviewer is
    never mistaken for a tamper) and BEFORE the no-repo refusal (so the block
    message names the append-only rule, not the generic lock demand)."""
    source = _ENFORCER.read_text(encoding="utf-8")
    carve = source.index("_is_sanctioned_plan_review_command(")
    db_gate = source.index("_is_governance_db_mutation_command(")
    refusal = source.index("if not _repo_for_gate:")
    assert carve < db_gate < refusal, "order: carve-out, then DB gate, then refusals"