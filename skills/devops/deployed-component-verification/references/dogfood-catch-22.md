# Dogfood Check Catch-22

## Problem

The MCP loop-governance server's dogfood check compares SHA256 hashes of
the governance enforcer at `~/.hermes/plugins/governance-enforcer/__init__.py`
and the repo source at `~/hermes-cortex/plugins/governance-enforcer/__init__.py`
before allowing `begin_change()`. If they differ, `begin_change` is blocked.

This creates a catch-22 when the **deployed** copy is ahead of the **repo**
(not the expected repo-ahead-of-deployed direction):

```
❌  DOGFOOD REQUIRED
    The governance plugin at ~/.hermes/plugins/governance-enforcer/ differs from
    the repo source (the commit you just pushed).
```

You need `begin_change` to write files, but `begin_change` is blocked
because the files differ.

**This can also happen when deployed is behind** — if you push enforcer
changes via `git push origin main` but never run `cortex-update.sh`
afterwards, the enforcer's pre-commit hook dogfood check (at
`~/.hermes-cortex/hooks/pre-commit` lines 76-94) blocks commits until
you deploy.

## Root Cause

The enforcer plugin at `~/.hermes/plugins/governance-enforcer/` is deployed
as a **standalone copy** (not a symlink) to support `chattr +i` immutability.
When someone or something modifies the deployed copy independently (e.g., a
hotfix applied directly, or a previous session that deployed changes without
committing), the repo falls behind.

The dogfood check has TWO locations:
1. **Pre-commit hook** (`~/.hermes-cortex/hooks/pre-commit` lines 76-94) —
   blocks `git commit` when enforcer files differ.
2. **`begin_change` MCP tool** (in loop-governance MCP server) — blocks
   `begin_change()` when enforcer files differ.

Both must pass before you can commit and start work.

## How It Manifests

| Scenario | Direction | Typical cause |
|----------|-----------|---------------|
| Repo ahead | `git pull` updated repo, deploy pending | Normal dogfood — run `cortex-update.sh --force-all` |
| **Deployed ahead** | Independent edit to deployed file | Hotfix applied directly, or session deployed changes without committing |
| **Both differ** | Working tree patched temporarily to match deployed | Temporary fix for deadlock, but never restored |

## Breaking the Cycle

### Key Constraint

The **governance enforcer blocks ALL write tool calls** (`terminal` with
write-pattern commands, `write_file`, `patch`, `execute_code`) when there's
no active governance lock. Since you can't get a governance lock while the
dogfood check fails, the tools that would normally write files are all
blocked. This is a **hard structural deadlock**.

### What DOES work (passes through the enforcer)

Since 2026-08-04 the enforcer has ONE sanctioned lock-free terminal command:
the exact `cortex-update.sh` deploy invocation. The DOGFOOD gate blocks
`begin_change()` until repo == deployed, so the ONLY way to deploy is
`cortex-update.sh` — the enforcer lets that exact command through without
a governance lock so the agent can self-recover:

```bash
bash ~/hermes-cortex/ops/scripts/cortex-update.sh
# allowed flags: --force-all --dry-run --status --delta --clean-stale
# EXACT match only — no sudo, no chaining (&&, ;, |, >), no other scripts
```

**Confirmed working (passes through without governance lock):**
```bash
bash ~/hermes-cortex/ops/scripts/cortex-update.sh   # sanctioned exact-path exception
ls / whoami / git status                            # READ_COMMAND_PATTERNS fast-path
```

**Blocked without governance lock:**
```bash
sudo hermes-plugin-lock unlock   # write-class — needs a lock (fail-closed since P0-2)
cp file1 file2                   # hits governance lock check
tee target                       # in WRITE_COMMAND_PATTERNS
git checkout -- file             # git checkout in WRITE_COMMAND_PATTERNS
rsync src dest                   # rsync in WRITE_COMMAND_PATTERNS
```

### Method 1: One-time human intervention (fastest)

If the deadlock happens mid-session and you need it resolved immediately —
**the sanctioned self-recovery is Method 3 (cortex-update.sh, lock-free)**.
The manual unlock/cp path below is the ORCHESTRATOR-ONLY fallback
(`sudo hermes-plugin-lock` requires the `--orchestrator` token and is
audit-logged; non-orchestrators are refused). Prefer Method 3 — it is the
enforcer's single sanctioned lock-free command:

```bash
bash ~/hermes-cortex/ops/scripts/cortex-update.sh   # sanctioned, lock-free
```

Then verify:
```bash
sha256sum ~/hermes-cortex/plugins/governance-enforcer/__init__.py \
          ~/.hermes/plugins/governance-enforcer/__init__.py
```

Both hashes must match. Then `begin_change()` works normally.

### Method 2: Sync repo source to match deployed (when deployed is ahead)

If the deployed copy has changes that need porting to the repo
(orchestrator-only; requires the `--orchestrator` token):

```bash
sudo hermes-plugin-lock unlock --orchestrator 2>/dev/null
cp ~/.hermes/plugins/governance-enforcer/__init__.py \
   ~/hermes-cortex/plugins/governance-enforcer/__init__.py
sudo hermes-plugin-lock lock 2>/dev/null
# Then git add/commit/push the repo change
```

### Method 3: Deploy repo → deployed (when repo is ahead) — SANCTIONED, LOCK-FREE

```bash
bash ~/hermes-cortex/ops/scripts/cortex-update.sh
```

Since 2026-08-04 the enforcer's `_is_sanctioned_cortex_update_command()`
allows this EXACT command through without a governance lock (exact path,
allowlisted flags only, no chaining/sudo/metacharacters). Since
Since `commit ce258342`, `deploy_governance_plugin()` always copies the
enforcer files from repo source (no `needs_update` gate).
**⚠️ Deploy ≠ load (2026-08-04):** `hermes plugins disable/enable` does NOT
reload the running enforcer — it only writes `config.yaml`. The gateway keeps
the OLD module in memory until `hermes gateway restart`, which agents cannot
perform (lifecycle guard; the host operator runs it). Symptom: repo == deployed
(SHA256 match) yet the sanctioned command STILL returns `GOVERNANCE LOCK
REQUIRED` → restart pending, not a code bug. Do not loop retrying — ask the
operator to restart the gateway.

## Prevention

### Structural fix (implemented 2026-08-04 — sanctioned recovery, not auto-deploy)

The dogfood check remains a hard BLOCK (auto-deploy on begin_change was
deliberately rejected — it would bypass the sanctioned deploy path). The
2026-08-04 fix instead makes the SANCTIONED recovery command executable in
the blocked state:

1. The enforcer's `_is_sanctioned_cortex_update_command()` allows the
   exact `bash ~/hermes-cortex/ops/scripts/cortex-update.sh` invocation
   through WITHOUT a governance lock (exact path, allowlisted flags only,
   no chaining/sudo/metacharacters).
2. The DOGFOOD message tells agents to run exactly that command.
3. `cortex-update.sh` deploys repo → deployed, then the agent re-acquires
   the lock with `begin_change()` (which now passes, repo == deployed).

This keeps enforcement structural (no bypass, no auto-deploy side channel)
while eliminating the deadlock: the gate's own sanctioned recovery path is
now actually runnable.

### Procedural prevention

After any session that modifies the enforcer plugin:

1. Run `cortex-update.sh --force-all` IMMEDIATELY after EVERY push
   that touches enforcer code. The dogfood check detects push-without-deploy.
2. Verify: `sha256sum ~/hermes-cortex/plugins/governance-enforcer/__init__.py
   ~/.hermes/plugins/governance-enforcer/__init__.py` matches.
3. If different, port the change immediately.

A mismatch discovered mid-task is expensive because it blocks every
subsequent `begin_change`. The dogfood check is validated at TWO points:
pre-commit hook AND `begin_change` MCP tool.

## Remediated Gaps from Past Sessions

### `cp` blocked by governance lock, not skills gate

A common misunderstanding: `cp file1 file2` is NOT in WRITE_COMMAND_PATTERNS
(confirmed by grep on line 475-500 — `cp` does not appear). It's blocked
by the **governance lock check** at line 811 of the enforcer, which blocks
ALL terminal commands that don't match READ_COMMAND_PATTERNS or
WRITE_COMMAND_PATTERNS equally. The enforcer treats `cp` as a non-read
command (it's not in READ_COMMAND_PATTERNS) and requires a governance lock
for any non-read terminal command.

This means `cp` without a governance lock hits the same "GOVERNANCE LOCK
REQUIRED" error as `git push` or `sudo chmod`. The only commands that
pass through are:
- Commands matching READ_COMMAND_PATTERNS (fast-path)
- `bash ~/hermes-cortex/ops/scripts/cortex-update.sh` (exact, allowlisted
  flags only) — the single sanctioned exception (2026-08-04)

### The single sanctioned exception (updated 2026-08-04)

`sudo hermes-plugin-lock unlock` is NO LONGER a pass-through — it is
write-class and requires a governance lock (manual use needs the
`--orchestrator` token; non-orchestrators are refused and audit-logged).
The ONE file-modifying command that works without a governance lock is the
exact sanctioned deploy invocation:

```bash
bash ~/hermes-cortex/ops/scripts/cortex-update.sh
# allowlisted flags only: --force-all --dry-run --status --delta --clean-stale
# EXACT match — no sudo, no chaining, no other scripts
```

The `cp` explanation above still holds (`cp` is blocked by the governance
lock check, not by WRITE_COMMAND_PATTERNS).
