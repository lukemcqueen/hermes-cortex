# Agent Learning Submissions — How to Send Learnings to the Orchestrator

Any Hermes Cortex agent can submit ad-hoc learnings to the orchestrator
(Moses) at any time. No need to wait for the 6h automated collection cycle.

## Quick Start

The `~/brain/learnings/pending` and `~/brain/learnings/sent` directories are
auto-created by the `agent-learning-collector` on its first tick (every 6h)
and by `bootstrap-brain.sh` during install — the `mkdir -p` below is only
needed for immediate use before the first collector run.

During an active session, write a structured `.md` file:

```bash
mkdir -p ~/brain/learnings/pending

cat > ~/brain/learnings/pending/$(date +%Y%m%d)-discovery.md << 'EOF'
---
title: Found a better pattern for X
type: discovery
---

## Discovery
What you found — the key insight.

## Evidence
Why it's correct — commands run, outputs observed, files read.

## Recommendation
What Moses should do with this: patch a skill, create one, update SOUL.md.
EOF
```

## Supported Types

| Type | Icon | When to use |
|------|------|-------------|
| `discovery` | 💡 | New pattern, trick, or approach discovered during work |
| `lesson` | 📘 | Hard-won knowledge after debugging or fixing something tricky |
| `improvement` | 🔧 | Suggestion for making a workflow, tool, or doc better |

## File Format

**With frontmatter (recommended):**
```markdown
---
title: Descriptive title for the learning
type: discovery  # or lesson, improvement
---
```

**Without frontmatter (fallback):** the first `# Heading` becomes the title.
Type defaults to `discovery`.

## What Happens Next

1. The next `agent-learning-collector` tick (every 6h, or on-demand via `--force`)
   picks up the file from `~/brain/learnings/pending/`
2. It's included in the Learning Report sent to `inbox_orchestrator`
3. The file is moved to `~/brain/learnings/sent/` after successful send
4. Moses evaluates and acts: patch a skill, create one, update SOUL.md

## On-Demand Flush

Don't want to wait 6h? Run the collector immediately:

```bash
python3 ~/.hermes-cortex/scripts/agent-learning-collector.py --force
```

This collects pending learnings + skills + lessons and sends the report
instantly. Runs in <1s — skips session mining (handled by overnight cron).

## Related

- `agent-learning-collector` (cron, every 6h)
- `agent-session-mine` (cron, 2am KST)
- `orch-skill-lifecycle` (cron, daily 4am — processes reports on Moses side)
