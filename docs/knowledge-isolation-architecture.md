# Knowledge Isolation Architecture

> **Version 2.0.0** — Published 2026-06-11
> Part of the [Hermes Cortex](https://github.com/lukemcqueen/hermes-cortex) documentation suite.

**Project isolation without multiple profiles — one agent, many legacy brain sources.**

---

## The Problem: Context Bleed

When a single agent session serves multiple domains — personal projects, work contracts, creative writing, system administration — knowledge from one inevitably leaks into another:

- **Hallucinated cross-project references** — The agent suggests a dependency from Project A while working on Project B because both are in the same brain index
- **Memory pollution** — Session notes for a client project get mixed with personal memories
- **Accidental disclosure** — A brain query returns results from all projects, potentially showing confidential content
- **Prompt bloat** — More indexed sources means more noise in every query

## The Solution: Single Agent, Isolated Sources

Hermes Cortex uses **one default agent profile** with project isolation achieved entirely through legacy brain source separation and the pointer memory pattern:

```
┌─────────────────────────────────────────────────────┐
│              Hermes Agent (default profile)          │
│                                                      │
│  ┌──────────┐    ┌──────────────────┐                │
│  │ MEMORY.md │───▶│  Pointer Pattern │                │
│  │ USER.md   │    │  (~120 chars ea) │                │
│  └──────────┘    └────────┬─────────┘                │
│                           │                           │
│                           ▼                           │
│                  ┌────────────────┐                    │
│                  │  legacy brain Query  │                    │
│                  │                │                    │
│                  │  --source ?    │                    │
│                  │    default     │──▶ ~/brain/default/│
│                  │    <project>   │──▶ ~/brain/<proj>/ │
│                  │    all         │──▶ all sources     │
│                  └────────────────┘                    │
└─────────────────────────────────────────────────────┘
         │                          ▲
         ▼                          │
┌──────────────────┐   ┌──────────────────────────┐
│ ~/.hermes/       │   │  ~/brain/                 │
│   memories/      │   │                           │
│     MEMORY.md    │   │  default/   (federated)    │
│     USER.md      │   │  shared/    (federated)    │
│   skills/        │   │  project-a/ (isolated)     │
│   plugins/       │   │  project-b/ (isolated)     │
│   cron/          │   │                           │
│                  │   │  Each brain dir has .git/  │
└──────────────────┘   │  + .gitignore:             │
                       │    MEMORY.md, USER.md      │
                       └──────────────────────────┘
```

### Key Principle: One Agent, Many Brains

- **One default Hermes profile** — All sessions run under `hermes` (no `--profile` flags)
- **Isolation via legacy brain `--source`** — Each brain directory is a separate legacy brain source
- **Federated sources** — `default`, `shared` — auto-searched on every query
- **Isolated sources** — `project-a`, `project-b` — only searched with explicit `--source <name>`
- **Pointer memory** — MEMORY.md (2,200 chars) holds compact pointers; full detail lives in the agent brain indexed by legacy brain

## Brain Directory Layout

```
~/brain/
├── default/              # Federated — auto-searched
│   ├── references/       # System config, recipes, global patterns
│   ├── lessons/          # Cross-domain lessons learned
│   └── decisions/        # Architectural decisions
│
├── shared/               # Federated — household, family, shared knowledge
│   ├── daily-briefings/
│   ├── music-copyright/
│   └── hermes-memory/    # Auto-synced from MEMORY.md
│
├── moses/                # Agent brain (pointer pattern target)
│   ├── references/
│   ├── decisions/
│   └── conversations/
│
├── project-a/            # Isolated — --source project-a only
├── project-b/            # Isolated — --source project-b only
└── project-c/            # Isolated — --source project-c only
```

## Query Isolation

```bash
# Federated sources only (default + shared)
legacy brain query "deployment pipeline"

# Single isolated source
legacy brain query "API auth flow" --source project-a

# Multiple explicit sources
legacy brain query "logging" --source default,project-a

# All sources
legacy brain query "anything" --source all
```

The `--source` flag acts as a namespace filter — legacy brain only returns chunks from the named sources. Without it, only federated sources are searched.

## Setting Up a New Project Brain

```bash
# 1. Create the brain directory
mkdir -p ~/brain/my-project/references
cd ~/brain/my-project
git init
cp ~/.hermes/docs/templates/gitignore.brain .gitignore

# 2. Register as legacy brain source
legacy brain sources add my-project --path ~/brain/my-project --name my-project

# 3. Sync
mycortex sync --source my-project

# 4. Add a pointer to MEMORY.md (optional)
# "My-project: contract API docs → /brain m my-project"
```

## When to Federate vs. Isolate

| Knowledge Type | Source Type | Reason |
|---------------|-------------|--------|
| System config, recipes, docs | **Federate** (default) | Universally relevant |
| Household, family, shared | **Federate** (shared) | Spans all contexts |
| Agent identity, SOUL.md | **Federate** (default) | Always needed |
| Client contracts, NDAs | **Isolate** (per client) | Confidential, must not leak |
| Competing projects | **Isolate** (per project) | No cross-project awareness |
| Creative writing, world-building | **Isolate** (per project) | One project only |
| Research papers, methodology | **Isolate** (per paper) | Cites and data stay contained |

**Decision tree:**

```
Is the knowledge...
├── ...about how the system works?        → FEDERATE (default)
├── ...about a shared tool or language?   → FEDERATE (default)
├── ...shared across all your work?       → FEDERATE (default)
├── ...specific to one engagement?        → ISOLATE (<project>)
├── ...personal AND project-specific?     → ISOLATE (<project>)
├── ...about competing projects?          → ISOLATE (separate source per project)
├── ...something you never want mixed?    → ISOLATE (<project>)
└── ...something you want auto-searched?  → FEDERATE (default or shared)
```

## The legacy brain `default` Source

The `default` legacy brain source is **built-in** — it cannot be removed or have its path changed. It manages `~/brain/default/` automatically. Do **not** create additional brain directories pointing at `~/brain/default/` as a separate legacy brain source; this creates a duplicate and will cause confusion at query time.

To add knowledge that should always be auto-searched:
1. Place files in `~/brain/default/`
2. legacy brain will index them automatically via the sync daemon
3. Query without `--source` to search them

For additional federated sources (e.g. `shared`), register them explicitly:
```bash
legacy brain sources add shared --path ~/brain/shared --name shared
legacy brain sources federate shared
```

## FAQ

### Q: Do I need multiple Hermes profiles?

**No.** Multiple profiles were the v1.x approach and have been deprecated in favor of legacy brain source isolation. A single default profile with source-filtered legacy brain queries achieves the same isolation with less complexity.

### Q: Can two projects share some knowledge?

Yes. Put shared knowledge in a federated source (`~/brain/default/` or `~/brain/shared/`) and project-specific knowledge in isolated sources. Query with `--source default,project-a` to search both.

### Q: What happens if I forget `--source` on an isolated project?

Only federated sources are searched. The agent gets zero results from that project — no data leak, but also no answer. Instruct the agent to retry with the correct `--source` flag when it knows a project context is active.

### Q: How do I move knowledge from one source to another?

```bash
mv ~/brain/default/client-notes.md ~/brain/project-a/
mycortex sync --source default
mycortex sync --source project-a
```

Update any MEMORY.md pointers that referenced the old location.

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 2.0.0 | 2026-06-11 | Rewritten for single-profile + legacy brain source isolation model. Deprecated multi-profile approach archived in `docs/deprecated-profile-model.md` |
| 1.0.0 | 2026-06-08 | Initial release — three-layer isolation model |

## See Also

- [Deprecated Profile Model](./deprecated-profile-model.md) — The old per-project profile approach (archived)
- [Memory Architecture (Pointer Pattern)](./agent-memory-pointer-pattern.md) — How MEMORY.md compact pointers work
- [Architecture Overview](./architecture.md) — System architecture
- [Troubleshooting](./troubleshooting.md)
