# Pipeline Reference — Hermes Cortex

Four growth pipelines that drive continuous system improvement.

## 1. 📖 Learnings (Memory That Compounds)

Captures bug fixes, workflows, and domain knowledge from agent sessions.

| Step | Tool | Schedule | LLM? | Output |
|------|------|----------|------|--------|
| Mine | `daily-lesson-mine.sh` | Daily 02:00 | ✗ | Lesson DB |
| Stats | `lesson-compound-stats-brief.sh` | Daily 02:30 | ✗ | Hit counts → Telegram |
| Promote | `promote-lessons-to-skills` (LLM cron) | Monthly 1st 09:00 | ✓ | Skill drafts → Telegram |

**Closed loop:** Session work → lesson mined → hit tracked → promoted to skill.

## 2. 💾 Session

Preserves active working context across agent sessions.

| Step | Tool | Schedule | LLM? | Output |
|------|------|----------|------|--------|
| Write | `update-session-state.sh` | Every 2h | ✗ | `.hermes-cortex/sessions/` |
| Archive | `hermes-cortex-session-state` (cron) | Every 2h | ✗ | Archived sessions |

**Closed loop:** Non-negotiable for context continuity.

## ⚡ 3. 📡 Skills (Moses orchestrator — multi-agent pipeline)

Discovers agent-developed skills from remote agents and evaluates them for upstreaming.

| Step | Tool | Schedule | LLM? | Output |
|------|------|----------|------|--------|
| Request | `agent-learning-collector` | Every 6h per agent | ✓ no_agent | Delta report (skills, lessons, sessions) → inbox_orchestrator |
| Evaluate | `orch-skill-lifecycle` | Daily 04:00 | LLM | Reads bus, cross-refs, upgrades skills → repo |

**Closed loop:** Request → collect → digest → evaluate → upstream (via `public-contribution` skill).

## 4. 🗄️ Memory

Persists stable facts, preferences, and conventions across sessions.

| Step | Tool | Schedule | LLM? | Output |
|------|------|----------|------|--------|
| Write | Session writes via `memory` tool | Per-turn | ✗ | MEMORY.md updates |
| Sync | `memory-to-brain-sync.py` | Every 6h | ✗ | Legacy Sync |
| Prune | `memory-pruning` (LLM cron) | Daily 04:00 | ✓ | Compacted MEMORY.md |
| Compress | `memory-compress.py` | Weekly Sun 05:00 | ✗ | Compressed archives |
| Budget | `check-memory-budget.sh` | Morning briefing | ✗ | Usage % alert |

**Closed loop:** Write → sync → prune → compress. Budget check prevents overflow.

## 5. ⚡ Quality (LLM-as-Judge trace scoring)

Evaluates Hermes conversation trace quality using a local LLM judge. Scores are posted to
Langfuse and serve as a feedback signal for agent behaviour.

| Step | Tool | Schedule | LLM? | Output |
|------|------|----------|------|--------|
| Score | `llm-judge-scorer.py` | Weekdays 13:30, 20:00 KST | ✗ (no_agent, calls Ollama internally) | Langfuse scores on unscoped traces |
|       |                     | Weekends 22:00 KST |      | |

**Closed loop:** Trace generated → judge scored → agent reads score → behaviour adjusts.

## 6. ⚡ Code Corpus (Offline Knowledge)

A 518-snippet code corpus deployed to every agent, searchable entirely offline via `offline_code search`.
The corpus is **self-improving** — agents contribute back when they find missing patterns.

| Step | Tool | Schedule | LLM? | Output |
|------|------|----------|------|--------|
| Deploy | `cortex-update.sh` (sync_code_corpus) | On each deploy | ✗ | `.md` files synced to `~/.hermes-cortex/offline/code-corpus/` |
| Index | `agent-offline-code-index` (cron) | Weekly Sun 05:00 | ✗ | Vector index refreshed (nomic-embed-text:v1.5) |
| Learn | `offline_code learn` | On demand (when web_search fills a gap) | ✗ | New `.md` snippet created in code-corpus |

**Agent workflow (mandatory):** `offline_code search "<question>"` → hit? use it. Miss? `web_search()`, then `offline_code learn` to fill the gap. Every cron job's quality gate enforces this cycle.

## ⚡ Consolidated Nightly Window (Luke's deployment — 02:00–05:00 KST)

Most writes happen overnight when the system is idle:

```
01:00 — Bible reading (LLM)
02:00 — Lesson mine (no_agent)
02:05 — Skill report request (no_agent)
02:10 — Process pending requests (LLM)
02:15 — Homebrew updates (LLM)
02:30 — Lesson compound stats (no_agent)
02:30 — Hermes update check (LLM)
03:00 — Web cache prune (no_agent)
03:00 — Skill evaluation (LLM)
04:00 — Memory pruning (LLM)
04:00 — Web cache backup (no_agent)
05:00 Sun — Memory compress (no_agent)
```

---

## Autonomous Agent Reliability Patterns

Based on Karpathy's research (41% → 3% mistake rate reduction with explicit constraints):

- **Task Contract** — For 3+ step tasks, define goal/success criteria/constraints/checkpoints *before* executing. Template: `docs/templates/task-contract.md`
- **Checkpoint Verification** — Verify each step before proceeding. Fixing state retroactively is 10x harder.
- **Conflict Surfacing** — When detecting multiple patterns, surface the conflict explicitly. Do NOT blend silently.
- **Read-Before-Write** — Read a file before editing it unless creating from scratch. 90% of mistakes come from missing context.
- **Eval-Driven Development** — Define evals BEFORE building. Capability evals (new features) + regression evals (maintain ≥95%). Skill: `eval-harness`.

## Structured Development Pipeline

When building new features or making significant changes, use this structured workflow:

```text
requirements-elicitation (structured requirements gathering)
    ↓
architecture-review (multi-role architecture review)
    ↓
product-requirements (concise product spec)
    ↓
story-decomposition (user-visible, testable stories)
    ↓
change-test-loop (RED-GREEN-REFACTOR with lessons)
    ↓
code-review (security scan, quality gate)
```

Each stage consumes the output of the prior one, reducing rework and enforcing quality gates before code is written.

## Skill Collection (Every 6h, All Agents → Orchestrator)

Every agent runs `agent-learning-collector` (no_agent, every 6h). It scans local skills (hash-based delta), checks for pending learning reports in `~/brain/learnings/pending/`, collects session stats, and sends a compact "Learning Report" to `inbox_orchestrator` (the shared orchestrator inbox) via PGMQ. The collector runs in <1s — no heavy processing.

Session mining (extracting lessons from past conversations) is handled by a separate overnight cron: `agent-session-mine` at 2am KST. It runs `session-mine mine --days 1 --auto`, which dumps mined lessons into `~/brain/lessons/`. The collector picks them up instantly on its next tick. On first run, it bootstraps all historical sessions.

**On-demand trigger:** agents can run `agent-learning-collector.py --force` to flush learnings immediately without waiting for the 6h schedule.

**Ad-hoc learning submissions:** any agent in an active session writes a structured `.md` file to `~/brain/learnings/pending/`. The next collector tick includes it in the report, then moves it to `~/brain/learnings/sent/`. See `docs/agent-learning-submissions.md` for file format.

Silent when nothing new (watchdog pattern). Every 24h sends a heartbeat even with no changes so Moses knows the agent is alive.

### Processing (Moses-side)

Moses runs `orch-skill-lifecycle` (LLM-driven, daily 04:00):

1. **Read** `inbox_orchestrator` for all Learning Reports from fleet agents
2. **Cross-reference** across agents — if 3 agents report the same fix, it's a consolidation candidate
3. **Deduplicate** against existing skills in the repo
4. **Classify** each item: patch existing skill / create new / merge duplicates / add principle to SOUL.md
5. **Execute** changes: patch skills via skill_manage or repo edit, update SOUL.md, prune stale content
6. **Upstream**: git commit + push → fleet pulls on next sync
7. **Archive** processed messages from the queue

On Monday: runs a deep evaluation pass (full dedup, staleness detection, cross-fleet merge candidates).

---

### 5. Governance & Quality

| Cron | Type | Schedule | Script / Skill | Deliver |
|------|------|----------|----------------|---------|
| `orch-skill-lifecycle` | LLM+skill | `0 4 * * *` | `orch-skill-lifecycle` | origin |
| `agent-learning-collector` | no_agent | `0 */6 * * *` | `agent-learning-collector.py` | local |
| `session-cache-build` | no_agent | `0 5 * * 1` | `session_cache.py` | origin |
| `cron-quality-watchdog` | no_agent | `*/10 * * * *` | `agent-cron-quality-watchdog.py` | origin |

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-15T00:00:00+00:00