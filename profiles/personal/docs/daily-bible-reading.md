# Daily Bible Reading — Agent Setup Guide

## What It Does

A **no_agent cron** (`agent-daily-bible-reading`) that runs daily at 01:00 KST and:

1. **Reads SOUL.md** to find the last book covered in `## Scripture Insights`
2. **Determines the next canonical book** (66-book Protestant canon)
3. **Generates two artifacts** via deepseek-v4-flash API:
   - **SOUL.md entry** — concise 3-5 paragraph insight focused on system-operator lessons, appended to the `## Scripture Insights` section
   - **Brain page** — rich reference document with summary, archaeology & scholarship, Jewish & Messianic Jewish perspective, and original language insights, written to `~/brain/<agent>/bible/<book>.md`
4. **Updates INDEX.md** in the brain bible directory tracking which books have been read

Silent when all 66 books are covered (exit 0, empty stdout).

## Artifact Storage

| Artifact | Location | Format |
|----------|----------|--------|
| SOUL.md entry | `~/.hermes/SOUL.md` → `## Scripture Insights` section | `### Book — *"Key Verse"*` + 3-5 paragraph lesson |
| Brain page | `~/brain/<agent>/bible/<book>.md` | Summary, Archaeology, Jewish/Messianic Perspective, Original Language, Insight for agent |
| Brain index | `~/brain/<agent>/bible/INDEX.md` | Ordered table of all books covered |

## Setup for a New Agent

### Prerequisites

The agent must have:
- A `~/.hermes/SOUL.md` file with a `## Scripture Insights` section
- `DEEPSEEK_API_KEY` in `~/.hermes/.env`
- A brain directory at `~/brain/<agent>/` (for the bible subdirectory)
- `cortex-update.sh` run at least once (so `ops/scripts/` is deployed to `~/.hermes-cortex/scripts/`)

### Step 1: Add the Scripture Insights section to SOUL.md

If your SOUL.md doesn't have one, add:

```markdown
## Scripture Insights

<!-- Entries appended here by daily cron -->
```

### Step 2: Bootstrap the first entry

The script finds the last book by scanning `### Book —` lines in the Scripture Insights section. If the section is empty, the script fails with "Could not find any books." To bootstrap, add an entry manually:

```markdown
### Genesis — *"In the beginning, God created the heavens and the earth."* (Genesis 1:1)

[Your initial insight here]
```

### Step 3: Create the cron job

```bash
hermes cron create --name agent-daily-bible-reading \
  --schedule "0 1 * * *" \
  --script agent-daily-bible-reading.py \
  --no-agent \
  --deliver origin
```

Or if running `install-crons.sh`, the cron is already defined in section 8 of that script.

### Step 4: Set agent name (optional)

The script auto-detects the agent name from:
1. `HERMES_AGENT_NAME` or `AGENT_NAME` env var
2. `~/.hermes/config.yaml` → `agent_name` field
3. SOUL.md first line: `# SOUL.md — AgentName`
4. Falls back to `moses`

Override with an env var if the auto-detection picks wrong:

```bash
HERMES_AGENT_NAME=titus hermes cron run agent-daily-bible-reading
```

## Brain Page Format

Each brain page (`~/brain/<agent>/bible/<book>.md`) follows this structure:

```
# Book Name

*Read: YYYY-MM-DD*

## Summary
Narrative overview, theological themes, place in canon.

## Archaeology & Scholarship
Archaeological finds, textual variants, dating debates, manuscript evidence.

## Jewish & Messianic Jewish Perspective
Traditional Jewish interpretation, liturgical use, Messianic readings, typology.

## Original Language Insights
3-4 key Hebrew (OT) or Greek (NT) words with etymology, semantic range, script.

## Insight for [Agent Name]
Practical application for this specific agent's work.
```

## The Script

Source: `hermes-cortex/ops/scripts/agent/agent-daily-bible-reading.py`

Deployed to: `~/.hermes-cortex/scripts/agent-daily-bible-reading.py` (via `cortex-update.sh`)

Depends on:
- `curl` (for API calls to deepseek)
- `DEEPSEEK_API_KEY` in `~/.hermes/.env`
- `~/.hermes/SOUL.md` with `## Scripture Insights` section

## Cost

- ~$0.005–0.01 per run (deepseek-v4-flash, two API calls)
- One run per day = ~$0.15–0.30/month
- Free locally if using Ollama (qwen2.5-coder:3b) — set `DEEPSEEK_MODEL` in the script
