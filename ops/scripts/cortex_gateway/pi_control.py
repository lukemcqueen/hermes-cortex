#!/usr/bin/env python3
"""pi-control — the harness adapter for PI commands the gateway cannot express
as a plain prompt (``compact``, ``check-model``, ``state``).

WHY THIS FILE EXISTS. The cortex gateway's ``kind: command`` backend runs an argv
per turn and takes stdout as the reply. That covers a *message*, but pi's
session-level commands (``/compact``, model validation) are not messages: pi
handles its built-in slash commands **only in interactive mode**, so sending
``/compact`` as a prompt to a non-interactive run is a no-op — the text becomes an
ordinary user turn (pi's own ``docs/rpc-commands.md``: "Built-in TUI commands are
not included … they would not execute if sent via prompt"). pi exposes the real
operations over RPC, so that is what this adapter speaks.

ONE IMPLEMENTATION, A THIN WAY IN. This file contains no policy: it does not know
what a chat is, which model is the default, or when compaction should happen. The
gateway decides *whether* to compact; this decides only *how to talk to pi about
it*, and prints one human line the gateway relays verbatim.

Usage (argv templates live in gateway.yaml, never here):

    pi-control compact     --session-id hc-pi-<chat> [--model M] [--instructions TEXT]
    pi-control check-model <provider/model>
    pi-control state       --session-id hc-pi-<chat>

Exit codes follow the fleet convention for a check that can fail three ways:

    0  the operation succeeded (verdict printed on stdout)
    1  a NEGATIVE answer — model not recognised, pi refused the operation
    3  COULD NOT VERIFY — pi itself could not be run or read; callers must not
       treat this as either success or a negative result
"""
from __future__ import annotations

import argparse
import json
import os
import select
import signal
import subprocess
import sys
import time

# The launcher is a symlink into a bin dir that is not on a service PATH, so a
# bare "pi" is a per-turn no-op under systemd. Resolve, then fail loudly.
PI_CANDIDATES = (
    os.environ.get("PI_BIN", ""),
    str(os.path.expanduser("~/.pi/agent/bin/pi")),
)

COULD_NOT_VERIFY = 3
REFUSED = 1


def _pi_bin() -> str:
    for cand in PI_CANDIDATES:
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    print("pi-control: pi is not installed (no launcher at ~/.pi/agent/bin/pi, "
          "no PI_BIN)", file=sys.stderr)
    raise SystemExit(COULD_NOT_VERIFY)


# ── RPC mode: one JSON record per line, in and out ───────────────────────────

def _rpc(base_argv: list, command: dict, *, deadline_s: float = 120.0) -> dict:
    """Send ONE command to a fresh pi RPC process; return its ``response`` record.

    A fresh process per command is deliberate: RPC mode is session-oriented and
    the gateway already owns session lifetime. Starting one, asking one question,
    and shutting down cannot leave a half-driven agent behind on the host.

    TWO end-of-answer signals, because one of them lies. EOF on the child's stdout
    is the obvious one — but pi's own MCP server children inherit its stdio, so a
    lingering grandchild keeps the write end of that pipe OPEN after pi itself has
    gone: no data ever arrives and EOF never comes, and a reader that waits only
    for EOF blocks for its whole deadline. Measured 2026-10-08: `/compact` hung
    exactly this way (~40% of runs) with NO pi process left alive, while the same
    command from a shell always answered in ~2s. So the loop also watches the
    child's EXIT — once pi is gone and a short grace has passed, the answer is
    simply not coming, and saying so beats waiting.
    """
    proc = subprocess.Popen(
        # --no-mcp: a CONTROL call (state/compact) uses no MCP tool, and pi connects
        # its four MCP servers at RPC startup — four more processes, each of which
        # can be slow or wedged (measured 2026-10-08: pi sat ALIVE and silent for the
        # full deadline on ~40% of /compact calls with MCP enabled, while the same
        # call always answered from a shell). Dropping the servers from a call that
        # cannot use them removes the whole class of waiting.
        [*base_argv, "--mode", "rpc", "--no-mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
        # Own process group: on a timeout we can reap pi AND the MCP children it
        # spawned, instead of leaving them to hold our pipes (and the host) open.
        start_new_session=True,
    )
    req = {"id": "pi-control-1", **command}
    try:
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
    except (BrokenPipeError, OSError) as e:
        _kill(proc)
        print(f"pi-control: pi exited before accepting the command ({e})",
              file=sys.stderr)
        raise SystemExit(COULD_NOT_VERIFY)

    deadline = time.monotonic() + deadline_s
    exited_at: float | None = None
    out = proc.stdout
    assert out is not None
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill(proc)
                tail = _stderr_tail(proc)
                print(f"pi-control: pi did not answer within {deadline_s:.0f}s"
                      + (f" — stderr: {tail}" if tail else ""), file=sys.stderr)
                if os.environ.get("CORTEX_PI_CONTROL_DEBUG"):
                    _debug_state(proc)
                raise SystemExit(COULD_NOT_VERIFY)
            ready, _, _ = select.select([out], [], [], min(remaining, 0.5))
            if ready:
                line = out.readline()
                if not line:
                    break                  # EOF — pi closed its stdout
                # pi reserves stdout for protocol records, but be defensive: a stray
                # diagnostic line must not crash the adapter.
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("id") == req["id"] and record.get("type") == "response":
                    return record
                continue
            if proc.poll() is not None:
                # pi is gone. Give anything still buffered a moment to arrive, then
                # stop: a grandchild holding the pipe means EOF is not a signal we
                # can rely on.
                if exited_at is None:
                    exited_at = time.monotonic()
                elif time.monotonic() - exited_at > 2.0:
                    break
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()         # orderly shutdown (pi's documented path)
        except OSError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _kill(proc)

    err = _stderr_tail(proc)
    print(f"pi-control: pi exited without a response (rc={proc.returncode})"
          + (f": {err}" if err else ""), file=sys.stderr)
    raise SystemExit(COULD_NOT_VERIFY)


def _kill(proc) -> None:
    """Take down pi AND the children it spawned.

    Killing only pi leaves its MCP server children alive holding our stdout and
    stderr pipes, which is exactly what turns a fast answer into a long wait.
    """
    _kill_group(proc)
    try:
        proc.kill()
    except OSError:
        pass


def _kill_group(proc) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError, PermissionError):
        pass


def _stderr_tail(proc, limit: int = 400) -> str:
    """Whatever the child said before it stopped — read WITHOUT waiting for EOF.

    A bare "did not answer" leaves the reader with nothing to act on, and a plain
    ``proc.stderr.read()`` here would block on exactly the condition being
    reported: a lingering grandchild holding the pipe open. So: select, then a
    raw read of what is actually there.
    """
    st = proc.stderr
    if st is None:
        return ""
    try:
        ready, _, _ = select.select([st], [], [], 0.5)
        if not ready:
            return ""
        return os.read(st.fileno(), 4096).decode("utf-8", "replace")[:limit].strip()
    except (OSError, ValueError):
        return ""


def _debug_state(proc) -> None:
    """Diagnostics for a stuck command (CORTEX_PI_CONTROL_DEBUG=1): who is still there.

    Answers the only question that matters when pi goes quiet: is the process gone
    (a lingering child holding the pipe) or alive and silent (pi is stuck)? The two
    need different fixes, and neither is visible from the timeout alone.
    """
    def _stat(pid: int) -> str:
        try:
            with open(f"/proc/{pid}/stat") as fh:
                parts = fh.read().split()
            with open(f"/proc/{pid}/wchan") as fh:
                wchan = fh.read().strip()
            with open(f"/proc/{pid}/cmdline") as fh:
                cmd = fh.read().replace("\0", " ").strip()
            return f"pid={pid} state={parts[2]} ppid={parts[3]} wchan={wchan} cmd={cmd[:160]}"
        except OSError as e:
            return f"pid={pid} (gone: {e})"

    print(f"  DEBUG child poll()={proc.poll()} returncode={proc.returncode} "
          f"pid={proc.pid}", file=sys.stderr)
    print("  DEBUG " + _stat(proc.pid), file=sys.stderr)
    try:
        kids = set()
        for task in os.listdir(f"/proc/{os.getpid()}/task"):
            with open(f"/proc/{os.getpid()}/task/{task}/children") as fh:
                kids.update(int(t) for t in fh.read().split())
        for kid in sorted(kids):
            print("  DEBUG child " + _stat(kid), file=sys.stderr)
    except OSError as e:
        print(f"  DEBUG could not list children: {e}", file=sys.stderr)


def _session_argv(args) -> list:
    if not args.session_id:
        print("pi-control: --session-id is required (the gateway pins one per chat)",
              file=sys.stderr)
        raise SystemExit(REFUSED)
    argv = [_pi_bin(), "--session-id", args.session_id]
    if getattr(args, "session_dir", ""):
        argv += ["--session-dir", args.session_dir]
    if getattr(args, "model", ""):
        argv += ["--model", args.model]
    return argv


# ── commands ────────────────────────────────────────────────────────────────

def cmd_compact(args) -> int:
    """Manually compact the session's context (pi RPC ``compact``).

    A ``get_state`` round trip comes FIRST, and it is not decoration: pi's RPC
    ``compact`` NEVER ANSWERS when the session transcript does not exist yet
    (measured 2026-10-08: no response in 45s, repeated; the same id answers
    ``get_state`` in ~1.2s and — having created the session — then compacts in
    ~1.2s). A chat that has just used ``/new``, or whose first turn has not run
    yet, is exactly that case, so asking for compaction blind wedges the gateway's
    turn until its own timeout. The state read fixes the hang and gives the honest
    answer for an empty conversation.
    """
    started = time.monotonic()
    state = _rpc(_session_argv(args), {"type": "get_state"},
                 deadline_s=min(args.timeout_s, 60.0))
    if not state.get("success"):
        print(str(state.get("error") or "pi could not read the session"),
              file=sys.stderr)
        return COULD_NOT_VERIFY
    if int((state.get("data") or {}).get("messageCount") or 0) == 0:
        print("Nothing to compact — this chat has no conversation yet.",
              file=sys.stderr)
        return REFUSED

    command = {"type": "compact"}
    if args.instructions:
        command["customInstructions"] = args.instructions
    remaining = max(30.0, args.timeout_s - (time.monotonic() - started))
    resp = _rpc(_session_argv(args), command, deadline_s=remaining)
    if not resp.get("success"):
        err = str(resp.get("error") or "pi refused the compaction")
        print(err, file=sys.stderr)
        return REFUSED
    data = resp.get("data") or {}
    before, after = data.get("tokensBefore"), data.get("estimatedTokensAfter")
    if isinstance(before, int) and isinstance(after, int):
        print(f"context compacted: {before:,} → {after:,} tokens "
              f"(estimate after summary)")
    elif isinstance(before, int):
        print(f"context compacted: was {before:,} tokens, summary written")
    else:
        # success with an unrecognised shape is still success — never invent numbers
        print("context compacted (pi reported success)")
    return 0


def cmd_check_model(args) -> int:
    """Is this model one pi can resolve? Offline, so it never blocks on a provider.

    ``pi --offline --list-models <pattern>`` prints a table, or exactly
    ``No models matching "<pattern>"`` **and exits 0** — so the VERDICT is the
    output, not the exit code (an empty result that exits 0 passes every
    rc-based check).
    """
    pattern = args.model
    if not pattern:
        print("pi-control: check-model needs a model name", file=sys.stderr)
        return REFUSED
    try:
        proc = subprocess.run([_pi_bin(), "--offline", "--list-models", pattern],
                              capture_output=True, text=True, timeout=args.timeout_s)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"pi-control: could not list models ({e})", file=sys.stderr)
        return COULD_NOT_VERIFY
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 or not out:
        print(f"pi-control: could not list models (rc={proc.returncode})",
              file=sys.stderr)
        return COULD_NOT_VERIFY
    if out.startswith("No models matching"):
        print(f"no model matches {pattern!r}", file=sys.stderr)
        return REFUSED
    rows = [ln for ln in out.splitlines()[1:] if ln.strip()]
    if not rows:
        print(f"no model matches {pattern!r}", file=sys.stderr)
        return REFUSED
    names = [ln.split()[1] for ln in rows if len(ln.split()) > 1]
    print(f"resolves to {len(rows)} model(s): " + ", ".join(names[:5]))
    return 0


def cmd_state(args) -> int:
    """Read-only: the model and message count pi holds for the session."""
    resp = _rpc(_session_argv(args), {"type": "get_state"}, deadline_s=args.timeout_s)
    if not resp.get("success"):
        print(str(resp.get("error") or "pi could not read the session"),
              file=sys.stderr)
        return REFUSED
    d = resp.get("data") or {}
    model = d.get("model") or {}
    if isinstance(model, dict):
        name = f"{model.get('provider', '')}/{model.get('id', '')}".strip("/")
    else:
        name = str(model)
    print(f"model={name or 'unset'} messages={d.get('messageCount')} "
          f"session={d.get('sessionId')}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pi-control",
                                 description="pi commands the gateway cannot send "
                                             "as a prompt (compact, check-model, state)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("compact", help="manually compact the session context")
    p.add_argument("--session-id", required=True)
    p.add_argument("--session-dir", default="")
    p.add_argument("--model", default="")
    p.add_argument("--instructions", default="")
    # Compaction is an LLM call over the whole session: measured 1m46s on a
    # 71-message pi session. 300s bounds a big session while staying under the
    # gateway-side control timeout, so the message names the RIGHT limit.
    p.add_argument("--timeout-s", type=float, default=300.0)
    p.set_defaults(fn=cmd_compact)

    p = sub.add_parser("check-model", help="does pi resolve this model?")
    p.add_argument("model")
    p.add_argument("--timeout-s", type=float, default=20.0)
    p.set_defaults(fn=cmd_check_model)

    p = sub.add_parser("state", help="model + message count for the session")
    p.add_argument("--session-id", required=True)
    p.add_argument("--session-dir", default="")
    p.add_argument("--model", default="")
    p.add_argument("--timeout-s", type=float, default=60.0)
    p.set_defaults(fn=cmd_state)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
