# Project Structure

AgentKore uses a **two-layer layout**: SOURCE (`src/agent-kore/`) is the canonical copy; ROOT is the deployment target. The project deploys its own framework files to itself and to other projects.

## Two-Layer Layout

```
agentkore/                          ← PROJECT ROOT (also a deployment target)
├── run                             ├ PROJECT-LEVEL: dev orchestrator, NOT in src/
├── deployed_projects.json          ├ PROJECT-LEVEL: deploy target list, NOT in src/
├── bin/                            ├ PROJECT-LEVEL: backup tools, NOT in src/
├── _archive/                       ├ PROJECT-LEVEL: old backups, NOT in src/
├── .git/                           ├ PROJECT-LEVEL: git repo, NOT in src/
│
├── AGENTS.md                       │ DUPLICATED (deployed FROM src/agent-kore/)
├── opencode.json                   │ DUPLICATED (deployed FROM src/agent-kore/)
├── opencode-instructions.md        │ DUPLICATED (deployed FROM src/agent-kore/)
├── .agentkore/                     │ DUPLICATED (deployed FROM src/agent-kore/)
├── .opencode/                      │ DUPLICATED (deployed FROM src/agent-kore/)
├── scripts/                        │ project-specific (not in source)
├── docs/                           │ DUPLICATED (deployed FROM src/agent-kore/)
├── memory/                         │ PROTECTED (survives deploy, but initially from src/)
│
└── src/agent-kore/                 ← *** SOURCE OF TRUTH ***
    ├── AGENTS.md, opencode.json, opencode-instructions.md
    ├── .agentkore/, .opencode/
    ├── scripts/, docs/, memory/
    └── (matches root deployed structure)
```

**Critical rule:** `./run deploy self` copies `src/agent-kore/` → root, overwriting all duplicate files. Editing root `.agentkore/` directly will be **clobbered** on next deploy. Always edit in `src/agent-kore/` and run `./run deploy self`.

## Directory Reference

### `.agentkore/` — AgentKore Runtime Config

```
.agentkore/
├── config/
│   ├── agentkore.json          # Main config: skills, flows, policies
│   ├── routing.md              # Task routing logic
│   └── modes.md                # Agent operating modes
├── hermes/skills/              # Hermes orchestration skills
│   ├── agentkore-router/       #   Task routing logic
│   ├── opencode-delegation/    #   OpenCode delegation
│   ├── task-contract/          #   Structured handoffs
│   └── security-boundaries/    #   Delegation boundaries
├── install_templates/          # Fresh-install templates
│   └── template_opencode.json  #   Template for opencode.json
├── prompts/
│   └── system.md               # System prompt
├── sessions/                   # Session state (protected)
│   └── current.md              #   Active session
└── scripts/                    # Maintenance scripts
    ├── agentkore-init.sh       #   Initialize a fresh project
    ├── agentkore-validate.sh   #   Validate system integrity
    └── ...                     #   7 more scripts
```

### `.opencode/` — OpenCode Executor Config

```
.opencode/
├── skills/                     # 16 core skills (always installed)
│   ├── agent-contract/         #   Core execution contract
│   ├── agent-flow/             #   Workflow selection
│   ├── change-test-loop/       #   Small-change verification
│   ├── git-workflow/           #   Safe git operations
│   ├── security/               #   Security guardrails + review
│   └── ...                     #   11 more core skills
├── optional-skills/            # 31 optional skills (install with ./run skills-install)
│   ├── nextjs-app-router/      #   Stack: Next.js
│   ├── python-fastapi/         #   Stack: Python FastAPI
│   ├── docker/                 #   Infra: Docker
│   ├── typescript/             #   Stack: TypeScript
│   └── ...                     #   27 more optional skills
├── commands/                   # Slash commands (/plan, /review, etc.)
│   ├── plan.md
│   ├── execute-task.md
│   ├── review.md
│   └── ...
└── agents/                     # Agent definitions
    ├── ak-executor.md
    ├── ak-planner.md
    └── ak-reviewer.md
```

### `.agentkore/scripts/` — Maintenance Scripts

```
.agentkore/scripts/
├── agentkore-init.sh           # Initialize a fresh project installation
├── agentkore-validate.sh       # Validate system integrity
├── agentkore-uninstall.sh      # Clean removal of AgentKore
├── agentkore-archive-session.sh
├── agentkore-check-skills.sh
├── agentkore-clean.sh
├── agentkore-context.sh
├── agentkore-new-doc.sh
└── agentkore-task.sh
```

### `docs/` — Project Documentation

```
docs/
├── README.md                   # Docs landing page
├── DOCS-INDEX.md               # Doc index
├── project_structure.md        # This file
├── agent_initialization_guide.md  # Agent init sequence
├── design/
│   └── DESIGN.md               # UI/visual design spec
├── architecture/
│   ├── ARCHITECTURE-NOTE-TEMPLATE.md
│   └── KORE-COUNCIL-TEMPLATE.md
├── decisions/
│   └── ADR-TEMPLATE.md
├── prd/
│   ├── PRD-LITE-TEMPLATE.md
│   └── KORE-ELICIT-TEMPLATE.md
├── research/
│   ├── RESEARCH-NOTE-TEMPLATE.md
│   └── AGENTKORE-REBUILD-PROMPT.md
└── tasks/
    └── TASK-PLAN-TEMPLATE.md
```

### `memory/` — Durable Knowledge

```
memory/
├── README.md         # Memory system overview
├── index.md          # Memory file index
├── patterns.md       # Recurring code/design patterns
├── decisions.md      # Key technical decisions
├── mistakes.md       # Lessons learned
└── commands.md       # Useful CLI commands
```

Memory files are **protected** — they survive `./run deploy self` and persist across re-installs.

## Deploy Workflow

```
1. Edit in src/agent-kore/        # Canonical source
2. ./run deploy self               # Copy src → root, validate
3. ./run deploy <project>          # Copy to other projects
4. git commit                      # Commit from root

Protected files that survive deploy:
  .env.example  .gitignore  AGENTS.md  opencode.json
  memory/       .agentkore/sessions/
```
