---
name: loop-governance
version: 1.5.0
category: devops
description: "TDD cycle scoring, self-improvement, and governance system for Hermes Cortex. Scores completeness/quality/progress per cycle with nomic embeddings, logs to SQLite, collects user feedback via CLI, auto-applies config patches with safety bounds, and integrates weekly evaluation + retention. Runtime config, test suite, setup/verify/update scripts, and auto-remediation health checks."
author: Moses (Hermes Cortex)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [loop-control, scoring, decision-matrix, bounded-iteration, no-progress, token-budget, governance]
    related_skills: [change-test-loop, subagent-driven-development, lesson-aware-agent, agent-flow]
---

# Loop Governance v1.5.0

> **The universal loop controller.** Every agent loop — whether TDD cycles, review→fix→review, or plan→execute→verify — needs three things: a way to **score** progress, a way to **decide** what to do next, and a **bound** that prevents infinite spinning.

## Overview

Loop governance provides a **scoring function** and a **decision matrix** that any workflow skill can import. The scorer uses `nomic-embed-text` (local, cheap, ~50ms per call) for three independent measurements:

| Dimension | What it measures | How (nomic) |
|-----------|-----------------|-------------|
| **Completeness** (0-10) | How much of the goal is achieved | Embed test output vs spec → cosine similarity |
| **Quality** (0-10) | Code density, TODOs, docstrings | Embed code → magnitude + heuristic penalties |
| **Progress** (0-10) | Did this iteration change anything? | Embed prev output vs current → 1 - cosine similarity |

These feed into a **weighted composite score** that drives the decision gate.

## When to Load This Skill

Load `loop-governance` whenever you are running **any multi-iteration loop**:

- After a change-test-loop cycle completes — decide whether to loop for more coverage
- After a review→fix→review cycle in subagent-driven-development — decide whether to keep iterating
- After a spike→evaluate→refine exploration loop
- After a plan→execute→verify pipeline iteration
- Anywhere you ask "should I loop again, stop, or escalate?"

## The Decision Matrix

```
┌──────────────────────────────────────────────────────┐
│                  LOOP GOVERNANCE                       │
│                                                        │
│   Iteration N → loop_scorer.py → composite score       │
│                                                        │
│   Composite >= 8.0  →  STOP ✓    (goal met, good)     │
│   Composite 5.0-7.9 →  LOOP 🔄   (keep iterating)     │
│   Composite 3.0-4.9 →  MOVE ON → (skip, escalate)     │
│   Composite < 3.0   →  STOP ✗    (hard fail)          │
│                                                        │
│   No-progress >= 3x →  STOP ✗    (spinning)           │
│   Max iterations hit → STOP ✗    (budget exhausted)    │
└──────────────────────────────────────────────────────┘
```

### Composite weights

| Dimension | Weight | Rationale |
|-----------|--------|-----------|
| Completeness | 40% | Goal achievement is primary |
| Quality | 30% | Works isn't enough; it must be maintainable |
| Progress | 30% | Must be moving forward, not spinning |

## The Scoring Function

### Session embedding cache (vector index)

A local SQLite vector cache (`session-embeddings.db`) stores embeddings from
sessions, loop DB cycles, and skills. It improves progress detection by comparing
current code against ALL stored good patterns, not just the immediate previous cycle.

**Build/re-build the cache:**
```bash
session-cache build   # scans sessions, loop DB, skills → embeds → stores
session-cache status  # show cache stats
session-cache search  # interactive similarity search
```

**Cache integration:** `loop_scorer._cache_boost()` checks the cache during every
`score_progress()` call. If the current output is very similar (cosine > 0.85)
to a known-good pattern in the cache, progress gets a +2 boost. For moderate
similarity (>0.75), +1 boost. This means scoring improves as the cache grows.

**Cron:** `session-cache-build` runs Monday 5am KST (before skill-miner at 6am).

**Agent data:** Agents contribute session data via skill-miner findings
(to=moses, topic=moses). The cache is rebuilt weekly, incorporating new data.

### Installation & invocation

The scorer module lives at `scripts/loop_scorer.py` in this skill directory (underscore so Python can import it directly). Run a demo from any directory:

```bash
python3 ~/.hermes/skills/devops/loop-governance/scripts/loop_scorer.py
```

Import the functions directly:

```python
from loop_scorer import score_progress, score_quality, score_completeness, composite_score

# Or for one-off scoring via shell
import json
result = json.loads(terminal(
    'python3 -c "from loop_scorer import composite_score; import json; print(json.dumps(composite_score(9, 8, 9)))"'
)["output"])
```

> **Naming convention:** Python modules use underscores (`loop_scorer.py`). CLI commands use hyphens (`score-cycle`, `loop-feedback`, `auto-apply`). This is deliberate — Python can't import hyphenated names, and CLI tools conventionally use hyphens.

### What each dimension measures

#### Completeness

Measures how much of the spec/requirements the implementation fulfills. Uses a **blended approach** (60/40):

1. **Test pass rate (60%)** — the strongest single signal. If all tests pass, completeness gets at least 6/10. Maps via: 100%→10, 90%→8, 80%→6, 50%→4, below→linear.
2. **Embedding similarity (40%)** — cosine similarity between test output embedding and spec text embedding, mapped to 0-10.

```python
completeness = score_completeness(test_output, spec_text, pass_pct=0.95)
# Returns 0-10 — blended: 60% pass rate, 40% embedding match
```

The pass-rate anchor prevents false negatives when the test output boilerplate (pytest headers, PASSED/FAILED markers) dilutes the embedding signal. Always pass `pass_pct` when the test runner output is available.

**Scale:**
- 8-10: All/most tests pass, spec comprehensively covered
- 5-7: Core behavior working, some edge cases or detail missing
- 2-4: Minimal test coverage, major spec gaps
- 0-1: No tests, all failing, or tests unrelated to spec

#### Quality

Embed the implementation code and compute a semantic density score. Apply heuristic penalties for TODO/FIXME markers, stub implementations, missing docstrings.

```python
quality = score_quality(code_text)
# Returns 0-10
```

**Scale:**
- 8-10: Well-structured, documented, no stubs, proper error handling
- 5-7: Functional with minor quality gaps (light docs, some edge cases)
- 2-4: Stubs present, sparse comments, weak structure
- 0-1: `pass` stubs or placeholder only

#### Progress

Embed the state from the **previous iteration** and the **current iteration**, then compute `1 - cosine_similarity`. The more different the embeddings, the more progress.

**Critical: compare CODE against CODE, not test output against test output.**
Test runner output (pytest, etc.) contains heavy boilerplate — PASSED/FAILED markers, headers, timing info — that stays nearly identical across iterations even when the code changes substantially. Comparing test output produces artificially low progress scores (0-1/10). Comparing implementation code produces accurate progress detection.

```python
# ✅ CORRECT — compare code
progress = score_progress(previous_code, current_code)

# ❌ WRONG — test output has too much boilerplate
progress = score_progress(previous_test_output, current_test_output)
```

**Scale:**
- 8-10: Completely different output — substantial change
- 5-7: Meaningfully different — real progress
- 2-4: Slightly different — minimal change
- 0-1: Nearly identical — no progress (trigger no-progress counter)

## No-Progress Detection

The most common token waste in loops is **spinning**: the agent keeps iterating but produces the same output each time. No-progress detection prevents this.

### Rule

```python
# Track across iterations
no_progress_count = 0
previous_embedding = None

for iteration in range(max_iterations):
    current_output = run_iteration(goal)
    
    if previous_embedding:
        progress = score_progress_from_embeddings(previous_embedding, embed(current_output))
        if progress < 2.0:      # threshold: less than 2/10 change
            no_progress_count += 1
        else:
            no_progress_count = 0   # reset on genuine progress
    
    previous_embedding = embed(current_output)
    
    if no_progress_count >= 3:
        return {"decision": "STOP ✗", "reason": "no-progress ≥ 3 iterations"}
```

**Key point:** Check progress at the semantic level (embeddings), not just text diff. A single comment change is not progress even though the text differs.

### When to apply

Apply no-progress detection to:
- Change-test-loop: between complete LEARN→RED→GREEN→REFACTOR cycles
- Subagent-driven-development: between review→fix→review cycles (same finding appearing repeatedly)
- Any exploration loop where successive iterations produce similar output

## Bounded Iteration

Every loop must have **at least one hard bound**:

| Bound | Default | When to adjust |
|-------|---------|---------------|
| **Max iterations** | 5 | Increase for complex multi-phase work, decrease for simple fixes |
| **No-progress limit** | 3 consecutive | Tighten to 2 for cost-sensitive tasks |
| **Token budget** | None (opt-in) | Set when running against paid API — e.g. "200K tokens total" |

### Setting bounds

```python
BOUNDS = {
    "max_iterations": 5,          # hard stop after this many cycles
    "max_no_progress": 3,         # stop after N iterations with < 2/10 progress
    "max_retries_per_phase": 2,   # per-phase retry limit (from change-test-loop)
    "token_budget": None,         # optional: max total tokens for this loop
}
```

**No bounds → open loop.** Open loops are only acceptable for continuous monitoring (cron jobs, watchdogs). Every code-workflow loop must be closed (bounded).

## Fresh Context Strategy

After each loop iteration, the next iteration should start with **fresh context** — not the accumulated reasoning and tool output from previous rounds. This prevents context window degradation.

For subagent loops, this is natural: each `delegate_task` gets a clean agent. For in-session loops (change-test-loop), you can:

1. **Summarize** the current state into a compact prompt for the next iteration
2. **Use the loop-scorer output** as the steering signal — summarizing current scores and remaining gaps.

## Data Capture & Self-Improvement

Every loop cycle generates data — scores, decisions, code, test results. Storing this data enables the system to **improve itself over time** by analyzing past decisions and tuning thresholds.

### Architecture

Two complementary storage backends:

| Backend | Purpose | Location |
|---------|---------|----------|
| **SQLite** (`loop_db.py`) | Structured querying, aggregation, analysis | `~/.hermes/data/loop-governance.db` |
| **JSON events** (built into `LoopDB.log_cycle`) | Streaming backup, portability, disaster recovery | `~/.hermes/data/loop-events/YYYY-MM-DD.jsonl` |

### Schema (auto-created)

```
loop_cycles       - Every cycle scores + decisions + content hashes
content_assets    - Content-addressable store (deduplicates code/spec/test text)
config_history    - Config change log for rollback
```

### How to log a cycle

**Option 1: Via env vars (any script can use this)**

```bash
SCORE_DB_PATH=~/.hermes/data/loop-governance.db \
SCORE_TASK_ID=my-feature \
SCORE_CYCLE_NUM=1 \
SCORE_SPEC="Add two numbers" \
SCORE_OUTPUT="def add(a,b): return a+b" \
python3 loop_scorer.py --score
```

Output includes `logged: true` on success.

**Option 2: Via `score-cycle` CLI (recommended for TDD cycles)**

The `score-cycle` command wraps scoring + DB logging + feedback ID in one call — see "Integration with Other Skills > With change-test-loop" below.

**Option 3: Direct Python import**

```python
from loop_db import LoopDB

db = LoopDB()
db.log_cycle_with_content(
    task_id="my-feature", cycle_num=1,
    spec_text="Add two numbers",
    code_text="def add(a,b): return a+b",
    test_output="1 passed, 0 failed",
    completeness=8.0, quality=6.0, progress=10.0,
    composite=7.0, no_progress=False, decision="LOOP",
)
db.close()
```

### Analysis queries

```python
db = LoopDB()
stats = db.get_summary_stats()
# total_cycles, avg_completeness, avg_quality, avg_progress, avg_composite
# stop_count, loop_count, move_on_count, hard_fail_count, no_progress_count

cycles = db.get_cycles_for_task("task-id")
streak = db.get_no_progress_streak("task-id")
accuracy = db.get_decision_accuracy()
db.record_user_outcome(cycle_id=42, accepted=True, note="Good stop")
```

### Self-improvement pipeline

```
Phase 1 - Data Capture:       Log every cycle (built into loop-scorer.py --score)
Phase 2 - Evaluation (cron):  Weekly report: drift, accuracy, threshold analysis
Phase 3 - Auto-Apply:         Safe config patches applied automatically (auto_apply.py)
Phase 4 - Feedback Loop:      User labels → evaluator → patch → auto-apply → improved decisions
```

## User Feedback (Ground-Truth Labels)

Every loop decision is a *prediction* — the scorer says "this is good enough to STOP" or "this needs another LOOP". User feedback provides the **ground-truth label** that turns predictions into a training dataset for meta-learning.

### When to provide feedback

Provide feedback whenever you see a loop decision that was **clearly right or clearly wrong**:

| Situation | Action |
|-----------|--------|
| All tests pass, coverage good, quality acceptable → STOP was correct | `loop-feedback accept <id>` |
| Tests pass but edge cases remain → LOOP would have been better | `loop-feedback override <id>` |
| Spinning for 3+ cycles with no change → STOP (hard fail) was correct | `loop-feedback accept <id>` |
| System gave up too early (MOVE ON) but a better prompt would work | `loop-feedback override <id>` |
| System kept looping when goal was already met | `loop-feedback override <id>` |

### How to provide feedback

The `loop-feedback` CLI is available globally. Use `--db <path>` to point at a non-default database:

```bash
# List cycles that need feedback
loop-feedback list

# List recent cycles (with or without feedback)
loop-feedback list --all
loop-feedback list --limit 20

# Use a custom DB path
loop-feedback list --db /path/to/loop-governance.db

# Accept a decision (it was correct)
loop-feedback accept <cycle_id> --note "All tests pass, quality is high"
loop-feedback accept 42

# Override a decision (it was wrong — the scorer was wrong)
loop-feedback override <cycle_id> --note "Should have kept going, missing null case"
loop-feedback override 7

# Show feedback statistics
loop-feedback stats

# JSON output (for programmatic use)
loop-feedback list --json
loop-feedback stats --json
```

### Interpretation

| DB value | Meaning |
|----------|---------|
| `user_overrode = NULL` | No feedback yet (default) |
| `user_overrode = 0` | **Accepted** — user agrees the decision was correct |
| `user_overrode = 1` | **Overridden** — user disagrees with the decision |

### How feedback drives meta-learning

The weekly evaluation cron (`loop_evaluator.py`) reads `user_overrode` to compute:

1. **Decision accuracy**: what % of decisions are correct? Drives confidence in the system.
2. **Threshold recommendations**: if STOP decisions are frequently overridden at composite 8.0, maybe the threshold should be 8.5.
3. **Weight recommendations**: correlates each score dimension (completeness, quality, progress) with user acceptance, suggesting weight adjustments.
4. **Config patches**: generates JSON patches that could be auto-applied at high confidence.

Without user feedback, the evaluator reports: `"No user feedback recorded yet. User feedback is the ground-truth label for meta-learning."`

## Auto-Apply (Phase 3 — Self-Tuning)

The auto-apply system reads the evaluator's config patch, validates every change against safety bounds, and applies low-risk modifications to the runtime config. This closes the loop: data → evaluation → recommendation → application → improved decisions.

### How it works

```
Weekly cron (Monday 9am KST)
        │
        ▼
  LoopEvaluator.generate_config_patch()
        │
        ▼
  auto_apply.py
        │
    ┌───┴──────────────┐
    │                  │
    ▼                  ▼
  confidence ≥ 0.7   skipped (low confidence)
    │                  │
    ▼                  ▼
  safety checks      reported in cron output
    │
    ┌───┴────────┐
    │            │
    ▼            ▼
  safe          blocked (delta > max)
  applied       reported as skipped
    │
    ▼
  Config file updated + logged to config_history
```

### Safety bounds

Every proposed change is validated against hard limits (from `loop-config.json`):

| Parameter | Bound | Rationale |
|-----------|-------|-----------|
| `min_confidence` | 0.7 | Don't act on noisy data |
| `max_threshold_delta` | 1.0 | At most 1 point adjustment per week |
| `max_weight_delta` | 0.10 | At most 10% weight shift per week |
| Stop threshold range | [5.0, 10.0] | Must stay meaningful |
| Move-on threshold range | [1.0, 5.0] | Must stay meaningful |
| Weight range | [0.05, 0.80] | No single dimension can dominate or vanish |

### CLI usage

```bash
# Normal — skip if confidence < 0.7
auto-apply

# Preview without applying
auto-apply --dry-run

# Bypass confidence check (use with caution)
auto-apply --force

# JSON output for cron consumption
auto-apply --json

# Dry-run with JSON
auto-apply --dry-run --json
```

### Runtime config

Thresholds and weights live in `~/.hermes/data/loop-governance-config.json` and are read by `composite_score()` on every call:

```bash
# View current config
python3 ~/.hermes/skills/.../scripts/loop_config.py --show

# Set a value manually
python3 ~/.hermes/skills/.../scripts/loop_config.py --set weights.completeness 0.45
```

See `references/config-format.md` for the full config schema, field descriptions, and rollback procedure.

### Cron schedule

All loop-governance crons managed via `crons.json` (versioned) + `install-crons.py`:

| Cron | Schedule | Mode | Behaviour |
|------|----------|------|-----------|
| `session-cache-build` | Mon 5am KST | no_agent | Rebuilds embedding cache from sessions, DB, skills |
| `agent-weekly-loop-eval` | Mon 9am KST | LLM-driven | Generates evaluation report, runs `auto-apply.py`, vacuums old cycles. Delivers combined message. |

**Versioning:** Bump the `version` field in `crons.json` to trigger agent updates.
The `install-crons.py` script reads the template, removes stale crons (by name),
and creates fresh ones idempotently with the correct argument order (prompt must
come BEFORE --flags in `hermes cron create`). Called automatically by `setup.sh`.

**New project setup:** The skill-miner and session-cache crons run only on machines
with the loop-governance toolchain installed. Health monitoring (Ollama, DB, nomic
model, cycle count) runs inside `system-alert.py` every 10 minutes — no separate
health cron needed.

Verify: `hermes cron list | grep -E '(loop|weekly|session-cache)'`

### Content sanitization

Code snapshots are sanitized before storage via `LoopDB.sanitize_code()`:
- API keys, tokens, passwords get redacted
- Connection strings with credentials are masked
- PEM private key blocks are removed

## Evaluation Pipeline

A weekly analysis pipeline (`loop_evaluator.py`) reads the loop governance DB and produces a structured report every Monday at 9am via cron.

### What it analyzes

| Analysis | What it detects | Example output |
|----------|----------------|----------------|
| **Summary stats** | Total cycles, unique tasks, avg scores | `total_cycles: 47, avg_composite: 6.2` |
| **Decision distribution** | STOP/LOOP/MOVE ON/HARD FAIL counts | `STOP: 12, LOOP: 28, MOVE ON: 5` |
| **Score trends** | Drift in each dimension (first vs second half) | `completeness ↑ +1.2, quality ↓ -0.8` |
| **No-progress hotspots** | Tasks with most no-progress cycles | `feature-auth: 7 np cycles` |
| **Spinning tasks** | 3+ consecutive no-progress cycles | `task-b-spinner: 5 consecutive` |
| **Decision accuracy** | User feedback vs decision match rate | `66.7% correct (2/3)` |
| **Threshold recommendations** | Suggested threshold adjustments | `Raise STOP to 8.5` |
| **Weight recommendations** | Correlation-based weight adjustments | `completeness: 40% → 45%` |

### How to run manually

```bash
# Full report
python3 ~/.hermes/skills/devops/loop-governance/scripts/loop_evaluator.py

# JSON output (for programmatic consumption)
python3 loop_evaluator.py --json

# Config patch only
python3 loop_evaluator.py --config-patch

# Custom time window
python3 loop_evaluator.py --days 30
```

### Cron schedule

A weekly evaluation runs every **Monday at 9:00 AM KST** via the `agent-weekly-loop-eval` cron job. It delivers the report automatically to the chat that created it.

### Config patch

The evaluator can generate a recommended config patch — suggested changes to thresholds and weights based on historical data. Patches are reviewed by a human before application (included in the cron output).

```json
{
  "changes": {
    "weight_completeness": 0.45,
    "weight_quality": 0.25,
    "stop_threshold": 8.5
  },
  "rationale": "completeness correlates 0.8 with user acceptance; quality correlates 0.3",
  "confidence": 0.6,
  "requires_review": true
}
```

### Data flow

```
Every score call ──► loop_scorer.py ──► LoopDB (SQLite + JSON)
                                              │
                                  Weekly cron ─┤
                                              ▼
                                     loop_evaluator.py
                                              │
                                     ┌───────┴───────┐
                                     ▼               ▼
                              Human report    auto_apply.py
                              (Telegram)      (safe config updates)
```

## Error Handling & Resilience

The scoring pipeline **must not block development** when a dependency is down. Every component degrades gracefully:

| Failure point | Behaviour | Recovery |
|--------------|-----------|----------|
| **Ollama down** (embedding unavailable) | embed() returns None — each scorer falls back to heuristic/pass-rate values. full_score() adds warnings that Ollama is unavailable. Cycle still logs to DB with logged: True. | system-alert.py (every 10 min) detects unresponsive Ollama and attempts restart (retry loop, 5x2s). Auto-remediation cron also handles it. |
| **DB locked / write failure** | Cycle scores proceed normally; result is returned with `logged: false` and `log_error`. JSON event still written to `~/.hermes/data/loop-events/`. | Next cycle retries automatically. Remediation sensor checks DB writability. |
| **Config file corrupt** | `get_config()` falls back to hardcoded defaults. Warning logged but scoring continues. | Remediation sensor detects corrupt JSON and restores from `config_history`. |
| **nomic model not pulled** | Ollama returns 404 → fallback zero vector. User sees abnormally low scores. | `setup.sh` pre-pulls the model. Auto-remediation runs `ollama pull nomic-embed-text` on detection. |
| **score-cycle CLI fails** | Non-zero exit code + error message to stderr. No silent failures. | Logged to cron job error tracker. Auto-remediation applies known fixes. |
| **Feedback DB query fails** | `loop-feedback` returns error with cycle info. DB state unchanged. | Check DB permissions, disk space, schema version. |

### What gets NOTIFIED

The weekly cron report includes a **health section** showing:
- DB size and row count
- Last successful log timestamp
- Any cycles logged with fallback (zero-vector scores)
- Config file validity

Auto-remediation sends Telegram alerts for any pipeline component that fails 3+ consecutive checks.

### Known verify.sh bugs (fixed)

Two bugs were found and fixed in `verify.sh` (all 3 copies: installed, skill, repo source):

1. **`set -euo pipefail` breaks JSON mode**: `pass()` and `info()` functions return the exit code of `[[ "$JSON" != "1" ]]` (exit 1 when JSON=1). With `set -e`, this kills the script on the first suppressed output. Fixed by adding `return 0` to both functions.
2. **JSON output mixed with human text**: The header/summary text was printed to stdout, making JSON output unparseable by downstream scripts. Fixed by wrapping all non-JSON output in `[[ "$JSON" != "1" ]]` guards.
3. **JSON Python string interpolation broken for multi-word entries**: `'${RESULTS[@]}'.split(' ')` produced unterminated string literals when entries contained spaces. Fixed by writing results to a temp file and making Python read from the file.

Also fixed a quoting bug in `loop-health-check.sh`: the verify.sh flags were inside the double-quoted path string (`"${INSTALL_DIR}/verify.sh --quick --json"`), making bash treat them as part of the filename. Fixed by moving flags outside the quotes.

### What gets AUTO-FIXED

The `auto-remediation` cron (every 5 minutes) handles these loop-governance issues:
- Ollama down → restart via systemd/launchctl
- Config file missing → recreate from defaults
- DB file missing → recreate schema
- Symlinks broken → re-link to canonical script paths

### Resilience design principle

> **The scoring function is advisory, not critical.** A failed score call must never block a build, a deploy, or a user's workflow. The system scores when it can, logs what it can, and reports what it can't — but it never halts.

## File Organization

Every piece of the loop-governance system lives in a predictable location. This structure
lets any agent find the tools regardless of which Hermes profile or project it's working in.

```
~/hermes-cortex/                                ← Repo root
├── src/
│   ├── loop-governance/                        ← Scoring, DB, CLI tools (detailed below)
│   ├── mcp-servers/                            ← MCP servers (registered with Hermes)
│   │   ├── loop-gov-mcp.py                    Loop governance tools (7)
│   │   └── inbox-mcp.py                       Agent inbox tools (3)
│   ├── agent-inbox/                            ← Inbox web server (FastAPI)
│   ├── agent-registry.json                     ← Agent roles, hostnames, is_orchestrator flag
│   └── scripts/                                ← Utility scripts (system health, etc.)
├── AGENTS.md                                   ← Agent guidelines
└── README.md                                   ← Public docs

~/hermes-cortex/               ← DEPRECATED: core/governance/ removed July 2026
                              ← Current governance is MCP-based:
                              ←   ~/.hermes-cortex/scripts/loop-gov-mcp.py
                              ←   MCP tools: begin_change, cycle_query, feedback_accept/override, end_change
                              ←   Plugin: ~/.hermes/plugins/governance-enforcer/
                              ←   DB: ~/.hermes/data/loop-governance.db
                              ←   Skill: skills/devops/loop-governance/ (this file)
│   ├── agent-inbox-architecture.md           Cross-machine inbox design
│   ├── cron-management.md                    Cron template + argument order pitfall
│   ├── data-schema.md                        DB schema reference
│   ├── config-format.md                      Config schema + rollback
│   └── macos-compatibility.md                Platform-specific details
└── tests/                                    Test suite (see below)

~/.hermes-cortex/tools/loop-governance/       ← Installed copy (per-machine, created by setup.sh)
~/.local/bin/score-cycle                       ← Symlinks to installed copy
~/.local/bin/loop-feedback
~/.local/bin/auto-apply
~/.local/bin/loop-config
~/.local/bin/skill-miner
~/.local/bin/inbox-watch
~/.local/bin/session-cache
~/.local/bin/session-cache-build

~/.hermes/data/loop-governance.db             ← SQLite database (per-machine)
`~/.hermes/data/loop-governance-config.json`    ← Runtime config (per-machine)
`~/.hermes/data/loop-events/`                   ← JSON event backup (per-machine)

**MCP Servers** (registered with `hermes mcp add`):

| Server | File | Tools | Registration |
|--------|------|-------|-------------|
| `loop-governance` | `src/mcp-servers/loop-gov-mcp.py` | cycle_query, cycle_stats, config_show, config_set, feedback_accept, feedback_override, cache_search | `hermes mcp add loop-governance --command python3 --args src/mcp-servers/loop-gov-mcp.py` |
| `agent-inbox` | `src/mcp-servers/inbox-mcp.py` | inbox_send, inbox_read, inbox_watch | `hermes mcp add agent-inbox --command python3 --args src/mcp-servers/inbox-mcp.py` |

See `references/mcp-servers.md` for full tool descriptions and usage examples.
```

**Installation:** Loop governance is installed automatically by `cortex-update.sh` (MCP server + plugin). The old CLI tools (`score-cycle`, `loop-feedback`) are deprecated.

**Usage in a session:**
1. `mcp_loop_governance_begin_change(task_id="<name>", description="...")` — start a change
2. Do the work (MCP server blocks write tools without a lock)
3. `mcp_loop_governance_cycle_query(task_id="<name>")` — find the cycle
4. `mcp_loop_governance_feedback_accept(id=N, note="...")` — score it
5. `mcp_loop_governance_end_change(task_id="<name>")` — release the lock

Or via the main installer: `bash hermes-cortex/install.sh` (loop-governance step removed in July 2026 — use cortex-update.sh instead).

## Database Retention

Without a retention policy, the SQLite DB grows without bound. Implement a retention
schedule appropriate for your task volume:

```python
from loop_db import LoopDB

db = LoopDB()
# Archive cycles older than 90 days to JSON events, delete from SQLite
db.conn.execute("""
    DELETE FROM loop_cycles
    WHERE timestamp < datetime('now', '-90 days')
""")
# Clean up orphaned content assets
db.conn.execute("""
    DELETE FROM content_assets WHERE hash NOT IN (
        SELECT spec_hash FROM loop_cycles WHERE spec_hash IS NOT NULL
        UNION
        SELECT code_hash FROM loop_cycles WHERE code_hash IS NOT NULL
        UNION
        SELECT test_output_hash FROM loop_cycles WHERE test_output_hash IS NOT NULL
    )
""")
# VACUUM to reclaim space
db.conn.execute("VACUUM")
db.conn.commit()
print("Retention applied: deleted cycles older than 90 days")
db.close()
```

The weekly evaluation cron can be extended to include a retention step.
For high-volume environments, archive the JSON events directory (`~/.hermes/data/loop-events/`) to cold storage before deleting.

## Test Suite

Every loop-governance module must have corresponding tests in `scripts/tests/`:

| Test file | What it covers |
|-----------|---------------|
| `test_loop_scorer.py` | Each scoring function with known inputs/outputs, boundary conditions (empty string, very long code, negative values) |
| `test_loop_db.py` | CRUD operations, content deduplication, sanitization, JSON event writing |
| `test_loop_feedback.py` | accept/override/duplicate/force, JSON output, edge cases (invalid cycle_id, already has feedback) |
| `test_auto_apply.py` | Safety bounds (delta too large, confidence too low, force bypass), dry-run vs real apply, config_history logging |
| `test_integration.py` | Full pipeline: seed data → run evaluator → generate patch → auto-apply → verify config changed |

Run with:
```bash
cd src/loop-governance
python3 -m pytest tests/ -v
```

**Current status:** 68 tests across 7 test files — all pass. Run with:
```bash
cd src/loop-governance
python3 -m pytest tests/ -v
```

## Auto-Recovery Integration

The loop-governance toolchain integrates with the existing auto-remediation pipeline
to self-heal when components fail:

```bash
# verify.sh supports machine-readable JSON output for cron consumption
bash verify.sh --quick --json

# Output:
# {"passed": 12, "warnings": 0, "failed": 0, "checks": [...]}
```

The `remediation-sensor` cron (every 5 minutes) should call `verify.sh --quick --json`
and check for:
- Ollama not running → attempt restart
- nomic-embed-text missing → pull model
- Config file missing → recreate from defaults
- DB missing → recreate schema
- Symlinks broken → re-link

When auto-remediation fires, it should also send a Telegram notification so the
user knows the system self-healed.

## Architecture Review Action Items

The most recent architecture review (2026-06-24, hc-party) produced these priority
action items for hardening the loop-governance system:

| Priority | Item | Status |
|----------|------|--------|
| P1 | Create `tests/` directory with unit + integration tests (68 tests, all pass) | ✅ Complete |
| P2 | Graceful degradation: `embed()` returns None on failure, all scorers fall back to heuristics | ✅ Complete |
| P3 | Wire `verify.sh --quick --json` into 10-min `loop-governance-health` cron (auto-restarts Ollama) | ✅ Complete |
| P4 | DB retention: `vacuum_old_cycles(days=90)` added to loop_db.py, called weekly | ✅ Complete |
| P5 | Add "TDD scoring workflow" to AGENTS.md (non-negotiable rule #10) | ✅ Complete |

These items are tracked here for reference. Each should be implemented before the
next version bump.

## Adoption Enforcement

The change-test-loop skill's **Iron Law** includes: *"NO CYCLE WITHOUT SCORING AND LOGGING
TO THE GOVERNANCE DB."* Every agent working on code in a hermes-cortex-managed repo
must:

1. Run `score-cycle` after every completed LEARN→RED→GREEN→REFACTOR cycle
2. Provide feedback via `loop-feedback accept/override` when a decision is controversial
3. Run `verify.sh` if any component (Ollama, scoring, DB) reports errors

The agent contract section of AGENTS.md enforces this as a non-negotiable rule:
*"A cycle that isn't logged is invisible to the self-improvement system. It didn't happen."*

## Script Naming Conventions

All loop-governance scripts follow a strict naming convention for consistency and importability:

| Convention | Where | Example |
|-----------|-------|---------|
| **Underscores** for Python modules | `scripts/` | `loop_scorer.py`, `score_cycle.py`, `loop_db.py` |
| **Hyphens** for CLI commands | `~/.local/bin/` symlinks | `score-cycle`, `loop-feedback`, `auto-apply`, `loop-config` |

**Why not one convention?** Python modules must use underscores (`import loop_scorer` fails with a hyphen). CLI commands conventionally use hyphens (`docker-compose`, `git push`, not `git_push`). The symlinks bridge the two worlds.

When adding a new script:
1. Name the `.py` file with underscores in `scripts/`
2. Create a hyphenated symlink in `~/.local/bin/`
3. Document both names in this skill

See `references/macos-compatibility.md` for full platform-specific details (grep patterns, timeout, launchd vs systemd, install flow).

### Progress on test output is noisy

Test runner output (pytest, etc.) contains heavy boilerplate — PASSED/FAILED markers, timing info, file paths — that stays nearly identical across iterations even when the code changes substantially. **Always compare implementation code for progress detection**, not test output.

```python
# Good
score_progress(previous_code, current_code)

# Bad — too much boilerplate, artificially low scores
score_progress(previous_test_output, current_test_output)
```

### Short code samples produce weak embeddings

nomic-embed-text has 2048 token context and works best on content above 100 chars. Code snippets under 50 chars produce noisy, unreliable vectors. When scoring very short snippets, pad with surrounding context or score at the file level instead.

### Pass rate beats embedding for completeness

Embedding similarity between test output and spec text is a weak signal — test output and spec are structurally different even when the implementation is perfect. The **pass rate heuristic** (60% weight) is far more reliable. Always pass `pass_pct` when available.

### User feedback is the only ground truth

The scoring function can self-validate (tests pass → good), but the only real measure of decision quality is whether the **user accepts or overrides** the STOP/LOOP/MOVE ON decision. Write `record_user_outcome()` calls after every user-facing decision to build the training dataset for meta-learning.

### Don't fine-tune nomic

The 137M parameter embedding model is adequate for semantic similarity at ~50ms per call. Fine-tuning it requires collecting a large, diverse, clean labeled dataset and risks embedding space drift that silently corrupts all future scores. Prefer **heuristic augmentation** (pass rate, diff size, lint count) over model fine-tuning.

## Agent Roles & Orchestrator-Only Crons

The fleet has one orchestrator (Moses) and several agent machines (Titus, Gisu, Joseph,
Kustos). Only the orchestrator runs cross-agent tasks. Regular agents run local-only tasks
(skill-miner, session-cache build, weekly-loop-evaluation).

**Agent registry:** `~/hermes-cortex/ops/services/agent-registry.json` defines each agent's role,
hostname, whether it's server-reachable (`accessible`), and whether it's the orchestrator
(`is_orchestrator`). The `install-crons.py` script reads this registry and compares the
local hostname against the orchestrator's hostname to decide which crons to install.

**Orchestrator-only flag:** Crons with `orchestrator_only: true` are skipped on non-orchestrator
machines. This prevents regular agents from running cross-agent health checks or other
orchestrator-specific tasks. Currently no crons are marked orchestrator-only — the flag is
ready for future use (e.g., cross-agent health monitoring).

**Health monitor:** `agent-team-health-monitor.py` polls server agents (those with `health_url`
in the registry) and skips client-only agents (Titus, `accessible: false`). It only runs on
the orchestrator machine — enforced by the cron installer.

See `references/cron-management.md` for the full orchestrator detection logic.

## Integration with Other Skills

### With change-test-loop

After each LEARN→RED→GREEN→REFACTOR cycle, use `score-cycle` to score progress and log to the database in one command:

```bash
score-cycle --task my-feature --cycle 3 \
  --spec-file spec.md \
  --code-file src/impl.py \
  --prev-code-file src/impl.prev.py \
  --test-file test_output.txt \
  --pass-pct 1.0
```

Output includes the composite score, decision, and cycle_id — plus a reminder to provide feedback:

```
  Cycle #42  |  my-feature  |  cycle 3
  ─────────────────────────────────────
  Completeness:   9.5/10
  Quality:        6.8/10
  Progress:       0.5/10
  ─────────────────────
  Composite:      6.0/10
  Decision:     LOOP 🔄 — keep iterating
  
  💡 Feedback: loop-feedback accept 42 --note "..."
     Or:       loop-feedback override 42 --note "..."
```

**Important:** Always pass `--prev-code-file` (or `--prev-code`) with the **code from the previous cycle**, not test output. Test runner output has heavy boilerplate that makes progress detection meaningless.

**Decision scoring** is built in: `score-cycle` calls `full_score()` which runs all three scorers, applies the decision matrix, and logs to SQLite. Use the output to steer the loop:

| Decision | Action |
|----------|--------|
| **STOP ✓** (composite ≥ 8) | Goal met. Exit the loop. |
| **LOOP 🔄** (composite 5-7.9) | Enter next LEARN→RED→GREEN→REFACTOR cycle. |
| **MOVE ON →** (composite 3-4.9) | Escalate to human. |
| **STOP ✗** (composite < 3) | Hard fail. Escalate to human. |

For programmatic use in scripts, use `--json`:

```bash
RESULT=$(score-cycle --task my-feature --cycle 3 --code-file impl.py --json)
CYCLE_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['cycle_id'])")
```

Insert between REFACTOR and the next LEARN phase:

```
LEARN → RED → GREEN → REFACTOR → [LOOP GOVERNANCE] → LEARN (or STOP)
```

### With subagent-driven-development

After a review→fix→review cycle (spec review fails, implementer fixes, spec review runs again), use loop-governance to detect if this is making progress or spinning:

- **Same finding 3x** → STOP ✗ (no progress, escalate to human)
- **Progress score ≥ 5** → LOOP 🔄 (keep iterating)
- **Progress score ≥ 8** → STOP ✓ (review passed, move to next task)

### With skill-miner (companion tool)

`skill-miner` is a companion tool that shares the loop-governance data stack.
It runs on every agent's machine (cron: Monday 6am) and mines local data for
reusable patterns. It is NOT part of the scoring pipeline — it's a separate
automation that feeds findings to the agent inbox for Moses to review and
incorporate into hermes-cortex.

**Data sources it shares with loop-governance:**
- Loop governance DB — high-scoring TDD cycles (composite ≥ 7, improving)
- Session history — success patterns from conversations (PII-scrubbed)
- Local memory — agent MEMORY.md, USER.md
- Custom skills — skills installed locally but not in the repo (full content sent)

**Flow:**
```
Agent's machine: skill-miner (Mon 6am) → POST to /api/send (to=moses, cc=luke)
Moses server:    inbox-watch (every 10 min) → reviews → pushes to repo
All agents:      git pull
```

The inbox now supports `to`/`cc` addressing. skill-miner sets `to=moses` so
findings appear in Moses's per-agent filtered view (`/api/inbox?for=moses`).
Every message auto-CCs `luke` (the human) so Luke sees everything.

**Inbox-watcher companion tool:** `inbox-watch` (symlink at `~/.local/bin/`) reads
the agent inbox and surfaces new messages from the fleet. See
`references/agent-inbox-architecture.md` for the full cross-machine design.

**Note:** skill-miner overlaps with `lesson-aware-agent` (both extract learnings).
skill-miner is automatic and runs on schedule; lesson-aware-agent is triggered
per-session. They are complementary, not alternatives.

**Manual trigger:** `skill-miner`

### With lesson-aware-agent

The loop-governance decision matrix pairs naturally with lesson search:
- Before starting a loop, search lessons for known approaches
- If a loop keeps failing with no progress, search lessons for the error pattern
- Save unsuccessful loop attempts as lessons ("tried X approach, no progress after 5 iterations")

See `references/agent-inbox-architecture.md` for the full cross-machine
communication design (three-repo separation, message flow, pitfalls).

## Efficiency Principles

1. **Score cheaply** — nomic embeddings at ~50ms cost less than 1% of an LLM call. Score on every iteration.
2. **Fail fast** — no-progress detection after 3 iterations saves potentially infinite wasted rounds.
3. **Bound early** — set max_iterations before starting. A rule of thumb: if you can't achieve the goal in 5 iterations, you won't achieve it in 50.
4. **Fresh context** — each iteration starts clean. Don't accumulate stale reasoning.
5. **Measure, don't guess** — the scoring function replaces "feels right" with quantitative evidence. Trust the score, not the instinct.
