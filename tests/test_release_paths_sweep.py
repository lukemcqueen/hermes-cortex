"""SWEEP: every path that drops a lock must resolve its cycle FIRST — pinned as a sweep.

A 2026-10-14 DeepSeek Pro review of the release-path work found the class defect this file
exists to prevent, by asking the one question the earlier fixes had not: "is there ANY
remaining path that frees a lock, or closes a cycle, without the other half happening?"
Enumerating the call sites answered it — two more instances were live:

  * `_advance_task_state`'s TERMINAL branch released the lock (and made the task terminal) with
    the cycle still PENDING, which the doctor counts as a leak with no live non-terminal lock;
  * `_check_lock`'s stale auto-release dropped the lock of a heartbeat-stale session without
    touching its cycle.

Fixing those two is not the deliverable — the SWEEP is: a new call site that drops a lock
without resolving a cycle has to fail this test, and every exemption has to be declared here
with the reason its release is already safe, and have that reason asserted against the source.

Pinned against the REAL module (never imported or executed): positioning is judged by reading
the function bodies, because a behavioural test here would need a live session, a live store
and a live lock on the developer's host.
"""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"
CLOSER = "_close_cycle_unscored"
RELEASE = "_release_lock("

# Releases that are already safe WITHOUT the closer, each with the property that makes it so.
# The property is asserted below, so an exemption cannot silently rot into a false one.
EXEMPT = {
    "_end_change": (
        "the close-out gate REFUSES to release while the task's cycle is unscored, so the cycle "
        "is always already resolved (scored) before this release",
        ["Cannot release lock", "NOT scored"],
    ),
    "_begin_change": (
        "the force path auto-SCORES the replaced task's PENDING cycle before it releases that "
        "lock",
        ["Auto-score", "PENDING"],
    ),
}


def _functions():
    src = SRC.read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef):
            yield node.name, ast.get_source_segment(src, node) or ""


def test_every_release_call_site_resolves_a_cycle_first():
    offenders, checked = [], 0
    for name, body in _functions():
        if name == "_release_lock" or RELEASE not in body:
            continue          # the remover itself, and any function that does not drop a lock
        checked += 1
        if CLOSER in body or name in EXEMPT:
            continue
        offenders.append(name)
    assert checked >= 4, f"expected several release call sites, found {checked} — the sweep is blind"
    assert not offenders, (
        "these functions drop a governance lock without resolving the task's cycle first "
        f"(a released lock beside a PENDING cycle is a doctor leak that blocks every push on the "
        f"host): {offenders}. Either call {CLOSER} before the release, or add an exemption to "
        "EXEMPT with the property that makes it safe."
    )


def test_every_exemption_still_holds():
    """An exemption is a claim about the source; assert it, or the list rots into a lie."""
    bodies = dict(_functions())
    for name, (reason, phrases) in EXEMPT.items():
        assert name in bodies, f"exempt function {name} no longer exists — drop the exemption"
        for phrase in phrases:
            assert phrase in bodies[name], (
                f"the exemption for {name} is no longer true: it claims {reason!r}, but "
                f"{phrase!r} is absent from the function now. Re-audit it — a release that is "
                "safe only because of a gate must keep that gate."
            )


def test_the_terminal_and_blocked_branches_both_close_before_releasing():
    body = dict(_functions())["_advance_task_state"]
    for branch in ('if new_state in TERMINAL_STATES:', 'elif new_state == "blocked":'):
        assert branch in body, f"branch {branch} vanished from _advance_task_state"
        seg = body.split(branch, 1)[1]
        closer_at, release_at = seg.find(CLOSER), seg.find("_release_lock(")
        assert closer_at != -1, f"{branch} releases the lock but never closes its cycle"
        assert release_at != -1, f"{branch} no longer releases the lock — is this branch dead?"
        assert closer_at < release_at, (
            f"{branch}: the cycle must be closed BEFORE the lock is dropped, or a crash between "
            "the two leaves a released lock beside a PENDING cycle"
        )


def test_the_reclaim_closes_cycles_before_removing_lock_files():
    body = dict(_functions())["_reclaim_dead_locks"]
    close_at, unlink_at = body.find(f"{CLOSER}("), body.find("unlink()")
    assert close_at != -1 and unlink_at != -1, "reclaim lost either the close or the unlink"
    assert close_at < unlink_at, (
        "reclaim removes lock files before resolving their cycles: a crash in between leaves a "
        "lockless PENDING cycle, which is the leak this whole path exists to remove"
    )


def test_the_reclaim_rechecks_staleness_under_the_state_lock():
    body = dict(_functions())["_reclaim_dead_locks"]
    lock_at = body.find("with _STATE_LOCK:")
    assert lock_at != -1, "the unlink loop must hold the state lock"
    inner = body[lock_at:]
    assert "fresh = json.loads(" in inner and "_is_lock_stale(fresh" in inner, (
        "the staleness decision must be re-taken INSIDE the state lock: the scan happens before "
        "it, so an owner that refreshed its heartbeat in the gap would have a LIVE lock removed"
    )


def test_the_reclaim_distinguishes_could_not_verify_from_zero():
    body = dict(_functions())["_reclaim_dead_locks"]
    assert "_still_pending(" in body, "the reclaim must MEASURE the outcome, not infer it"
    assert "leftovers < 0" in body, (
        "a could-not-verify outcome needs its own branch: reporting 0 for both 'nothing to "
        "close' and 'the store could not be read' hides a leak the doctor will find"
    )
    assert "is_error=" in body, "a partial outcome must not be returned as a success"
