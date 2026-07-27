# Bootstrap + Incremental Data Collection

## Pattern

For any data source that takes a long time to fully process the first time,
use a two-phase approach: **bootstrap all history on first run, then
incremental after.**

## Implementation

```python
state["collection_bootstrap_done"] = state.get("collection_bootstrap_done", False)
days = 365 if not state["collection_bootstrap_done"] else 1

cmd = ["source-tool", "process", "--days", str(days), "--auto"]

# After successful run, mark bootstrap complete
state["collection_bootstrap_done"] = True
```

## Example: session-mine in agent-learning-collector

The collector runs every 6h on every agent. First execution:

```
session-mine mine --days 365 --auto   → mines ALL past sessions
state["session_mining_bootstrap_done"] = True
```

Subsequent executions:

```
session-mine mine --days 1 --auto   → only today's sessions
```

## Requirements

- The data source tool must support a `--days` flag
- The collector must persist state between runs (JSON state file)
- The bootstrap flag must be tracked in the state file, not derived (e.g.
  checking file counts fails if the source is legitimately empty)
- Error handling: if bootstrap fails, DO NOT set the flag — retry on next
  run. If incremental fails, log WARN and continue (old data is stale but
  not critical)

## When to use

| Signal | Don't bootstrap |
|--------|----------------|
| Processing takes >30s on first run | Source has <100 items |
| Source has years of accumulated data | Source has <1 day of data |
| Processing depends on external service (LLM, API) that's expensive | Source is a local deterministic scan |

## Anti-pattern

Do NOT use bootstrap on sources that auto-purge or rotate (logs, temp
sessions). Only use it on archival data where history genuinely matters.
