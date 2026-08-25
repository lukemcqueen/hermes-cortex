---
name: hermes-agent-regression-triage
version: 1.0.0
category: devops
description: "Use when hermes-agent breaks after update; audit+pin."
metadata:
  hermes:
    tags: [hermes-agent, upstream, regression, mcp, pin, fleet, git]
---

# Hermes-Agent Regression Triage

Use when a host's Hermes tools (especially MCP-backed tools like
loop-governance) break after a hermes-agent update, or when asked "did
something change with X?" across the fleet. The failure is usually NOT in
the user's governance/config — it's an upstream hermes-agent commit the
host pulled.

## The three traps that waste hours

1. **Version string ≠ actual commit.** `Hermes Agent v0.20.5 (2026.8.19) ·
   upstream b85032fc` — the version label does NOT move per commit. The
   `upstream <sha>` is the ground truth. Two hosts both reporting "v0.20.5"
   can be on materially different commits (one clean, one carrying a bug).
   Always audit by SHA, never by version string.
2. **`git merge-base --is-ancestor` can LIE.** History rewrites (remerges,
   cherry-picks, rebased PR trains) break ancestry as a proxy for "does
   this commit contain bug X?". In one real case the ancestry check said
   NO (clean) while the file at that SHA contained the buggy code — because
   the bug arrived via a different lineage. **File content is ground truth**:
   `git show <sha>:<path> | grep -c <bug-symbol>`.
3. **Author date ≠ committer date.** A commit authored before a bug landed
   can be *committed* after it, pulling the bug into its tree. Always check
   BOTH dates (`git show -s --format="%h author=%ad committer=%cd"`) before
   declaring a commit "predates" a bug.

## Diagnostic workflow

### 1. Identify the actual commit on the affected host

```bash
hermes --version   # shows "Hermes Agent vX.Y.Z (date) · upstream <sha>"
cd ~/.hermes/hermes-agent && git log --oneline -1   # local HEAD
```

### 2. Find the raise site of the error

Grep the hermes-agent tree for the exact error text (or its distinctive
prefix — UI truncates):

```bash
grep -rn "MCP stdio" --include="*.py" tools/ | head
grep -n "MCP call failed" tools/mcp_tool.py
```

The gateway raises `MCP call failed: <ExcType>: <msg>` — the ExcType+msg
identify the code path. For MCP fast-fail: `TimeoutError: MCP stdio
subprocess for '<server>' has exited` is the #81995 fast-fail, not a real
timeout.

### 3. Distinguish "server dead" from "gateway thinks it's dead"

| Signal | Meaning |
|--------|---------|
| tool_describe works (0.0s) | schemas are cached — proves nothing about live calls |
| doctor MCP probe ✅ | doctor spawns its OWN probe instance — bypasses the gateway fast-fail path |
| tool_call fails in 0.0s | fast-fail fired, not a slow handshake — the gateway believes the transport is dead |
| all three co-occur | server is healthy; the gateway's liveness check is wrong |

### 4. Audit whether a known bug is present — by FILE CONTENT

```bash
# For each host SHA of interest:
git show <sha>:tools/mcp_tool.py | grep -c "<buggy-symbol>"
# 0 = clean, N>0 = bug present — regardless of what ancestry says
```

Also find which commits touched a function:

```bash
git log --all --oneline -S "<function-name>" -- tools/mcp_tool.py
```

### 5. Check whether upstream main still has the bug

```bash
git fetch origin
git show origin/main:tools/mcp_tool.py | grep -c "<buggy-symbol>"
git show -s --format="%h %ad" origin/main
```

If still present, the fix is NOT yet upstream — pin, don't update.

### 6. Pin to the last clean release tag

```bash
cd ~/.hermes/hermes-agent
git status --short              # check for local mods FIRST
git stash -u                    # preserve them
git fetch origin --tags
git checkout v2026.8.19         # the clean tag; detached HEAD is fine
git stash pop                   # restore local patches (auto-merges cleanly)
grep -c "<buggy-symbol>" tools/mcp_tool.py   # expect 0
# restart the gateway — deploy ≠ load
```

Identify the clean tag by auditing tags: `git show <tag>:tools/mcp_tool.py
| grep -c <buggy-symbol>` → 0.

### 7. Fleet advisory (orchestrators)

Self-test on your own inbox first, then send one message per agent:

```bash
hc send <you> "COMMAND:hold-hermes-update" "<advisory>" --self-tested
python3 ~/.hermes-cortex/scripts/agent-message-handler.py --once
# verify consumed, then:
for agent in moses joseph gisu kustos titus; do
  hc send "$agent" "COMMAND:hold-hermes-update" "$ADVISORY" --self-tested
done
hc inbox <agent>   # verify pending in every inbox
```

Note: a `COMMAND:` advisory to a fleet agent produces an
`Unknown subject` error RESULT back to inbox_moses — that is the handler's
known delivery-confirmation behavior for COMMAND: messages, not a failure.
It self-cleans via the silent `*_RESULT` handling.

## Verification checklist

- [ ] Host's actual SHA identified (not version string)
- [ ] Bug presence confirmed by file-content grep at that SHA
- [ ] Upstream main checked — is the bug still live? (decides pin vs update)
- [ ] Clean tag verified by grep before pinning
- [ ] Local patches stashed → checkout → popped → verified intact
- [ ] Gateway restarted (deploy ≠ load)
- [ ] Fleet advisories pending in every inbox; self-test done first

## Related

- `deployed-component-verification` — deployed-vs-repo matching (complementary)
- `fleet-commands` — full bus dispatch protocol
- `cortex-deployment-sync` — cortex update mechanics
- Reference: `references/2026-08-25-stdio-children-dead-inversion.md` — full case study
