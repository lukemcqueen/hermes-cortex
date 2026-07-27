# Automation Over Checklist

## Principle

When the user says "can you make this self-healing?" or "add this to skills," they mean: **build a cron or script that auto-detects and auto-fixes the issue, not just a checklist item.**

The hierarchy of responses to a recurring issue:

1. **Best** — Self-healing cron (e.g. `orch-skill-lifecycle` runs doctor and auto-fixes stale expected lists)
2. **Good** — Deterministic no_agent script (e.g. `agent-learning-collector` collects and sends without LLM)
3. **Fallback** — Checklist item in `change-checklist` (use only when automation is genuinely impractical)

## How to decide

| If | Then |
|----|------|
| Issue is detectible by a terminal command + parsable output | Build a no_agent cron or add detection to an existing one |
| Issue requires judgment to classify but the fix is deterministic | Build an LLM cron with terminal+file access (e.g. `orch-skill-lifecycle`) |
| Issue requires human judgment | Add to `change-checklist` |

## Examples from this session

| Issue | Approach | Why |
|-------|----------|-----|
| Stale cron entries in uninstall arrays causing doctor ❌ | Self-healing in `orch-skill-lifecycle` Phase 3 | Doctor detects → cron reads output → cron fixes uninstall array |
| AGENTS.md out of sync | Self-healing in `orch-skill-lifecycle` | Cron runs diff command → detects → syncs |
| Session mining not producing lessons | Added to `agent-learning-collector` Phase 0 | Deterministic: try `session-mine --auto`, skip if CLI absent |
