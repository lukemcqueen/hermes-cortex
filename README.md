# 🧠 Hermes Cortex

> *The config, skills, memory, and observability layer for a personal Hermes AI agent.*

**Version: 1.0.0** · ![GitHub](https://img.shields.io/github/license/fleet-operator/hermes-cortex) · [Hermes Agent](https://hermes-agent.nousresearch.com)

![Hermes Cortex](avatar.png)

**Hermes Cortex** is a self-contained system installer and public skill set for the [Hermes Agent](https://hermes-agent.nousresearch.com) runtime. It sets up:

- **Ollama** — Local LLM server (free embeddings)
- **Bun** + **GBrain** — Persistent knowledge brain (PGLite, zero-config)
- **ClawMetry** — Real-time observability dashboard (legacy)
- **Langfuse** — LLM trace evaluation and scoring (primary observability)
- **Cortex Dashboard** — Companion dashboard for Langfuse + system health
- **Brain directory structure** — MECE-organized knowledge sources
- **gbrain sync daemon** — Automatic 2-minute sync
- **Hermes plugin** — `/brain` slash command
- **Utility scripts** — Heartbeat watchdog, memory sync, system health

## 🚀 One-Command Install

```bash
# Clone the public system
git clone https://github.com/fleet-operator/hermes-cortex.git ~/hermes-cortex

# Run the installer (idempotent — safe to re-run)
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
| 6 | **Observability** | Langfuse + Cortex Dashboard + ClawMetry (legacy) |
| 7 | **`/brain` plugin** | Hermes slash command for gbrain queries |
| 8 | **Scripts** | Heartbeat, memory sync, Langfuse scoring, dashboard |
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

The installer supports any number of brain sources:

```bash
export CORTEX_SOURCES="luke,amy,shared,default"
bash ~/hermes-cortex/install.sh
```

This creates isolated sources, a federated shared source, and a default. The `/brain` slash command adapts to whatever sources you configure.

## 🗄️ Private Configuration

Personal config, secrets, API keys, and private skills live in a **separate private repo**:

```
git clone git@github.com:fleet-operator/hermes-cortex-private.git ~/hermes-cortex-private
```

This repository holds:

| What | Location |
|------|----------|
| Full personal config.yaml | `config/config.yaml` |
| Environment secrets (API keys, tokens) | `.env` (not committed) |
| Utility & monitoring scripts (13) | `scripts/` |
| Cortex Dashboard (Flask + JS) | `dashboard/` |
| nginx reverse proxy config | `nginx/` |
| Brain content | Private `brain-*` branches (not on `main`) |

After running the public installer, apply your private config:

```bash
cp ~/hermes-cortex-private/config/config.yaml ~/.hermes/config.yaml
# Source your .env, copy scripts, etc.
git clone git@github.com:fleet-operator/hermes-cortex-private.git ~/hermes-cortex-private
```

## 🎯 Philosophy

**Thin harness, fat skills.** The agent is the runtime — the real value lives in well-crafted skills, persistent memory, and deep observability. Every tool, config tweak, and workflow is tracked here so nothing is ever lost.

---

*Built by [@fleet-operator](https://github.com/fleet-operator) · Powered by 🦞 Hermes Agent · Version `v1.0.0`*
