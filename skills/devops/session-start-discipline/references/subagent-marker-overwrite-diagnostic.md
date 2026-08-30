# Subagent Marker Overwrite Diagnostic

When `delegate_task` subagents overwrite the `.skills-loaded` marker, write
tools get blocked. Here's how to diagnose and recover.

## Symptoms

- ✅ `echo`, `pwd`, `whoami` work (fast commands pass before re-check)
- ❌ `python3 script.py`, `bash script.sh` get blocked (longer commands trigger re-check)
- `cat ~/.hermes-cortex/state/.skills-loaded` shows a session ID different from
  yours (the subagent's session)

The enforcer says "8/8 always-section skills loaded" immediately followed by
"session skills not fully loaded". This IS the marker-mismatch symptom.

## Recovery

```bash
# Confirm the mismatch
cat ~/.hermes-cortex/state/.skills-loaded
# → session:20260730_195730_2bebe5 (subagent)

# Re-establish your marker — call ANY loaded skill again
skill_view('session-start-discipline')
# The enforcer auto-creates the marker with YOUR session ID
```

## Prevention

Call `skill_view('<any>')` immediately before each `terminal()` call that
runs a long command (`python3`, `bash`, `curl`). A single skill_view call
triggers the enforcer's auto-create with your current session ID.
