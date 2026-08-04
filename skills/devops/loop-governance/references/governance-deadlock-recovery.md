# Governance Lock Enforcement Deadlock Recovery

## The Structural Deadlock

The governance enforcer (at `~/.hermes/plugins/governance-enforcer/`) enforces
two sequential gates:

1. **Skills gate** — agent must load all 8 always-section skills (proven via
   content-verified marker file) before write tools work
2. **Governance lock** — agent must have an active `begin_change()` lock
   before ANY non-read terminal command works

When either gate fails, write tools are blocked. Recovery from a failed
governance lock is normally straightforward (call `begin_change`). But when
the **dogfood check** (which runs inside `begin_change`) fails because the
enforcer plugin files don't match, **you cannot get a governance lock**,
and **you cannot write files without one** — a structural deadlock.

## Recovery Chain

### What Passes Through the Enforcer

| Command | Status | Why |
|---------|--------|-----|
| `bash ~/hermes-cortex/ops/scripts/cortex-update.sh` (exact, allowlisted flags) | ✅ Works | SANCTIONED lock-free self-recovery (2026-08-04) |
| `sudo hermes-plugin-lock unlock` / `lock` | ❌ Blocked | Write-class — requires a governance lock (+ token for manual use) |
| `whoami`, `ls`, `cat`, `grep` | ✅ Works | READ_COMMAND_PATTERNS fast-path |
| `cp file1 file2` | ❌ Blocked | Hits governance lock check |
| `git checkout -- file` | ❌ Blocked | `git checkout` in WRITE_COMMAND_PATTERNS |
| `tee target` | ❌ Blocked | `tee` in WRITE_COMMAND_PATTERNS |
| `rsync src dest` | ❌ Blocked | `rsync` in WRITE_COMMAND_PATTERNS |
| `write_file`, `patch` | ❌ Blocked | WRITE_TOOLS |
| `execute_code` | ❌ Blocked | WRITE_TOOLS |
| `terminal` with write commands | ❌ Blocked | Governance lock check |

### Recovery Procedure

#### If deployed is ahead of repo (has independent changes):

ORCHESTRATOR-ONLY (moses|esther) — requires the `--orchestrator` token;
non-orchestrators are refused and audit-logged:

```bash
sudo hermes-plugin-lock unlock --orchestrator
cp ~/.hermes/plugins/governance-enforcer/__init__.py \
   ~/hermes-cortex/plugins/governance-enforcer/__init__.py
sudo chmod 444 ~/.hermes/plugins/governance-enforcer/__init__.py
sudo hermes-plugin-lock lock
```

Then: `git add` → `git commit` → `git push` the synced repo change.

#### If repo is ahead of deployed (pushed without deploying):

```bash
bash ~/hermes-cortex/ops/scripts/cortex-update.sh --force-all
```

#### After recovery:

```bash
sha256sum ~/hermes-cortex/plugins/governance-enforcer/__init__.py \
          ~/.hermes/plugins/governance-enforcer/__init__.py
```

Both must match. Then `begin_change()` works normally.

## Prevention

The self-healing dogfood check is not yet implemented (tracked in
`tododb:4c90acfd`). Until then:

1. **Always run cortex-update.sh after any push** that touches enforcer code
2. After any manual edit to `~/.hermes/plugins/governance-enforcer/`,
   immediately port the change to the repo source
3. Verify: `sha256sum` of repo and deployed copies must match

## Why the Sanctioned Command Works Without a Lock (2026-08-04)

`sudo hermes-plugin-lock` does NOT pass through — it is write-class and
blocked without a governance lock. The ONE lock-free file-modifying command
is the exact `bash ~/hermes-cortex/ops/scripts/cortex-update.sh` invocation:
`_is_sanctioned_cortex_update_command()` allows exactly that path plus the
allowlisted flags (`--force-all/--dry-run/--status/--delta/--clean-stale`),
with no metacharacters — so a DOGFOOD-blocked agent (no lock, no skills
marker) can deploy and self-recover.

**Deploy ≠ load:** after the deploy, the RUNNING gateway still runs the OLD
enforcer module until `hermes gateway restart` (agent-blocked — the host
operator runs it). If the sanctioned command still returns `GOVERNANCE LOCK
REQUIRED` after a deploy, the restart is pending, not the fix missing.
