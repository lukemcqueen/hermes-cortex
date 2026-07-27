# Cron Management

The loop-governance system uses Hermes Agent's internal cron scheduler, not OS-level
cron/launchd. This means crons work identically on Linux, macOS, and Windows.

## Canonical Template

All loop-governance crons are defined in a single versioned JSON template:

```
~/hermes-cortex/core/governance/crons.json
```

The template has a `version` field and a `crons` array. Each cron specifies its name,
schedule, delivery target, and either a `script` (for no_agent watchdog mode) or a
`prompt` (for LLM-driven reports with optional `skills`).

```json
{
  "version": 5,
  "crons": [
    {
      "name": "skill-miner",
      "schedule": "0 6 * * 1",
      "script": "skill-miner",
      "no_agent": true,
      "deliver": "origin",
      "description": "Mines local data for patterns."
    },
    {
      "name": "weekly-loop-evaluation",
      "schedule": "0 9 * * 1",
      "prompt": "Run the evaluation pipeline...",
      "skills": ["loop-governance"],
      "deliver": "origin",
      "orchestrator_only": false,
      "description": "Weekly evaluation."
    }
  ]
}
```

**Fields:**
- `orchestrator_only` (boolean, default false) — set true for crons that should
  only run on the orchestrator machine. The installer checks `agent-registry.json`
  to determine if this machine is the orchestrator, and skips `orchestrator_only`
  crons on non-orchestrator agents.
- `enabled` (boolean, default true) — can be set false to prevent creation.
- `description` (string) — human-readable description.

**Bump the `version` field when adding or changing crons.** The installer checks
this version against `.cron-version` to decide whether to re-install.

## Agent Registry Integration

The installer (`install-crons.py`) checks `src/agent-registry.json` to determine
whether the current machine is the orchestrator:

```python
registry = load("src/agent-registry.json")
hostname = os.uname().nodename.lower()
is_orchestrator = any(
    entry.get("is_orchestrator") and entry.get("hostname") in hostname
    for entry in registry["agents"]
)
```

Agent machines only get non-orchestrator crons. Orchestrator gets all crons.
No manual config needed — automatic via hostname match.

## Installer

The `install-crons.py` script reads the template and creates/updates crons:

```bash
python3 install-crons.py                    # install/update
python3 install-crons.py --check            # dry-run
python3 install-crons.py --force            # re-install even if same version
```

**Idempotency:** Records installed version in `.cron-version` (gitignored). If version
matches template version, skips. Run with `--force` to force overwrite.

**Cleanup:** Removes existing jobs with matching names before creating fresh ones.
Duplicates are common when the installer runs multiple times without cleaning up
old jobs — `--force` handles this.

## Argument Order (Critical Pitfall)

The `hermes cron create` command requires the prompt to come RIGHT AFTER the schedule,
before any `--flags`:

```python
# ✅ Works
cmd = ["cron", "create", "0 9 * * 1", "Run eval", "--name", "weekly-task"]

# ❌ Fails — flags before prompt
cmd = ["cron", "create", "0 9 * * 1", "--name", "weekly-task", "Run eval"]
```

The `install-crons.py` handles this correctly. Shell scripts calling `hermes cron create`
directly must respect this order.

## Delivery for no_agent Crons

Always set `deliver: origin` (not `local`) so output goes to the agent's home channel:

```json
{ "name": "skill-miner", "script": "skill-miner", "no_agent": true, "deliver": "origin" }
```

With `deliver: local`, findings are stranded on the filesystem and never reach the user.

## Verification

```bash
hermes cron list | grep -E '(loop|weekly)'
```

If duplicates appear, run `install-crons.py --force` to clean up.
