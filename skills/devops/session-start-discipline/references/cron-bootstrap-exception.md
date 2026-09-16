# Cron Bootstrap Exception to .skills-loaded Rule

## The Rule

Interactive sessions: you must NEVER `touch ~/.hermes-cortex/state/.skills-loaded`.
The enforcer auto-creates this marker when all 8 always-section skills have
been loaded via actual `skill_view()` calls. A bare `touch` creates an empty
file that fails content verification.

## The Exception

**Non-interactive sessions** (`cron_*` and `bg_*` session IDs) are handled
differently. The enforcer's `_on_session_start` hook auto-creates the
`.skills-loaded` marker at session initialization — before any tool call — by:

1. Reading `~/.hermes-cortex/skills.yaml` for the `always` section
2. Verifying each required skill has a `SKILL.md` file on disk under
   `~/.hermes/skills/`
3. If all skills are present, calling `_auto_create_skills_marker()` with the
   session ID — same function used when all `skill_view()` calls succeed

This is NOT a bypass. The bootstrap:
- Only activates for non-interactive session IDs (`cron_`/`bg_`, via
  `_session_type()`) — interactive sessions unaffected
- Validates all skills exist on disk before creating the marker
- Uses the same session-verified marker format (`session:{session_id}`)
- Is as tight as the interactive path (both verify skill presence)

## Why This Exists

Cron/bg sessions start fresh with no `.skills-loaded` marker. The enforcer
blocks all write tools until skills are loaded. But non-interactive agents may
not have `skill_view()` in their tool registry (depends on platform/provider),
creating a bootstrapping deadlock. The bootstrap path is the only way to
break this cycle without reducing security for interactive sessions. The guard
covers the full non-interactive class (`cron_` + `bg_`) because both may have
`enabled_toolsets` that exclude the skills toolset entirely (Titus terminal
deadlock, 2026-09-16).

## Implementation

See `plugins/governance-enforcer/__init__.py`:
- `_on_session_start()` — calls `_bootstrap_cron_skills()` for non-interactive
  sessions (`_session_type(session_id) in ("cron","bg")`)
- `_bootstrap_cron_skills()` — verifies skills.yaml + SKILL.md on disk
- Session-type detection: `_session_type()` (cron_/bg_ → non-interactive)
