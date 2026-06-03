# 🧠 Hermes Cortex

> *The config, skills, memory, and observability layer for my personal Hermes AI agent.*

![Hermes Cortex](avatar.png)

**Hermes Cortex** is the persistent brain and mission control for my autonomous AI agent. It holds everything that makes my agent smarter, more visible, and more capable over time.

## 🦞 What's Inside

```
hermes-cortex/
├── config/         # Hermes Agent configuration
├── skills/         # Custom skills & workflows
├── docs/           # Architecture & setup docs
├── .clawmetry/     # ClawMetry observability setup
└── plans/          # Agent-generated plans & roadmaps
```

## 🔧 Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| **Agent Runtime** | [Hermes Agent](https://hermes-agent.nousresearch.com) | Self-improving autonomous agent |
| **Observability** | [ClawMetry](https://clawmetry.com) | Real-time dashboard for agent activity |
| **Memory** | GBrain *(coming soon)* | Long-term persistent knowledge graph |
| **Code** | GitHub | Version control for agent config & skills |

## 🚀 Quick Start

```bash
# ClawMetry dashboard (local)
pip install clawmetry
clawmetry --workspace ~/.hermes
# → http://localhost:8900
```

## 🎯 Philosophy

**Thin harness, fat skills.** The agent is the runtime — the real value lives in well-crafted skills, persistent memory, and deep observability. Every tool, config tweak, and workflow is tracked here so nothing is ever lost.

---

*Built by [@fleet-operator](https://github.com/fleet-operator) · Powered by 🦞 Hermes Agent*
