---
name: cron-quality-gate
version: 1.0.0
category: devops
description: "Prevents LLM cron jobs from delivering garbage with a self-check quality gate and automated watchdog."
author: Hermes Cortex
license: MIT
metadata:
  hermes:
    tags: [cron, quality, watchdog, overspend, guardrails]
---

# Cron Output Quality Gate

A two-layer guard that prevents LLM-driven cron jobs from delivering gibberish, runaway output, or empty responses.

## Architecture

```
Layer 1 — Self-Check (in the cron prompt)
  Every LLM cron prompt includes a quality gate block that
  tells the agent to self-evaluate before delivering.
  Failure → agent outputs QUALITY_G_BLOCKED token instead
  of garbage.

Layer 2 — Watchdog (no_agent script, every 10 min)
  Script scans recent cron output for:
  - QUALITY_G_BLOCKED token → alert
  - Oversized output (>6000 chars) → possible runaway
  - Empty output → silent failure
  - Corrupted unicode / repetitive gibberish → encoding corruption

  Silent when clean (watchdog pattern).
```

## The Quality Gate Prompt Block

Add this to **every** LLM cron prompt:

```
## QUALITY GATE — CRITICAL
### Cost-saving: offline-first
BEFORE calling `web_search()` or making any external API call:
1. Load the `offline-code` skill (loaded automatically if attached to cron)
2. Run `offline_code search "<diagnostic question>"` to check the corpus
3. If offline result is relevant → use it. Zero cost, zero latency.
4. Only fall back to `web_search()` if offline has nothing useful.

### Self-check
Before delivering, self-check:
1. Is the output useful, readable, and on-topic?
2. Did you run actual tools, not fabricate results?
3. Did you check the offline corpus before making external calls?
4. If you used web_search because offline had nothing → did you
   run `offline_code learn` to add the result back to the corpus?
5. Is it the right length (not oversized, not empty)?
If ANY answer is NO → output EXACTLY this one line:
QUALITY_G_BLOCKED

If all YES → deliver as normal.
```

## Watchdog Script

Location: `~/.hermes/scripts/agent-cron-quality-watchdog.py`

Runs as `no_agent=True` cron on schedule `*/10 * * * *`. Delivers to origin.

### What it checks

| Check | Threshold | Severity |
|-------|-----------|----------|
| `QUALITY_G_BLOCKED` token in output | Any occurrence | 🔴 Agent self-blocked |
| Output length | > 6000 chars | 🟠 Possible runaway |
| Empty/whitespace-only | < 5 bytes | 🟡 Silent failure |
| Suspicious unicode ratio | > 30% non-ASCII/control | 🔴 Encoding corruption |
| Repetitive content | Substring repeats > 30% | 🔴 Gibberish |

## Installation

1. Create the script at `~/.hermes/scripts/agent-cron-quality-watchdog.py`
2. Create the cron: `*/10 * * * *`, no_agent=True, script=agent-cron-quality-watchdog.py
3. Append the quality gate block to every LLM cron prompt

## Adding to a new LLM cron

Every time you create a new LLM-driven cron, append the quality gate block to its prompt.

## Relationship to the drift guard

The drift guard (built into Hermes cron, documented in the `cron-job-management` skill) and the quality gate are **complementary layers**:

| Guard | Prevents | How |
|-------|----------|-----|
| **Drift guard** | Silent overspend on wrong provider/model | Blocks the cron from running at all if provider/model changed since creation |
| **Quality gate** | Garbage/runaway output even when running on the right model | Self-check in prompt + external watchdog |

The drift guard is a **pre-flight** check (no inference call if it fails). The quality gate is a **post-flight** check (inference runs, but garbage is caught before it reaches the user).

**When both are active:**
1. Drift guard checks provider/model identity → blocks if drifted
2. Cron runs normally on the correct provider/model
3. Quality gate self-check runs → agent blocks itself if garbage
4. Watchdog scans output → alerts you if anything slipped through

Always pin LLM crons explicitly (`provider=openrouter model=...`) so the drift guard doesn't block them, and always append the quality gate block so the output is verified.

## Maintenance

To update the watchdog script:
```bash
patch ~/.hermes/scripts/agent-cron-quality-watchdog.py
```

To check watchdog health:
```bash
python3 ~/.hermes/scripts/agent-cron-quality-watchdog.py
```