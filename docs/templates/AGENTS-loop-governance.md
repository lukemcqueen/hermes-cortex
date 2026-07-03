# Loop Governance Integration Template

Copy this section into your project's `AGENTS.md` to adopt loop-governance
scoring. See `hermes-cortex/AGENTS.md` for the full reference.

---

## Rule: Score every change

Every change — code, config, script, or deployment — must be logged to the
loop-governance DB. Two paths:

**Path A — MCP tools (for agents with MCP access):**
- Before coding: `mcp_loop_governance_cache_search(query="task description")`
- After change: `mcp_loop_governance_cycle_query(task_id="<task>")`
- Provide feedback: `mcp_loop_governance_feedback_accept(cycle_id=N)`
  or `mcp_loop_governance_feedback_override(cycle_id=N, correct_decision="...", note="...")`

**Path B — CLI tools (for pre-commit hooks, scripts, shell):**
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
| score-cycle not found | `bash ~/hermes-cortex/src/loop-governance/setup.sh --symlinks-only` |
| MCP tool returns error | `hermes mcp add --command python3 --args ~/hermes-cortex/src/mcp-servers/loop-gov-mcp.py loop-governance` |

**Fallback:** If scoring is genuinely blocked, re-score once the issue is
resolved. Never skip permanently.

## Setup

```bash
# One-time (requires hermes-cortex cloned)
bash ~/hermes-cortex/src/loop-governance/setup.sh
hermes mcp add --command python3 --args ~/hermes-cortex/src/mcp-servers/loop-gov-mcp.py loop-governance
ollama pull nomic-embed-text:v1.5
bash ~/.hermes/scripts/install-score-hook.sh --path $(pwd)
bash ~/.hermes-cortex/tools/loop-governance/verify.sh
```
