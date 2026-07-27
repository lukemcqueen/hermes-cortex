# Agent Labels + Targeted Fleet Updates — Design Document

> **BUS-P0-3:** Canary deployments via agent metadata.
> Priority: 🔴 P0 (enables staged rollouts). Effort: 4 hours.

## Problem

Fleet updates (`UPDATE_REQUEST`) are all-or-nothing. Moses sends to every agent
simultaneously. A bad update crashes every agent at once. There is no canary
deployment, no A/B test, no staged rollout.

## Solution

Add metadata labels to agents and allow Moses to target updates by label.

### Agent Labels

Each agent has a JSON `labels` map stored in `bus.permissions.labels`:
```json
{
  "group": "canary",
  "region": "us-east-1",
  "os": "linux",
  "owner": "luke"
}
```

Labels are: flat key-value strings, set by the operator, used for routing only.

### UPDATE_REQUEST Targeting

Add two optional fields to the UPDATE_REQUEST body:

| Field | Type | Description |
|-------|------|-------------|
| `target_labels` | map[string,string] | Must match all specified labels |
| `target_agents` | string[] | Exact agent name list |

When either is present, agents check for a match before processing.
When neither is present, all agents process (current behavior).

### Agent-Side Implementation

In `agent-message-handler.py`:

```python
def _should_process(body, agent_name, agent_labels):
    """Check if this update targets this agent."""
    target_agents = body.get("target_agents")
    target_labels = body.get("target_labels", {})
    
    # If nothing specified, all agents process (backward compat)
    if not target_agents and not target_labels:
        return True
    
    # Check exact agent match
    if target_agents and agent_name in target_agents:
        return True
    
    # Check label match (all must match)
    if target_labels and agent_labels:
        for key, value in target_labels.items():
            if agent_labels.get(key) != value:
                return False
        return True
    
    return False
```

### Agent Labels API

```bash
# Set labels
hermes cortex agent label set gisu group=canary region=us-east-1

# Remove a label
hermes cortex agent label unset gisu region

# Show labels
hermes cortex agent label show gisu

# List all agents with labels
hermes cortex agent list --show-labels
```

Labels are stored in `bus.permissions.labels` and cached in the
agent's local `cortex-bus.conf` (or a companion `.labels` file)
so the `agent-message-handler.py` can read them without bus access
for label checks.

### Fleet Update Flow with Canary

```
1. Moses sends UPDATE_REQUEST to 100 agents
   target_labels: {group: canary}
   
2. 10 canary agents (group=canary) process the update
   90 general agents (group=general) skip, respond "label_mismatch"

3. Moses verifies all 10 canary agents reported success

4. Moses sends UPDATE_REQUEST to all 100 agents
   (no target_labels = all process)
```

### Files Changed

| File | Action |
|------|--------|
| `ops/scripts/agent/agent-message-handler.py` | Add label check logic |
| `ops/scripts/manage/cortex-agent-manager.py` | Already includes label subcommands |
| `docs/fleet-update-protocol.md` | Document `target_labels` and `target_agents` |
