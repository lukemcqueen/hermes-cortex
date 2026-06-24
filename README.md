# 🧠 Hermes Cortex

> *An open-source installer and skill set for your personal Hermes AI agent.
> Privacy-first, offline-capable, built for non-technical users with an AI agent.*

**Version: 1.0.0** · ![GitHub](https://img.shields.io/github/license/fleet-operator/hermes-cortex) · [Hermes Agent](https://hermes-agent.nousresearch.com)

![Hermes Cortex](avatar.png)

**Hermes Cortex** is a self-contained system installer and public skill set for the [Hermes Agent](https://hermes-agent.nousresearch.com) runtime:

> **Prerequisite:** [Hermes Agent](https://hermes-agent.nousresearch.com) must be installed first. This project adds skills, offline content, and system services on top of it — it is not a standalone agent.

### Who is this for?

- **You want a personal AI agent** that runs on your own computer (no cloud dependency)
- **You care about privacy** — everything stays on your machine
- **You travel or have unreliable internet** — the offline stack works without connectivity
- **You want observability** — see what your agent is doing with Langfuse tracing

### What you get

**▸ Core Platform**
- **Ollama** — Local LLM server (free embeddings + Qwen2.5-Coder for offline code RAG)
- **Bun** + **GBrain** — Persistent knowledge brain (PGLite, zero-config, 4 sources)
- **Langfuse** — LLM trace evaluation and scoring (6 Docker containers: ClickHouse, MinIO, Redis, Postgres)
- **Cortex Dashboard** — Companion dashboard for Langfuse + system health (Flask, dark-theme, drag-and-drop)
- **Web Cache** — Semantic search cache (sqlite-vec + Ollama embeddings, ~200MB LRU)
- **gbrain sync daemon** — Automatic 2-minute sync
- **Hermes plugin** — `/brain` slash command
- **8 shared skills** — Subagent orchestration, debugging, TDD, planning, memory architecture, code review, spikes, systematic debugging
- **Brain directory structure** — MECE-organized knowledge sources with .gitignore isolation

**▸ Offline Stack**
- **Offline Knowledge** — Cascade lookup: web-cache → kiwix ZIM (Wikipedia, WikiMed, Wikivoyage free locally) → gbrain → LLM. Saves API costs online, works without internet.
- **Offline Code Assistant** — 386 curated code snippets across 26 languages. Semantic search + RAG-powered code generation via Ollama. Run `offline_code search "flask api"` or `offline_code gen "worker pool go"`.
- **Offline Reader** — Single-file web UI (`python3 src/offline/offline-reader.py`) for browsing Bible (55+ languages), hymns (public domain), and wiki reference in any browser — zero dependencies.

**▸ Security**
- **nginx reverse proxy** — TLS + Basic Auth on all external ports (13001/13002), rate-limited (20 req/5s)
- **pf firewall** — Default-deny, port-range rules, SSH rate-limiting
- **fail2ban** — 4 jails with ban escalation (1h→4wk): http-auth, limit-req, botsearch, bad-request
- **Ollama** — Bound to localhost only (hardened during install)

**▸ Operations**
- **Auto-Update** — Silent cron-based updater for content updates
- **Computer Specs Guide** — Hardware-aware recommendations per RAM tier
- **Multi-person setup** — Federated brain sources with isolated memory per user

---

> *"The more we get to know about our universe, the more the hypothesis that there is a Creator God, who designed the universe for a purpose, gains in credibility as the best explanation of why we are here."* — John Lennox

---

## 🚀 One-Command Install

> **🔒 Before installing:** Read the [Security Guide](docs/SECURITY.md) to understand how your system is protected.

**Quick start (30 seconds):** If you just want to try the TDD scoring tools:
```bash
bash src/loop-governance/setup.sh    # installs deps + symlinks
score-cycle --help                    # ready to use
```

**Full install (5-15 min):**
```bash
# One-liner — no clone needed (auto-detects and downloads the repo)
curl -fsSL https://raw.githubusercontent.com/fleet-operator/hermes-cortex/main/install.sh | bash

# Or clone for offline install / inspection:
git clone --depth 1 https://github.com/fleet-operator/hermes-cortex.git ~/hermes-cortex
bash ~/hermes-cortex/install.sh

# Check prerequisites only (no install):
bash ~/hermes-cortex/install.sh --check

# macOS — Laptop profile: lean, no Docker (Langfuse, Dashboard, nginx skipped)
CORTEX_PROFILE=laptop bash ~/hermes-cortex/install.sh

# Linux — auto-detects systemd, apt/dnf/pacman
CORTEX_OS=linux bash ~/hermes-cortex/install.sh

# Windows — uses winget/choco + scheduled tasks (limited)
CORTEX_OS=windows bash ~/hermes-cortex/install.sh

# ⚡ Then give your Hermes agent the prompt it prints out
# to set up cron jobs and activate the /brain command
```

### Upgrading

```bash
cd ~/hermes-cortex && git pull && bash install.sh
```
The installer is **idempotent** — safe to re-run. It skips already-installed components and only updates changed files. Check the [changelog](https://github.com/fleet-operator/hermes-cortex/releases) before upgrading.

### What `install.sh` does

| Step | What | Why |
|------|------|-----|
| 0 | **System Check** | Verifies OS, RAM, disk, Docker, network before touching anything |
| — | **OS Detection** | Auto-detects macOS/Linux/Windows, sets package + service managers |
| 1 | **Ollama** (cross-platform) | Native installer per OS; bound to localhost |
| 2 | **Bun** | JavaScript runtime for gbrain |
| 3 | **gbrain** | Persistent knowledge brain (PGLite, zero-config) |
| 4 | **Brain dirs** | `~/brain/{default,…}` with MECE directory schema + .gitignore + git init |
| 5 | **gbrain sync** | Launchd daemon — syncs brain every 2 minutes |
| 6 | **Observability** † | Langfuse + Cortex Dashboard |
| 7 | **`/brain` plugin** | Hermes slash command for gbrain queries |
| 8 | **Scripts** | Heartbeat, memory sync, Langfuse scoring, dashboard |
| 9 | **Plugin enable** | Auto-activates in Hermes config |
| 10 | **Skills** | 8 shared skills installed to `~/.hermes/skills/` |
| 11 | **Web Cache** | Semantic web result cache (sqlite-vec + Ollama) |
| 12 | **Offline Knowledge** | Cascade tool + kiwix ZIM Docker + prep scripts |
| 13 | **Offline Reader** | `python3 src/offline/offline-reader.py` — zero-dependency web UI |
| 14 | **Code Corpus** | 386 snippets across 26 languages; RAG index via Ollama |
| 15 | **Auto-Update** | `auto-update.sh` — silent cron-based content updater |
| 16 | **nginx** † | Reverse proxy for Langfuse + Dashboard + hardening |
| 17 | **Cron prompt** | Instructions for Hermes agent setup |
| | *† Server profile only* | |

### Configuration

Set these environment variables before running for a custom setup:

```bash
export CORTEX_OS="linux"                     # Auto-detected: darwin, linux, windows
export CORTEX_PROFILE="laptop"               # 'server' (default) or 'laptop'
export CORTEX_SOURCES="me,shared,default"    # Brain source names (default: "default")
export CORTEX_HOME="$HOME"                  # User home directory
export HERMES_HOME="$HOME/.hermes"          # Hermes config directory
export CORTEX_USER="$USER"                  # Your name for plugin metadata
```

**OS Support:**
- **macOS** — Fully supported. launchd services, Homebrew packages, all features
- **Linux** — systemd services, apt/dnf/pacman detection. Ollama via install script
- **Windows** — scheduled tasks, winget/choco detection. Some features limited

**Profiles:**
- **`server`** (default) — Full stack: Ollama, gbrain, Langfuse (Docker), Dashboard, nginx, Web Cache, Offline Knowledge
- **`laptop`** — Lean: Ollama, gbrain, Web Cache, Offline Knowledge. Skips Docker-dependent services. Ideal for mobile machines.

### Multi-Person Setup

The installer supports any number of brain sources:

```bash
export CORTEX_SOURCES="luke,amy,shared,default"
bash ~/hermes-cortex/install.sh
```

Each source has isolated memory and .gitignore. The `/brain` slash command adapts to whatever sources you configure. Federated sources (like `shared`) are auto-searched on every query.

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

See [docs/computer-specs.md](docs/computer-specs.md) for model and content recommendations based on your RAM tier (8 GB → 64+ GB). Intel Macs benefit from lighter quantized models.

### Architecture

```
Agent question → web_cache (fastest) → kiwix ZIM (local) → gbrain (RAG) → LLM (always)
                      │                      │                    │              │
                 50μs hit ✅           localhost:8080      personal KB     model knows it
                 skip web_call         free, private        your data      fallback
```

## 🗄️ Private Configuration

Personal config, secrets, API keys, and private skills live in a **separate private repo**:

```bash
git clone git@github.com:fleet-operator/hermes-cortex-private.git ~/hermes-cortex-private
```

This repository holds:

| What | Location |
|------|----------|
| Full personal config.yaml | `deploy/config/config.yaml` |
| Environment secrets (API keys, tokens) | `.env` (not committed) |
| Utility & monitoring scripts (13) | `src/scripts/` |
| Cortex Dashboard (Flask + JS) | `src/dashboard/` |
| nginx reverse proxy config | `deploy/nginx/` |
| Brain content | Private `brain-*` branches (not on `main`) |

After running the public installer, apply your private config:

```bash
cp ~/hermes-cortex-private/config/config.yaml ~/.hermes/config.yaml
# Source your .env, copy scripts, etc.
```

## 🎯 Philosophy

**Thin harness, fat skills.** The agent is the runtime — the real value lives in well-crafted skills, persistent memory, and deep observability.

## 🛠️ Troubleshooting

### "Install fails at 'brew install'"
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### "gbrain command not found after install"
```bash
export PATH="$HOME/.bun/bin:$PATH"
```
Add to `~/.zshrc` or equivalent.

### "Ollama won't start on macOS"
Check **System Settings → Privacy & Security** — Gatekeeper may block it.

### "docker compose command not found"
Make sure Docker Desktop is running.

### "Permission denied when running install.sh"
```bash
chmod +x ${CORTEX_REPO:-$HOME/hermes-cortex}/install.sh
```

### "Cron jobs not created after install"
The installer requires Hermes Agent to be installed first. If you see:
```
⚠ Hermes Agent not found — cron jobs cannot be created
```

Then install Hermes Agent first, then run:
```bash
bash ~/.hermes/scripts/install-hermes-crons.sh
```

### "Cron job failing or not running"
```bash
# List all crons
hermes cron list

# Check cron job health
cat ~/.hermes/cron/jobs.json | python3 -m json.tool

# Recreate all crons (force)
bash ~/.hermes/scripts/install-hermes-crons.sh --force

# Check script permissions
ls -la ~/.hermes/scripts/*.py ~/.hermes/scripts/*.sh
```

### "I don't have macOS"
See the [Troubleshooting Guide](docs/troubleshooting.md) for Linux and Windows notes.

## 📚 More Documentation

| Document | What it covers |
|----------|---------------|
| [Security Guide](docs/SECURITY.md) | 🔒 Port risks, file permissions, firewall setup, recovery — essential reading |
| [Architecture](docs/architecture.md) | System diagram, services, port map, design principles, security stack |
| [Troubleshooting](docs/troubleshooting.md) | 25+ common issues and fixes — Docker, Dashboard, install, nginx, Langfuse data, memory, Linux |
| [Computer Specs](docs/computer-specs.md) | Hardware recommendations by RAM tier, model selection for Intel/Apple Silicon |
| [Offline Scenarios](docs/offline-travel-stack.md) | Using Hermes without internet (travel, dev, education) |
| [Third-Party Licenses](docs/THIRD_PARTY_LICENSES.md) | Attribution for all open-source components used |
| [Docs Index](docs/DOCS-INDEX.md) | Full list of every document in this repo |

---

*Built by [@fleet-operator](https://github.com/fleet-operator) · Powered by 🦞 [Hermes Agent](https://hermes-agent.nousresearch.com) · Version `v1.0.0` · [MIT License](LICENSE) · See [Third-Party Licenses](docs/THIRD_PARTY_LICENSES.md) for component attributions*
