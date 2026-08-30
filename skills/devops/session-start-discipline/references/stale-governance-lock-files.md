# Stale Governance Lock Files — Pre-Commit Gate Failures

Subagents (`delegate_task`) create their own governance lock files under
`~/.hermes-cortex/state/.governance-*.json`. When the subagent completes
but the lock file is not cleaned up, these accumulate.

## Symptom

The pre-commit hook's **reflexion-check gate** fails even though you
loaded `skill_view('reflexion-check')` in your own session:

```
❌ Reflexion check not completed.
```

## Root Cause

The hook finds session_id from governance lock files:

```python
lock_files = glob.glob(os.path.join(gov_dir, '.governance-*.json'))
for f in lock_files:
    d = json.load(open(f))
    if d.get('repo_slug') == repo_slug:
        session_id = d.get('session_id')
        break
```

`glob.glob` returns files in alphabetical order. The subagent's lock file
(named after a more recent session_id) appears first. The hook then queries
messages for THAT subagent's session instead of yours — and the subagent
didn't load `reflexion-check`.

## Recovery

Remove stale subagent lock files, keeping only your own:

```bash
ls ~/.hermes-cortex/state/.governance-*.json  # review all lock files
rm -f \
  ~/.hermes-cortex/state/.governance-<subagent1>.json \
  ~/.hermes-cortex/state/.governance-<subagent2>.json
```

To identify your lock file: it contains your session_id. The lock file
naming pattern is `.governance-{session_id}.json`. Yours will match
your current session.

After cleanup, load reflexion-check and commit:

```bash
AGENT_ID=$(grep AGENT_NAME ~/.hermes-cortex/cortex-bus.conf | cut -d= -f2) \
  git commit -m "your message"
```

If `begin_change` doesn't create a lock file (perhaps a bug in some
versions), the hook falls back to the 3 most recent non-cron sessions.
Subagent sessions may also occupy these slots. The same fix applies:
clean up stale lock files ensures the hook falls through to your session.

## Prevention

When dispatching subagents, add cleanup instructions to the context:

> After completing your file changes, delete any governance lock file you
> created: `rm -f ~/.hermes-cortex/state/.governance-*.json` (only if
> the file contains your session_id — do not delete lock files from the
> parent session).
