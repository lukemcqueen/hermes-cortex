# Project Separation Architecture

> **Version 1.0.0** — Published 2026-06-08
> Part of the [Hermes Cortex](https://github.com/lukemcqueen/hermes-cortex) documentation suite.

**A guide to isolating project knowledge, preventing context bleed between agents, and choosing when to federate vs. when to isolate.**

---

## Table of Contents

1. [The Problem: Context Bleed](#1-the-problem-context-bleed)
2. [Overview: The Three Isolation Layers](#2-overview-the-three-isolation-layers)
3. [Layer 1: Brain Directory (Knowledge Sources)](#3-layer-1-brain-directory-knowledge-sources)
   - [`~/brain/default/` — Federated (Auto-Searched)](#31-braindefault--federated-auto-searched)
   - [`~/brain/<project>/` — Isolated (`--source` Only)](#32-brainproject--isolated---source-only)
   - [gbrain Isolated Sources per Project](#33-gbrain-isolated-sources-per-project)
4. [Layer 2: Hermes Profile (Identity & Memory)](#4-layer-2-hermes-profile-identity--memory)
   - [Per-Profile `MEMORY.md` / `USER.md`](#41-per-profile-memorymd--usermd)
5. [Layer 3: Project Registration (Orchestration)](#5-layer-3-project-registration-orchestration)
6. [cortex-profile.sh Automation](#6-cortex-profilersh-automation)
7. [When to Federate vs. Isolate: Decision Guide](#7-when-to-federate-vs-isolate-decision-guide)
8. [Architecture Diagram](#8-architecture-diagram)
9. [Migration Guide](#9-migration-guide)
10. [FAQ](#10-faq)

---

## 1. The Problem: Context Bleed

When a single agent session serves multiple projects — contract work, personal research,
creative writing, system administration — knowledge from one domain inevitably leaks
into another. Symptoms include:

- **Hallucinated cross-project references** — The agent suggests using a dependency
  from Project A when working on Project B because both are in the same brain index.
- **Memory pollution** — Session memories for a client project get mixed with personal
  memories, risking PII exposure.
- **Prompt bloat** — The more sources indexed into gbrain, the noisier every query
  becomes. Irrelevant chunks compete with relevant ones.
- **Accidental disclosure** — `gbrain query` without `--source` filtering returns
  results across all projects, potentially showing confidential content.

Hermes Cortex solves this with a **three-layer isolation model** that cleanly separates
knowledge sources, agent identity, and runtime configuration on a per-project basis.

---

## 2. Overview: The Three Isolation Layers

```
┌─────────────────────────────────────────────────────────────┐
│                 Layer 3: Project Registration                │
│          ~/.cortex-projects.json  (orchestration)            │
├─────────────────────────────────────────────────────────────┤
│                 Layer 2: Hermes Profile                       │
│    ~/.hermes/profiles/<project>/                             │
│    └─ memories/{MEMORY.md, USER.md}  (isolated per profile)  │
├─────────────────────────────────────────────────────────────┤
│                 Layer 1: Brain Directory                      │
│    ~/brain/default/          Federated (auto-searched)       │
│    ~/brain/<project>/        Isolated (--source only)        │
│                                                              │
│    gbrain sources control which directories are queried.     │
│    Federated sources searched by default; isolated sources   │
│    require explicit --source <project> flag.                 │
└─────────────────────────────────────────────────────────────┘
```

| Layer | What It Isolates | Scope |
|-------|-----------------|-------|
| **1. Brain Directory** | Knowledge content (references, decisions, conversations, lessons) | `~/brain/<name>/` per project |
| **2. Hermes Profile** | Agent identity, memory, skills, plugins, cron | `~/.hermes/profiles/<name>/` |
| **3. Project Registration** | Full project metadata (path, brain, profile, gbrain source) | `~/.cortex-projects.json` |

---

## 3. Layer 1: Brain Directory (Knowledge Sources)

The `~/brain/` directory is the root for all agent-readable knowledge. It is organized
as a collection of **federated** and **isolated** sources.

```
~/brain/
├── default/              # Federated — auto-searched by gbrain
│   ├── references/
│   │   ├── repos.md
│   │   ├── crons.md
│   │   └── docker.md
│   ├── decisions/
│   ├── lessons/
│   └── daily-briefings/
│
├── moses/                # Agent brain (pointer pattern target)
│   ├── references/
│   ├── decisions/
│   └── conversations/
│
├── shared/               # Shared knowledge (family, household)
│   ├── daily-briefings/
│   └── music-copyright/
│
├── luke/                 # Personal research
│   └── conversations/
│
├── amy/                  # Another user's context
│   └── conversations/
│
├── <project-a>/          # Isolated — gbrain --source <project-a>
├── <project-b>/          # Isolated — gbrain --source <project-b>
└── <project-c>/          # Isolated — gbrain --source <project-c>
```

### 3.1 `~/brain/default/` — Federated (Auto-Searched)

The `default` source is the **general knowledge pool**. It is indexed by gbrain as a
federated source, meaning queries without an explicit `--source` flag will search it.

**Characteristics:**

- Always searched unless `--source` explicitly excludes it.
- Best for: system knowledge, common recipes, reusable patterns, global reference.
- Every new Hermes profile inherits access to the default source.
- Content: `references/`, `decisions/`, `lessons/`, shared operability guides.

**gbrain configuration (conceptual):**

```bash
gbrain sources add default --path ~/brain/default --federated true
```

### 3.2 `~/brain/<project>/` — Isolated (`--source` Only)

Project-specific brain directories are **isolated** — they are not searched by default.
A query must explicitly name the source via `--source <project>`.

**Characteristics:**

- **Not auto-searched** — must be explicitly requested.
- Best for: client knowledge, proprietary data, confidential conversations, contract-specific
  reference material.
- Each project directory is a self-contained git repository, typically pushed to a
  private remote as an orphan branch.
- No content from one project leaks into another.

**Query pattern:**

```bash
gbrain query "deployment pipeline"          # Searches default only
gbrain query "API auth flow" --source acme  # Searches only ~/brain/acme/
gbrain query "logging" --source default,acme # Searches both explicitly
```

### 3.3 gbrain Isolated Sources per Project

gbrain registers each isolated project brain as a named source. The source name
matches the project name for clarity.

```bash
# Register an isolated source
gbrain sources add acme --path ~/brain/acme --name acme

# List all sources
gbrain sources list
# Output:
#   default     (federated) ~/brain/default/
#   acme        (isolated)  ~/brain/acme/
#   client-b    (isolated)  ~/brain/client-b/
```

**Source isolation is enforced at query time.** The `--source` flag acts as a
namespace filter — gbrain only returns chunks from the named sources. Without it,
only federated sources are searched.

---

## 4. Layer 2: Hermes Profile (Identity & Memory)

Hermes Agent supports **named profiles** that encapsulate a full runtime environment.
Each profile lives under `~/.hermes/profiles/<name>/` and has its own:

- `memories/MEMORY.md` — Compressed pointers and agent state
- `memories/USER.md` — User identity, preferences, context
- `skills/` — Profile-specific skills
- `plugins/` — Profile-specific plugins
- `cron/` — Profile-specific cron jobs

### 4.1 Per-Profile `MEMORY.md` / `USER.md`

Each profile's `MEMORY.md` and `USER.md` are **completely isolated** from every other
profile. A session running with `--profile client-a` reads only the memory files
under `~/.hermes/profiles/client-a/memories/`.

**Why this matters:**

- A client project's MEMORY.md will never mention personal household cron jobs.
- A contract agent won't accidentally reveal memory from another contract.
- Each profile can have its own **pointer pattern** targets (different brain directories
  for different contexts).

**Activation:**

```bash
hermes --profile client-a          # Start a session with client-a identity
hermes --profile personal          # Start a session with personal identity
hermes                            # No flag → uses default profile
```

**Default profile:**

```
~/.hermes/
├── memories/MEMORY.md            # Default agent memory
├── memories/USER.md              # Default user identity
└── ...                           # Default skills, plugins, cron
```

---

## 5. Layer 3: Project Registration (Orchestration)

The file `~/.cortex-projects.json` acts as a **registry of all known Cortex projects**.
It is the orchestration layer that ties together the brain directory, Hermes profile,
and gbrain source for each project.

**Schema:**

```json
[
  {
    "project_name": "acme",
    "location": "/Users/luke/Developer/AI/acme",
    "brain": "/Users/luke/brain/acme",
    "profile": "acme",
    "gbrain_source": "acme"
  },
  {
    "project_name": "client-b",
    "location": "/Users/luke/Developer/AI/client-b",
    "brain": "/Users/luke/brain/client-b",
    "profile": "client-b",
    "gbrain_source": "client-b"
  }
]
```

**Purpose:**

- **Discovery** — Other tools (cortex dashboard, automation scripts) read this file to
  enumerate all active projects.
- **Consistency** — The project name is the single canonical key. Brain directory,
  profile name, and gbrain source all derive from it.
- **Lifecycle management** — Adding or removing a project is a single JSON edit
  (or one call to `cortex-profile.sh`).

---

## 6. cortex-profile.sh Automation

The `scripts/cortex-profile.sh` script automates the creation of a fully isolated
project profile. It performs all three layers in one command.

**Usage:**

```bash
bash scripts/cortex-profile.sh <project-name> [project-path]
```

- If `project-path` is omitted, defaults to `~/Developer/AI/<project-name>`.

**What it creates:**

| Step | Action | Path |
|------|--------|------|
| 1 | Creates project directory | `~/Developer/AI/<name>/` (or custom path) |
| 2 | Creates Hermes profile with empty MEMORY.md/USER.md | `~/.hermes/profiles/<name>/memories/` |
| 3 | Creates brain directory with git init + .gitignore | `~/brain/<name>/` |
| 4 | Registers as isolated gbrain source | gbrain sources add `<name>` |
| 5 | Registers in `~/.cortex-projects.json` | Adds entry linking project, brain, profile, source |

**Idempotent:** The script checks for existing directories, gbrain sources, and
cortex-projects.json entries before creating anything. Safe to re-run.

**Post-creation workflow:**

```bash
# 1. Create the project profile
bash scripts/cortex-profile.sh acme

# 2. Start a Hermes session in that project
cd ~/Developer/AI/acme
hermes --profile acme

# 3. Inside the session, seed memory
# The agent's MEMORY.md and USER.md under
# ~/.hermes/profiles/acme/memories/ are isolated.
# Brain knowledge lives at ~/brain/acme/ and is only
# searched when --source acme is explicitly specified.
```

---

## 7. When to Federate vs. Isolate: Decision Guide

### Always Federate (Default Source)

| Scenario | Reason |
|----------|--------|
| System config & recipes | Docker, nginx, cron, launchd — universally relevant |
| Global reference | Common commands, patterns, and conventions |
| Shared family/household info | Daily briefings, alarms, shared calendar |
| Tool usage guides | Skills documentation, tool reference |
| Public knowledge | Wikipedia excerpts, language references, public docs |
| "This is how I always work" | Personal productivity patterns that span all projects |

### Always Isolate (Per-Project Source)

| Scenario | Reason |
|----------|--------|
| Client contracts | Proprietary knowledge, NDAs, confidential stack details |
| Competing projects | No cross-project awareness of API keys, DB schemas, business logic |
| Personal vs. work identity | Agent persona, tone, and memory should not mix |
| Creative writing | Character bibles, plot notes, world-building — one project only |
| Research papers | Citation graph, methodology notes, source code for one specific paper |
| Job applications | Tailored resumes, cover letters, interview prep — never leak between roles |
| Freelance gigs | Each client gets a sealed environment with zero visibility into others |

### Decision Matrix

Use this matrix when unsure:

```
Is the knowledge...
├── ...about how the system itself works?        → FEDERATE (default)
├── ...about a tool, language, or framework?      → FEDERATE (default)
├── ...shared across all your work?               → FEDERATE (default)
├── ...specific to one client or engagement?      → ISOLATE (<project>)
├── ...personal but not project-specific?         → FEDERATE (default)
│   (put pointer in MEMORY.md, detail in default brain)
├── ...personal AND project-specific?             → ISOLATE (<project>)
├── ...about competing projects?                  → ISOLATE (separate <project> per client)
├── ...something you never want mixed?            → ISOLATE (<project>)
└── ...something you want auto-searched always?   → FEDERATE (default)
```

### Migration Rules

| Current State | Desired State | Action |
|---------------|---------------|--------|
| Knowledge in `default/` that belongs to a project | Isolated | `mv ~/brain/default/<topic>.md ~/brain/<project>/` then re-sync gbrain |
| Knowledge in `~/brain/<project>/` that is universally useful | Federated | `mv ~/brain/<project>/<topic>.md ~/brain/default/` then re-sync gbrain |
| Running `hermes --profile default` but want isolation | Profile + source | Run `cortex-profile.sh <name>` to create new isolated profile |
| Isolated project ending | Deprecated | Remove from `~/.cortex-projects.json`; optionally archive or delete the brain dir and profile |

---

## 8. Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                      Hermes Agent Session                         │
│                                                                   │
│  ┌──────────┐     ┌───────────────────┐     ┌────────────────┐   │
│  │ MEMORY.md │────▶│  Pointer Pattern  │────▶│  Agent Identity │   │
│  │ USER.md   │     │  (~120 chars ea)  │     │  (per profile)  │   │
│  └──────────┘     └─────────┬─────────┘     └────────────────┘   │
│                             │                                      │
│                             ▼                                      │
│                    ┌────────────────┐                              │
│                    │  gbrain Query  │                              │
│                    │                │                              │
│                    │  --source ?    │                              │
│                    │    default     │──▶ ~/brain/default/          │
│                    │    <project>   │──▶ ~/brain/<project>/        │
│                    │    both/other  │──▶ specific source(s)        │
│                    └────────────────┘                              │
└──────────────────────────────────────────────────────────────────┘
         │                          ▲
         │                          │
         ▼                          │
┌─────────────────────┐   ┌──────────────────────┐
│ ~/.hermes/profiles/ │   │  ~/brain/             │
│                     │   │                       │
│ default/            │   │  default/  (federated) │
│   memories/         │   │  moses/    (isolated)  │
│     MEMORY.md       │   │  shared/   (isolated)  │
│     USER.md         │   │  luke/     (isolated)  │
│   skills/           │   │  amy/      (isolated)  │
│   plugins/          │   │  <proj-a>/ (isolated)  │
│   cron/             │   │  <proj-b>/ (isolated)  │
│                     │   │                       │
│ acme/               │   │  Each with .git/       │
│   memories/         │   │  + .gitignore:         │
│     MEMORY.md       │   │    MEMORY.md           │
│     USER.md         │   │    USER.md             │
│   skills/           │   │    .env, *.key, *.pem  │
│   plugins/          │   └──────────────────────┘
│   cron/             │
└─────────────────────┘
         │
         ▼
┌────────────────────────────────────┐
│ ~/.cortex-projects.json            │
│                                    │
│ [                                  │
│   { "project_name": "acme",        │
│     "location": "~/Dev/AI/acme",   │
│     "brain": "~/brain/acme",       │
│     "profile": "acme",             │
│     "gbrain_source": "acme" }      │
│ ]                                  │
└────────────────────────────────────┘
```

---

## 9. Migration Guide

### Moving from Single to Multi-Project Setup

If you have been running everything under the default profile with a single brain
source, here is the step-by-step migration:

**Step 1: Audit current knowledge.**

```bash
ls ~/brain/
cat ~/.hermes/memories/MEMORY.md
gbrain sources list
```

Identify which knowledge belongs to which project vs. what is universally useful.

**Step 2: Create isolated project profiles.**

```bash
bash scripts/cortex-profile.sh client-a
bash scripts/cortex-profile.sh client-b
```

**Step 3: Move project-specific knowledge.**

```bash
mv ~/brain/default/client-a-notes.md ~/brain/client-a/
mv ~/brain/default/client-b-deployment.md ~/brain/client-b/
gbrain sync --source client-a
gbrain sync --source client-b
```

**Step 4: Update MEMORY.md pointers.**

If the default profile's MEMORY.md had pointers referencing project-specific files,
move those pointers to the respective profile's MEMORY.md:

```bash
# ~/.hermes/profiles/client-a/memories/MEMORY.md
# Add: Client-a deployment: 4-stage pipeline → /brain m client-a-deployment
```

**Step 5: Re-sync gbrain for default.**

```bash
gbrain sync --source default
```

**Step 6: Verify isolation.**

```bash
gbrain query "anything-client-specific"
# Should return zero results if moved correctly
gbrain query "anything-client-specific" --source client-a
# Should return the moved content
```

### Archiving a Deprecated Project

```bash
# 1. Remove from registry
python3 -c "
import json
with open('$HOME/.cortex-projects.json') as f:
    projects = json.load(f)
projects = [p for p in projects if p['project_name'] != 'old-project']
with open('$HOME/.cortex-projects.json', 'w') as f:
    json.dump(projects, f, indent=2)
"

# 2. Remove gbrain source
gbrain sources remove old-project

# 3. Optional: Archive brain and profile
tar -czf ~/brain/archive/old-project.tar.gz -C ~/brain old-project
rm -rf ~/brain/old-project ~/.hermes/profiles/old-project
```

---

## 10. FAQ

### Q: Can I have both federated and isolated sources in the same session?

Yes. The `--source` flag accepts multiple comma-separated values:

```bash
gbrain query "deployment" --source default,acme
```

This searches both the federated default source and the isolated acme source.
A single Hermes session can use any combination of sources.

### Q: What happens if I forget `--source` on an isolated project?

Only federated sources are searched. If the isolated project's brain has not been
added as a federated source, the query returns zero results from that source. No
data leak — but also no data found. The agent should be instructed to retry with
the correct `--source` flag when it knows a project context is active.

### Q: Can two profiles share the same brain directory?

Yes. The brain directory is just a file path — nothing prevents multiple profiles
from pointing at it. However, this breaks isolation. Only do this when you
intentionally want shared knowledge (e.g., both `luke` and `moses` profiles
talking to `~/brain/shared/`).

### Q: Do profile skills also isolate?

Yes. Skills under `~/.hermes/profiles/<name>/skills/` are only loaded when that
profile is active. The default `~/.hermes/skills/` is always loaded as a base set.
Skills are additive — profile skills extend base skills, they do not replace them.

### Q: Is `~/.cortex-projects.json` required?

No. It is a convenience registry. You can run `hermes --profile acme` and query
gbrain with `--source acme` without ever touching the JSON file. The registry
exists for automation, discovery, and dashboard integration.

### Q: How do I know which project my current session belongs to?

If launched with `--profile <name>`, the profile name is the project name.
You can check `echo $HERMES_PROFILE` inside a session or inspect the profile
directory name: `basename $(dirname $(readlink ~/.hermes/profile))`.

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-06-08 | Initial release — three-layer isolation model, decision guide, migration guide, automation docs |
