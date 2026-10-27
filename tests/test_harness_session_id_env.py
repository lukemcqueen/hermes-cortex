"""A non-Hermes harness must be able to give its session its OWN governance id.

Defect (measured, evidence committed at
docs/evidence/shared-session-id-non-hermes-2026-10-27/transcript.txt): with no
per-call `session_id` injected, get_session_id() falls back to ONE id persisted
per REPO (`state/.session-<slug>.id`), so two sessions in the same repo resolve
to the same id and therefore the same lock file `.governance-<session_id>.json`.
Case A of that transcript: two processes, one repo, both `sess_108f05ce7587`,
one lock file.

The fix is to read a session id the CALLER'S OWN environment already provides,
because one MCP child serves one session. The names honoured here are surveyed,
not invented:
  CORTEX_SESSION_KEY - the fleet's documented per-session key
                       (docs/runbooks/context-integration.md; pinned per chat by
                       ops/scripts/cortex_gateway/agents.py)
  PI_SESSION_ID      - Pi's own "Current session ID" (its packaged
                       docs/environment-variables.md)

Tests are written to run under pytest and to be inert on import; none of them
takes a pytest fixture, so the file also runs standalone:
    python3 tests/test_harness_session_id_env.py
"""
import importlib.util
import os
import tempfile
from pathlib import Path

MCP_PATH = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"

_ENV_KEYS = ("CORTEX_SESSION_KEY", "PI_SESSION_ID")


def _fresh_module(state_dir):
    """A module instance with its own state dir and no cached process id."""
    name = "lgm_env_%s" % os.urandom(4).hex()
    spec = importlib.util.spec_from_file_location(name, MCP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.GOVERNANCE_STATE_DIR = Path(state_dir)
    mod._PROCESS_SESSION_ID = ""
    return mod


def _with_env(values):
    """Set exactly the given env keys, restoring every prior value afterwards."""
    saved = {k: os.environ.pop(k, None) for k in _ENV_KEYS}
    for key, value in values.items():
        os.environ[key] = value
    return saved


def _restore_env(saved):
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _per_repo_files(state_dir):
    return sorted(p.name for p in Path(state_dir).glob(".session-*.id"))


def test_two_different_session_keys_get_disjoint_ids():
    """THE DEFECT: two sessions, one repo -> two ids, so two lock files."""
    with tempfile.TemporaryDirectory() as td:
        saved = _with_env({"CORTEX_SESSION_KEY": "hc-pi-chat-aaa"})
        try:
            mod_a = _fresh_module(td)
            a = mod_a.get_session_id(None)
            os.environ["CORTEX_SESSION_KEY"] = "hc-pi-chat-bbb"  # the OTHER session
            mod_b = _fresh_module(td)
            b = mod_b.get_session_id(None)
        finally:
            _restore_env(saved)
        assert a and b
        assert a != b, f"two sessions in one repo shared the id {a}"
        # the id IS the lock filename, so unequal ids are unequal locks — this is
        # the mechanism the defect exploited (case A: one id, one lock file)
        assert mod_a._session_lock_path(a) != mod_b._session_lock_path(b)


def test_pi_session_id_is_used_and_deterministic():
    """Pi's own variable, and the id does not depend on process-local state."""
    with tempfile.TemporaryDirectory() as td:
        value = "01a17c0b-82ee-72f1-be80-f25d7f225015"
        saved = _with_env({"PI_SESSION_ID": value})
        try:
            first = _fresh_module(td).get_session_id(None)
            second = _fresh_module(td).get_session_id(None)
        finally:
            _restore_env(saved)
        assert value in first, f"PI_SESSION_ID not honoured: {first}"
        assert first == second, "the id must survive an MCP-child restart"


def test_cortex_session_key_wins_over_pi_session_id():
    with tempfile.TemporaryDirectory() as td:
        saved = _with_env({"CORTEX_SESSION_KEY": "hc-pi-chat-bbb",
                           "PI_SESSION_ID": "01a17c0b-82ee-72f1"})
        try:
            sid = _fresh_module(td).get_session_id(None)
        finally:
            _restore_env(saved)
        assert "hc-pi-chat-bbb" in sid, f"wrong source won: {sid}"
        assert "01a17c0b" not in sid


def test_per_call_injected_id_still_wins():
    """Hermes is unchanged: the enforcer's per-call id is returned verbatim."""
    with tempfile.TemporaryDirectory() as td:
        saved = _with_env({"CORTEX_SESSION_KEY": "hc-pi-chat-ccc",
                           "PI_SESSION_ID": "01a17c0b-82ee-72f1"})
        try:
            sid = _fresh_module(td).get_session_id({"session_id": "sess_hermes_xyz"})
        finally:
            _restore_env(saved)
        assert sid == "sess_hermes_xyz", sid


def test_empty_or_whitespace_env_is_ignored():
    with tempfile.TemporaryDirectory() as td:
        saved = _with_env({"CORTEX_SESSION_KEY": "   ", "PI_SESSION_ID": ""})
        try:
            mod = _fresh_module(td)
            mod._derive_slug = lambda *a, **k: "probe-repo"
            sid = mod.get_session_id(None)
        finally:
            _restore_env(saved)
        assert sid.startswith("sess_")
        assert " " not in sid
        assert sid != "sess_", sid


def test_unsafe_characters_are_sanitised_into_one_path_component():
    """A hostile or merely awkward key must not become a path or break the name."""
    hostile = "../../etc/passwd a\\b\nc\td"
    with tempfile.TemporaryDirectory() as td:
        saved = _with_env({"CORTEX_SESSION_KEY": hostile})
        try:
            mod = _fresh_module(td)
            sid = mod.get_session_id(None)
            lock_path = mod._session_lock_path(sid)
        finally:
            _restore_env(saved)
        # the value must be the one the env supplied (so this test exercises the
        # sanitiser, not the per-repo fallback, which is safe by construction)
        assert "passwd" in sid, f"env value was not the source: {sid!r}"
        for bad in ("/", "\\", " ", "\n", "\t", ".."):
            assert bad not in sid, f"{bad!r} survived sanitisation: {sid!r}"
        assert Path(td).resolve() in lock_path.resolve().parents, lock_path
        assert lock_path.parent == Path(td).resolve()


def test_no_env_falls_back_to_the_per_repo_file():
    """Regression guard: the CLI and a bare harness keep their old behaviour."""
    with tempfile.TemporaryDirectory() as td:
        saved = _with_env({})
        try:
            mod = _fresh_module(td)
            mod._derive_slug = lambda *a, **k: "probe-repo"
            first = mod.get_session_id(None)
            mod._PROCESS_SESSION_ID = ""
            second = mod.get_session_id(None)
        finally:
            _restore_env(saved)
        assert first == second
        assert _per_repo_files(td) == [".session-probe-repo.id"]


def test_env_id_does_not_write_the_per_repo_file():
    """An env-provided id is already restart-stable, so the file is untouched."""
    with tempfile.TemporaryDirectory() as td:
        saved = _with_env({"PI_SESSION_ID": "01a17c0b-82ee-72f1"})
        try:
            _fresh_module(td).get_session_id(None)
        finally:
            _restore_env(saved)
        assert _per_repo_files(td) == [], _per_repo_files(td)


def _main():
    """Standalone runner: no pytest needed, and no fixtures anywhere above."""
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failed.append(name)
            print(f"  FAIL  {name} — {exc}")
        except Exception as exc:  # noqa: BLE001 — report the type, do not mask it
            failed.append(name)
            print(f"  ERROR {name} — {type(exc).__name__}: {exc}")
        else:
            print(f"  PASS  {name}")
    print()
    if failed:
        print(f"{len(failed)} of {len(tests)} FAILED: {', '.join(failed)}")
        raise SystemExit(1)
    print(f"ALL PASS ({len(tests)} tests)")


if __name__ == "__main__":
    _main()
