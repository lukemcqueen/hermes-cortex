# Fleet Mitigation Playbook — Pinned Hosts & Update-Cron Disable (2026-08-25)

Companion to the stdio-children-dead case study. Covers what comes AFTER
pinning a host: disabling the update cron so the bug can't re-land, and
standing up a watchdog so the fleet knows when to un-pin.

## Why pinning alone is not enough

Every host registers `agent-hermes-update` (schedule `23 22 * * *`, runs
`hermes update -y`). For a git install that is `git pull origin/main` —
exactly the vector that drags a buggy main back onto a pinned host. On the
2026-08-25 incident, Titus's original infection (b85032fc) was almost
certainly pulled by this cron. The tick is within 24h, so pause BEFORE the
next scheduled run.

## Pause the cron on one host

```bash
hermes cron list | grep -B1 "Name:.*agent-hermes-update"   # ID is ABOVE the name
hermes cron pause <job-id>
```

**Pitfall A — grep direction:** `hermes cron list` renders each job as:

```
  195fa856001d [active]
    Name:      agent-hermes-update
```

The job ID is the line ABOVE "Name:". `grep -A1` (after) prints the Name
but cuts the ID; use `grep -B1` (before) to see it.

**Pitfall B — paused jobs vanish from the CLI:** after pausing, `hermes
cron list` shows NOTHING for the job (empty grep ≠ job gone). The `cronjob`
tool's list action is the source of truth: it reports `state: paused,
enabled: false` for the paused job. Always verify with the cronjob tool,
never with the CLI grep.

**Pitfall C — don't over-pause:** the adjacent `agent-hermes-cortex-sync`
cron (22:33) pulls the hermes-cortex repo, NOT hermes-agent — safe to
leave running. And `agent-hermes-update.sh` is the only deployed script
that runs `hermes update`; grep `~/.hermes/scripts/` to confirm no other
update vector exists.

**Pitfall D — resume later:** the cron is the fleet's update safety net.
Leaving it paused silently freezes hermes-agent versioning forever. Resume
it on every host once the upstream fix is verified.

## Daily upstream-fix watchdog (know when to un-pin)

A silent-until-fixed no_agent cron (zero tokens per tick) that fetches the
live origin/main file and greps for the buggy symbol:

```python
# ~/.hermes-cortex/scripts/check-hermes-upstream-fix.py (shape)
import os, re, urllib.request
URL = "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/tools/mcp_tool.py"
MARKER = os.path.expanduser("~/.hermes/state/upstream-hermes-fix-notified")
BUGGY = "return True  # alive"          # the inverted-return marker
# fetch → if BUGGY still in file: exit 0 SILENT
#         if fixed and no marker: print notification, write marker, exit 0
#         if fixed and marker exists: exit 0 silent (dedup)
#         on fetch exception: print error to stderr, exit 1 (alert — a
#         broken check must not go silent)
```

Register with the cronjob tool:

```
cronjob create --name check-hermes-upstream-fix --schedule "0 9 * * *" \
  --no_agent --script check-hermes-upstream-fix.py --deliver origin
```

Test BOTH paths before scheduling:
- real origin/main URL → expect silent, exit 0 (bug still present)
- clean tag URL (e.g. .../v2026.8.19/tools/mcp_tool.py) → expect the
  notification to fire
- confirm the marker file does NOT exist yet, so the first real fix notifies

The notification should carry the fleet action list: `hermes update` on all
hosts, resume paused crons, verify `grep -c <buggy-symbol>` = 0, remove the
pin.

## Fleet audit by upstream-commit (before/while pinning)

When multiple hosts report different "upstream" SHAs, audit each by file
content at that exact SHA (see case study). A host whose *running* HEAD is
clean can still be one `hermes update` away from the bug if its *upstream*
target SHA is buggy — the update-cron disable matters most for those hosts.
