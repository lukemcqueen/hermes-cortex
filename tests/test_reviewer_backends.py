#!/usr/bin/env python3
"""Reviewer-backend tests: the adversarial verifier's transport is pluggable,
its contract is not.

What this pins down:
  - the llm backend stays the default and still fails closed with no credential
  - the agent backend runs a CONFIGURED command (never an invented per-CLI table),
    passes the prompt on stdin, and returns the agent's stdout
  - every failure mode REFUSES the close rather than silently passing it:
    no command, non-zero exit, empty output, unknown backend
  - SELF-REVIEW is refused when the review agent is the change's author
  - the recorded reviewer label says which backend actually ran

Hermetic: a fake agent CLI in TMPDIR, no network, no credentials.

Run: python3 tests/test_reviewer_backends.py
"""
import importlib.util
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_FAIL = []


def _check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        _FAIL.append(label)


def _load():
    spec = importlib.util.spec_from_file_location("loop_gov_mcp", REPO / "mcp-servers" / "loop-gov-mcp.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load loop-gov-mcp.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_agent(tmp: Path, name: str, body: str) -> str:
    p = tmp / name
    p.write_text("#!/usr/bin/env python3\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return f"{sys.executable} {p}"


def _raises(fn, *a, **kw) -> str:
    """Return the error text if fn raised, else ''."""
    try:
        fn(*a, **kw)
        return ""
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def test_backends():
    mcp = _load()
    saved = {k: os.environ.get(k) for k in (
        "ADVERSARIAL_REVIEW_BACKEND", "ADVERSARIAL_REVIEW_AGENT_CMD",
        "ADVERSARIAL_REVIEW_AGENT_NAME", "ADVERSARIAL_REVIEW_API_KEY_ENV",
        "ADVERSARIAL_REVIEWER_MODEL")}
    try:
        for k in saved:
            os.environ.pop(k, None)

        _check("default backend is llm", mcp._reviewer_backend() == "llm")
        _check("llm records the MODEL as the reviewer",
               mcp._reviewer_label() == mcp.REVIEWER_MODEL_DEFAULT, mcp._reviewer_label())

        # llm backend with no credential must REFUSE (fail-closed), not pass
        os.environ["ADVERSARIAL_REVIEW_API_KEY_ENV"] = "DEFINITELY_NOT_SET_XYZ"
        err = _raises(mcp._call_reviewer, "prompt")
        _check("llm backend with no credential raises (close is refused, not skipped)",
               "not set" in err, err)

        # unknown backend: never guess a reviewer
        os.environ["ADVERSARIAL_REVIEW_BACKEND"] = "telepathy"
        err = _raises(mcp._call_reviewer, "prompt")
        _check("unknown backend is refused, not guessed", "unknown" in err.lower(), err)

        # agent backend with no command
        os.environ["ADVERSARIAL_REVIEW_BACKEND"] = "agent"
        err = _raises(mcp._call_reviewer, "prompt")
        _check("agent backend without a command is refused",
               "AGENT_CMD" in err, err)

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)

            # a configured command that returns findings
            os.environ["ADVERSARIAL_REVIEW_AGENT_CMD"] = _fake_agent(
                tmp, "good.py",
                'import json,sys\n'
                'p=sys.stdin.read()\n'
                'print(json.dumps({"verdict":"CLEAN","findings":[],"saw_prompt":len(p)>0}))\n')
            os.environ["ADVERSARIAL_REVIEW_AGENT_NAME"] = "claude-code"
            out = mcp._call_reviewer("REVIEW MATERIAL", author="esther-agent <esther@x>")
            _check("agent backend returns the agent's stdout",
                   json.loads(out).get("saw_prompt") is True, out[:120])
            _check("agent backend records agent:<name> as the reviewer",
                   mcp._reviewer_label() == "agent:claude-code", mcp._reviewer_label())

            # SELF-REVIEW: the agent IS the change's author (case-insensitive)
            err = _raises(mcp._call_reviewer, "REVIEW MATERIAL",
                          author="Claude-Code Agent <cc@example.com>")
            _check("SELF-REVIEW is refused (agent name matches the change's author)",
                   "SELF-REVIEW" in err, err)

            # non-zero exit
            os.environ["ADVERSARIAL_REVIEW_AGENT_CMD"] = _fake_agent(
                tmp, "boom.py", 'import sys\nsys.stderr.write("agent exploded")\nsys.exit(3)\n')
            os.environ["ADVERSARIAL_REVIEW_AGENT_NAME"] = "codex"
            err = _raises(mcp._call_reviewer, "MATERIAL", author="esther-agent <esther@x>")
            _check("agent non-zero exit refuses the close", "exited 3" in err, err)

            # silence must not read as CLEAN
            os.environ["ADVERSARIAL_REVIEW_AGENT_CMD"] = _fake_agent(tmp, "quiet.py", "pass\n")
            os.environ["ADVERSARIAL_REVIEW_AGENT_NAME"] = "opencode"
            err = _raises(mcp._call_reviewer, "MATERIAL", author="esther-agent <esther@x>")
            _check("agent silence is refused (silence is never CLEAN)", "no output" in err, err)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_env_resolution():
    """Config resolution is DECOUPLED from Hermes: process env, then the canonical
    cortex env, and ~/.hermes/.env only as a last resort — read per call."""
    mcp = _load()
    saved = {k: os.environ.get(k) for k in
             ("CORTEX_ENV_FILE", "GOV_TEST_KEY", "GOV_TEST_KEY2", "ADVERSARIAL_TRIAGE_MODEL", "CORTEX_REPO")}
    try:
        # The shell that runs this test may already export the enable switch (it
        # does on this host), and the PROCESS env is legitimately consulted first —
        # so clear it, otherwise this tests the shell, not the resolution order.
        os.environ.pop("ADVERSARIAL_TRIAGE_MODEL", None)
        os.environ.pop("GOV_TEST_KEY", None)
        os.environ.pop("GOV_TEST_KEY2", None)
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "cortex.env"
            f.write_text('GOV_TEST_KEY="from-cortex-file"\nADVERSARIAL_TRIAGE_MODEL=from-cortex-file\n')

            os.environ["CORTEX_ENV_FILE"] = str(f)

            _check("value is read from the canonical cortex env",
                   mcp._env_value("GOV_TEST_KEY") == "from-cortex-file",
                   mcp._env_value("GOV_TEST_KEY"))
            _check("quotes are stripped",
                   mcp._env_value("GOV_TEST_KEY") == "from-cortex-file")

            # the canonical cortex env BEATS the Hermes file for the same name
            # (the repo .env sets this to 'jev'; CORTEX_ENV_FILE must win)
            _check("the cortex file WINS over ~/.hermes/.env, not the reverse",
                   mcp._env_value("ADVERSARIAL_TRIAGE_MODEL") == "from-cortex-file",
                   mcp._env_value("ADVERSARIAL_TRIAGE_MODEL"))

            os.environ["GOV_TEST_KEY"] = "from-process"
            _check("the PROCESS env wins over any file",
                   mcp._env_value("GOV_TEST_KEY") == "from-process",
                   mcp._env_value("GOV_TEST_KEY"))

            _check("a missing name returns the default, not an exception",
                   mcp._env_value("DEFINITELY_ABSENT_XYZ", "fallback") == "fallback")

            # read per call: a later edit to the file is visible with no restart.
            # Uses a name that is NOT in the process env, else the process wins and
            # this measures nothing.
            f.write_text("GOV_TEST_KEY2=first\n")
            first = mcp._env_value("GOV_TEST_KEY2")
            f.write_text("GOV_TEST_KEY2=changed-later\n")
            _check("files are re-read per call (a long-lived server is not frozen)",
                   first == "first" and mcp._env_value("GOV_TEST_KEY2") == "changed-later",
                   f"first={first!r} second={mcp._env_value('GOV_TEST_KEY2')!r}")

            # decoupling: the Hermes path is LAST, never first
            paths = [str(p) for p in mcp._env_file_paths()]
            _check("the Hermes env is consulted LAST, not first",
                   paths and paths[-1].endswith("/.hermes/.env")
                   and not paths[0].endswith("/.hermes/.env"), str(paths))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_tiering():
    """The complexity gate is tiered: light-but-complex changes get the FAST
    chat-completions reviewer even on an `agent`-backend host; heavy changes
    (always-review surface or a diff far above the gate) keep the deep backend.
    Every branch still goes through a reviewer — enforcement is unchanged."""
    import unittest.mock as mock
    mcp = _load()
    saved = {k: os.environ.get(k) for k in (
        "ADVERSARIAL_REVIEW_BACKEND", "ADVERSARIAL_REVIEW_AGENT_CMD",
        "ADVERSARIAL_REVIEW_AGENT_NAME", "ADVERSARIAL_REVIEW_API_KEY_ENV",
        "ADVERSARIAL_REVIEW_LIGHT_MODEL", "ADVERSARIAL_REVIEWER_MODEL")}
    try:
        for k in saved:
            os.environ.pop(k, None)

        # _tier() decision matrix — reuse the measured _complexity() shape.
        _check("plain complex change is light",
               mcp._tier({"lines": 60, "files": 2, "always_review": False}) == "light")
        _check("always-review surface is heavy",
               mcp._tier({"lines": 1, "files": 1, "always_review": True}) == "heavy")
        _check(">=10 files is heavy",
               mcp._tier({"lines": 0, "files": 10, "always_review": False}) == "heavy")
        _check(">=200 lines is heavy",
               mcp._tier({"lines": 200, "files": 1, "always_review": False}) == "heavy")
        _check("below heavy bars stays light",
               mcp._tier({"lines": 199, "files": 9, "always_review": False}) == "light")

        # ROUTING on an agent-backend host: light -> fast llm reviewer; heavy ->
        # the configured agent. Assert via mock so no network/credential is needed.
        os.environ["ADVERSARIAL_REVIEW_BACKEND"] = "agent"
        os.environ["ADVERSARIAL_REVIEW_LIGHT_MODEL"] = "light/fast-model"
        os.environ["ADVERSARIAL_REVIEW_AGENT_NAME"] = "pi"

        # LIGHT: the llm backend is invoked with the FAST model; the agent never runs.
        calls = {}
        def fake_llm(prompt, *, model=None):
            calls["light_model"] = model
            return "{\"verdict\":\"CLEAN\",\"findings\":[]}"
        def fake_agent(prompt, author=None):
            calls["agent_ran"] = True
            return "{\"verdict\":\"CLEAN\",\"findings\":[]}"
        with mock.patch.object(mcp, "_call_reviewer_llm", side_effect=fake_llm), \
             mock.patch.object(mcp, "_call_reviewer_agent", side_effect=fake_agent):
            mcp._call_reviewer("M", author="esther@x",
                               cx={"lines": 60, "files": 2, "always_review": False})
            _check("light change routes to the FAST llm reviewer on an agent host",
                   calls.get("light_model") == "light/fast-model"
                   and "agent_ran" not in calls, str(calls))
            _check("light reviewer is recorded as the fast model",
                   mcp._reviewer_label(cx={"lines": 60, "files": 2, "always_review": False}) == "light/fast-model",
                   mcp._reviewer_label({"lines": 60, "files": 2, "always_review": False}))

            # HEAVY: the agent backend is still used.
            calls.clear()
            mcp._call_reviewer("M", author="esther@x",
                               cx={"lines": 220, "files": 1, "always_review": False})
            _check("heavy change still routes to the agent backend",
                   calls.get("agent_ran") is True and "light_model" not in calls, str(calls))
            _check("heavy reviewer label records the agent",
                   mcp._reviewer_label(cx={"lines": 220, "files": 1, "always_review": False}) == "agent:pi",
                   mcp._reviewer_label({"lines": 220, "files": 1, "always_review": False}))

            # cx=None (caller did not measure): agent backend used as configured.
            calls.clear()
            mcp._call_reviewer("M", author="esther@x")
            _check("no cx: configured agent backend used unchanged",
                   calls.get("agent_ran") is True, str(calls))
            _check("no cx: reviewer label is the agent, not a guest light model",
                   mcp._reviewer_label() == "agent:pi", mcp._reviewer_label())
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


if __name__ == "__main__":
    print("Reviewer backends — pluggable transport, fixed fail-closed contract")
    test_backends()
    print()
    print("Config resolution — decoupled from Hermes")
    test_env_resolution()
    print()
    print("Reviewer tiering — depth by measured complexity, enforcement unchanged")
    test_tiering()
    print()
    if _FAIL:
        print(f"{len(_FAIL)} FAILED: {', '.join(_FAIL)}")
        sys.exit(1)
    print("ALL PASS")
