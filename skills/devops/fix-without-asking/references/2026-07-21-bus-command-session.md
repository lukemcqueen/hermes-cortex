# Bus Command Session — 2026-07-21

## What Happened

Session goal: test sending bus commands to agents and getting responses back.

### Failure Sequence

1. **Sent COMMAND messages with hc send** but used `subject: "COMMAND:health-check"` instead of the protocol's `subject: "EXEC"`. Agents archived them as unknown subjects. **Lesson: use the right subject.**

2. **Archived test messages before agents could process them.** Joseph, Gisu, Titus messages were archived before their handlers polled. **Lesson: let the round-trip complete before cleaning up.**

3. **Tested on Esther before testing locally.** Esther's handler picked up the EXEC but couldn't complete because of connectivity/auth issues. Wasted 10+ minutes debugging remote. **Lesson: test on self before fleet.**

4. **Removed handler cron but didn't update doctor's expected list.** Doctor reported ❌ Crons missing: agent-message-handler. **Lesson: any cron removal must also update install-crons.sh uninstall array.**

5. **Focused on "backlog" instead of fixing the one-per-tick design.** Called the symptom (messages piling up) the problem instead of the root cause (handler processes 1 msg per 5-min tick). **Lesson: fix root causes, not symptoms.**

### Timeline

| Time | Event |
|------|-------|
| 08:46 | Sent COMMAND messages via hc send — wrong format |
| 08:49 | Esther consumed the message (processing state) but never completed |
| 08:50 | Sent EXEC to self — tested locally |
| 09:00 | hc exec sent EXEC with proper format. Handler picked it up. |
| 09:09 | Handler processed EXEC, returned EXEC_RESULT. Round-trip confirmed. |
| 09:31 | Removed agent-message-handler cron from Moses |
| 09:32 | Doctor FAIL — missing cron expected |
| 09:44 | Fixed install-crons.sh uninstall array. Doctor clean. |
| 18:39 | Final successful local round-trip: EXEC → handler → EXEC_RESULT → Telegram notification |

### What Was Built

- `agent-message-handler.py`: Telegram notifications (📥 pickup, ✅/❌ completion)
- Idempotency archive fix: archive on skip instead of leaving infinite loop
- `hc exec` usage pattern: sends EXEC, polls inbox_moses for result

### Skills Updated

- **fix-without-asking**: "Complete the Full Cycle" section, "Doctor-Clean Requirement", "Local Test Before Fleet"
- **change-checklist** (devops): already had Phase 5 doctor check (no update needed)

### What Still Needs Work

- Handler processes 1 msg per 5-min tick → needs drain-all fix for fleet agents
- Esther's handler couldn't connect back to bus — unknown cause (maybe forwarder/paused)
- `hc exec` doesn't archive the EXEC_RESULT after finding it (leaves it in inbox)
