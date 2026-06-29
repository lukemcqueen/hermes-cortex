---
name: repo-organization
description: "Canonical repo organization for Hermes Cortex — structure, naming, consolidation, symlinks, and audit procedures."
version: 1.0.0
author: Hermes Cortex (Moses)
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [repo-organization, structure, naming, conventions, audit, cleanup]
    related_skills: [code-review, project-map, hermes-agent-skill-authoring]
---

# Hermes Cortex — Repo Organization Standard

This skill defines the canonical structure for Hermes Cortex repos. Use it when:
- Setting up a new Hermes Cortex installation
- Auditing an existing repo for structural issues
- Deciding where a new file should live
- Renaming or consolidating scattered data

---

## 1. Core Principle: Three-Layer Model

Hermes Cortex uses three distinct layers, each with a clear purpose:

| Layer | Path | Purpose | Backed up? |
|-------|------|---------|------------|
| **Repo** | `~/hermes-cortex/` | Public source code, skills, docs, installer | ✅ Git (GitHub) |
| **Agent Infra** | `~/hermes-cortex/.hermes-cortex/` | Per-project agent data (sessions, memory, skills) | ✅ Git (part of repo) |
| **Hermes Config** | `~/.hermes/` | Hermes Agent runtime (config, logs, cache, DBs) | ❌ Machine-local |

**Rule:** Never put agent-generated data in the repo root. Never put source code in `~/.hermes/`. Never put logs in the repo.

---

## 2. Canonical Directory Structure

```
hermes-cortex/
├── AGENTS.md                  # Agent guidelines — orients every agent on entry
├── README.md                  # Human-readable intro + quick-start
├── LICENSE                    # MIT
├── VERSION                    # Single version source (e.g., "1.0.0")
├── install.sh                 # Single-command installer (idempotent)
├── quick-start.sh             # 10-second TDD scoring setup
├── pytest.ini                 # Test configuration
│
├── src/                       # All source code
│   ├── scripts/               # Runable scripts (watchdogs, utilities)
│   │   ├── system-alert-watchdog.py
│   │   ├── service-recovery.py
│   │   ├── orch-team-health.py
│   │   └── ...
│   ├── skills/                # Canonical skills (organized by domain)
│   │   ├── software-development/
│   │   ├── devops/
│   │   ├── github/
│   │   └── ...
│   ├── agent-inbox/           # Inbox server (FastAPI)
│   ├── dashboard/             # Cortex dashboard
│   ├── loop-governance/       # TDD scoring + evaluation pipeline
│   ├── mcp-servers/           # MCP server implementations
│   ├── agent-registry.json    # Canonical agent list (who, where, accessible?)
│   └── project-map/           # Dependency graph analysis
│
├── .hermes-cortex/            # Agent infra (gitignored content is per-user)
│   ├── sessions/
│   │   ├── current.md         # Active session state
│   │   └── archive/           # Timestamped snapshots
│   ├── memory/                # Per-user MEMORY.md, USER.md (gitignored)
│   └── skills/                # Project-specific skills (tracked)
│
├── deploy/                    # Deployment configs
│   ├── nginx/                 # Nginx site configs
│   ├── config/                # App configs
│   └── patches/               # Patch files
│
├── docs/                      # Documentation
│   ├── templates/             # Seed templates
│   ├── design/                # Design docs
│   └── images/                # Screenshots, diagrams
│
├── tests/                     # Test suite
│
├── .gitignore
├── .github/                   # GitHub Actions, templates
│
└── agent-inbox-private/       # Agent messages repo (git submodule or clone)
```

---

## 3. Naming Conventions

### Files and Directories

| Pattern | Example | When to use |
|---------|---------|-------------|
| `kebab-case` | `system-alert-watchdog.py`, `service-recovery.py` | Source files, scripts, configs — **default** |
| `snake_case` | `loop_scorer.py`, `score_cycle.py` | Python modules (PEP 8). Only for importable modules |
| `PascalCase` | — | Never in file names. Only for Python classes inside files |
| Descriptive names | `orch-team-health.py` | Describe WHAT the file does, not how. Human-readable |
| No abbreviations | `product-requirements/` not `prd/` | Every new name must be understandable without context |

### Cron Jobs

| Prefix | Example | Meaning |
|--------|---------|---------|
| `agent-*` | `agent-auto-remediate` | LLM-driven: an AI agent does the work |
| No prefix | `service-recovery`, `system-alert-watchdog` | Script-driven: no agent involvement |

### Skills

| Pattern | Example | Meaning |
|---------|---------|---------|
| `kebab-case` | `code-review`, `test-driven-development` | Skill directory name = `name:` in SKILL.md frontmatter |

---

## 4. Consolidation Rules

### What goes where

| This belongs in the repo (`src/`) | This belongs in `.hermes-cortex/` | This stays in `~/.hermes/` |
|-----------------------------------|-----------------------------------|----------------------------|
| Runable scripts | Session state | Agent config (config.yaml) |
| Skill source code | Agent memory (MEMORY.md, USER.md) | Runtime DBs (loop-governance.db) |
| Templates | Per-user project skills | Logs |
| Installers | Cron output | LLM caches |
| MCP servers | — | Agent registry (local copy) |
| Dashboards | — | Cron `jobs.json` |

### Consolidation Procedure

When you find data in the wrong place:

1. **Move** it to the correct location
2. **Symlink** from the old location if any tool or cron references the old path
3. **Update** all references to point to the new canonical path
4. **Document** the change in AGENTS.md and the relevant SKILL.md

---

## 5. Symlink Strategy

Use symlinks ONLY when:
- A tool/cron expects a file at a specific path AND
- The canonical location is different AND
- You can't update all the references yet

**Auditable symlinks:** Keep a manifest at `scripts/symlink-audit.sh` that lists every symlink and its target. Run `scripts/symlink-audit.sh --check` to verify all links are valid.

**What NOT to symlink:**
- Config files — use references or imports instead
- Secrets — never symlink across boundaries
- Agent memory — it's per-user and should stay in `.hermes-cortex/memory/`

---

## 6. Audit Checklist

Run this checklist when auditing the repo:

```
[ ] No source code in ~/.hermes/
[ ] No agent data in ~/hermes-cortex/ root
[ ] All cron names follow agent-* / no-prefix convention
[ ] All skill directory names match name: field in SKILL.md
[ ] No stale .cron-version markers in git tracking
[ ] AGENTS.md under 20K bytes
[ ] All scripts referenced by crons exist
[ ] All symlinks point to valid targets
[ ] No duplicate files (same content, different locations)
[ ] .gitignore covers all generated files
[ ] VERSION is single source of truth
```

---

## 7. Quick-Fix Script

Run this to check the most common issues:

```bash
# Check for name mismatch in skills
for d in src/skills/software-development/*/; do
  name=$(basename "$d")
  yaml_name=$(grep "^name:" "$d/SKILL.md" 2>/dev/null | head -1 | cut -d: -f2- | tr -d ' ')
  if [ "$yaml_name" != "$name" ]; then
    echo "MISMATCH: $name vs $yaml_name"
  fi
done

# Check no .cron-version in git
git ls-files | grep "\.cron-version" && echo "ERROR: .cron-version tracked in git"

# Check AGENTS.md size
if [ $(wc -c < AGENTS.md) -gt 20000 ]; then
  echo "AGENTS.md too large ($(wc -c < AGENTS.md) bytes)"
fi

# Check all symlinks
find . -type l ! -path './.git/*' | while read link; do
  if [ ! -e "$link" ]; then
    echo "BROKEN: $link"
  fi
done
```

---

## 8. Migration Checklist (from Old Layout)

When migrating an existing install to this standard:

1. **Rename crons:** `cron-*` → `agent-*` for LLM-driven crons
2. **Consolidate skills:** Move skill content from `~/.hermes/skills/` to `src/skills/` if it belongs in the repo
3. **Fix skill names:** Ensure `name:` in SKILL.md matches the directory name
4. **Audit symlinks:** Replace hard copies with symlinks where files must exist in multiple locations
5. **Clean .gitignore:** Add generated files (`.cron-version`, `*.db`, `IMPROVEMENTS.md`)
6. **Update AGENTS.md:** Keep it under 20K by trimming verbose sections
7. **Test install:** `bash install.sh --check` must pass, `pytest` must pass
