# Cron Delivery Pipeline — Understanding Modes & [SILENT] Protocol

> **Lesson from production:** An agent once saw a cron's output going to the wrong place, assumed it was an unconfigurable property of LLM-driven mode, and switched the cron to `no_agent` mode — changing the engine instead of fixing the delivery. This document exists to prevent that.

## The Two Modes

### `no_agent` mode (watchdog)
- Script runs on schedule; its stdout IS the message
- `no_agent=True`, the prompt is ignored
- Empty stdout + exit 0 → **silent** (nothing delivered, no notification)
- Non-empty stdout → delivered verbatim as the message
- Non-zero exit / timeout → error alert delivered

### LLM-driven mode (default)
- An agent session starts every tick with the full prompt context
- The agent **reasons and outputs** — tokens are consumed
- The agent's **final response** is the delivery content
- No built-in "silent on success" — if the agent writes anything, it's delivered
- **HOWEVER:** the agent can output exactly `[SILENT]` (with brackets, all caps) to suppress delivery

## The [SILENT] Protocol

When an LLM-driven cron has nothing to report (everything is healthy, no new data, nothing changed):

```
Your response: [SILENT]
```

The Hermes cron scheduler detects this exact string and **drops the delivery** — nothing is sent to the user. No notification, no log noise.

Used by: agent-auto-remediate, agent-fixer-* crons, and any LLM-driven cron that should only notify when there's something to act on.

### Rules
- Must be the **only content** in the response (trimmed)
- Must be exactly `[SILENT]` (case-sensitive, brackets included)
- `[SILENT] and then some text` → NOT silent, delivered as-is
- `[silent]` (lowercase) → NOT silent, delivered as-is

## When to Change Modes

| Current symptom | Likely fix | NOT the fix |
|---|---|---|
| Delivery going to wrong chat | Change `deliver` parameter | Changing `no_agent` ↔ LLM-driven |
| Cron outputting noise on every tick | Use [SILENT] for LLM-driven, or silent-on-success pattern for no_agent | Switching modes |
| Script-only task (no AI needed) | `no_agent=True` is correct | Using LLM-driven for a script-only job |
| Cron needs reasoning (filter, summarize, decide) | LLM-driven is correct | Switching to no_agent just to change delivery |

### Diagnostic checklist — before changing the mode

1. **Is the issue about delivery target or delivery volume?**
   - Wrong channel → change `deliver` parameter
   - Too much output → implement [SILENT] or silent-on-success
   - Never delivered → check cron's `last_status` and `last_delivery_error`

2. **Is the cron already running correctly except for delivery?**
   - If `last_status: ok` and the script/logic works, the engine is fine
   - Only the delivery configuration needs adjustment

3. **Do I understand how the current mode delivers output?**
   - `no_agent`: script stdout = message (empty = silent)
   - LLM-driven: agent response = message (`[SILENT]` = silent)
   - If unsure, survey before changing — or ask

## The Rule

> **Never change the engine when the complaint is about delivery.**

- Delivery is a configuration concern (`deliver` parameter, [SILENT] protocol, silent-on-success pattern)
- Mode (no_agent vs LLM-driven) is an architecture concern (does the task need AI reasoning?)
- Mixing the two is the most common and most expensive mistake in cron management
