# 🏗️ Hermes Cortex Architecture

## Overview

```
  You (Telegram/CLI)
       │
       ▼
┌─────────────────────┐     ┌─────────────────┐
│   Hermes Agent      │────▶│   ClawMetry     │
│   (Runtime)         │     │   (Dashboard)   │
│                     │     │   localhost:8900 │
│  • Tools & Skills   │     └─────────────────┘
│  • Cron Jobs        │
│  • Memory           │     ┌─────────────────┐
│  • Subagents        │     │   GBrain        │
│                     │────▶│   (Memory Graph)│
└─────────────────────┘     └─────────────────┘
```

## Layers

| Layer | What | Why |
|-------|------|-----|
| **Agent** | Hermes Agent | Self-improving runtime with learning loop, subagents, cron |
| **Observability** | ClawMetry | Real-time dashboard: live trace, session replay, costs, cron history, alerts |
| **Memory** | GBrain *(planned)* | Long-term knowledge graph via Markdown + hybrid search |
| **Config** | GitHub | Version-controlled skills, configs, and workflows |

## Design Principles

1. **Thin harness, fat skills** — The agent framework stays lean; the value lives in well-crafted skills and memory
2. **Visibility first** — Every agent action should be observable, traceable, and auditable
3. **Persistence by design** — Nothing is lost. Config, skills, and memory are version-controlled
4. **Self-improving loop** — The agent creates skills from patterns, optimizes them over time
