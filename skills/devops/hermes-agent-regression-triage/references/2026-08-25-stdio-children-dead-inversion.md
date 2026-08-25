# Case Study: `_stdio_children_dead()` Inversion (2026-08-25)

Full investigation trail for the upstream hermes-agent bug that broke
loop-governance MCP tool calls on fleet host Titus. All SHAs verified by
file-content grep at the time of writing; upstream may move.

## Symptom on Titus

```
tool_desc mcp__loop_governance__cycle_stats/check_lock/config_show  0.0s OK
tool_call mcp__loop_governance__*  →  [MCP call failed: TimeoutError:
MCP stdio subp...]  (0.0s, repeated ×3)
```

- Gateway restarted → same error (so not a "restart pending" deploy issue).
- Doctor on Titus: ✅ MCP server (loop-governance), ✅ MCP Python, ✅ gate smoke.
- Titus venv: mcp 2.0.0 (identical to Esther) — SDK-version theory dead.

## The bug

Upstream commit `2f33833de` (2026-08-24, "fix(mcp): recover poisoned
connections + fail fast on dead stdio transports (#85125 3b)", author
kshitijk4poor) added `MCPServerTask._stdio_children_dead()` in
`tools/mcp_tool.py` with INVERTED returns:

```python
def _stdio_children_dead(self) -> bool:
    """True when every stdio child we spawned has exited."""
    pids = getattr(self, "_stdio_child_pids", None)
    if not pids or self._is_http():
        return False
    for pid in pids:
        import psutil
        if not psutil.pid_exists(pid):
            continue  # this one is dead
        return True  # alive  ← WRONG: caller reads True as "has exited"
        return False  # at least one child alive  ← unreachable dead code
    return True
```

Caller (`_call` fast-fail, #81995): `if _stdio_dead(): raise TimeoutError(
"MCP stdio subprocess for '<server>' has exited; failing the call fast...")`.

Net effect: ANY host with a live tracked child PID fast-fails EVERY stdio
MCP tool call in 0.0s, even though the server is healthy. Follow-up
`786f37071` (2026-08-25, "Windows footgun") swapped os.kill→psutil but
PRESERVED the inversion. Still present on origin/main at `64a6f42cb`.

Why tests passed (639 ✅): the fast-fail is guarded by
`isinstance(_stdio_dead(), bool)` to dodge MagicMock — unit tests never
exercise the live-PID path.

## Fleet audit — version string is a trap

Titus reported "Hermes Agent v0.20.5 (2026.8.19) · upstream b85032fc".
`b85032fc` is NOT the release — it's a post-release main commit (Aug 24)
containing the bug. Same version label, different commits:

| Commit | `_stdio_children_dead` count | Verdict |
|---|---|---|
| `64a6f42cb3` (latest main) | 3, inverted | 🔴 buggy |
| `5400fb88e5` (Moses/kustos upstream) | 3, inverted | 🔴 buggy (committed 08-24 19:59 -0700 despite author date 08-21!) |
| `b85032fc7` (Titus) | 3, inverted | 🔴 buggy |
| `fcbd1076a9` (tag v2026.8.19) | 0 | ✅ clean |
| `0c713049e` (Esther/Moses local HEAD) | 0 | ✅ clean |
| `057dcdf23` (Joseph/Gisu/kustos) | 0 | ✅ clean |

Key gotcha hit during triage: `git merge-base --is-ancestor 2f33833de
5400fb88` → NO (clean), but the file at `5400fb88` contained the buggy
function. The bug reached that commit through a different lineage (author
date 08-21 < bug, committer date 08-24 19:59 > bug). **File content grep
is the only reliable check; ancestry and author dates both lie.**

## Fix applied (Titus + Esther + kustos)

1. `git status --short` → stash local cost patches: `git stash -u`
2. `git fetch origin --tags`
3. `git checkout v2026.8.19` (detached HEAD is fine for a pin)
4. `git stash pop` → auto-merged cleanly, local patches intact
5. Verify: `grep -c "_stdio_children_dead" tools/mcp_tool.py` → 0
6. Restart the gateway (deploy ≠ load)

## Fix PR drafted (local branch, not pushed — no gh CLI on host)

- Branch `fix/stdio-children-dead-inversion` from origin/main
- One-line change: `return True  # alive` → `return False` (alive child ⇒
  NOT all dead ⇒ don't fail fast); loop falls through to `return True`.
- Logic probe (run with python3):
  `dead({live_pid})→False`, `dead({dead_pid})→True`, `dead({})→False`.
- PR description at `/tmp/pr-stdio-children-dead-fix.md`;
  patch at `/tmp/fix-stdio-children-dead.patch`.

## Fleet advisory dispatch (orchestrator pattern)

Self-tested on own inbox first (hc send esther + run handler --once), then
`COMMAND:hold-hermes-update` to moses/joseph/gisu/kustos/titus; verified
pending in every inbox. Titus (inbox-only health) warns but delivers.
COMMAND: advisories produce an `Unknown subject` error RESULT to
inbox_moses — known handler behavior, self-cleans, not a failure.
