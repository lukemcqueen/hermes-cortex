#!/usr/bin/env python3
"""Every MCP server must be deployed to EVERY host — and only one class per source.

Found 2026-10-02 via Titus (worker-4): `cortex-bus-mcp.py` was registered with
`register_orch` (orchestrator-only), so non-orchestrator hosts never received it.
Nothing failed loudly — `install-pi-mcp.sh` warned and went on to register 3 of the 4
MCP servers, so that host's Pi integration silently lacked the bus, and the agent
copied the file into place by hand. A hand-copy is a workaround, not a fix.

The invariant: an MCP server some hosts never receive is invisible until someone needs
it. So:

  A. every `mcp-servers/*.py` must be registered (deploy or orch) — an unregistered
     server is dead weight that only surfaces when someone misses it;
  B. `cortex-bus-mcp.py` must be a PLAIN register: its tools are all client tools
     (inbox_send/read/watch/list_agents/send_task/…) and every agent's card declares
     `bus_access: client`, while install-pi-mcp.sh requires the file on every host;
  C. `loop-gov-mcp.py` must be a plain register — the governance gate is needed
     everywhere, not only on orchestrators;
  D. a source may appear in ONE class only. Both `register` and `register_orch` for
     the same file is a trap: the orch entry looks authoritative while the plain entry
     is what actually ships (or the reverse, depending on the deploy order) — the fix
     for the bug above initially left exactly this duplicate behind.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
UPDATE = REPO / "ops" / "scripts" / "cortex-update.sh"

# Sources that are deliberately orchestrator-only, WITH the reason. Adding to this
# list is a decision, and it is visible in review.
ORCH_OK: dict[str, str] = {}

_F: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        _F.append(name)


def _registrations() -> list[tuple[str, str, str]]:
    """(class, source, dest) for every register/register_orch entry."""
    text = UPDATE.read_text()
    out = []
    for m in re.finditer(r'^(register|register_orch)\s+"([^"]+)"\s+"([^"]+)"', text, re.M):
        out.append((m.group(1), m.group(2), m.group(3)))
    return out


def test_mcp_servers_are_deployed_everywhere() -> None:
    regs = _registrations()
    assert regs, "parsed 0 registrations — the parser, not the repo, is broken"

    servers = sorted(p.name for p in (REPO / "mcp-servers").glob("*.py"))
    _check("mcp-servers/*.py found", bool(servers), f"found {servers}")

    by_source: dict[str, set[str]] = {}
    for cls, src, _dst in regs:
        by_source.setdefault(src, set()).add(cls)

    # A. every server is registered somewhere
    unregistered = [s for s in servers
                    if not any(k.endswith(f"mcp-servers/{s}") for k in by_source)]
    _check("every MCP server is registered for deploy", not unregistered,
           f"never deployed (invisible until someone needs it): {unregistered}")

    # B. the bus MCP ships to every host
    bus = [k for k in by_source if k.endswith("mcp-servers/cortex-bus-mcp.py")]
    bus_cls = sorted(by_source.get(bus[0], set())) if bus else []
    _check("cortex-bus-mcp.py is registered", bool(bus))
    _check("cortex-bus-mcp.py is NOT orchestrator-only",
           bus_cls == ["register"],
           f"classes={bus_cls} — every agent is a bus client (agent cards say "
           f"bus_access: client) and install-pi-mcp.sh needs it on every host")

    # C. the governance gate ships to every host
    gate = [k for k in by_source if k.endswith("mcp-servers/loop-gov-mcp.py")]
    gate_cls = sorted(by_source.get(gate[0], set())) if gate else []
    _check("loop-gov-mcp.py is registered for every host",
           gate_cls == ["register"], f"classes={gate_cls}")

    # D. one class per source
    both = {k: sorted(v) for k, v in by_source.items() if len(v) > 1}
    _check("no source is registered in two classes", not both, f"conflicting: {both}")

    assert not _F, f"{len(_F)} MCP deployment check(s) failed: {', '.join(_F)}"


def _with_modified_update(replacement: tuple[str, str]) -> None:
    """Run the guard against a modified COPY of cortex-update.sh."""
    global UPDATE
    orig = UPDATE
    try:
        import tempfile
        tmp = Path(tempfile.mkdtemp()) / "cortex-update.sh"
        tmp.write_text(orig.read_text().replace(*replacement))
        UPDATE = tmp
        test_mcp_servers_are_deployed_everywhere()
    finally:
        UPDATE = orig


def test_guard_catches_an_orch_only_regression() -> None:
    """CONTROL: if the bus MCP goes back to orchestrator-only, the guard must fire.

    Without this, check B could be passing because it is simply not looking.
    """
    try:
        _with_modified_update(('register "mcp-servers/cortex-bus-mcp.py"',
                               'register_orch "mcp-servers/cortex-bus-mcp.py"'))
    except AssertionError as e:
        assert "NOT orchestrator-only" in str(e), f"fired for the wrong reason: {e}"
        print("  PASS  control: the guard fires when the bus MCP becomes orch-only")
        return
    raise AssertionError("CONTROL FAILED: the guard did not fire on an orch-only bus MCP")


def test_guard_catches_a_duplicate_registration() -> None:
    """CONTROL: the duplicate-class trap (the bug's own first fix) must fire too."""
    try:
        _with_modified_update(('register "mcp-servers/cortex-bus-mcp.py"',
                               'register "mcp-servers/cortex-bus-mcp.py"\n'
                               'register_orch "mcp-servers/cortex-bus-mcp.py"'))
    except AssertionError as e:
        assert "NOT orchestrator-only" in str(e) or "two classes" in str(e), \
            f"fired for the wrong reason: {e}"
        print("  PASS  control: the guard fires on a duplicate registration")
        return
    raise AssertionError("CONTROL FAILED: the guard did not fire on a duplicate")


if __name__ == "__main__":
    test_mcp_servers_are_deployed_everywhere()
    test_guard_catches_an_orch_only_regression()
    test_guard_catches_a_duplicate_registration()
    print("\n✅ MCP deployment checks passed")
    sys.exit(0)
