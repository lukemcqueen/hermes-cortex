#!/usr/bin/env python3
"""Task-queue visibility — the "invisible work" class.

The defect these pin, found by reading rows rather than inferring: a slice that is
`pending` WITH an assignee is not claimable (the pool requires `assignee IS NULL`)
and is not `in_progress` either, so no worker can take it and nobody is working it.
Six such slices had been stranded since 2026-08-23 while every board view showed
them as ordinary pending work.

Two independent faults had to line up for that:
  1. there was no RELEASE path — `unclaim_slice` required `status='in_progress'`,
     so an assignment handed out at decomposition could never be given back;
  2. the board counted assigned-pending rows as plain `pending`, overstating the
     available queue (18 shown, 9 actually claimable).

The morning pass that reported this blamed the `kaesa-90day` PROJECT label and
called `waiting` "not a v3 lifecycle state". Both were inference and both were
wrong: the pool query has no project filter at all, and `waiting` is a documented
v3/v008 status (task-db.py STATUSES). Hence these tests check the MECHANISM.

Run: python3 -m pytest tests/test_task_queue_visibility.py -q
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
TASK_DB = _REPO / "ops" / "scripts" / "manage" / "task-db.py"
TASK_MCP = _REPO / "mcp-servers" / "task-mcp.py"
SCHEMA_DIR = _REPO / "ops" / "services" / "tasks" / "schema"

_SRC_DB = TASK_DB.read_text()
_SRC_MCP = TASK_MCP.read_text()


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── R4: every real lifecycle state must be queryable through the MCP ────────

def _cli_statuses() -> set:
    """The statuses the STORE actually accepts, straight from task-db.py."""
    m = re.search(r"^STATUSES\s*=\s*\(([^)]*)\)", _SRC_DB, re.M | re.S)
    assert m, "could not parse STATUSES from task-db.py — fix the test, not the code"
    return set(re.findall(r"\"([a-z_]+)\"", m.group(1)))


def _mcp_enums() -> list:
    """Every status enum the MCP advertises, with the line it sits on."""
    out = []
    for i, line in enumerate(_SRC_MCP.splitlines(), 1):
        m = re.search(r'"enum":\s*\[([^\]]*)\]', line)
        if m and "pending" in m.group(1):
            out.append((i, set(re.findall(r'"([a-z_]+)"', m.group(1)))))
    return out


def test_the_store_uses_states_the_mcp_cannot_filter_by():
    """The MCP must not under-advertise the store's real states.

    `waiting`, `blocked` and `review` are all real (STATUSES + the review state the
    claim/verify cycle produces). A filter enum that omits them means an agent cannot
    ASK for those rows — they are invisible to every MCP-driven board, which is how
    six `waiting` rows sat unflagged for six weeks.
    """
    real = _cli_statuses()
    enums = _mcp_enums()
    assert enums, "no status enum found in task-mcp.py — fix the test's parser"
    for line_no, advertised in enums:
        missing = sorted(real - advertised)
        assert not missing, (
            f"task-mcp.py:{line_no} filters by {sorted(advertised)} but the store "
            f"also uses {missing} — those rows are unqueryable through MCP")


def test_the_real_states_really_are_real():
    """Premise guard: if `waiting` ever stops being a store state, the test above
    silently stops protecting anything. Pin the premise so it cannot rot."""
    real = _cli_statuses()
    for state in ("waiting", "blocked", "review", "pending"):
        assert state in real, (
            f"{state!r} is no longer in STATUSES — re-derive these tests")


# ── R1/R3: no pending slice may be invisible, and the board must not lie ────

def test_claimable_and_assigned_views_are_complementary():
    """Together the two pending views must cover EVERY pending slice.

    This is the class-level guard: it is not enough that the claimable view exists.
    There must be a second view for the rows the pool deliberately excludes, or the
    excluded half has no reader at all.
    """
    assert re.search(r"assignee IS NULL", _SRC_DB), (
        "the claimable view no longer filters on assignee — re-derive this guard")
    assert re.search(r"assignee IS NOT NULL", _SRC_DB), (
        "there is no view for pending slices WITH an assignee: those rows are "
        "unclaimable and unwatched, which is exactly how they rot unnoticed")


def test_the_board_separates_assigned_from_claimable():
    """`pending: 18` was a lie: 9 were claimable. A count that cannot be acted on
    hides the rot it contains."""
    boardish = _SRC_DB[_SRC_DB.index("def cmd_list_board"):]
    body = boardish[:boardish.index("\ndef ")]
    assert "assignee" in body, (
        "cmd_list_board no longer distinguishes assigned-pending rows, so the "
        "pending count again implies work that cannot be claimed")


# ── R2: a stale hand-off must be releasable ────────────────────────────────

def _migrations() -> list:
    """All schema migrations, newest last.

    Scanned as a SET rather than "the newest file": the runner SKIPS an already-applied
    version (v010 was written precisely because a fixed v009 had already shipped), so a
    later arc has to arrive as its own migration and the guard must find it anywhere.
    """
    cands = sorted(SCHEMA_DIR.glob("v0*.sql"))
    assert cands, "no schema migrations found"
    return cands


def _release_body() -> str:
    """The migration text that redefines unclaim_slice, wherever it lives."""
    for path in reversed(_migrations()):
        text = path.read_text()
        if "unclaim_slice" in text and "CREATE OR REPLACE" in text:
            return text
    raise AssertionError(
        "no migration redefines unclaim_slice — there is still no way to release a "
        "pending slice that was assigned and never started")


def test_a_release_migration_exists():
    assert _release_body(), "no release migration found"


def test_the_release_migration_accepts_a_pending_assignment():
    """The old body required status='in_progress', which is precisely why these
    rows were stuck. The new body must accept a pending row that has an assignee."""
    body = _release_body()
    assert "in_progress" in body, (
        "the release path must still handle the in_progress case it always did")
    assert re.search(r"pending", body), (
        "the release path must also accept a pending row (the stuck case)")
    assert "assignee" in body, (
        "the release path must clear the assignee, or the row stays unclaimable")


def test_the_release_migration_keeps_the_own_work_guard():
    """Widening the WHERE must not drop the authorisation guard."""
    body = _release_body()
    assert "created_by" in body and "profile_of" in body, (
        "the widened release must keep the created_by / profile_of own-work guard")


def test_the_release_migration_keeps_the_derivation_column_in_sync():
    """hand-written UPDATEs that miss the column-derivation CHECK fail at runtime;
    the row must set `column` alongside `status`."""
    assert re.search(r'"column"\s*=', _release_body()), (
        "the release UPDATE must set `column` too — the derivation CHECK depends on it")


# ── the OTHER half of the stranding: a parked row cannot return to the pool ──

def _strip_sql_comments(text: str) -> str:
    """Drop `--` comments before parsing arms.

    An arm carrying an explanatory comment between THEN and RETURN is still valid SQL,
    and v012 does exactly that. Matching raw text would call a correct migration broken.
    """
    return "\n".join(re.sub(r"--.*$", "", line) for line in text.splitlines())


def test_a_parked_row_can_return_to_the_pull_pool():
    """`waiting`, `blocked` and `paused` are PARKED states, and none of them could
    transition to `pending`. So a parked slice could never re-enter the claim pool:
    the only route back was a manual `--status in_progress`, which defeats the pull
    model entirely. Found live — the update that tried it was refused:
      'illegal task transition: waiting -> pending'.

    v010 fixed exactly this shape of omission for the in_progress arc; this pins the
    parked arcs so the same hole cannot reopen.
    """
    newest = _migrations()[-1]
    text = _strip_sql_comments(newest.read_text())
    assert "transition_allowed" in text, (
        f"{newest.name} does not touch transition_allowed — parked rows still cannot "
        "return to pending, so they can never be claimed")

    # The arc itself: for each parked state, `pending` must be an allowed target.
    for state in ("paused", "blocked", "waiting"):
        m = re.search(rf"WHEN '{state}' THEN\s*RETURN p_to IN \(([^)]*)\)", text,
                      re.I | re.S)
        assert m, f"no transition_allowed arm found for {state!r}"
        assert "pending" in m.group(1), (
            f"{state!r} still cannot transition to 'pending' — a slice parked there "
            "can never re-enter the claim pool")


def test_the_parked_arc_guard_would_notice_a_missing_arc():
    """Control: the parser must actually be able to FAIL.

    Both directions — the real file parses, and a file with the arc removed does not
    match. Without this the guard could pass by never matching anything.
    """
    text = _strip_sql_comments(_migrations()[-1].read_text())
    m = re.search(r"WHEN 'waiting' THEN\s*RETURN p_to IN \(([^)]*)\)", text,
                  re.I | re.S)
    assert m, "the real migration's waiting arm must parse"
    assert "pending" in m.group(1), "control premise: the arc is present"

    crippled = text.replace("'completed', 'cancelled', 'pending'",
                            "'completed', 'cancelled'")
    m2 = re.search(r"WHEN 'waiting' THEN\s*RETURN p_to IN \(([^)]*)\)", crippled,
                   re.I | re.S)
    assert m2 and "pending" not in m2.group(1), (
        "the guard must detect the arc when it is absent — it is not vacuous")


def test_the_transition_gate_is_the_one_that_refused_us():
    """Premise guard: the refusal we saw really does come from transition_allowed."""
    gate = (SCHEMA_DIR / "v005__lifecycle.sql").read_text()
    assert "illegal task transition" in gate and "transition_allowed" in gate, (
        "the transition gate moved — re-derive these tests")


# ── the MCP must expose the release, not just the schema ───────────────────

def test_mcp_documents_the_release_path():
    """unclaim is how a worker gives back work; it is now also how a stale hand-off
    is released. If the tool description still says in_progress only, an agent will
    never try it on a pending row."""
    tools = ""
    for line in _SRC_MCP.splitlines():
        if "task_unclaim" in line or "in_progress slice to pending" in line:
            tools += line + "\n"
    assert "in_progress" in tools, "the unclaim description lost its original case"
    assert re.search(r"pending|assignee|handed", tools, re.I), (
        "the unclaim tool description does not mention releasing an assigned "
        "PENDING slice, so an agent has no reason to use it for that")
