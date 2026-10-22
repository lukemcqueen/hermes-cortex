---
name: hermes-agent-regression-triage
version: 1.0.0
category: devops
description: "Use when hermes-agent breaks after update or won't update."
metadata:
  hermes:
    tags: [hermes-agent, upstream, regression, mcp, pin, fleet, git]
---

# Hermes-Agent Regression Triage

Use when a host's Hermes tools (especially MCP-backed tools like
loop-governance) break after a hermes-agent update, when `hermes update`
itself refuses to run, or when asked "did something change with X?" across
the fleet. The failure is usually NOT in the user's governance/config —
it's an upstream hermes-agent commit the host pulled, or the state of the
checkout's own git clone.

## The three traps that waste hours

0. **Many crons failing with the SAME exception at once = scheduler-level fault, not per-job — and the cause is often an UNCOMMITTED local edit, not upstream.** If a batch of unrelated agent crons (ai-brief, sustainability, job-scanner, backlog-driver) all report the identical `'_FireAudit' object has no attribute 'agent'`-style error within one window, stop auditing commits and check the SHARED firing path first: `git status --short` + `git diff cron/scheduler.py` on the hermes-agent tree. A stale uncommitted scratch edit (a prior session's half-applied change) re-introduces a broken line the committed base never had — `git blame` shows `Not Committed Yet` with today's timestamp. Repair the file directly (`python3 -m py_compile` + a minimal instantiate-and-call probe of the failing object), not by checking out a pinned tag. **FIRST check whether a cortex patcher re-injects that line.** Patchers in `~/hermes-cortex/ops/scripts/install/` (e.g. `install-lean-index.py`) run on EVERY `cortex-update.sh`, so a hand-repair is silently undone at the next sync — the durable fix is the patcher's snippet in the repo, deployed, with a repair step that heals an already-broken host. **Hosts diverge on the injected text** (one sets `self.agent = agent`, another `self._agent = agent`); a snippet written against one AttributeErrors on the other, so normalise the name before injecting — otherwise the fix for one host is the breakage for the next to update. **Prefer config/extension points to patching core at all:** make a patch removable from CONFIG so a broken optional feature is switched off without editing Python, and remember an audit-write bug fails EVERY cron because the write sits inside the job's `try`. A fix to a Hermes core file ships on that host only — it is not in the cortex repo.

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

## `hermes update` aborts at channel resolution (`merge-base` timed out)

Symptom: the update prints `→ Update channel: stable` and then
`✗ Could not resolve the stable source channel: Command '['git', 'merge-base',
'--is-ancestor', ...]' timed out after 10 seconds. No update was applied.`

The probe is not slow by nature and the release commit is not missing upstream.
Reproduce the exact command by hand before theorising:

```bash
cd ~/.hermes/hermes-agent
time git merge-base --is-ancestor <release-sha> HEAD
```

- **Commit present locally → ~0.2s, rc=1.** Then the failure was a *missing
  object*, not a slow repo — stop looking for a slow-history cause.
- **Commit absent locally → ~50s of CPU, then `fatal: Not a valid commit name`.**
  It does not fail fast, and the call site allows only `timeout=10`
  (`hermes_cli/source_releases.py`), so the hang is what aborts the update.

Rules:

- **`GIT_NO_LAZY_FETCH=1` does NOT make an absent object fail fast.** git prints
  `lazy fetching disabled; some objects may not be available` and then burns the
  same ~50s. The guard turns a slow lazy fetch into a slow spin; both exceed the
  timeout. Never assume the guard already fails closed.
- **A partial clone can never see a release commit.** Check
  `git config --get remote.origin.promisor` (`true`) and
  `--get remote.origin.partialclonefilter` (`blob:none`). Release commits live on
  release TAGS/branches, so a refspec of only `+refs/heads/main:...` never
  fetches them. Confirm where the commit actually lives with
  `git ls-remote origin | grep <sha>`, and whether it is local with
  `git tag --contains <sha>` — **`git branch -a --contains` alone is not enough,
  it misses tags.** Empty output from both = not local.
- **A non-zero exit from the probe is BENIGN; only the TIMEOUT is fatal.** The
  caller treats any non-zero rc as "not an ancestor" and continues. So "make the
  missing object fail fast" is a valid fix direction, while "hang" cannot be
  recovered from — do not read the timeout as a git error.
- **Fix the environment, never the checkout source.** This fleet does not patch
  `~/.hermes/hermes-agent` (it is overwritten on update). Add the refspec hermes
  itself already uses (`+refs/tags/v*:refs/tags/v*`, see `hermes_cli/gitlock.py`)
  and fetch:

```bash
git config --add remote.origin.fetch '+refs/tags/v*:refs/tags/v*'
git fetch --no-tags origin 'refs/tags/v*:refs/tags/v*'
```

  Verify in this order: `git tag --contains <release-sha>` now lists the tag;
  the probe returns in ~0.2s (bare AND under `GIT_NO_LAZY_FETCH=1`);
  `hermes update --check` exits 0.
- **It recurs on the next release, so report a remedy, not a permanent fix.**
  The update flow fetches the target ref only AFTER channel resolution
  (`hermes_cli/update_cmd.py`), so a brand-new release commit is again absent
  when the probe runs. The added refspec only helps if something fetches — tell
  the operator the one-liner (`git fetch --tags` before updating) or wire a
  pre-fetch into the update path.
- **Do NOT run `hermes update` yourself to "prove" the fix in an interactive
  session** — it restarts the gateway and kills the session mid-turn. The
  read-only proofs are `hermes update --check` and `hermes update --plan`.

Diagnostic recipe plus the measurements that rule out I/O, pack count and
missing commits: `references/update-channel-resolution-timeout.md`.

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

- `deploy-load-verification` — deployed-vs-repo matching (complementary)
- `fleet-commands` — full bus dispatch protocol
- `cortex-deployment-sync` — cortex update mechanics
- `references/update-channel-resolution-timeout.md` — `hermes update` dies at
  channel resolution: partial-clone probe recipe and ruling-out measurements
- Reference: `references/2026-08-25-stdio-children-dead-inversion.md` — full case study
