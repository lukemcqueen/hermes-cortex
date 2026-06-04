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
├── install.sh      # 🚀 Full-system installer
└── plans/          # Agent-generated plans & roadmaps
```

## 🔧 Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| **Agent Runtime** | [Hermes Agent](https://hermes-agent.nousresearch.com) | Self-improving autonomous agent |
| **Observability** | [ClawMetry](https://clawmetry.com) | Real-time dashboard for agent activity |
| **Memory** | [GBrain](https://github.com/garrytan/gbrain) | Long-term persistent knowledge graph |
| **Code** | GitHub | Version-controlled config, skills & brain |

## 🚀 One-Command Install

```bash
# Clone the cortex
git clone https://github.com/fleet-operator/hermes-cortex.git ~/hermes-cortex

# Run the installer (safe to re-run — it's idempotent)
bash ~/hermes-cortex/install.sh

# ⚡ Then give your Hermes agent the prompt it prints out
# to set up cron jobs and activate the /brain command
```

### What `install.sh` does

| Step | What | Why |
|------|------|-----|
| 1 | **Ollama** | Local LLM server for free embeddings |
| 2 | **Bun** | JavaScript runtime for gbrain |
| 3 | **gbrain** | Persistent knowledge brain (PGLite, zero-config) |
| 4 | **Brain dirs** | `~/brain/{default,…}` with MECE directory schema |
| 5 | **gbrain sync** | Launchd daemon — syncs brain every 2 minutes |
| 6 | **ClawMetry** | Dashboard at `localhost:8900` |
| 7 | **`/brain` plugin** | Hermes slash command for gbrain queries |
| 8 | **Scripts** | `heartbeat.py` + `memory-to-brain.py` |
| 9 | **Plugin enable** | Auto-activates in Hermes config |
| 10 | **Cron prompt** | Instructions for Hermes agent setup |

### Configuration

Set these environment variables before running for a custom setup:

```bash
export CORTEX_SOURCES="me,shared,default"   # Brain source names (default: "default")
export CORTEX_HOME="$HOME"                  # User home directory
export HERMES_HOME="$HOME/.hermes"          # Hermes config directory
export CORTEX_USER="$USER"                  # Your name for plugin metadata
```

### Multi-Person Setup

The installer supports any number of brain sources. For a two-person household:

```bash
export CORTEX_SOURCES="luke,amy,shared,default"
bash ~/hermes-cortex/install.sh
```

This creates isolated sources (`luke`, `amy`), a federated shared source (`shared`), and a default. The `/brain` slash command adapts to whatever sources you configure.

## 🎯 Philosophy

**Thin harness, fat skills.** The agent is the runtime — the real value lives in well-crafted skills, persistent memory, and deep observability. Every tool, config tweak, and workflow is tracked here so nothing is ever lost.

---

*Built by [@fleet-operator](https://github.com/fleet-operator) · Powered by 🦞 Hermes Agent*
