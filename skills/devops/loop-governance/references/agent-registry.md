# Agent Registry

The agent registry at `src/agent-registry.json` defines all agents in the fleet.
It is used by the cron installer, health monitor, and any tool that needs to know
which agents are server-reachable vs client-only.

## Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Agent name (moses, titus, gisu, joseph, kustos) |
| `role` | string | Functional role (orchestrator, operations, developer, etc.) |
| `hostname` | string | Machine hostname (used for orchestrator detection) |
| `host` | string | Optional: public IP address |
| `is_server` | boolean | True if this machine runs as a persistent server |
| `is_orchestrator` | boolean | True only for Moses — the orchestrator |
| `accessible` | boolean | True if reachable via API (server agents only) |
| `health_url` | string | Optional: health endpoint URL for polling |
| `platform` | string | Optional: linux, macos, windows |
| `description` | string | Human-readable description |

## Current Agents

| Agent | Hostname | Server? | Accessible? | Role |
|-------|----------|---------|-------------|------|
| Moses | moses-server | Yes | Yes | Orchestrator |
| Gisu | cisnet03 | Yes | Yes | Operations |
| Joseph | joseph-server | Yes | Yes | Web/Infra |
| Kustos | kustos-server | Yes | Yes | Security |
| Titus | LAM2 | No | No | Developer (client-only) |

## Usage

The `install-crons.py` script reads this file to determine if the local machine is
the orchestrator. The `agent-team-health-monitor.py` reads it to know which agents
to poll and which to skip.

```python
import json, os
from pathlib import Path

registry = json.loads(Path("src/agent-registry.json").read_text())
hostname = os.uname().nodename.lower()

# Find the orchestrator
orchestrator = next(
    (e for e in registry["agents"] if e.get("is_orchestrator")), None
)
am_i_orchestrator = orchestrator and orchestrator["hostname"] in hostname

# Find server agents to poll
server_agents = [
    e for e in registry["agents"]
    if e.get("accessible") and e.get("health_url")
]

# Find client-only agents (skip for API polling)
client_agents = [
    e for e in registry["agents"]
    if not e.get("accessible")
]
```
