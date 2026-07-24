# Loop Governance — Full Reference

> Detailed setup, scoring guidelines, and troubleshooting.
> Agents should follow the mandatory workflow in `AGENTS.md` for daily work.

---

## Interface: MCP tools vs CLI

| Situation | Use | Example |
|-----------|-----|---------|
| Agent before coding | `cache_search(query)` | `mcp_loop_governance_cache_search(query="build user auth")` |
| Agent session init | `config_show()` + `cycle_stats()` | At session start, query current thresholds + recent stats |
| Agent after a cycle | `feedback_accept(cycle_id=...)` / `feedback_override(cycle_id=..., ...)` | Confirm or correct the decision |
| Agent reviewing cycles | `cycle_query(task_id="...")` | Check what was scored for a task |
| Pre-commit hook | `score-cycle --task ... --pass-pct ...` | Runs automatically on `git commit` |
| Script/CI pipeline | `score-cycle --task ... --json` | Programmatic scoring without MCP |

## Per-change scoring flow

```
Before coding: cache_search(task_description) ← learn from past
[Coding work — RED-GREEN-REFACTOR or config change]
After verifying: cycle_query(task_id="story-name") ← review the cycle
                 feedback_accept / feedback_override ← train the model
```

## Multi-file changes — how to score

| Pattern | What to do |
|---------|------------|
| One logical change across N files | Score once. Use most representative file as `--code-file`. Describe scope in task name. |
| Independent changes in same session | Score each logical change separately with distinct task IDs |
| Config changes across 2+ files | Score once. Omit `--test-file`. `pass-pct 100` if verified. |

## Scoring guidelines by change type

| Change Type | `--test-file` | `--pass-pct` |
|---|---|---|
| Code change (TDD cycle) | Test file | Actual test pass rate |
| Config/IT change | N/A (omit) | 100 if verification passed, 0 if failed |
| Script edit | Any invocation that proves it works | 100 if ran without error |
| Deployment | Health check endpoint or proof of life | 100 if healthy |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `embedding failed` / `Ollama connection refused` | Ollama not running | `ollama serve` or `brew services restart ollama` |
| `Model nomic-embed-text:v1.5 not found` | Model not pulled | `ollama pull nomic-embed-text:v1.5` (274 MB) |
| `DB locked` | Concurrent score-cycle process | Wait and retry, or `rm ~/.hermes-cortex/data/loop-governance.db-journal` |
| `score-cycle not found` | Symlink missing | `bash ~/hermes-cortex/core/governance/setup.sh --symlinks-only` |
| `warning: all tests failed — score may be inaccurate` | Test suite broken | Fix tests first, then re-score |
| MCP tool returns `error` | MCP server not registered | `hermes mcp add --command python3 --args ~/hermes-cortex/mcp-servers/loop-gov-mcp.py loop-governance` |

**Fallback protocol:** If scoring is genuinely blocked (Ollama down, DB corrupt, network unreachable):
1. Diagnose with `bash ~/.hermes-cortex/tools/loop-governance/verify.sh`
2. If fix takes > 2 minutes, record the change manually by running `score-cycle` once the issue is resolved
3. Never skip entirely — the cron auditor will flag unscored changes

## Setup first time

```bash
# Full install — deps, symlinks, config, crons
bash ~/hermes-cortex/core/governance/setup.sh

# Register MCP server (so agents can use MCP tools)
hermes mcp add --command python3 --args ~/hermes-cortex/mcp-servers/loop-gov-mcp.py loop-governance

# Pull embedding model (required for scoring)
ollama pull nomic-embed-text:v1.5

# Deploy pre-commit hooks across all repos
bash ~/.hermes/scripts/install-score-hook.sh --all

# Verify everything
bash ~/.hermes-cortex/tools/loop-governance/verify.sh
```

**Dependencies:** Ollama + **nomic-embed-text:v1.5** (for scoring — the only model required). 274 MB. Run `bash core/governance/cleanup-ollama.sh` to remove unnecessary models and free disk space.

## Enforcement layers

| Layer | What | How to install | Bypass |
|-------|------|---------------|--------|
| **Governance enforcer plugin** | **Primary** — blocks write tools at Hermes runtime via `pre_tool_call` hook | `ln -sf ~/hermes-cortex/plugins/hermes-governance-enforcer ~/.hermes/plugins/` + `/reset` | `allow_tool_override: true` (human override in config) |
| **Survey-before-cron gate** (enforcer plugin) | Blocks `cronjob(action='create')` unless `.cron-survey-done` marker exists. Agent must run `cronjob(list)` + `search_files()` + `skills_list()` first. | Ships with enforcer plugin. Activated on next `/reset` after git pull. | N/A (structural — cannot bypass mid-session) |
| Pre-commit hook | Runs `score-cycle` on every `git commit` — now scores ALL staged files, not just the first. | `bash ~/.hermes/scripts/install-score-hook.sh --all` | `--no-verify` (logged to no-verify-audit cron) |
| **Verification-before-push gate** (pre-push hook) | Blocks `git push` unless `.verification-done` marker exists. Agent must test the change before pushing. | Ships with pre-push hook (re-deployed by `cortex-update.sh`). | `--no-verify` (logged to no-verify-audit cron) |
| Pre-push hook (secondary) | Pull-before-push check — blocks push if local `main` is behind `origin/main`. | Ships with pre-push hook. | `--no-verify` |
| SOUL.md directive | Rule appears in every Hermes session's system prompt | Edit `~/.hermes/SOUL.md` | Remove the directive |
| Cron auditor | `governance-auditor` scans every 6h for unscored changes + cleans stale locks (>12h) + now auto-scores unscoped files | Auto-created by `install-crons.sh` | N/A |
