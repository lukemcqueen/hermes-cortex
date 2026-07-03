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
| Request | `request-skill-reports.sh` | Daily 02:05 | ✗ | Inbox broadcast to agents |
| Collect | `collect-agent-skills.sh` (agent-side) | Every 6h per agent | ✗ | Full SKILL.md → Moses inbox |
| Digest | `process-skill-reports.py` | Every 6h at :15 | ✗ | Summary digest → Telegram |
| Evaluate | `evaluate-skill-reports` (LLM cron) | Daily 03:00 | ✓ | Scored recommendations → Telegram |

**Closed loop:** Request → collect → digest → evaluate → upstream (via `public-contribution` skill).

## 4. 🗄️ Memory

Persists stable facts, preferences, and conventions across sessions.

| Step | Tool | Schedule | LLM? | Output |
|------|------|----------|------|--------|
| Write | Session writes via `memory` tool | Per-turn | ✗ | MEMORY.md updates |
| Sync | `memory-to-brain-sync.py` | Every 6h | ✗ | gbrain sync |
| Prune | `memory-pruning` (LLM cron) | Daily 04:00 | ✓ | Compacted MEMORY.md |
| Compress | `memory-compress.py` | Weekly Sun 05:00 | ✗ | Compressed archives |
| Budget | `check-memory-budget.sh` | Morning briefing | ✗ | Usage % alert |

**Closed loop:** Write → sync → prune → compress. Budget check prevents overflow.

## 5. ⚡ Quality (LLM-as-Judge trace scoring)

Evaluates Hermes conversation trace quality using a local LLM judge. Scores are posted to
Langfuse and serve as a feedback signal for agent behaviour.

| Step | Tool | Schedule | LLM? | Output |
|------|------|----------|------|--------|
| Score | `llm-judge-scorer.py` | Weekdays 12:00, 20:00 KST | ✗ (no_agent, calls Ollama internally) | Langfuse scores on unscoped traces |
|       |                     | Weekends 22:00 KST |      | |

**Closed loop:** Trace generated → judge scored → agent reads score → behaviour adjusts.

## 6. ⚡ Code Corpus (Offline Knowledge)

A 518-snippet code corpus deployed to every agent, searchable entirely offline via `offline_code search`.
The corpus is **self-improving** — agents contribute back when they find missing patterns.

| Step | Tool | Schedule | LLM? | Output |
|------|------|----------|------|--------|
| Deploy | `cortex-update.sh` (sync_code_corpus) | On each deploy | ✗ | `.md` files synced to `~/.hermes/offline/code-corpus/` |
| Index | `offline-code-index` (cron) | Weekly Sun 05:00 | ✗ | Vector index refreshed (nomic-embed-text:v1.5) |
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