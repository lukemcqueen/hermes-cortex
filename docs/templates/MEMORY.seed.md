<!-- Part of Hermes Cortex. See docs/SECURITY.md for privacy. -->
# Hermes Agent — MEMORY.md

Your agent reads this file on every message turn. Keep it under **2,200 characters**.

Use the **pointer pattern** — store full detail in brain directories, keep only compact pointers here.
Pointers look like: `→ /brain <source> <topic>` (e.g. `→ /brain m docker`).

---

## System Topology

*(Your machine, OS, installed services, repo structure)*

- **OS:**
- **Shell:**
- **Package manager:**
- **Repos:**
- **Services:**
- **Key tools:**

---

## Orchestration

*(Your agent identity, model providers, coordination patterns)*

- **Agent identity:**
- **Default provider/model:**
- **Other agents sharing this setup:**
- **Brain topology:**

---

## Agent Context

*(Activated skills, cron jobs, pointer references)*

- **Skills:**
- **Crons:**
- **References:** `/brain m <topic>` for full detail

---

## Design Principles

1. **Keep < 2,200 chars** — this file is injected every turn
2. **Pointer pattern** — compact here, deep in brain
3. **No task artifacts** — completed work goes to docs or brain, not memory
4. **No public knowledge** — if another agent would benefit, write it to `docs/`
5. **No PII** — real names, emails, tokens, domains stay out of memory
