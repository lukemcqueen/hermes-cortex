---
name: upstream-fix-watchdog
version: 1.0.0
description: Watch upstream for a bug fix to land; silent until fixed.
tags: [cron, watchdog, upstream, fix, fleet, pin, monitoring]
related_skills: [watchers, fleet-commands, cron-format-standard, hermes-cortex-maintenance]
---

# Upstream Fix Watchdog

When an upstream project (e.g. hermes-agent by NousResearch) ships a bug that
forces you to **pin a version and pause fleet update crons**, you need a cheap
watchdog that tells you the moment the fix lands — without nagging every day
while it's still broken.

Pattern proven 2026-08-25→28: `_stdio_children_dead()` inversion in
hermes-agent's `tools/mcp_tool.py` broke every stdio MCP call on all hosts.
Fleet pinned, paused `agent-hermes-update`, and a daily cron
(`check-hermes-upstream-fix`) watched upstream until the fix appeared, then
alerted with the exact fleet-action steps. Generalize this for every future
upstream pin.

## When to use

- Upstream bug forces a pin/pause; you want to know when it's safe to unpin
- A dependency you don't control may silently keep a known-bad state
- You need a "wake me up the day this changes" watch on a raw upstream file
- User asks for "a watcher for an upstream fix" / "notify me when X is fixed"

## Core design (all non-negotiable)

1. **Silent while bug present** — exit 0 with EMPTY stdout. `no_agent=true`
   cron watchdog pattern: empty stdout = silent tick, no delivery, no tokens.
2. **Notify exactly once** — marker file dedupes:
   `MARKER = ~/.hermes/state/<incident>-notified`; write it after first
   notify; skip future notifies if it exists.
3. **Fetch failure = LOUD error** — network/HTTP errors print
   `CHECK FAILED: ...` to stderr and exit 1, so a broken check can never go
   silent. A silent watchdog that stopped polling is worse than no watchdog.
4. **Conservative detection** — when the upstream file's structure changes so
   the marker can't be parsed, treat as "not fixed" (return False), never as
   "fixed". False-negative → one more day of silence; false-positive → wakes
   the fleet for nothing.
5. **Concrete buggy-marker anchor** — match the exact inverted line (e.g.
   `return True  # alive`), PLUS positive proof of the fix (e.g. the
   corrected `return False` path present, or the function deleted entirely).

## Script skeleton

```python
#!/usr/bin/env python3
"""Watchdog: notify when upstream <repo> fixes <bug>. Silent until then."""
import os, re, sys, urllib.request

DEFAULT_URL = "https://raw.githubusercontent.com/<org>/<repo>/main/<path>"
MARKER = os.path.expanduser("~/.hermes/state/<incident>-notified")
BUGGY_MARKER = "<exact buggy line>"
NOTIFY_TEXT = """🟢 UPSTREAM FIX DETECTED: <bug> is fixed on origin/main.
Fleet action:
  1. <unpin/update steps>
  2. <resume paused crons: hermes cron resume <job_id>>
  3. <verify: grep -c '<buggy-symbol>' <file> on each host>
  4. <remove the pin once all hosts verify clean>"""

def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-cortex-fix-watchdog"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")

def is_fixed(src: str) -> bool:
    # 1. Function/symbol absent entirely -> bug gone
    # 2. Extract the function body; if BUGGY_MARKER in body -> not fixed
    # 3. Else require positive proof (correct return path present)
    raise NotImplementedError  # per-incident logic

def main(argv):
    url = argv[0] if argv and argv[0].startswith("http") else DEFAULT_URL
    dry = "--dry-run" in argv
    try:
        src = fetch(url)
    except Exception as exc:
        print(f"CHECK FAILED: could not fetch {url}: {exc}", file=sys.stderr)
        return 1
    if not is_fixed(src):
        return 0  # silent
    if not dry and os.path.exists(MARKER):
        return 0  # already notified
    print(NOTIFY_TEXT)
    if not dry:
        os.makedirs(os.path.dirname(MARKER), exist_ok=True)
        open(MARKER, "w").write("notified\n")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Full working example: `~/.hermes/scripts/check-hermes-upstream-fix.py`
(2026-08-25 incident — real `is_fixed()` regex, marker handling, notify text).

## Cron wiring

```
hermes cron create --name <name> --schedule '0 9 * * *' \
  --script <name>.py --no-agent --deliver origin
```

- `no_agent=true` — script stdout IS the delivery; empty = silent tick
- Daily 09:00 is a sane cadence for upstream fixes (they don't land hourly)
- Test before enabling: `python3 <script>.py --dry-run` (must print the
  notify text but NOT write the marker), then `python3 <script>.py` once with
  the marker deleted to see a real tick
- When the fix fires and the fleet converges, **pause the cron**
  (`cronjob(action='pause')`) — the job is done; don't let it tick
  pointlessly forever. Keep the script for the next incident.

## When the fix fires — fleet convergence playbook

1. **Verify on the authoritative source first** — `git fetch origin && git
   log --oneline -1 origin/main` or curl the raw file and eyeball the diff.
   The watchdog is a tripwire, not proof.
2. **Unpin / update on the orchestrator host first** (esther/moses), verify
   the service actually works (not just "command exited 0").
3. **Dispatch the fleet — ALWAYS, without asking** (Luke directive
   2026-08-28: *"always send for these types of updates. you never have to
   ask and it just wastes time actually"*). Do NOT pause to ask permission
   for a fix/update dispatch — it is the default, not a decision point.
   `orch-bus-fleet-dispatch.py --execute` (sync stale local
   agent-registry from the bus host first — see `fleet-commands` skill), or
   `hc send <agent> UPDATE_REQUEST ...`.
   Include ALL agents; the dispatch tool skips dev-agents — send those
   manually. When the registry's `health_url` is a stale placeholder
   (e.g. `your-domain.com`), `hc send` liveness refuses — use `--force`
   (the bus is the authoritative proof; verify against `bus.archives`).
   Verify UPDATE_RESULT `git_sha_after` on the AUTHORITATIVE bus
   (never the local mirror — it lags).
4. **Resume paused crons** — `hermes cron resume <job_id>` for each
   `agent-hermes-update`-class job paused during the incident.
5. **Verify per host** — `grep -c '<buggy-symbol>' <file>` = 0, or confirm
   the fixed logic.
6. **Pause the watchdog** (see Cron wiring above).

## Upstream update may ask "restore local changes now?" — decide by content

During `hermes update` the updater autostashes local changes and asks whether
to restore. Decide by content, not by default:

- `git stash show --stat stash@{0}` — see what's inside (working tree is
  clean when the stash exists, so status won't help)
- **Local workarounds are DELIBERATE here** (fleet preference): lean skill
  index, cost guard, max-cost preflight. Restore them — they're your
  environment protection, not accidental edits
- Check upstream first: `git show HEAD:<file> | grep -c <symbol>` — if
  upstream now HAS the functionality (e.g. a `lean` mode), the local patch
  may be partially redundant; restore anyway (semantics may differ)
- Conflict check: `git rev-list --count <stash-base>..HEAD -- <files>` — low
  count = safe; `git stash show -p stash@{0}` inspects WITHOUT mutating
- ⚠️ **`git stash apply` MUTATES the working tree** — it is NOT a dry run.
  To inspect: `git stash show -p stash@{0}`. Only `apply`/`pop` when you
  intend to restore. (Learned 2026-08-28: an "inspection" apply created a
  real conflict mid-update; restored via
  `git restore --source=HEAD --staged --worktree <files>` + `git rm --cached`
  for untracked stash files.)

## Pitfalls

- **The upstream "fix" may be incomplete — grep sibling call sites (2026-08-28).**
  The `_stdio_children_dead()` inversion was fixed upstream, but the same
  feature's `_watch_stdio_children` probe still had its own coroutine-leak
  bug: `inspect.isawaitable(_watch_children())` INVOKES the async function,
  creating a never-awaited coroutine per MCP call (`RuntimeWarning: coroutine
  'MCPServerTask._watch_stdio_children' was never awaited`). On Titus this
  made loop-governance MCP calls fail silently — `begin_change` never
  completed, so the enforcer blocked ALL write tools "even for inspection."
  **Before trusting an upstream fix, grep the whole feature for the same
  flaw class** — a fix to one function often leaves siblings broken. See
  `references/mcp-tool-watch-probe-case.md` for the full reproduction.
- **Marker file must be per-incident** — reuse the same `<name>` for a new
  incident and the old marker suppresses the new notify. Name it after the
  incident (`upstream-hermes-fix-notified`), not generically.
- **Raw URL vs git clone** — `raw.githubusercontent.com` is the cheap fetch
  (single file, no auth, no clone). Only clone when you need the whole tree.
- **Don't trust `return True`/`False` alone** — the exact inverted line is
  the anchor; the fix's positive return path is the proof. Stubs that remove
  all returns are NOT fixes.
- **Delivery target `origin`** — one alert to the operator's DM is the
  point; don't fan out to every agent.
- **Keep the script after the incident** — the next upstream break is a
  5-minute edit (URL + marker + notify text), not a new build.
- **`set -euo pipefail` assignment trap** — if the script is bash and reads
  an optional file, terminate the fallback chain with `|| true` and gate on
  `[[ -n $VAR ]]` (see shell-scripting skill).

## Related

- `watchers` skill — feed polling with watermark dedup (RSS/JSON/GitHub
  issues); use for "new items" streams. This skill is for "did ONE specific
  bug get fixed" — marker dedup instead of watermark, silent-until-fixed
  semantics instead of new-item emission.
- `fleet-commands` — UPDATE_REQUEST dispatch + authoritative-bus verification.
