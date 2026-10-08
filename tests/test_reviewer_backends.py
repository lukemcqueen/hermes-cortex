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


def _raises_typeerror(fn):
    """True if calling fn() raises exactly a TypeError."""
    try:
        fn()
        return False
    except TypeError:
        return True
    except Exception:
        return False


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
        "ADVERSARIAL_REVIEWER_MODEL", "CORTEX_ENV_FILE",
        "CORTEX_REPO", "CORTEX_DEPLOY_HOME")}
    try:
        for k in saved:
            os.environ.pop(k, None)
        # Isolate from the deployed cortex config: this host's ./cortex.env repo
        # .env sets ADVERSARIAL_REVIEW_BACKEND=agent, which would break the
        # "llm is the default backend" sentinel assertions below. Point every
        # cortex env source (CORTEX_ENV_FILE, the repo .env via CORTEX_REPO, and
        # the deploy home) at an EMPTY temp dir so the resolver finds nothing.
        with tempfile.TemporaryDirectory() as _td:
            os.environ["CORTEX_ENV_FILE"] = str(Path(_td) / "empty.env")
            os.environ["CORTEX_REPO"] = _td
            os.environ["CORTEX_DEPLOY_HOME"] = _td

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
        def fake_llm(prompt, *, model=None, timeout=None):
            calls["light_model"] = model
            calls["light_timeout"] = timeout
            return "{\"verdict\":\"CLEAN\",\"findings\":[]}"
        def fake_agent(prompt, author=None, timeout=None):
            calls["agent_ran"] = True
            calls["agent_timeout"] = timeout
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
            _check("light change carries an llm-scaled wait budget",
                   isinstance(calls.get("light_timeout"), int), str(calls))

            # HEAVY: the agent backend is still used.
            calls.clear()
            mcp._call_reviewer("M", author="esther@x",
                               cx={"lines": 220, "files": 1, "always_review": False})
            _check("heavy change still routes to the agent backend",
                   calls.get("agent_ran") is True and "light_model" not in calls, str(calls))
            _check("heavy change carries an agent-scaled wait budget",
                   isinstance(calls.get("agent_timeout"), int), str(calls))
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


def test_the_reviewer_is_the_canonical_model_on_every_path():
    """Luke, 2026-10-08: "make sure the reviewer is deepseek v4 pro".

    The light-but-complex tier is a TRANSPORT choice (a fast chat-completions call
    instead of spawning a coding agent), NOT a depth choice — so with nothing
    configured it must review with the SAME canonical model as every other path.
    It used to default to a hardcoded `deepseek/deepseek-v4-flash-0731`, which
    meant a light-but-complex change was silently judged by a different, cheaper
    model than the one the fleet documents: the stored row said so, but nothing
    had chosen it. An explicit ADVERSARIAL_REVIEW_LIGHT_MODEL still wins —
    reviewing with a different model is allowed, it just has to be CHOSEN.
    """
    import unittest.mock as mock
    mcp = _load()
    saved = {k: os.environ.get(k) for k in (
        "ADVERSARIAL_REVIEW_BACKEND", "ADVERSARIAL_REVIEW_AGENT_NAME",
        "ADVERSARIAL_REVIEW_LIGHT_MODEL", "ADVERSARIAL_REVIEWER_MODEL")}
    try:
        for k in saved:
            os.environ.pop(k, None)
        canonical = mcp.REVIEWER_MODEL_DEFAULT
        _check("the canonical reviewer model is deepseek-v4-pro",
               canonical == "deepseek/deepseek-v4-pro", canonical)

        # With nothing configured, every resolution path agrees.
        _check("_reviewer_model() is the canonical model",
               mcp._reviewer_model() == canonical, mcp._reviewer_model())
        _check("the light tier resolves to the canonical model, not a cheaper one",
               mcp._light_reviewer_model() == canonical, mcp._light_reviewer_model())
        _check("the recorded label is the canonical model",
               mcp._reviewer_label() == canonical, mcp._reviewer_label())
        _check("no hardcoded cheaper light-model constant remains",
               not hasattr(mcp, "REVIEWER_LIGHT_MODEL_DEFAULT"),
               "a hardcoded default is a model nobody chose")

        # The light tier on an AGENT host really reviews with the canonical model —
        # measured through the dispatch, not by reading the constant.
        os.environ["ADVERSARIAL_REVIEW_BACKEND"] = "agent"
        os.environ["ADVERSARIAL_REVIEW_AGENT_NAME"] = "pi"
        seen = {}

        def fake_llm(prompt, *, model=None, timeout=None):
            seen["model"] = model
            return '{"verdict":"CLEAN","findings":[]}'

        def fake_agent(prompt, author=None, timeout=None):
            seen["agent"] = True
            return '{"verdict":"CLEAN","findings":[]}'

        cx_light = {"lines": 60, "files": 2, "always_review": False}
        with mock.patch.object(mcp, "_call_reviewer_llm", side_effect=fake_llm), \
             mock.patch.object(mcp, "_call_reviewer_agent", side_effect=fake_agent):
            mcp._call_reviewer("M", author="esther@x", cx=cx_light)
        _check("a light change on an agent host reviews with the canonical model",
               seen.get("model") == canonical and "agent" not in seen, str(seen))
        _check("...and is RECORDED as the canonical model",
               mcp._reviewer_label(cx=cx_light) == canonical,
               mcp._reviewer_label(cx=cx_light))

        # An explicit choice still wins: different is allowed, not default.
        os.environ["ADVERSARIAL_REVIEW_LIGHT_MODEL"] = "chosen/other-model"
        _check("an explicitly chosen light model still wins",
               mcp._light_reviewer_model() == "chosen/other-model",
               mcp._light_reviewer_model())
        _check("...and does not leak into the deep path",
               mcp._reviewer_model() == canonical, mcp._reviewer_model())
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_reviewer_timeout():
    """_reviewer_timeout scales the wait budget INSIDE the client ceiling.

    A change with measured complexity (files + added/removed lines) gets a
    proportionally larger reviewer wait window than a flat-config call; a None cx
    keeps the configured default. The budget can NEVER exceed
    REVIEWER_TIMEOUT_CEILING: the MCP client gives up at 300s, so a longer budget
    is not a longer wait but an unobservable hang. It used to have a cap of its
    own (REVIEWER_TIMEOUT_CAP = 1800), which silently overrode the ceiling —
    that is the regression this asserts against (2026-10-08)."""
    mcp = _load()
    saved = {k: os.environ.get(k) for k in
             ("ADVERSARIAL_REVIEW_TIMEOUT", "ADVERSARIAL_REVIEW_AGENT_TIMEOUT")}
    try:
        for k in saved:
            os.environ.pop(k, None)

        ceil = mcp.REVIEWER_TIMEOUT_CEILING
        # No cx -> the configured default, CLAMPED. The shipped defaults (300 llm /
        # 900 agent) are both at or above the ceiling, so both land ON it.
        _check("no cx: llm wait is clamped to the ceiling",
               mcp._reviewer_timeout(None, "llm") == ceil,
               mcp._reviewer_timeout(None, "llm"))
        _check("no cx: agent wait is clamped to the ceiling",
               mcp._reviewer_timeout(None, "agent") == ceil,
               mcp._reviewer_timeout(None, "agent"))

        # Growth redistributes time INSIDE the observable window. A default base is
        # already at the ceiling, so there is no room; it applies to a base an
        # operator configures BELOW the ceiling.
        os.environ["ADVERSARIAL_REVIEW_TIMEOUT"] = "60"
        small = {"lines": 60, "files": 2, "always_review": False}
        llm_wait = mcp._reviewer_timeout(small, "llm")
        _check("below the ceiling, a change grows the wait above its base",
               llm_wait > 60, llm_wait)
        _check("small change stays inside the window", llm_wait <= ceil, llm_wait)

        # Larger change: grows MORE than the small one (22 files, 240 lines).
        big = {"lines": 240, "files": 22, "always_review": False}
        _check("bigger change gets a longer wait than a small one",
               mcp._reviewer_timeout(big, "llm") > llm_wait,
               f"{mcp._reviewer_timeout(big, 'llm')} vs {llm_wait}")

        # Growth is per-100-lines: 95 lines adds nothing, 105 adds one step.
        base_0 = mcp._reviewer_timeout({"lines": 0, "files": 0, "always_review": False}, "llm")
        under_100 = mcp._reviewer_timeout({"lines": 95, "files": 0, "always_review": False}, "llm")
        over_100 = mcp._reviewer_timeout({"lines": 105, "files": 0, "always_review": False}, "llm")
        _check("per-100-lines growth: 95 lines is same as 0 lines",
               under_100 == base_0, f"{under_100} vs {base_0}")
        _check("per-100-lines growth: 105 lines adds one step",
               over_100 == base_0 + mcp.REVIEWER_TIMEOUT_PER_100_LINES,
               f"{over_100} vs {base_0 + mcp.REVIEWER_TIMEOUT_PER_100_LINES}")

        # THE CEILING IS ABSOLUTE: neither change size nor an operator override can
        # drive the budget past it. There must be no second, larger cap to bypass it.
        huge = {"lines": 500000, "files": 99999, "always_review": False}
        _check("huge change is hard-capped at the ceiling",
               mcp._reviewer_timeout(huge, "llm") == ceil,
               mcp._reviewer_timeout(huge, "llm"))
        _check("no REVIEWER_TIMEOUT_CAP exists to override the ceiling",
               not hasattr(mcp, "REVIEWER_TIMEOUT_CAP"),
               "a second, larger cap is exactly how the ceiling was bypassed")
        for val in ("900", "100000"):
            os.environ["ADVERSARIAL_REVIEW_AGENT_TIMEOUT"] = val
            got = mcp._reviewer_timeout(huge, "agent")
            _check(f"oversized agent override {val}s is clamped to the ceiling",
                   got == ceil, got)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_reviewer_leaf_callers_accept_passed_timeout():
    """The leaf reviewers are callable with a size-scaled timeout and their
    env fallback never passes a string where _reviewer_timeout wants a dict.

    Regression for the 2026-10-07 end_change blocker: two _reviewer_timeout
    defs (env-clamp vs size-scaled) collided — renamed the env-clamp one to
    _reviewer_env_timeout and made _call_reviewer_llm/_agent honor their
    'timeout' arg instead of always re-resolving. Before the fix,
    _call_reviewer_llm called _reviewer_timeout(\"ADVERSARIAL...\", 300) which
    bound the STRING to 'cx' -> \"'str' object has no attribute 'get'\" on
    every non-trivial end_change.

    Hermetic: mocks _reviewer_api_key, the HTTP transport, subprocess.run, and
    sets ADVERSARIAL_REVIEW_AGENT_CMD (which _call_reviewer_agent validates
    before reaching subprocess.run).
    """
    import unittest.mock as mock
    mcp = _load()
    saved = {k: os.environ.get(k) for k in
             ("ADVERSARIAL_REVIEW_TIMEOUT", "ADVERSARIAL_REVIEW_AGENT_TIMEOUT",
              "ADVERSARIAL_REVIEW_AGENT_CMD")}
    try:
        for k in ("ADVERSARIAL_REVIEW_TIMEOUT", "ADVERSARIAL_REVIEW_AGENT_TIMEOUT"):
            os.environ.pop(k, None)
        # _call_reviewer_agent refuses (RuntimeError) if AGENT_CMD is unset BEFORE
        # reaching the mocked subprocess.run, so set a stub to keep it hermetic.
        os.environ["ADVERSARIAL_REVIEW_AGENT_CMD"] = "stub-agent-cmd"

        # The two helpers are distinct names (no shadowing).
        _check("env-clamp helper exists under its own name",
               hasattr(mcp, "_reviewer_env_timeout"), "missing _reviewer_env_timeout")
        _check("size-scaled helper kept its name",
               hasattr(mcp, "_reviewer_timeout"), "missing _reviewer_timeout")

        # _call_reviewer_llm honors a passed scoped timeout (mock the HTTP call).
        llm_calls = {}

        def fake_urlopen(req, timeout):  # noqa: D103
            llm_calls["timeout"] = timeout

            class _R:
                def read(self):  # noqa: D103
                    return b'{"choices":[{"message":{"content":"{}"}}]}'
                def __enter__(self):  # noqa: D105
                    return self
                def __exit__(self, *exc):  # noqa: D105
                    return False
            return _R()

        key_patch = mock.patch.object(mcp, "_reviewer_api_key", return_value="dummy-key")
        urlopen_patch = mock.patch.object(mcp.urllib.request, "urlopen", side_effect=fake_urlopen)
        with key_patch, urlopen_patch:
            # Pass an explicit scoped timeout; it must be honored, not clobbered.
            mcp._call_reviewer_llm("review", timeout=1234)
        _check("passed llm timeout is honored", llm_calls.get("timeout") == 1234,
               f"got {llm_calls.get('timeout')}")

        # Env fallback path also works and never crashes (no string->cx).
        llm_calls.clear()
        with key_patch, mock.patch.object(mcp.urllib.request, "urlopen", side_effect=fake_urlopen):
            mcp._call_reviewer_llm("review", model="m")
        _check("llm env-fallback callable without a string crash",
               isinstance(llm_calls.get("timeout"), int), f"got {llm_calls.get('timeout')}")

        # Agent path: honors a passed scoped timeout (mock subprocess).
        agent_calls = {}

        def fake_run(*args, **kwargs):  # noqa: D103
            agent_calls["timeout"] = kwargs.get("timeout")
            return mock.Mock(returncode=0, stdout='{"verdict":"CLEAN"}', stderr="")

        with key_patch, mock.patch.object(mcp.subprocess, "run", side_effect=fake_run):
            mcp._call_reviewer_agent("review", author="someone-else", timeout=4321)
        _check("passed agent timeout is honored", agent_calls.get("timeout") == 4321,
               f"got {agent_calls.get('timeout')}")

        # Agent env fallback: no string->cx crash.
        agent_calls.clear()
        with key_patch, mock.patch.object(mcp.subprocess, "run", side_effect=fake_run):
            mcp._call_reviewer_agent("review", author="someone-else")
        _check("agent env-fallback callable without a string crash",
               isinstance(agent_calls.get("timeout"), int), f"got {agent_calls.get('timeout')}")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_reviewer_timeout_signature_contract():
    """The root-cause contract: the size-scaled _reviewer_timeout must never
    receive a str in place of its cx dict, and the env-clamp is a DISTINCT
    function (renamed _reviewer_env_timeout).

    Direct regression for the 2026-10-07 end_change blocker. Before the fix,
    two functions shared the name _reviewer_timeout (env-clamp at 1921 and
    size-scaled at 2355); Python bound the LAST def, so leaf callers that
    passed a STRING first arg (e.g. _call_reviewer_llm ->
    _reviewer_timeout(\"ADVERSARIAL_REVIEW_TIMEOUT\", 300)) bound the string to
    'cx' -> cx.get(\"files\") -> \"'str' object has no attribute 'get'\".
    """
    mcp = _load()
    _check("size-scaled _reviewer_timeout exists (takes cx, backend)",
           callable(getattr(mcp, "_reviewer_timeout", None)), "missing _reviewer_timeout")
    _check("env-clamp helper is a DISTINCT name, not a shadow",
           callable(getattr(mcp, "_reviewer_env_timeout", None)), "missing _reviewer_env_timeout")
    _check("the two timeout helpers are different functions",
           getattr(mcp, "_reviewer_timeout") is not getattr(mcp, "_reviewer_env_timeout"),
           "same object — collision not resolved")

    # A cx that is a str must be rejected with a clear TypeError (fail-fast),
    # NOT crash as the old silent AttributeError did. This is the exact
    # 2026-10-07 crash: a str bound to cx flowed into cx.get(\"files\") as
    # \"'str' object has no attribute 'get'\". Callers pass a dict from
    # _complexity; a str is programmer error and must fail loudly.
    saved = {k: os.environ.get(k) for k in
             ("ADVERSARIAL_REVIEW_TIMEOUT", "ADVERSARIAL_REVIEW_AGENT_TIMEOUT")}
    try:
        for k in saved:
            os.environ.pop(k, None)
        # A valid dict cx still scales (regression-guard the happy path).
        small = {"lines": 60, "files": 2, "always_review": False}
        _check("size-scaled helper accepts a dict cx",
               isinstance(mcp._reviewer_timeout(small, "llm"), int),
               mcp._reviewer_timeout(small, "llm"))
        # A str cx is rejected loudly (TypeError), not silently crashed.
        _check("str cx raises TypeError (fail-fast, not hidden AttributeError)",
               _raises_typeerror(lambda: mcp._reviewer_timeout("ADVERSARIAL_REVIEW_TIMEOUT", 300)),
               "expected TypeError for str cx")
        # None cx keeps the configured default (no scaling) — resolved through the
        # ceiling clamp, so the shipped 300s llm default lands ON the 240s ceiling.
        _check("None cx returns the configured default, clamped to the ceiling",
               mcp._reviewer_timeout(None, "llm") == mcp.REVIEWER_TIMEOUT_CEILING,
               mcp._reviewer_timeout(None, "llm"))
        _check("None cx is NOT scaled: it equals the clamped default exactly",
               mcp._reviewer_timeout(None, "llm")
               == mcp._reviewer_env_timeout("ADVERSARIAL_REVIEW_TIMEOUT", 300),
               mcp._reviewer_timeout(None, "llm"))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_tiering_dogfood_script():
    """The standalone dogfood script (ops/scripts/manage/dogfood-reviewer-tiering.py)
    runs the REAL loop-gov-mcp.py module and prints PASS for the tier decision
    matrix and light/heavy/always-review routing. Run it via subprocess so its
    output is machine-verifiable and a regression that breaks routing fails."""
    import subprocess
    dogfood = REPO / "ops" / "scripts" / "manage" / "dogfood-reviewer-tiering.py"
    _check("dogfood script exists", dogfood.exists(), str(dogfood))
    if not dogfood.exists():
        return
    r = subprocess.run([sys.executable, str(dogfood)], capture_output=True, text=True, timeout=60)
    out = r.stdout + r.stderr
    _check("dogfood script exits 0", r.returncode == 0, f"exit={r.returncode}")
    _check("dogfood reports ALL PASS", "ALL PASS" in out, out[-300:])


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
    print("Reviewer model — one canonical model on every path (light tier is a transport choice)")
    test_the_reviewer_is_the_canonical_model_on_every_path()
    print()
    print("Reviewer wait-budget scaling — by change size, hard-capped")
    test_reviewer_timeout()
    print()
    print("Reviewer leaf callers — passed-timeout honored, env fallback no string crash")
    test_reviewer_leaf_callers_accept_passed_timeout()
    print()
    print("Reviewer timeout signature contract — cx is a dict, env-clamp is distinct")
    test_reviewer_timeout_signature_contract()
    print()
    print("Reviewer tiering dogfood script — real module routing")
    test_tiering_dogfood_script()
    print()
    if _FAIL:
        print(f"{len(_FAIL)} FAILED: {', '.join(_FAIL)}")
        sys.exit(1)
    print("ALL PASS")
