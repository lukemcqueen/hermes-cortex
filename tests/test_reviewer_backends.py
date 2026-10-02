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


if __name__ == "__main__":
    print("Reviewer backends — pluggable transport, fixed fail-closed contract")
    test_backends()
    print()
    if _FAIL:
        print(f"{len(_FAIL)} FAILED: {', '.join(_FAIL)}")
        sys.exit(1)
    print("ALL PASS")
