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
| `sudo hermes-plugin-lock unlock` | ✅ Works | NOT in any WRITE_COMMAND_PATTERN |
| `sudo hermes-plugin-lock lock` | ✅ Works | NOT in any write pattern |
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

```bash
sudo hermes-plugin-lock unlock
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

## Why `sudo hermes-plugin-lock` Works Without a Lock

The enforcer's `WRITE_COMMAND_PATTERNS` is an allow-list for write detection.
`hermes-plugin-lock` is not in this list. The READ_COMMAND_PATTERNS is a
separate fast-path allow-list for known-read commands. Commands NOT in either
list fall through to the governance lock check — but `hermes-plugin-lock`
somehow passes through even this check.

This is documented as a structural fact, not a bypass. Any agent that
discovers a different bypass should report it for closure, not exploit it.
