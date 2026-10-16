#!/usr/bin/env python3
"""The reviewer call must be BOUNDED — in thinking budget and in wall clock.

Two measured defects, one file:

1. `max_tokens` pays for reasoning AND the answer together on most providers, so
   an unbounded judge spends the whole budget thinking and answers with empty
   content (`finish_reason=length`). Measured on an 8-file/381-line range at
   `max_tokens=48000` AND again at `96000` — i.e. a bigger cap buys more thinking,
   not an answer. The request must therefore carry an explicit reasoning budget,
   and the failure must report the measurement (`reasoning_tokens`).

2. `urllib`'s `timeout` bounds a single socket operation, so a response that
   arrives slowly outlives it: measured 15 and 26 MINUTES in flight against a
   240s clamp, with the MCP client giving up at 300s — the lock stayed held, no
   receipt was written, and an always-review push was refused with nothing to
   blame. The call must carry a HARD deadline.

Both are proven against a local, in-process transport — no network, no provider.

Run:  python3 tests/test_reviewer_budget.py
   or: pytest tests/test_reviewer_budget.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Discrimination seam: point it at a pre-change module and this file MUST fail —
# that revision sends no reasoning budget and enforces only the socket timeout.
SERVER = Path(os.environ.get("CORTEX_LOOP_GOV_SERVER", REPO / "mcp-servers" / "loop-gov-mcp.py"))
BASE_URL_ENV = "ADVERSARIAL_REVIEW_BASE_URL"


def _load_server(tmp: Path):
    spec = importlib.util.spec_from_file_location("loop_gov_budget_under_test", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.LOOP_DB = tmp / "loop-governance.db"
    mod.GOVERNANCE_STATE_DIR = tmp / "state"
    os.environ["OPENROUTER_API_KEY"] = "test-key-not-a-secret"
    os.environ.pop("REVIEWER_REASONING_EFFORT", None)
    return mod


class _FakeUrllib:
    """A PER-MODULE urllib stand-in.

    Patching the real ``urllib.request.urlopen`` replaces the transport for every
    later user of it in the process — measured: the deadline case then "passed"
    against a stub instead of a socket. So the loaded module's own reference is
    swapped, and the shared module is never touched.
    """

    def __init__(self, urlopen):
        # The module builds its request with urllib.request.Request and then calls
        # urlopen, so the shim must expose BOTH — a partial shim fails for the wrong
        # reason and reads as a defect in the code under test.
        self.request = types.SimpleNamespace(
            urlopen=urlopen, Request=urllib.request.Request)
        self.error = urllib.error


class _Resp:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _stub_urlopen(payload: dict, captured: dict):
    def _open(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        captured["timeout"] = timeout
        return _Resp(payload)
    return _open


def test_the_request_carries_a_bounded_reasoning_budget(tmp_path):
    mod = _load_server(tmp_path)
    captured: dict = {}
    mod.urllib = _FakeUrllib(_stub_urlopen(
        {"choices": [{"message": {"content": '{"verdict":"CLEAN","findings":[]}'},
                      "finish_reason": "stop"}],
         "usage": {"completion_tokens": 10}}, captured))
    out = mod._call_reviewer_llm("judge this", timeout=5)
    assert "CLEAN" in out, out
    body = captured["body"]
    assert "reasoning" in body, (
        "the request must bound the THINKING budget: max_tokens alone lets a "
        f"reasoning model spend the whole reply thinking: {body}"
    )
    effort = (body.get("reasoning") or {}).get("effort")
    assert effort in mod.REVIEWER_REASONING_EFFORTS, (
        f"reasoning.effort must come from the provider's own vocabulary: {effort!r}"
    )
    assert body.get("max_tokens") == mod._reviewer_max_tokens(), body


def test_an_invalid_effort_falls_back_rather_than_becoming_a_400(tmp_path):
    mod = _load_server(tmp_path)
    os.environ["REVIEWER_REASONING_EFFORT"] = "extremely-hard-please"
    try:
        captured: dict = {}
        mod.urllib = _FakeUrllib(_stub_urlopen(
            {"choices": [{"message": {"content": '{"verdict":"CLEAN","findings":[]}'},
                          "finish_reason": "stop"}], "usage": {}}, captured))
        mod._call_reviewer_llm("judge this", timeout=5)
        assert captured["body"]["reasoning"]["effort"] == \
            mod.REVIEWER_REASONING_EFFORT_DEFAULT, (
                "an unknown effort must fall back to the default (a 400 at review time "
                f"reads exactly like a reviewer outage): {captured['body']}"
            )
    finally:
        os.environ.pop("REVIEWER_REASONING_EFFORT", None)


def test_the_floor_reports_the_measurement_not_a_remedy_already_tried(tmp_path):
    mod = _load_server(tmp_path)
    mod.urllib = _FakeUrllib(_stub_urlopen(
        {"choices": [{"message": {"content": None}, "finish_reason": "length"}],
         "usage": {"completion_tokens": 96000,
                   "completion_tokens_details": {"reasoning_tokens": 95990}}}, {}))
    try:
        mod._call_reviewer_llm("judge this", timeout=5)
        raise AssertionError("a null content reply must RAISE, never return")
    except RuntimeError as exc:
        msg = str(exc)
    assert "reasoning_tokens=95990" in msg, (
        f"the failure must carry the measurement that explains it: {msg}"
    )
    assert "finish_reason=length" in msg, msg


def _stalled_server() -> tuple[socket.socket, str]:
    """A peer that TRICKLES a response forever — the measured production failure.

    Not merely a peer that accepts and says nothing: that case the socket timeout
    already bounds (measured — the pre-change revision passes it). The real hang
    ran 15 and 26 minutes against a 240s clamp, which only happens when bytes keep
    arriving and every read RESETS the socket timer. So this peer sends a chunk
    every 0.4s and never finishes, and ONLY a hard wall-clock deadline can abort it.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)

    def _trickle(conn: socket.socket) -> None:
        try:
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                         b"Transfer-Encoding: chunked\r\n\r\n")
            # Bounded: a peer that trickled forever would hang a revision with no hard
            # deadline (the baseline) and take this suite with it. Stopping after 20s
            # lets that revision fall back to the socket timeout, so it reports a LATE
            # abort — a failure — instead of hanging.
            stop = time.monotonic() + 20
            while time.monotonic() < stop:
                conn.sendall(b"1\r\n \r\n")     # a byte every beat: reads keep succeeding
                time.sleep(0.4)
        except OSError:
            return

    def _accept_forever() -> None:
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=_trickle, args=(conn,), daemon=True).start()

    threading.Thread(target=_accept_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.getsockname()[1]}/v1"


def test_the_call_has_a_hard_wall_clock_deadline(tmp_path):
    mod = _load_server(tmp_path)
    srv, base = _stalled_server()
    os.environ[BASE_URL_ENV] = base
    # Called in the MAIN thread on purpose: SIGALRM (the mechanism) only fires there,
    # so running it off-thread would test the disclosed fallback instead of the fix.
    started = time.monotonic()
    err = ""
    try:
        mod._call_reviewer_llm("judge this", timeout=3)
        err = "returned normally"
    except BaseException as exc:  # noqa: BLE001 — the assertion is about WHICH
        err = f"{type(exc).__name__}: {exc}"
    elapsed = time.monotonic() - started
    try:
        assert "TimeoutError" in err, f"expected the hard deadline to abort: {err}"
        assert elapsed < 15, (
            "the deadline must fire PROMPTLY against a trickling peer — without a hard "
            f"deadline the socket timeout never fires (took {elapsed:.1f}s)"
        )
    finally:
        os.environ.pop(BASE_URL_ENV, None)
        srv.close()


def test_the_ceiling_follows_the_caller_not_the_reviewer(tmp_path):
    """Verifies the wait ceiling is resolved per CALLER: 240s with no marker, the CLI
    ceiling when CORTEX_LOOP_GOV_CLIENT=cli, and that an env override clamps to whichever
    caller's ceiling applies.
    """
    mod = _load_server(tmp_path)
    os.environ.pop(mod.CLIENT_MARKER_ENV, None)
    try:
        assert mod._reviewer_timeout_ceiling() == mod.REVIEWER_TIMEOUT_CEILING, (
            "without the marker the budget must stay under the 300s MCP client: "
            f"{mod._reviewer_timeout_ceiling()}"
        )
        os.environ[mod.CLIENT_MARKER_ENV] = "cli"
        assert mod._reviewer_timeout_ceiling() == mod.REVIEWER_TIMEOUT_CEILING_CLI, (
            "the CLI adapter waits on the process and must get its own ceiling: "
            f"{mod._reviewer_timeout_ceiling()}"
        )
        assert mod.REVIEWER_TIMEOUT_CEILING_CLI > mod.REVIEWER_TIMEOUT_CEILING, (
            "the point of the split is that the CLI budget is LARGER than the MCP one"
        )
        os.environ["ADVERSARIAL_REVIEW_TIMEOUT"] = str(mod.REVIEWER_TIMEOUT_CEILING_CLI + 500)
        assert mod._reviewer_env_timeout("ADVERSARIAL_REVIEW_TIMEOUT", 300) == \
            mod.REVIEWER_TIMEOUT_CEILING_CLI, "an override clamps to THIS caller's ceiling"
        os.environ.pop(mod.CLIENT_MARKER_ENV, None)
        assert mod._reviewer_env_timeout("ADVERSARIAL_REVIEW_TIMEOUT", 300) == \
            mod.REVIEWER_TIMEOUT_CEILING, "and to the MCP ceiling without the marker"
    finally:
        os.environ.pop(mod.CLIENT_MARKER_ENV, None)
        os.environ.pop("ADVERSARIAL_REVIEW_TIMEOUT", None)


def test_the_cli_adapter_marks_itself_so_the_budget_is_not_clamped(tmp_path):
    """Drives the adapter's load_governance() and asserts the governance module it returns
    resolves the CLI ceiling — the marker verified at the end the fleet runs, not by
    reading source. The adapter exits 3 when it cannot find the server module, which this
    reports as a failure rather than as a passing skip.
    """
    adapter = REPO / "ops" / "scripts" / "loop-gov.py"
    saved = os.environ.pop("CORTEX_LOOP_GOV_CLIENT", None)
    try:
        spec = importlib.util.spec_from_file_location("loop_gov_adapter_under_test", adapter)
        assert spec is not None and spec.loader is not None, f"cannot load {adapter}"
        adapter_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter_mod)
        try:
            gov = adapter_mod.load_governance()
        except SystemExit as exc:            # the adapter exits 3 when it cannot find it
            raise AssertionError(
                f"the CLI adapter could not load the governance module (exit {exc.code})"
            ) from exc
        assert gov._reviewer_timeout_ceiling() == gov.REVIEWER_TIMEOUT_CEILING_CLI, (
            "load_governance() must mark itself as the CLI client, or every CLI close "
            "is clamped to the MCP ceiling — measured too short for the heaviest blob of "
            f"a range: {gov._reviewer_timeout_ceiling()}"
        )
    finally:
        if saved is not None:
            os.environ["CORTEX_LOOP_GOV_CLIENT"] = saved
        else:
            os.environ.pop("CORTEX_LOOP_GOV_CLIENT", None)


def test_the_pre_change_revision_is_unbounded(tmp_path):
    """Discrimination: the baseline must FAIL these same checks."""
    if SERVER == REPO / "mcp-servers" / "loop-gov-mcp.py":
        print("SKIP: this is the discrimination case — run it with "
              "CORTEX_LOOP_GOV_SERVER=<pre-change copy>")
        return
    src = SERVER.read_text()
    assert '"reasoning"' not in src, (
        "the baseline already sends a reasoning budget — it is not a pre-change "
        "revision and this comparison proves nothing"
    )
    assert "_hard_deadline" not in src, (
        "the baseline already carries a hard deadline — not a pre-change revision"
    )


if __name__ == "__main__":
    import tempfile

    CASES = (
        test_the_request_carries_a_bounded_reasoning_budget,
        test_an_invalid_effort_falls_back_rather_than_becoming_a_400,
        test_the_floor_reports_the_measurement_not_a_remedy_already_tried,
        test_the_call_has_a_hard_wall_clock_deadline,
        test_the_ceiling_follows_the_caller_not_the_reviewer,
        test_the_cli_adapter_marks_itself_so_the_budget_is_not_clamped,
        test_the_pre_change_revision_is_unbounded,
    )
    failures = 0
    for fn in CASES:
        with tempfile.TemporaryDirectory() as td:
            try:
                fn(Path(td))
                print(f"✅ {fn.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"❌ {fn.__name__}: {exc}")
            except Exception as exc:  # noqa: BLE001 — a missing symbol is a finding too
                failures += 1
                print(f"❌ {fn.__name__}: {type(exc).__name__}: {exc}")
    sys.exit(1 if failures else 0)
