# Session State: project_current_session.md

The `project_current_session.md` file at each repo root is the canonical session state persistence mechanism for hermes-cortex projects. It replaces the legacy `.agentkore/sessions/current.md` pattern.

## Why Not .agentkore/

- `.agentkore/` was an agentkore-specific dot-directory — migrating to hermes-cortex means removing agentkore artifacts entirely
- Cron jobs that write to `.agentkore/sessions/current.md` recreate the directory on every run, causing leftover artifacts even after cleanup
- `.agentkore/` files are gitignored — they're invisible to collaborators and lost on machine migration
- `project_current_session.md` is committed to git — visible to all contributors, survives machine changes

## Setup Pattern

1. Create `project_current_session.md` at repo root with Moses's template (see hermes-cortex repo for example)
2. Replace all cron job prompts that referenced `.agentkore/sessions/current.md` to write to `project_current_session.md` instead
3. Remove the `session-manager` skill dependency from cron jobs (it hardcodes the old path)
4. Remove legacy one-shot `session-update-*` jobs that target `.agentkore/`
5. Delete the `.agentkore/` directory after confirming no cron jobs recreate it

## Cron Job Pattern

```bash
# Create a recurring auto-save cron job:
hermes cron create \
  --name "auto-save-session" \
  --schedule "every 2h" \
  --prompt "Read project_current_session.md, check git activity, update the Recent Activity section." \
  --workdir /path/to/repo \
  --enabled_toolsets terminal,file
```

Key: toolsets should include `terminal` (for git commands) and `file` (for reading/writing the session file). No need for `session-manager` skill — the prompt is self-contained.

## Pitfalls

- **Cron jobs with old prompts will recreate .agentkore/ on next run** — always update the prompt, not just delete the directory. Verify by checking the job's prompt_preview.
- **One-shot session-update jobs** created during active work sessions should be removed after their prompts are updated. They're easy to miss because they expire quietly.
- **The agentkore repo itself** may have its own auto-save-session cron — update it to use project_current_session.md too.
