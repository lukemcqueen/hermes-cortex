#!/usr/bin/env python3
"""Pi skill-load evidence must be RECORDABLE and FINDABLE — both halves, together.

WHY THIS EXISTS (2026-10-15)

Titus reported: "I don't have a skill_view tool - I used read to read the SKILL.md
files." He was right, and the fleet was wrong. Pi has no `skill_view`:

  * `node ops/install/harnesses/pi/probe-pi-skill-mechanism.mjs` drives the
    INSTALLED Pi package through its own factory and prints Pi's `read` tool schema
    (`{path, offset, limit}` → the parameter the model actually emits) plus Pi's own
    system-prompt instruction: "Use the read tool to load a skill's file...". The
    Pi bundle contains no `skill_view` identifier at all.

Three defects followed, and fixing any ONE of them alone changes nothing:

  1. the evidence writer (`ops/install/harnesses/pi/extensions/cortex-context.ts`)
     recorded only `toolName === "skill_view"` → unreachable on Pi, so NOTHING was
     ever recorded;
  2. the checker (`store.py::loaded_skill`) hard-coded `tool_name = 'skill_view'`
     → a read of the skill's file could not count even if it were recorded;
  3. the writer keyed its row to `CORTEX_SESSION_KEY` (`hc-pi-<chat>`) while the
     reflexion gate queries the ACTIVE LOCK's `session_id` (`sess_<hex>` for a
     non-Hermes caller) → the two could never agree.

This suite pins all three, in the two shapes it must be able to tell apart, and
pins the SEAM as well: that the id the writer is told to use is the id the gate
asks with. A test of either half alone would have passed throughout the outage.

Hermetic where it can be (the lock/identity cases) and namespaced-and-cleaned
where it must touch the real store.

Run:  python3 tests/test_pi_skill_load_evidence.py
   or: pytest tests/test_pi_skill_load_evidence.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = Path(os.environ.get("CORTEX_LOOP_GOV_SERVER", REPO / "mcp-servers" / "loop-gov-mcp.py"))
STORE_PATH = REPO / "ops" / "services" / "mycortex-mem" / "store.py"
EXTENSION = REPO / "ops" / "install" / "harnesses" / "pi" / "extensions" / "cortex-context.ts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_server():
    return _load(SERVER, "loop_gov_identity_under_test")


def _load_store():
    return _load(STORE_PATH, "mycortex_store_under_test")


def _seed_lock(state_dir: Path, name: str, *, repo_path: str, mod,
               session_id: str | None = None) -> str:
    """Write one lock in the shape the server reads; return its session_id.

    `session_id` is overridable because the id's PREFIX carries meaning: the gate
    (and `_session_identity`) treat `cron_`/`bg_` ids as unattended, so a fixture
    that wants to exercise that rule must build the real shape rather than a
    decorative name.
    """
    now = mod._now_iso()
    sid = session_id or f"sess-{name}"
    lock = {
        "task_id": f"task-{name}",
        "session_id": sid,
        "agent": "pi-evidence-test",
        "status": "executing",
        "started_at": now,
        "heartbeat_at": now,
        "ttl_seconds": mod.DEFAULT_TTL,
        "repo_slug": Path(repo_path).name,
        "repo_path": repo_path,
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / f".governance-{sid}.json").write_text(json.dumps(lock))
    return sid


def _identity(mod, repo: str) -> dict:
    return json.loads(mod._session_identity({"repo_path": repo}).content[0].text)


# ── the SEAM: the writer's key must be the gate's key ───────────────────────


def test_identity_matches_the_lock_the_gate_will_query(tmp_path):
    """A live lock covering the repo ⇒ the writer is told THAT lock's id.

    This is the whole fix for defect 3 in one assertion: the gate asks the store
    about the active lock's session_id, so the writer has to be handed that exact
    value rather than inventing `hc-pi-<chat>`.
    """
    mod = _load_server()
    mod.GOVERNANCE_STATE_DIR = tmp_path / "state"
    proj = tmp_path / "proj"
    proj.mkdir(parents=True)
    (proj / ".git").mkdir()
    sid = _seed_lock(mod.GOVERNANCE_STATE_DIR, "withlock", repo_path=str(proj), mod=mod)

    got = _identity(mod, str(proj))
    assert got["effective_session_id"] == sid, (
        "the writer would record under a DIFFERENT key than the reflexion gate "
        f"queries — the evidence can never be found: {got}"
    )
    assert got["lock_session_id"] == sid, got


def test_identity_before_begin_change_uses_the_id_the_lock_will_carry(tmp_path):
    """No lock yet (task-start loads skills BEFORE begin_change) ⇒ still usable.

    A skill load made before `begin_change` must not be lost. The answer is this
    caller's own per-repo id, which is the SAME value `begin_change` stamps on the
    lock a moment later (get_session_id's Priority 1 persists it per repo), so the
    two sides converge instead of requiring the lock to exist first.
    """
    mod = _load_server()
    mod.GOVERNANCE_STATE_DIR = tmp_path / "state"
    mod._PROCESS_SESSION_ID = ""  # no cached id: exercise the real resolution
    proj = tmp_path / "nolock"
    proj.mkdir(parents=True)
    (proj / ".git").mkdir()

    got = _identity(mod, str(proj))
    assert got["lock_session_id"] is None, f"no lock covers this repo yet: {got}"
    assert got["effective_session_id"], f"the writer got no usable key at all: {got}"
    assert got["effective_session_id"] == got["session_id"], (
        "with no lock, the effective id must be this caller's own — the value the "
        f"lock will carry: {got}"
    )
    # And it must be PERSISTED, or the later begin_change would mint a different
    # one and the evidence would be stranded under the abandoned id.
    persisted = list((tmp_path / "state").glob(".session-*.id"))
    assert persisted, "the per-repo id was not persisted; a later lock could differ"


def test_identity_prefers_an_interactive_lock_over_a_cron_one(tmp_path):
    """Two locks covering one repo: the writer must pick what the GATE picks.

    hc-reflexion-check prefers a non-cron/bg lock (judging an interactive commit by
    a cron's evidence is wrong). If the writer picked the other lock, the two sides
    would disagree exactly when it matters — so the preference is pinned here.
    """
    mod = _load_server()
    mod.GOVERNANCE_STATE_DIR = tmp_path / "state"
    proj = tmp_path / "both"
    proj.mkdir(parents=True)
    (proj / ".git").mkdir()
    _seed_lock(mod.GOVERNANCE_STATE_DIR, "cronjob",
               repo_path=str(proj), mod=mod,
               session_id="cron_1_20260101_000000")
    interactive = _seed_lock(mod.GOVERNANCE_STATE_DIR, "interactive",
                             repo_path=str(proj), mod=mod)

    got = _identity(mod, str(proj))
    assert got["effective_session_id"] == interactive, (
        f"the writer picked a lock the gate would not judge against: {got}"
    )
    assert len(got["covering_locks"]) == 2, (
        "both covering locks must be REPORTED, or a divergence is invisible: " f"{got}"
    )


# ── the CHECKER: both mechanisms, and only the right ones ───────────────────


class _FakePg:
    """Captures the SQL the real predicate builds; returns a canned row."""

    def __init__(self) -> None:
        self.sql = []
        self.hit = False

    def row(self, sql, role=None):  # noqa: ANN001, D102 — mirrors Store.pg.row
        self.sql.append(sql)
        return ["1"] if self.hit else None


def _checker_with(fake_pg):
    store = _load_store()
    st = store.Store.__new__(store.Store)   # no __init__: never touch the live PG
    st.pg = fake_pg
    # loaded_skill lives on the SESSIONS store (`store.sessions`), not on Store —
    # the gate reaches it the same way, so the fake is attached where it is used.
    st.sessions = store.SessionStore.__new__(store.SessionStore)
    st.sessions.pg = fake_pg
    return store, st


def test_the_predicate_accepts_both_mechanisms_and_demands_the_own_directory():
    """The SQL itself: a `read` of the skill's OWN file counts; nothing else does.

    Executed against a captured query rather than a live row so the PREDICATE is
    what is judged — and the discriminating parts are asserted explicitly, because
    the first draft of this fix copied the neighbouring suffix idiom and produced a
    pattern that could never match (a trailing quote that only one stored shape
    has).
    """
    fake = _FakePg()
    store, st = _checker_with(fake)

    assert st.sessions.loaded_skill("reflexion-check", "", session_key="sess-x") is False
    sql = fake.sql[-1]

    assert "e.tool_name = 'skill_view'" in sql, "the Hermes mechanism was dropped"
    assert "e.tool_name = 'read'" in sql, "the Pi mechanism was not added"
    # Whitespace-tolerant on purpose: the SQL is composed across f-string lines, so
    # asserting an exact `LIKE '...'` spacing would fail on a reformat that changed
    # nothing (a probe that reports the author's line breaks as a defect).
    assert "'%/reflexion-check/SKILL.md%'" in sql, (
        "the Pi branch must match the skill's OWN directory, so a read of an "
        f"unrelated file cannot satisfy it: {sql}"
    )
    assert '%/reflexion-check/SKILL.md%"%' not in sql, (
        "the Pi pattern must NOT require a trailing quote: the stored JSON is the "
        "read tool's own input, so the path is not necessarily the last value"
    )
    assert "s.session_key = " in sql, "the predicate stopped being session-scoped"


def test_a_like_wildcard_in_a_skill_name_cannot_over_match():
    """LIKE metacharacters in a skill name must be ESCAPED, not interpolated.

    `_` matches any single character in LIKE and `%` matches anything, so a skill
    named `a_b` interpolated raw would also match a read of `axb` — reporting a
    skill load that never happened. The gate's answer is a PERMISSION, so an
    over-match is a false pass, exactly what fail-closed exists to prevent.
    """
    fake = _FakePg()
    _, st = _checker_with(fake)
    st.sessions.loaded_skill("a_b", "", session_key="sess-z")
    sql = fake.sql[-1]
    assert "'%/a\\_b/SKILL.md%'" in sql, (
        "the underscore in the skill name was not escaped — a read of `axb` "
        f"would satisfy `a_b`: {sql}"
    )


def test_a_skill_name_containing_a_like_wildcard_does_not_over_match():
    """The same rule against the REAL store: `a_b` must not match `axb`."""
    store = _load_store()
    st = store.Store()
    if not st.available():
        print("SKIP: HC session/memory store unreachable (not a failure)")
        return
    key = f"hctest-pi-load-{os.getpid()}-wild"
    try:
        st.sessions.record_tool_event(
            "pi", "read", {"path": "/skills/a_b/SKILL.md"}, session_key=key
        )
        assert st.sessions.loaded_skill("a_b", "", session_key=key) is True
        assert st.sessions.loaded_skill("axb", "", session_key=key) is False, (
            "an underscore in the recorded name acted as a LIKE wildcard"
        )
    finally:
        for sql in (
            "DELETE FROM mycortex_mem.tool_events WHERE session_id IN "
            "(SELECT id FROM mycortex_mem.sessions WHERE session_key LIKE 'hctest-pi-load-%');",
            "DELETE FROM mycortex_mem.sessions WHERE session_key LIKE 'hctest-pi-load-%';",
        ):
            for role in ("mycortex_mem_admin", "mycortex_mem_writer"):
                try:
                    st.pg.run_sql(sql, role=role)
                    break
                except Exception:  # noqa: BLE001 — try the next role
                    continue


def test_a_loaded_row_is_reported_loaded_both_ways():
    """Both mechanisms must return True through the real code path."""
    for tool in ("skill_view", "read"):
        fake = _FakePg()
        fake.hit = True
        _, st = _checker_with(fake)
        assert st.sessions.loaded_skill("reflexion-check", "", session_key="sess-y") is True, (
            f"a recorded {tool} row was not honoured"
        )


# ── the round trip against the REAL store (namespaced, cleaned up) ──────────


def test_real_store_round_trip_accepts_a_pi_read_and_refuses_an_unrelated_read():
    """Writer → store → checker, for real. Skips cleanly when the store is down.

    This is the half a captured-SQL test cannot prove: that Postgres actually
    matches the shapes the writer produces. It uses a namespaced session key and
    DELETES it in `finally`, so it never leaves debris in the fleet's store.
    """
    store = _load_store()
    st = store.Store()
    if not st.available():
        print("SKIP: HC session/memory store unreachable (not a failure)")
        return

    key = f"hctest-pi-load-{os.getpid()}"
    skill = "reflexion-check"
    try:
        # 1. What the fixed extension now records for Pi's `read`.
        st.sessions.record_tool_event(
            "pi", "read",
            {"path": f"/skills/software-development/{skill}/SKILL.md"},
            session_key=key,
        )
        assert st.sessions.loaded_skill(skill, "", session_key=key) is True, (
            "a Pi read of the skill's file is not honoured by the real store"
        )
        # 2. A read of a DIFFERENT skill must not satisfy the question.
        assert st.sessions.loaded_skill("shell-scripting", "", session_key=key) is False, (
            "a read of another skill's file satisfied this skill's question"
        )
        # 3. A read of an unrelated file must satisfy nothing.
        st.sessions.record_tool_event(
            "pi", "read", {"path": "/etc/hostname"}, session_key=key
        )
        assert st.sessions.loaded_skill("hostname", "", session_key=key) is False, (
            "an unrelated read was counted as a skill load"
        )
        # 4. The Hermes mechanism still works, unchanged.
        st.sessions.record_tool_event(
            "hermes", "skill_view", {"name": skill}, session_key=key
        )
        assert st.sessions.loaded_skill(skill, "", session_key=key) is True
        # 5. A different session must not inherit this session's evidence.
        assert st.sessions.loaded_skill(skill, "", session_key=key + "-other") is False, (
            "evidence leaked across sessions — the gate would pass on nothing"
        )
    finally:
        # The writer role can INSERT but not DELETE, so cleanup uses the admin
        # role the schema ships (`mycortex_mem_admin`); the writer-role attempt is
        # kept as a fallback so a host that grants it still cleans up.
        deletes = (
            "DELETE FROM mycortex_mem.tool_events WHERE session_id IN "
            "(SELECT id FROM mycortex_mem.sessions WHERE session_key LIKE 'hctest-pi-load-%');",
            "DELETE FROM mycortex_mem.sessions WHERE session_key LIKE 'hctest-pi-load-%';",
        )
        errors = []
        for sql in deletes:
            for role in ("mycortex_mem_admin", "mycortex_mem_writer"):
                try:
                    st.pg.run_sql(sql, role=role)
                    errors = []
                    break
                except Exception as exc:  # noqa: BLE001 — try the next role
                    errors.append(f"{role}: {exc}")
        assert st.sessions.loaded_skill(skill, "", session_key=key) is False, (
            "the test fixture was NOT cleaned up — a fleet test must not leave "
            f"debris in the store; last errors: {errors}"
        )


# ── the writer's SOURCE: it must ask, not derive ────────────────────────────


def test_the_extension_asks_the_shared_cli_for_the_session_id():
    """The writer must not re-derive 'which session' — it must ASK.

    A structural assertion, kept alongside the behavioural ones in
    `verify-extension.mjs` (which EXECUTE the handler): this one catches the
    plausible-looking regression of swapping the CLI call for an env var or a
    direct file read, which would reintroduce a second derivation of identity.
    """
    src = EXTENSION.read_text(encoding="utf-8")
    assert "session_identity" in src, "the extension no longer asks for the session id"
    assert "effective_session_id" in src, "the extension ignores the resolved key"
    # The event must be keyed EXPLICITLY. Passing no session_key is what silently
    # fell back to an env-derived key and made the evidence unfindable, and it is
    # invisible in a diff — so the construct itself is asserted, not the absence of
    # one name (the file's own comment mentions CORTEX_SESSION_KEY to explain why
    # it is gone, and a bare-name search would report that explanation as the bug).
    assert "session_key: sessionKey" in src, (
        "the extension stopped passing an explicit session_key — the evidence "
        "would land under a key the gate does not query"
    )
    assert 'toolName !== "skill_view"' in src, "the skill_view mechanism was dropped"
    assert "/SKILL.md" in src, "Pi's read-of-SKILL.md mechanism is gone"


if __name__ == "__main__":
    import inspect
    import tempfile

    failures = 0
    for fn in (
        test_identity_matches_the_lock_the_gate_will_query,
        test_identity_before_begin_change_uses_the_id_the_lock_will_carry,
        test_identity_prefers_an_interactive_lock_over_a_cron_one,
        test_the_predicate_accepts_both_mechanisms_and_demands_the_own_directory,
        test_a_like_wildcard_in_a_skill_name_cannot_over_match,
        test_a_skill_name_containing_a_like_wildcard_does_not_over_match,
        test_a_loaded_row_is_reported_loaded_both_ways,
        test_real_store_round_trip_accepts_a_pi_read_and_refuses_an_unrelated_read,
        test_the_extension_asks_the_shared_cli_for_the_session_id,
    ):
        wants_path = len(inspect.signature(fn).parameters) == 1
        with tempfile.TemporaryDirectory() as td:
            try:
                fn(Path(td)) if wants_path else fn()
                print(f"✅ {fn.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"❌ {fn.__name__}: {exc}")
            except Exception as exc:  # noqa: BLE001 — a crash is a failure, named
                failures += 1
                print(f"❌ {fn.__name__}: UNEXPECTED {type(exc).__name__}: {exc}")
    print(f"\n{'❌ SOME TESTS FAILED' if failures else '✅ ALL TESTS PASSED'}")
    sys.exit(1 if failures else 0)
