# 🧠 Hermes Cortex

> *An open-source installer and skill set for your personal Hermes AI agent.
> Privacy-first, offline-capable, built for non-technical users with an AI agent.*

**Version: 1.0.0** · ![GitHub](https://img.shields.io/github/license/lukemcqueen/hermes-cortex) · [Hermes Agent](https://hermes-agent.nousresearch.com)

![Hermes Cortex](avatar.png)

**Hermes Cortex** is a self-contained system installer and public skill set for the [Hermes Agent](https://hermes-agent.nousresearch.com) runtime. It sets up:

### Who is this for?

- **You want a personal AI agent** that runs on your own computer (no cloud dependency)
- **You care about privacy** — everything stays on your machine
- **You travel or have unreliable internet** — the offline stack works without connectivity
- **You're not a developer** — the one-command installer handles everything
- **You want observability** — see what your agent is doing with Langfuse tracing

### What you get

- **Ollama** — Local LLM server (free embeddings)
- **Bun** + **GBrain** — Persistent knowledge brain (PGLite, zero-config)
- **Langfuse** — LLM trace evaluation and scoring (primary observability)
- **Cortex Dashboard** — Companion dashboard for Langfuse + system health
- **Brain directory structure** — MECE-organized knowledge sources
- **gbrain sync daemon** — Automatic 2-minute sync
- **Hermes plugin** — `/brain` slash command
- **8 shared skills** — Subagent orchestration, debugging, TDD, planning, memory architecture, code review, spikes
- **Web Cache** — Local semantic cache for web search/extract results (sqlite-vec + Ollama embeddings). Reduces API costs, enables offline operation.
- **Offline Knowledge** — Cascade knowledge lookup: web-cache → kiwix ZIM (Wikipedia, WikiMed, Wikivoyage) → gbrain → LLM. Works identically online (saves API costs) and offline (no internet needed).
|- **Bible Content** — Download Bible translations in 55+ languages (KJV, WEB, Spanish, Korean, Arabic, Chinese, Russian, and more). Searchable via `offline_knowledge bible search`.
|- **Hymn Collection** — Public domain hymnody from the Open Hymnal Project: full hymnal PDF with scores, ABC music notation, MIDI audio, and searchable lyrics. Searchable via `offline_knowledge hymns search`.
- **Computer Specs Guide** — Hardware-aware recommendations for models and ZIM content bundles based on your RAM.
- **Pre-Flight Tool** — `prep-offline.sh` downloads ZIM content, seeds cache, starts kiwix-serve. One command to prepare for no-internet scenarios.
- **Utility scripts** — Heartbeat watchdog, memory sync, system health

## 🚀 One-Command Install

> **🔒 Before installing:** Read the [Security Guide](docs/SECURITY.md) to understand how your system is protected.

```bash
# Clone the public system
git clone https://github.com/lukemcqueen/hermes-cortex.git ~/hermes-cortex

# macOS — Server profile (default): full stack
bash ~/hermes-cortex/install.sh

# macOS — Laptop profile: lean, no Docker services
CORTEX_PROFILE=laptop bash ~/hermes-cortex/install.sh

# Linux — auto-detects systemd, apt/dnf/pacman
CORTEX_OS=linux bash ~/hermes-cortex/install.sh

# Windows — uses winget/choco + scheduled tasks (limited)
CORTEX_OS=windows bash ~/hermes-cortex/install.sh

# ⚡ Then give your Hermes agent the prompt it prints out
# to set up cron jobs and activate the /brain command
```

### What `install.sh` does

| Step | What | Why |
|------|------|-----|
| 0 | **System Check** | Verifies OS, RAM, disk, Docker, network, dependencies before touching anything |
| — | **OS Detection** | Auto-detects macOS/ Linux/Windows, sets package + service managers |
| 1 | **Ollama** (cross-platform) | Native installer per OS: brew cask / curl script / direct download |
| 2 | **Bun** | JavaScript runtime for gbrain |
| 3 | **gbrain** | Persistent knowledge brain (PGLite, zero-config) |
| 4 | **Brain dirs** | `~/brain/{default,…}` with MECE directory schema |
| 5 | **gbrain sync** | Launchd daemon — syncs brain every 2 minutes |
| 6 | **Observability** † | Langfuse + Cortex Dashboard |
| 7 | **`/brain` plugin** | Hermes slash command for gbrain queries |
| 8 | **Scripts** | Heartbeat, memory sync, Langfuse scoring, dashboard |
| 9 | **Plugin enable** | Auto-activates in Hermes config |
| 10 | **Skills** | 8 shared skills installed to `~/.hermes/skills/` |
| 11 | **Web Cache** | Semantic web result cache (sqlite-vec + Ollama) |
| 12 | **Offline Knowledge** | Cascade tool + kiwix ZIM Docker + prep-offline + prep-bible + prep-hymns scripts |
| 13 | **nginx** † | Reverse proxy for Langfuse + Dashboard |
| 14 | **Cron prompt** | Instructions for Hermes agent setup |
| | *† Server profile only* | |

### Configuration

Set these environment variables before running for a custom setup:

```bash
export CORTEX_OS="linux"                     # Auto-detected: darwin, linux, windows
export CORTEX_PROFILE="laptop"               # 'server' (default) or 'laptop'
export CORTEX_SOURCES="me,shared,default"   # Brain source names (default: "default")
export CORTEX_HOME="$HOME"                  # User home directory
export HERMES_HOME="$HOME/.hermes"          # Hermes config directory
export CORTEX_USER="$USER"                  # Your name for plugin metadata
```

**OS Support (experimental):**
- **macOS** — Fully supported. launchd services, Homebrew packages, all features
- **Linux** — systemd services, apt/dnf/pacman detection. Ollama via install script
- **Windows** — scheduled tasks, winget/choco detection. Some features limited

**Profiles:**
- **`server`** (default) — Full stack: Ollama, gbrain, Langfuse (Docker), Cortex Dashboard, nginx reverse proxy, Web Cache, Offline Knowledge (kiwix ZIM)
- **`laptop`** — Lean stack: Ollama, gbrain, Web Cache, Offline Knowledge. Skips Docker-dependent services (Langfuse, Dashboard, nginx). Perfect for mobile machines where Docker isn't always available.

### Multi-Person Setup

The installer supports any number of brain sources:

```bash
export CORTEX_SOURCES="luke,amy,shared,default"
bash ~/hermes-cortex/install.sh
```

This creates isolated sources, a federated shared source, and a default. The `/brain` slash command adapts to whatever sources you configure.

## 🧠 Offline Knowledge Stack

The offline knowledge system makes Hermes useful **with or without internet**:

- **Online mode:** Cascade cache → ZIM → web → LLM. Saves API costs — cache hits skip web_search entirely.
- **Offline mode:** Same cascade, but kiwix ZIM files become your "internet." Wikipedia, WikiMed (medical), Wikivoyage (travel guides), and Wikibooks all available locally.

### Three Scenarios

| Scenario | `prep-offline` mode | Content | Size |
|---|---|---|---|
| 🌴 **Jungle Travel** | `--mode=travel` | WikiMed + Wikivoyage + Simple Wiki + Wiktionary | ~6 GB |
| 🏗️ **Offline Dev** | `--mode=build` | Simple Wiki + Wikibooks + Wiktionary | ~7 GB |
| 📚 **Kid Learning** | `--mode=education` | Simple Wiki + Wikibooks + Wikivoyage | ~5 GB |

### Quick Start for Offline

```bash
# After install.sh, download content:
prep-offline --mode=travel

# Check system status:
offline_knowledge stats

# Query anything (works same online/offline):
offline_knowledge query "symptoms of malaria"
```

### Hardware Guide

See [docs/computer-specs.md](docs/computer-specs.md) for model and content recommendations
based on your RAM tier (8 GB → 64+ GB).

### Architecture

```
Agent question → web_cache (fastest) → kiwix ZIM (local) → gbrain (RAG) → LLM (always)
                      │                    │                    │              │
                 50μs hit ✅           localhost:8080      personal KB     model knows it
                 skip web_call         free, private        your data      fallback
```

## 🗄️ Private Configuration

Personal config, secrets, API keys, and private skills live in a **separate private repo**:

```
git clone git@github.com:lukemcqueen/hermes-cortex-private.git ~/hermes-cortex-private
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
git clone git@github.com:lukemcqueen/hermes-cortex-private.git ~/hermes-cortex-private
```

## 🎯 Philosophy

**Thin harness, fat skills.** The agent is the runtime — the real value lives in well-crafted skills, persistent memory, and deep observability. Every tool, config tweak, and workflow is tracked here so nothing is ever lost.

## 🛠️ Troubleshooting

### "Install fails at 'brew install'"
Make sure Homebrew is installed, or install it manually:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### "gbrain command not found after install"
Make sure `~/.bun/bin` is in your PATH:
```bash
export PATH="$HOME/.bun/bin:$PATH"
```
Add the same line to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.) to make it permanent.

### "Ollama won't start on macOS"
Check if it's blocked by Gatekeeper: go to **System Settings → Privacy & Security** and allow it.

### "docker compose command not found"
Make sure Docker Desktop is running.

### "Permission denied when running install.sh"
You might need to make the script executable:
```bash
chmod +x ~/hermes-cortex/install.sh
```

### "I don't have macOS"
The installer is optimized for macOS. Linux users can run individual steps manually. See the [Troubleshooting Guide](docs/troubleshooting.md) for more help.

## 📚 More Documentation

| Document | What it covers |
|----------|---------------|
| [Security Guide](docs/SECURITY.md) | 🔒 Port risks, file permissions, firewall setup, recovery — essential reading |
| [Architecture](docs/architecture.md) | System diagram, services, port map, design principles |
| [Troubleshooting](docs/troubleshooting.md) | 20+ common issues and fixes |
| [Computer Specs](docs/computer-specs.md) | Hardware recommendations by RAM tier |
| [Offline Scenarios](docs/offline-travel-stack.md) | Using Hermes without internet (travel, dev, education) |
| [Third-Party Licenses](docs/THIRD_PARTY_LICENSES.md) | Attribution for all open-source components used |
| [Docs Index](docs/DOCS-INDEX.md) | Full list of every document in this repo |

---

*Built by [@lukemcqueen](https://github.com/lukemcqueen) · Powered by 🦞 [Hermes Agent](https://hermes-agent.nousresearch.com) · Version `v1.0.0` · [MIT License](LICENSE) · See [Third-Party Licenses](docs/THIRD_PARTY_LICENSES.md) for component attributions*
