# 🦞 ClawMetry Setup

## What It Is

Real-time observability dashboard for Hermes Agent. Shows live agent thinking, session replays, token costs, cron job status, and more.

## Installation

```bash
pip install clawmetry
```

## Running

```bash
clawmetry --workspace ~/.hermes
# Opens at http://localhost:8900
```

## Dashboard Tabs

| Tab | What You See |
|-----|-------------|
| **Overview** | Agent health, heartbeat, autonomy score, spending, system health |
| **Flow** | Animated message/tool-call diagram |
| **Brain** | Live agent thinking stream |
| **Usage/Cost** | Token spend by model & session |
| **Sessions** | Full chat transcript replay |
| **Crons** | Scheduled job history & status |
| **Memory** | File browser with version history |
| **Alerts** | Budget caps, error triggers, webhook notifications |
| **Logs** | Real-time color-coded log streaming |
| **Skills** | Fidelity telemetry (healthy/unused/dead/stuck classification) |

## Notes

- **Free for local use.** Cloud sync $5/node/month (optional).
- Beta Hermes support — reads from `~/.hermes/` session data.
