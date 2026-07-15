# Loop Governance Integration Template

> **⚠️ TWO HARD RULES — Every Agent Must Follow**
>
> **RULE 1: USE LOOP GOVERNANCE ALWAYS**
> Every code/config/cron change REQUIRES: `begin_change` → work → `cycle_query` → `feedback_accept/override` → `end_change`. No exceptions. If `end_change` rejects, confess and force-clear — never silently skip the loop. The MCP server blocks write tools without an active lock — this is enforced at the tool level, not optional.
>
> **RULE 2: SHARE IMPROVEMENTS TO THE PUBLIC REPO**
> Every improvement you make that benefits other agents MUST go into the `hermes-cortex` repo — template files, skills, scripts, docs, config patterns. Not just your local profile. The repo is how every agent benefits from each other's work. If you built something useful, upstream it.

Copy this section into your project's `AGENTS.md` to adopt loop-governance
scoring. See `~/hermes-cortex/docs/loop-governance-reference.md` for the full reference.

---

## Enforcement Hierarchy

Scoring enforcement has two layers:

1. **MCP server (primary)** — `loop-gov-mcp.py` blocks write tools (`write_file`, `patch`, `terminal`, `skill_manage`, `cronjob`) unless `begin_change()` created an active governance lock. **This is unbypassable.** Agents cannot write files or create crons without calling `begin_change()` first.

2. **Pre-commit hook (secondary logger)** — runs `score-cycle --json` on every `git commit` for data collection. Optional for enforcement but useful for keeping the scoring DB populated.

See the `loop-governance` skill for the full four-layer model.

## Rule: Score every change

Every change — code, config, script, or deployment — must be logged to the
loop-governance DB. Two paths:

**Path A — MCP tools (PRIMARY — enforced by the MCP server):**
- Before coding: `mcp_loop_governance_begin_change(task_id="<task>", description="...")`
- `mcp_loop_governance_cache_search(query="task description")` — learn from past
- After change: `mcp_loop_governance_cycle_query(task_id="<task>")`
- Provide feedback: `mcp_loop_governance_feedback_accept(cycle_id=N)`
  or `mcp_loop_governance_feedback_override(cycle_id=N, correct_decision="...", note="...")`
- Release lock: `mcp_loop_governance_end_change(task_id="<task>")`

**Path B — CLI tools (secondary, for manual scoring or script use):**
```bash
score-cycle --task <project>-<feature> --cycle 1 \
  --code-file path/to/main/file \
  --pass-pct 100
```

For changes with no tests, use `pass-pct 100` if verification succeeded,
`pass-pct 0` if it failed. No exceptions — without this data the system
cannot self-improve.

## Session initialization

At the start of every session, run:

```python
mcp_loop_governance_config_show()           # check thresholds
mcp_loop_governance_cycle_stats(days=7)     # review scoring health
mcp_loop_governance_cache_search(query="<current task>")  # learn from past
```

## Multi-file changes

| Pattern | What to do |
|---------|------------|
| One logical change across N files | Score once. Most representative file as `--code-file`. |
| Independent changes in same session | Score each with distinct task IDs. |
| Config changes across 2+ files | Score once, omit `--test-file`. |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Ollama connection refused | `ollama serve` or `brew services restart ollama` |
| nomic-embed-text:v1.5 not found | `ollama pull nomic-embed-text:v1.5` |
| score-cycle not found | `bash ~/hermes-cortex/core/governance/setup.sh --symlinks-only` |
| MCP tool returns error | `hermes mcp add --command python3 --args ~/hermes-cortex/runtime/mcp-servers/loop-gov-mcp.py loop-governance` |

**Fallback:** If scoring is genuinely blocked, re-score once the issue is
resolved. Never skip permanently.

## Setup

```bash
# One-time (requires hermes-cortex cloned)
bash ~/hermes-cortex/core/governance/setup.sh
hermes mcp add --command python3 --args ~/hermes-cortex/runtime/mcp-servers/loop-gov-mcp.py loop-governance
ollama pull nomic-embed-text:v1.5
bash ~/.hermes/scripts/install-score-hook.sh --path $(pwd)
bash ~/.hermes-cortex/tools/loop-governance/verify.sh
```
