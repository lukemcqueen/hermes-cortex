# Cron Path ≠ Deploy Path — the Two-Directory Trap

**Confirmed 2026-07-31** while verifying a NameError fix in
`orch-bus-forwarder.py` (cron `orch-bus-forwarder-sync`, every 2m).

## The Trap

| Directory | Who writes it | Who reads it |
|-----------|---------------|--------------|
| `~/.hermes-cortex/scripts/` | `cortex-update.sh` `register()` deploys fresh code here | Doctor checks, `diff` against repo |
| `~/.hermes/scripts/` | **NOT updated by deploy** | **The cron runner executes from here** (`HERMES_HOME/scripts`, scheduler.py) |

The intended bridge is a directory symlink `~/.hermes/scripts →
~/.hermes-cortex/scripts/`, created at the end of cortex-update.sh. It is
**skipped** when `~/.hermes/scripts/` contains files not present in the
deploy dir — the script warns `~/.hermes/scripts/ has unique files: ... —
not replacing`. Local-only scripts routinely block it: `remediation-sensor.py`,
`inbox-sensor.py`, `bus-sensor.py`, `local-*.sh`, `agent-daily-bible-reading.py`.

## Why the Doctor Misses It

The doctor's staleness checks compare repo vs `~/.hermes-cortex/scripts/`
(which cortex-update keeps fresh), so it reports PASS. It does NOT compare
repo vs `~/.hermes/scripts/` — the directory the cron actually executes.

## Symptom

You deploy a fix, verify the deployed file matches repo, but the cron keeps
running old behavior. In the 2026-07-31 case: `orch-fleet-watchdog.py` was
updated to decode `{"v": [...]}` health vectors, but the cron ran the Jul 17
copy — fleet-state showed `ok=False` for every agent because the stale
watchdog couldn't parse the vector payloads, and real health degradation was
silently masked. The fleet watchdog was BLIND and nobody knew.

## Detection

```bash
# 1. Did the cron's own output change after your deploy?
ls -t ~/.hermes/cron/output/<job-id>/*.md | head -5   # check Status lines

# 2. Compare the two script dirs (NOT repo — deployed files carry a
#    "# SOURCE:" header so repo-diff always reports drift):
diff ~/.hermes/scripts/<script> ~/.hermes-cortex/scripts/<script>

# 3. Is the bridge symlink present?
ls -la ~/.hermes/scripts        # should be "-> ~/.hermes-cortex/scripts"

# 4. What blocks it?
comm -23 <(cd ~/.hermes/scripts && ls *.py *.sh | sort) \
         <(cd ~/.hermes-cortex/scripts && ls *.py *.sh | sort)
```

## Fix (safe)

Copy SHARED scripts (present in both dirs, including the `manage/` subdir)
from `~/.hermes-cortex/scripts/` to `~/.hermes/scripts/`, plus any
cron-referenced script missing entirely from the cron dir:

```bash
cd ~/.hermes-cortex/scripts
for f in *.py *.sh; do
  [ -f ~/.hermes/scripts/$f ] && cp "$f" ~/.hermes/scripts/$f
done
mkdir -p ~/.hermes/scripts/manage && cp manage/*.py manage/*.sh ~/.hermes/scripts/manage/ 2>/dev/null
```

Then run the script FROM `~/.hermes/scripts/` to prove the cron path is
fixed, and confirm the next cron tick's output file flips to
`silent (empty output)`.

**Do NOT** `rm -rf ~/.hermes/scripts` to force the symlink: local-only files
include active cron scripts and would vanish, breaking those jobs.

## Governance Side-Effect

`cortex-update.sh` **purges governance locks on every run**. After a deploy:
1. `begin_change` again before further terminal work
2. Expect MULTIPLE pending cycles from re-acquires — query `cycle_query`
   and score ALL of them (`feedback_accept`) before `end_change`
3. Otherwise the doctor flags "PENDING cycles" as a FAIL
