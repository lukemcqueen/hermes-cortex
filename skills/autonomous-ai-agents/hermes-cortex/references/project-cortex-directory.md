# Project `.hermes-cortex/` Directory Convention

> **Read this first — two directories share the name, and they are NOT the same.**
>
> - `~/.hermes-cortex/` is the **runtime infra dir** (deployed by `cortex-update.sh`):
>   `scripts/`, `state/`, `sessions/`, `memory/`, `hooks/`, and the `skills.yaml` the
>   **enforcer** reads. Always write it with the `~/` anchor.
> - `.hermes-cortex/` (as below) is a **repo-local overlay inside a CONSUMER project**,
>   created by `seed-project.sh`.
>
> A bare `.hermes-cortex/` is never the runtime dir. Agents that conflate them go
> looking for the infra dir inside the project and report the overlay as "the Hermes
> agent infra directory". It is also why the Cortex repo itself must carry **no**
> repo-local `.hermes-cortex/` — inside `~/hermes-cortex` the name shadows the runtime
> dir (doctor check `Repo-local .hermes-cortex`, see `docs/review-receipt-gate.md`).

## Summary

Projects using Hermes Cortex can keep agent infrastructure in a hidden **repo-local** `.hermes-cortex/` directory at the repo root instead of cluttering the top level with `memory/`, `sessions/`, etc.

## Layout

```
project-root/
├── .gitignore                  # + .hermes-cortex/memory/
├── AGENTS.md                   # STAYS at root (tool convention)
├── docs/                       # STAYS at root (team docs)
├── scripts/                    # STAYS at root (project utilities)
│
└── .hermes-cortex/
    ├── sessions/
    │   ├── current.md          # Active session (cron updates this)
    │   └── archive/            # Timestamped session snapshots
    ├── memory/                 # Gitignored — per-user agent memory
    │   ├── MEMORY.md
    │   └── USER.md
    ├── skills/                 # Tracked — project-specific skills
    └── .gitkeep
```

## Git Tracking

| Path | Tracked? | Why |
|------|----------|-----|
| `.hermes-cortex/sessions/` | Yes | Session history is project narrative |
| `.hermes-cortex/skills/` | Yes | Project-specific skills are team assets |
| `.hermes-cortex/memory/` | No | Per-user agent memory (MEMORY.md/USER.md) |

**.gitignore:** `.hermes-cortex/memory/`

## Agent Discovery

Agents check for `.hermes-cortex/` first. If it exists, use it. If not, fall back to `memory/` and `project_current_session.md` at the repo root. Both layouts work.

## When to Use

The convention kicks in once a project has 3+ agent infrastructure files (`AGENTS.md`, `memory/`, `docs/`, `sessions/`, `scripts/`, etc.). For tiny projects (3-file utility scripts), skip it — keep everything at root until the clutter justifies the hidden directory.

## See Also

- hermes-cortex `docs/knowledge-isolation-architecture.md`
- Moses's original proposal commit: `5ddcca5`
