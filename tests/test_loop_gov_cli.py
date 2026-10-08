#!/usr/bin/env python3
"""Tests for the generic governance adapter (loop-gov) and the re-review path.

These cover the CHANGED code paths directly — a green suite that never touches
mcp-servers/loop-gov-mcp.py or ops/scripts/loop-gov.py does not verify them.
Each test here fails without the change it guards.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SERVER = REPO / "mcp-servers" / "loop-gov-mcp.py"
CLI = REPO / "ops" / "scripts" / "loop-gov.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gov():
    return _load(SERVER, "loop_gov_under_test")


def cli(*args: str, timeout: int = 180):
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, timeout=timeout)


# ── The change that lets a no-MCP host drive governance ──────────

def test_server_is_importable_and_usable_without_the_mcp_sdk(gov):
    """The SDK import must be guarded, and the handlers must still work.

    This is what makes the CLI possible at all: without the guard, importing the
    server on a harness with no `mcp` package raises and governance is
    unreachable from that host.
    """
    assert hasattr(gov, "MCP_AVAILABLE"), "no MCP_AVAILABLE flag — the guard is gone"
    # Handlers are SDK-independent and return a CallToolResult either way.
    r = gov._check_lock({})
    dumped = r.model_dump()
    text = dumped["content"][0]["text"]
    assert "active" in text, text[:200]


def test_shim_tool_accepts_the_sdk_camelcase_kwarg():
    """The shim must accept `inputSchema`, exactly as the real SDK and every call
    site in the server do. A shim that only understood `input_schema` would raise
    on `list_tools()` for a host without the SDK — precisely the hosts this
    mechanism exists to serve.

    Exercised for REAL, in a subprocess where `mcp` cannot be imported: on a
    machine that HAS the SDK the shim is never defined, so asserting on the
    imported module here would test nothing (it did — that was a bad probe).
    """
    script = (
        "import importlib.util, sys\n"
        # A None entry in sys.modules makes `import mcp` raise ImportError — the
        # supported way to simulate an absent SDK (a finder that raises from
        # find_spec propagates instead of being caught).
        "sys.modules['mcp'] = None\n"
        "sys.modules['mcp.server'] = None\n"
        "sys.modules['mcp.server.stdio'] = None\n"
        "sys.modules['mcp.types'] = None\n"
        "spec = importlib.util.spec_from_file_location('gov_nomcp', sys.argv[1])\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "assert m.MCP_AVAILABLE is False, 'guard did not engage'\n"
        "t = m.Tool(name='x', description='d', inputSchema={'type': 'object'})\n"
        "assert t.input_schema == {'type': 'object'}, t.input_schema\n"
        "r = m._check_lock({})\n"                       # handlers still work
        "assert 'active' in r.model_dump()['content'][0]['text']\n"
        "print('NOMCP_OK')\n"
    )
    r = subprocess.run([sys.executable, "-c", script, str(SERVER)],
                       capture_output=True, text=True, timeout=180)
    assert "NOMCP_OK" in r.stdout, f"{r.stdout[-300:]}\n{r.stderr[-500:]}"


# ── The generic CLI ─────────────────────────────────────────────

def test_cli_lists_and_manifests_the_surface():
    r = cli("--list")
    assert r.returncode == 0, r.stderr
    assert "begin_change" in r.stdout and "end_change" in r.stdout

    r = cli("--tools-json")
    assert r.returncode == 0, r.stderr
    manifest = json.loads(r.stdout)
    assert manifest["transport"] == "cli"
    assert manifest["exit_codes"]["1"] == "governance refused"
    names = {t["name"] for t in manifest["tools"]}
    assert {"begin_change", "end_change", "check_lock"} <= names


def test_every_advertised_tool_has_a_handler(gov):
    """Drift guard: the manifest and the handlers cannot disagree. The CLI maps
    `<tool>` to `_<tool>`, so a tool advertised without a handler is a dead entry
    an agent would call and fail on."""
    import asyncio
    result = asyncio.run(gov.list_tools(None))
    for t in result.tools:
        assert hasattr(gov, f"_{t.name}"), f"advertised but no handler: {t.name}"


def test_cli_refusal_exits_1_not_0():
    """A governance refusal must be visible to a script gating on the exit code.

    This shipped wrong: 'Error: Lock belongs to task X' exited 0, so an automation
    checking the code would conclude a locked repo was free.

    The exact wording depends on ambient lock state (a foreign lock → 'belongs to
    task', no lock at all → 'No governance session active'), so this asserts the
    CONTRACT rather than one phrasing: exit 1 AND `is_refusal()` reads the message
    as a refusal. Exit code and message must agree — a caller gating on either
    must reach the same conclusion. Specific phrasings are pinned hermetically in
    the test below.
    """
    r = cli("end_change", '{"task_id":"definitely-not-locked"}')
    assert r.returncode == 1, f"expected refusal exit 1, got {r.returncode}: {r.stdout[:200]}"
    mod = _load(CLI, "loop_gov_cli_under_test")
    assert mod.is_refusal({}, r.stdout) is True, \
        f"exit code says refused but the message reads as success: {r.stdout[:200]}"


def test_record_review_replace_actually_replaces(gov):
    """rereview_change's verdict must not be silently discarded.

    THE BUG: the gate recorded its judgement with replace=False. adversarial_reviews
    has cycle_id UNIQUE, and the non-replace path swallows IntegrityError as an
    idempotent no-op — so a re-review's verdict was thrown away and the original
    FINDINGS row stayed frozen. That is the exact gap rereview_change was written to
    close, and its docstring claimed it was closed.

    This fails on the old code: the second call is a no-op and the stored verdict
    stays FINDINGS.
    """
    cycle_id = 990001  # a cycle id no real run will use
    try:
        gov._record_review(cycle_id, "rev-1", "model-x", "FINDINGS", "[]", "first")
        first = gov._stored_review(cycle_id)
        assert first and first["verdict"] == "FINDINGS"

        gov._record_review(cycle_id, "rev-2", "model-x", "CLEAN", "[]", "second",
                           replace=True, fingerprint="fp-abc")
        after = gov._stored_review(cycle_id)
        assert after is not None, "no row after replace"
        assert after["verdict"] == "CLEAN", \
            f"replace did not take: verdict is still {after['verdict']}"
        assert after["fingerprint"] == "fp-abc", \
            f"fingerprint not stored: {after.get('fingerprint')!r}"
    finally:
        conn = gov._db()
        try:
            conn.execute("DELETE FROM adversarial_reviews WHERE cycle_id=?", (cycle_id,))
            conn.commit()
        finally:
            conn.close()


def test_replace_records_the_first_review_of_a_cycle(gov):
    """replace=True must also CREATE the row when the cycle has none yet.

    THE BUG: replace was implemented as a plain UPDATE, and the first review of a
    cycle has no row to update — so the verdict was silently never stored. It
    surfaced later as rereview_change answering "no recorded review" for a cycle the
    gate had just judged. The replace test above only exercises the
    update-an-existing-row path, so it passed while this was broken.
    """
    cycle_id = 990004
    try:
        assert gov._stored_review(cycle_id) is None, "probe cycle id is not clean"
        gov._record_review(cycle_id, "rev-first", "model-x", "CLEAN", "[]", "first",
                           replace=True, fingerprint="fp-first")
        row = gov._stored_review(cycle_id)
        assert row is not None, "first review with replace=True was not recorded"
        assert row["verdict"] == "CLEAN", row
        assert row["fingerprint"] == "fp-first", row
    finally:
        conn = gov._db()
        try:
            conn.execute("DELETE FROM adversarial_reviews WHERE cycle_id=?", (cycle_id,))
            conn.commit()
        finally:
            conn.close()


def test_review_fingerprint_pins_the_material(gov):
    """A CLEAN is only reusable for the exact material it judged."""
    a = gov._review_fingerprint("note\n\ndiff A")
    b = gov._review_fingerprint("note\n\ndiff B")
    assert a != b, "fingerprint does not change when the diff changes"
    assert a == gov._review_fingerprint("note\n\ndiff A"), "fingerprint is not stable"


def test_gate_accepts_force_but_the_repo_check_runs_first(gov):
    """A gate with no governed repo fails CLOSED before any reviewer call.

    Written as the honest version of a probe that was wrong: the first attempt
    asserted that force=True reaches the reviewer, and failed — because an empty
    lock has no repo_slug, so the gate refuses at the complexity check first. The
    short-circuit itself is verified end-to-end against a real cycle instead of
    through an artificial lock.
    """
    import inspect
    sig = inspect.signature(gov._adversarial_review_gate)
    assert "force" in sig.parameters, "the gate has no force parameter"
    assert sig.parameters["force"].default is False, \
        "force must default to False — only rereview_change may re-judge"

    block = gov._adversarial_review_gate({}, {"id": 990003, "outcome_note": "n"})
    text = block.model_dump()["content"][0]["text"]
    assert "no governed repo" in text, f"expected a fail-closed repo refusal, got: {text[:120]}"


def test_refusal_detector_covers_the_no_session_phrasing():
    """The SECOND wording of the same refusal class, pinned hermetically.

    The live CLI test above depends on ambient lock state, so it passed while a
    stale lock for another task happened to exist and failed once it was cleared.
    This asserts the contract directly, with no state at all:

      $ loop-gov end_change '{"task_id":"definitely-not-locked"}'
      No governance session active. Nothing to release.   → exit 0  ✗

    A caller gating on that exit code concludes the release succeeded. `is_refusal`
    enumerates phrasings, so every refusal the server can emit must be pinned here
    or the next new wording silently reads as success again.
    """
    mod = _load(CLI, "loop_gov_cli_under_test")
    assert mod.is_refusal({}, "No governance session active. Nothing to release.") is True, \
        "no-session refusal still reports success to a caller gating on exit codes"
    assert mod.is_refusal({}, "Error: Lock belongs to task 'x', not 'y'.") is True
    assert mod.is_refusal({"isError": True}, "") is True
    # ...and a genuine success must NOT be read as a refusal.
    assert mod.is_refusal({}, '{"active": false}') is False


def test_cli_usage_errors_are_distinct():
    assert cli("no_such_tool", "{}").returncode == 2
    assert cli("check_lock", "{not json").returncode == 2


def test_cli_stdout_is_machine_readable():
    """The server logs at DEBUG with force=True on import; the CLI must not let
    that noise onto stdout, or every consumer has to filter it."""
    r = cli("check_lock", "{}")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)          # stdout must parse as JSON, cleanly
    assert "active" in payload


# ── The re-review path (the friction fix) ───────────────────────

def test_rereview_is_advertised(gov):
    """Registered as a real tool, so the CLI exposes it with no CLI change."""
    import asyncio
    result = asyncio.run(gov.list_tools(None))
    names = {t.name for t in result.tools}
    assert "rereview_change" in names
    assert hasattr(gov, "_rereview_change")


def test_rereview_requires_a_note(gov):
    """A re-review without new material is the same request twice — refused, so
    the path cannot be used to re-roll a verdict instead of fixing a finding."""
    r = gov._rereview_change({"task_id": "whatever"})
    text = r.model_dump()["content"][0]["text"]
    assert "requires a NEW note" in text, text[:200]


def test_rereview_requires_a_task(gov):
    r = gov._rereview_change({})
    assert "requires task_id" in r.model_dump()["content"][0]["text"]


def test_record_review_can_replace_a_verdict(gov):
    """The frozen UNIQUE row is what made a FINDINGS verdict permanent. The
    replace path must exist, or a fixed change can never be re-judged."""
    import inspect
    sig = inspect.signature(gov._record_review)
    assert "replace" in sig.parameters, "no replace path — verdict stays frozen"
    assert sig.parameters["replace"].default is False, \
        "replace must be opt-in; normal reviews stay idempotent"


def test_rereview_cannot_bypass_the_reviewer(gov):
    """It must ask the reviewer again, never decide for itself: it has to go
    through the same gate, and it must not write a verdict row on its own."""
    src = inspect.getsource(gov._rereview_change)
    assert "_adversarial_review_gate" in src, \
        "re-review must re-run the same gate, not decide for itself"
    assert "_record_review(" not in src, \
        "re-review must let the gate record the verdict, not record one itself"


# ── The pi/CLI path must tag the lock with the CWD repo, not the host-canonical ──
#
# A pi / coding-agent session drives governance through `ops/scripts/loop-gov.py`,
# which calls the server handlers DIRECTLY — it never passes through the
# gateway's enforcer pre_tool_call hook, so `_inject_session_context` never
# stamps `repo_path`/`repo_slug` onto the call. `_derive_slug` then falls to
# Priority 1 (the host-canonical governed repo), which tags the lock
# `hermes-cortex` whenever `~/hermes-cortex` exists on the host — even though the
# session is working in a different repo (observed on Titus: a pi session in
# steadfaste-s1-model locked `hermes-cortex`, the close gate refused forever).
#
# The CLI KNOWS its cwd repo (it chdir's to `--repo` or runs in cwd), so it must
# stamp the payload the way the enforcer does. These tests pin that contract.

import os as _os  # noqa: E402
import tempfile as _tempfile  # noqa: E402


def _mkrepo(path: Path, with_commit: bool = True) -> Path:
    import time
    path.mkdir(parents=True, exist_ok=True)
    def git(*a, **kw):
        return subprocess.run(["git", "-C", str(path), *a],
                              capture_output=True, text=True, **kw)
    git("init", "-q")
    git("config", "user.email", "agent@hermes.local")
    git("config", "user.name", "agent")
    hooks = path / ".nohooks"
    hooks.mkdir(exist_ok=True)
    git("config", "core.hooksPath", str(hooks))
    if with_commit:
        (path / "work.txt").write_text("x\n")
        git("add", "work.txt")
        git("commit", "-q", "-m", "work")
    return path


def _stamp(cli_mod, payload: dict, cwd: Path) -> dict:
    """Run the CLI's repo-stamping helper (the function under test); return the
    (possibly unstamped) payload dict, matching the first tuple element."""
    return cli_mod._stamp_repo_into_payload(dict(payload), cwd)[0]


def _stamp_status(cli_mod, payload: dict, cwd: Path) -> str:
    """Return the stamp status string (stamped / no-repo / unexpected)."""
    return cli_mod._stamp_repo_into_payload(dict(payload), cwd)[1]


def test_cli_stamps_the_cwd_repo_not_the_host_canonical():
    """THE BUG (Titus cycle 5742): a CLI/pi begin_change in a non-canonical repo
    must tag the lock with that repo, not `hermes-cortex` (which exists on the
    host and won Priority 1 because the enforcer never injected the real repo).

    The helper must resolve the git root of the cwd and stamp BOTH `repo_path`
    (absolute) and `repo_slug` (name) — the same pair `_derive_slug` Priority 0
    and `_lock_repo` consume, so a nested checkout resolves correctly."""
    home = Path(_tempfile.mkdtemp(prefix="cli-stamp-home-"))
    canonical = _mkrepo(home / "hermes-cortex", with_commit=False)
    proj = _mkrepo(home / "repos" / "steadfaste-s1-model", with_commit=True)
    mod = _load(CLI, "loop_gov_cli_stamp")

    stamped = _stamp(mod, {"task_id": "t"}, proj)

    assert stamped.get("repo_path") == str(proj), (
        f"cwd repo path was not stamped: {stamped.get('repo_path')!r}")
    assert stamped.get("repo_slug") == "steadfaste-s1-model", (
        f"cwd repo slug was not stamped: {stamped.get('repo_slug')!r}")


def test_cli_stamp_does_not_override_an_injected_path():
    """If a caller already supplied repo identity (e.g. the enforcer on a gateway
    path, or an explicit --repo caller), the helper must not clobber it."""
    home = Path(_tempfile.mkdtemp(prefix="cli-stamp-override-"))
    proj = _mkrepo(home / "proj", with_commit=True)
    mod = _load(CLI, "loop_gov_cli_stamp2")

    payload = {"task_id": "t", "repo_path": str(proj), "repo_slug": "proj"}
    stamped = _stamp(mod, payload, Path("/"))

    assert stamped["repo_path"] == str(proj), "explicit repo_path was clobbered"
    assert stamped["repo_slug"] == "proj", "explicit repo_slug was clobbered"


def test_cli_stamp_is_a_noop_outside_a_git_repo():
    """No cwd repo → stamp nothing; let the server fall back to its own logic
    (single-repo hosts / a non-repo cwd). Never invent a path."""
    tmp = Path(_tempfile.mkdtemp(prefix="cli-stamp-norepo-"))
    mod = _load(CLI, "loop_gov_cli_stamp3")
    payload = {"task_id": "t"}
    stamped = _stamp(mod, payload, tmp)
    assert "repo_path" not in stamped, f"stamped a repo for a non-repo cwd: {stamped}"
    assert "repo_slug" not in stamped, f"stamped a slug for a non-repo cwd: {stamped}"


def test_cli_stamp_warns_when_git_is_an_unexpected_failure():
    """The finding ADV-4479-1: an unexpected operational failure (git missing /
    hung / unreadable) MUST fail closed (return \"unexpected\", never silently
    swallow) so begin_change cannot fall back to the host-canonical repo and
    recreate the exact wrong-repo lock this fix exists to prevent."""
    tmp = Path(_tempfile.mkdtemp(prefix="cli-stamp-warn-"))
    mod = _load(CLI, "loop_gov_cli_stamp_warn")
    import subprocess as _sp

    def _boom(*a, **kw):
        raise _sp.TimeoutExpired(cmd="git", timeout=5)
    orig = _sp.run
    _sp.run = _boom
    try:
        import contextlib
        import io
        errbuf = io.StringIO()
        with contextlib.redirect_stderr(errbuf):
            stamped, status = mod._stamp_repo_into_payload({"task_id": "t"}, tmp)
    finally:
        _sp.run = orig

    assert status == "unexpected", (
        f"unexpected git failure did not fail closed (status={status!r}); "
        f"begin_change would tag the host-canonical repo")
    assert "could not resolve the cwd repo" in errbuf.getvalue(), (
        f"no warning emitted for the unexpected failure: {errbuf.getvalue()!r}")
    assert "repo_path" not in stamped, (
        "a failed git probe must not fabricate a repo_path")


def test_cli_begin_change_fails_closed_when_repo_unresolvable(monkeypatch, capsys):
    """The ADV-4479-1 end-to-end shape: main() REFUSES begin_change (exit 1,
    not 3; a decision, not a crash) when the cwd repo cannot be resolved, so an
    unstamped payload can never reach _begin_change and tag the wrong repo."""
    mod = _load(CLI, "loop_gov_cli_failclosed")
    import subprocess as _sp
    import sys as _sys

    def _boom(*a, **kw):
        raise _sp.TimeoutExpired(cmd="git", timeout=5)
    monkeypatch.setattr(_sp, "run", _boom)
    tmp = str(Path(_tempfile.mkdtemp(prefix="cli-failclosed-")))
    monkeypatch.chdir(tmp)
    monkeypatch.setattr(
        _sys, "argv", ["loop-gov", "begin_change",
                       '{"task_id":"t","description":"d"}'])

    rc = mod.main()
    assert rc == 1, f"begin_change did not fail closed (rc={rc})"
    out = capsys.readouterr().out
    assert "fall back" in out, (
        f"refusal did not explain the fail-closed reason: {out[:200]}")
    assert "Cannot begin" in out, (
        f"refusal did not name begin_change: {out[:200]}")



def test_cli_begin_change_locks_the_cwd_repo_end_to_end():
    """End-to-end (maximally hermetic): a begin_change issued through the CLI
    from inside a non-canonical repo must resolve to that repo — the exact
    chain that was broken for Titus (cycle 5742).

    Chains the two functions the fix connects without a real DB or lock file:
    the CLI's `_stamp_repo_into_payload` stamps the cwd git root, and the
    server's `_derive_slug` (Priority 0, exactly what begin_change uses to tag
    the lock) honours the stamped `repo_path` over the host-canonical default.
    A decoy `~/hermes-cortex` repo is present to prove the canonical fallback
    does NOT win when the session works elsewhere.
    """
    home = Path(_tempfile.mkdtemp(prefix="cli-e2e-home-"))
    _mkrepo(home / "hermes-cortex", with_commit=False)   # decoy canonical repo
    proj = _mkrepo(home / "repos" / "steadfaste-s1-model", with_commit=True)
    cli_mod = _load(CLI, "loop_gov_cli_e2e")
    server = _load(SERVER, "loop_gov_e2e_server")
    server.HOME = home
    server._PROCESS_SESSION_ID = ""

    payload, status = cli_mod._stamp_repo_into_payload(
        {"task_id": "e2e-task", "description": "d"}, proj)
    assert status == "stamped", f"cwd repo did not stamp (status={status!r})"
    slug = server._derive_slug(payload)

    assert payload.get("repo_path") == str(proj), (
        f"CLI did not stamp the cwd repo path: {payload.get('repo_path')!r}")
    assert slug == "steadfaste-s1-model", (
        f"begin_change would lock {slug!r}, expected the cwd repo "
        f"(Titus cycle 5742); payload={payload}")



