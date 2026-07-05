---
name: inbox-remediation
description: "Auto-remediate hermes-cortex issues reported by peer agents via the agent inbox. Scans pending remediation markers every 10 minutes, reads the original message, applies the fix, and marks the request as done."
version: 1.0.0
author: Moses
license: MIT
metadata:
  hermes:
    tags: [cron, remediation, inbox, multi-agent, auto-fix]
    related_skills: [orch-weekly-auto-fix, agent-inbox, public-contribution]
---

# Moses Inbox Remediation

## When to Use

Load this skill when:
- Setting up the orch-process-agent-messages cron
- Other agents need to report hermes-cortex issues and have them auto-fixed
- You want a multi-agent auto-remediation pipeline

## Architecture

```
[Peer Agent] sends message to inbox topic → general/luke/all/<agentname>
    ↓
[orch-team-messages.sh] runs every 10m (no_agent)
    ↓  Detects keywords: error, failed, broken, crash, help, etc.
    ↓  Writes remediation marker to ~/.hermes/state/remediate/
    ↓
[orch-inbox-remediate.sh] companion script (no_agent)
    ↓  Reads markers + original messages
    ↓  Outputs structured JSON: [{sender, subject, body, marker_file}]
    ↓
[orch-process-agent-messages] LLM-driven cron every 10m
    ↓  Reads companion script output
    ↓  Applies fix using terminal/web tools
    ↓  Runs orch-weekly-auto-fix.py as safety net
    ↓  Moves marker to remediate/done/
    ↓  Commits private repo state
    ↓
[Reports to user] — compact summary of what was fixed
```

## Setup

### 1. Deploy the companion script

```bash
cp hermes-cortex/scripts/orch-inbox-remediate.sh ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/orch-inbox-remediate.sh
```

### 2. Create the orch-process-agent-messages cron

```bash
hermes cron create \
  --name "orch-process-agent-messages" \
  --schedule "every 10m" \
  --prompt "$(cat << 'PROMPT'
You are Moses, the orchestration mind of Hermes. This is your agent message processor.

## Step 1: Check for pending remediation markers

Run the companion script:
```bash
~/.hermes/scripts/orch-inbox-remediate.sh
```

If output is `[]`, respond with `[SILENT]` — nothing needs remediation.

## Step 2: Process each pending item

For each item in the JSON array, you have:
- sender, subject, body (full message), marker_file (path)

Read the message body carefully to understand what needs fixing.

## Step 3: Fix it

Use terminal and web tools. Check git, Docker, permissions, missing files.
Run orch-weekly-auto-fix.py as a safety net:
```bash
python3 ~/.hermes/scripts/orch-weekly-auto-fix.py --verbose
```

## Step 4: Mark remediation as done

```bash
mkdir -p ~/.hermes/state/remediate/done
mv <marker_file_path> ~/.hermes/state/remediate/done/
cd ${CORTEX_REPO:-$HOME/hermes-cortex}-private && git add -A && git commit -m "remediation: ..." && git push
```

## Step 5: Report compact summary
PROMPT
)" \
  --enabled-toolsets terminal,file,web
```

### 3. Ensure the message detector is running

The existing `orch-team-messages.sh` cron (every 10m, no_agent) handles step 1 of the pipeline — detecting new messages and writing remediation markers. Verify it's active:

```bash
hermes cron list | grep orch-team-messages
```

If not present, create it:
```bash
cp hermes-cortex/scripts/orch-team-messages.sh ~/.hermes/scripts/
hermes cron create --name "orch-team-messages" --schedule "every 10m" --script "orch-team-messages.sh" --no-agent --deliver origin
```

## Detection Keywords

The `orch-team-messages.sh` script flags messages containing these keywords in the subject or body:

- error
- failed
- crash
- down
- help
- broken
- stuck
- not working
- issue
- problem
- script failure

Messages in broadcast topics (luke, all, general, <agentname>) trigger remediation markers. Non-broadcast topics are Moses-direct messages (moved to processed/ without remediation).

## SLA

| Step | Interval | Worst Case |
|------|----------|------------|
| Message detection | every 10m | ~10 min |
| Remediation processing | every 10m | ~10 min |
| Total from send to fix | — | ~20 min |

Since both agents run every 10m on offset schedules, practical worst case is ~10 minutes — the next tick of either job catches the new message.

## Pitfalls

- **Marker files without corresponding inbox messages.** If the private repo's inbox is cleaned before the processor runs, the marker will point to a non-existent file. The script handles this gracefully (empty body).
- **Don't re-process old markers.** The companion script only reads `remediate/` root — files in `remediate/done/` are ignored.
- **Git push may fail due to remote changes.** The processor should attempt the push but not fail if it can't — the remediation is local state.
- **The cron needs terminal + file + web toolsets.** Without `terminal`, it can't run git/Docker commands. Without `file`, it can't read the marker files.
- **Credentials in message bodies.** Never put secrets in inbox messages — they're plaintext in git history. The remediation processor reads the body to understand the issue, but secrets should never be there in the first place.
