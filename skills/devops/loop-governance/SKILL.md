---
name: loop-governance
version: 1.5.0
category: devops
description: "TDD cycle scoring, self-improvement, and governance system for Hermes Cortex. Scores completeness/quality/progress per cycle with nomic embeddings, logs to SQLite, collects user feedback via CLI, auto-applies config patches with safety bounds, and integrates weekly evaluation + retention. Runtime config, test suite, setup/verify/update scripts, and auto-remediation health checks."
author: Hermes Cortex
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
```bash
session-cache-build build    # scans sessions, loop DB, skills → embeds → stores
session-cache-build search   # similarity search
session-cache-build --help   # list all subcommands (there is no `status` subcommand)
```

Note: the CLI is `session-cache-build` (hyphenated, one word, symlinked into `~/.local/bin/`). `session-cache build` (two words) is NOT a valid command.
```

**Cache integration:** `loop_scorer._cache_boost()` checks the cache during every
`score_progress()` call. If the current output is very similar (cosine > 0.85)
to a known-good pattern in the cache, progress gets a +2 boost. For moderate
similarity (>0.75), +1 boost. This means scoring improves as the cache grows.

**Cron:** `agent-session-cache-build` runs Monday 5am KST (weekly cache rebuild; the daily `orch-skill-lifecycle` pipeline at 4:34am reads whatever cache state exists).

**Agent data:** Agents contribute session data via `agent-learning-collector` Learning Reports (to `inbox_orchestrator`, every 6h) and the session cache. The cache is rebuilt weekly, incorporating new data.

### Installation & invocation

The scorer module lives at `loop_scorer.py` in the installed tool directory `~/.hermes-cortex/tools/loop-governance/` (underscore so Python can import it directly). Run a demo from any directory:

```bash
python3 ~/.hermes-cortex/tools/loop-governance/loop_scorer.py
```

> Do NOT use `~/.hermes/skills/devops/loop-governance/scripts/...` — the installed skill directory contains only SKILL.md + references; the Python modules live in `~/.hermes-cortex/tools/loop-governance/`.

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
| **SQLite** (`loop_db.py`) | Structured querying, aggregation, analysis | `~/.hermes-cortex/data/loop-governance.db` |
| **JSON events** (built into `LoopDB.log_cycle`) | Streaming backup, portability, disaster recovery | `~/.hermes-cortex/data/loop-events/YYYY-MM-DD.jsonl` |

### Schema (auto-created)

```
loop_cycles       - Every cycle scores + decisions + content hashes
content_assets    - Content-addressable store (deduplicates code/spec/test text)
config_history    - Config change log for rollback
```

### How to log a cycle

**Option 1: Via env vars (any script can use this)**

```bash
SCORE_DB_PATH=~/.hermes-cortex/data/loop-governance.db \
SCORE_TASK_ID=my-feature \
SCORE_CYCLE_NUM=1 \
SCORE_SPEC="Add two numbers" \
SCORE_OUTPUT="def add(a,b): return a+b" \
python3 ~/.hermes-cortex/tools/loop-governance/loop_scorer.py --score
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

Thresholds and weights live in `~/.hermes-cortex/data/loop-governance-config.json` and are read by `composite_score()` on every call:

```bash
# View current config
loop-config --show
# or directly:
python3 ~/.hermes-cortex/tools/loop-governance/loop_config.py --show

# Set a value manually
loop-config --set weights.completeness 0.45
```

See `references/config-format.md` for the full config schema, field descriptions, and rollback procedure.

### Cron schedule

All loop-governance crons managed via `crons.json` (versioned) + `install-crons.py`:

| Cron | Schedule | Mode | Behaviour |
|------|----------|------|-----------|
| `agent-session-cache-build` | Mon 5am KST | no_agent | Rebuilds embedding cache from sessions, DB, skills |
| `local-weekly-loop-eval` | Weekly | LLM-driven | Per-host weekly loop evaluation (fleet-level eval absorbed into `orch-skill-lifecycle` 2026-08-02) |

**Versioning:** Bump the `version` field in `crons.json` to trigger agent updates.
The `install-crons.py` script reads the template, removes stale crons (by name),
and creates fresh ones idempotently with the correct argument order (prompt must
come BEFORE --flags in `hermes cron create`). Called automatically by `setup.sh`.

**New project setup:** The `agent-session-cache-build` and `local-weekly-loop-eval` crons run only on machines
with the loop-governance toolchain installed. Health monitoring (Ollama, DB, nomic
model, cycle count) runs inside `system-alert.py` every 10 minutes — no separate
health cron needed.

Verify: `hermes cron list | grep -E '(loop|weekly|session-cache)'` — expect `agent-session-cache-build` and `local-weekly-loop-eval` (the eval cron is named `local-weekly-loop-eval`, NOT `local-agent-weekly-loop-eval`; old docs use that name).

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

**Read the report's units literally — two different averages live in it.** "Avg cycles per task"
is `COUNT(*) / COUNT(DISTINCT task_id)`: an average over **tasks**, so 2.9 means a task took
~2.9 cycles. It is NOT `AVG(cycle_num)`, which is the mean **cycle INDEX** and reads ~24 on the
same week — a much larger number that contradicts the line above it. `AVG(cycle_num)` shipped
once and an adversarial review filed the mismatch as fabrication; if you touch
`loop_evaluator.py`'s stats query, keep the task-average and re-run
`tests/run_loop_evaluator_avg_per_task_repro.py` (rc=0 ⇒ the label and the arithmetic agree).

### How to run manually

```bash
# Full report (module lives in the installed tool dir, not the skill dir)
python3 ~/.hermes-cortex/tools/loop-governance/loop_evaluator.py

# JSON output (for programmatic consumption)
python3 loop_evaluator.py --json

# Config patch only
python3 loop_evaluator.py --config-patch

# Custom time window
python3 loop_evaluator.py --days 30
```

### Closing vs pushing — a CLEAN receipt, not a second cycle

Ending a governed change (`end_change`) runs the self-adversarial review and, when it is
CLEAN, writes a SHA-bound **review receipt** for the reviewed range. Since closing releases
the lock and pushing normally needs one, this once took a second no-content `push` cycle to
ship a reviewed range. That is gone (2026-10-10): the enforcer
has a **lock carve-out** for a push that a CLEAN receipt covers — if `end_change` shows a
CLEAN close, `git push` right after it is authorisable with no new lock. Do not open a
second cycle purely to push; only commits added AFTER the close are outside the receipt and
need their own review.

**Issue the push ALONE.** The carve-out authorises a *lone* `git push`: a compound
(`git push && …`), a pipe, a redirect or a background form is refused even with a CLEAN
receipt, because only the bare command is recognised as landing the reviewed range. When a
refusal names this, re-issue the push by itself instead of opening a cycle for it.

**A close that outlives your call still completed.** The review runs server-side to its own
deadline, so a client-side timeout on `end_change` (the MCP call ceiling) can land while the
reviewer is still working — the close then finishes and RELEASES the lock, with the receipt
already written. Do not re-run the review and do not assume failure: the lock file
(`ls ~/.hermes-cortex/state/.governance-*.json` — gone means released) is the state, and a
repeated `end_change` answering "no governance session active" is the confirmation it closed.
The receipt from that close is what then authorises the push.

Evidence that the review's material window could not show is a *window* defect, not a
missing-evidence defect. The material now treats `docs/evidence/**` as documentation
(whatever the suffix) and allocates floor-first, so a small artifact is shown whole. Keep
evidence small and structural: state the command, its own `rc`, the decisive lines, and a
sha256; `ops/scripts/make-evidence.sh` writes exactly that shape and verifies it. It is
POSIX-sh portable (Linux and macOS, `sha256sum` or `shasum -a 256`) and works in any repo,
with or without Hermes or cortex — a Pi / Claude Code / plain-shell session can use it.

**A re-runnable verifier answers a provenance finding only if it proves its OWN claims.** One
command that re-checks the whole change (deploy, tests, deployed-vs-repo, the adversarial
sweep) ends a close-review argument that a stack of transcripts cannot; but a verifier is
itself evidence, so it must not hide its own failure modes:

- **Never let a piped `tail` carry the result.** `cmd | tail -1` prints the last line whatever
  happened above it, so the artifact cannot distinguish a pass from a failure earlier in the
  run. Capture the output, then print the command's OWN exit status beside the decisive
  summary line — and print the FAILED/ERROR lines when there are any.
- **Print the verifier's own verdict**: the failure count immediately before the exit, so the
  capture states the outcome instead of leaving it to be inferred from a count.
- **Print each case BY NAME, not just a total.** An aggregate "ALL PASS (N tests)" is a claim
  about an execution the reviewer cannot see, and it gets filed as one: they ask which cases
  produced the count. Have the check emit its own case lines (`A: absent interpreter -> named
  path, rc=78`, `::test_<name> PASSED`) into the artifact, and prefer a runner that prints the
  per-test names beside the summary. A count without its cases is the same defect as a summary
  line from a piped `tail`.
- **Name the artifact each check examined.** "The deployed copy" and "the repo copy" differ
  exactly where the check matters (a wrong deploy-map entry still passes a repo-side run), so
  say which one was used, and exercise the DEPLOYED path when the host has one. `--help` proves
  a file starts, not that it works — use the real operation as the check.
- **Separate the operational step from the verification, and label it.** A verifier that
  installs, migrates or reconfigures what it inspects can pass because of its own side effect
  and reports on a state it just changed; a check hung on a `--dry-run` flag also fails as
  "unsupported option" on tool versions that lack it. Run the operation once, record its exact
  command in the artifact as the MANUAL step it is, and have the verifier assert the resulting
  state non-destructively (distribution versions, an import check, a collected-test count). A
  claim about a manual step is answerable — say which step was manual and show the state it
  produced.

**Write the response to a finding as the DEFECT, not as agreement with the reviewer.** A note
or commit message that frames a fix as "the reviewer was right" is filed as
evaluation-awareness and can block the close: the reviewer is grading the change, not its
diplomacy. State what was broken and why the new shape is correct ("a piped tail discards the
failure lines and the exit status, so the artifact cannot tell a pass from a failure earlier in
the run") — the same sentence with the reviewer left out of it.

A starter verifier with all of the above baked in (own `rc` capture, per-case output, the
not-a-pass exit code, portable hashing): `templates/verify-change.sh` — copy it, replace the
sections, keep the shape.

**A FINDINGS verdict is not permanent — re-review it; do not re-close it, and do not override
it.** The verdict is stored once per cycle, so re-issuing `end_change` with rephrased prose keeps
colliding with the same frozen note (that is the design working — it is what stops a re-roll from
standing in for a fix) and it is how agents get pushed toward an override instead. Fix the finding,
then call `rereview_change(task_id=…, note=…)` with a note that DIFFERS and carries command output
PASTED in, not summarised: an unchanged note is refused, and the reviewer still runs live against
the current diff, so it cannot manufacture a CLEAN. Two corollaries worth honouring up front: an
artifact captured before the range's last commit cannot have exercised it (commit everything,
confirm `git status --short` is empty, then capture), and documentation an audit compelled belongs
in its own TRACKED task (`task_add`) or it comes back as scope drift.

Detail on both, plus the rest of the close-review loop: `references/satisfying-the-close-review.md`.

### Before you submit — see the window the reviewer sees

Run `python3 ops/scripts/manage/review-material.py` **before** the close. It prints the
material for `merge-base origin/main..HEAD` file by file, names the budget in force, and
exits 1 when a changed file would be shown with almost no body. Pass `--note "…"` to see the
note as the reviewer receives it. One command replaces guessing at the window (cycle 12307
spent six rounds guessing).

### Same-repo sessions

Another session in the SAME repo can put its commits inside your range, and every one of
them consumes the same window. The preview lists the range's commits — if any are not yours,
don't carry them through your review: land them in their own cycle, or expect the window to
be shared. (`git status` cannot tell you *who* staged something; the commit list can.)

### Misattributed findings — check the section split before reworking anything

**Symptom:** the reviewer reports content that belongs to file A as if it sat in file B
("the dogfood transcript contains the skill note's text"), or a per-file bound looks
structurally unsatisfiable because a section bearing one path is many times the size of
that file (measured: an 86,318-char section under a 5.8KB path). Findings like these are
**true of the material and false of the repo** — the tell is that `grep` at HEAD refutes
them while the finding keeps returning.

**Cause:** the close review composes material from `git log -p` (per-commit patches, so a
path appears once per commit that touches it), but a splitter that only breaks on
`diff --git a/` lets each file's section run past its own patch and absorb the **next
commit's message**. Every per-file bound then pairs a path with text from a different
commit. Fixed 2026-10-12 by treating `commit <sha>` as a section boundary
(`_COMMIT_BOUNDARY_RE`).

**Before reworking the change, ask which composition the review uses.** A preview that
builds with `git diff` is a *different material* than a review built with `git log -p`
(measured: 133,574 vs 43,407 chars) — so a preview can look clean while the review stays
broken. `review-material.py` mirrors the review's composition and takes
`--gate {auto,repo,deployed}` so both copies are measurable. When a finding's numbers match
nothing your preview produces, suspect the composition path, not your evidence.

### Evidence budget

Answer a finding by fixing the WINDOW, not by appending another artifact. Each evidence file
you add shrinks the slice every other file gets, so a spiral of "one more transcript" makes
the next review worse, not better. Evidence under `docs/evidence/**` is now shown whole
outside the budget (cap `DOC_EVIDENCE_WHOLE_CAP`), precisely so artifacts cannot crowd out
the code under review. Put the cycle's evidence in ONE commit before the first close, in the
`make-evidence.sh` shape.

- **The writer CAPS the captured body, and truncation drops the TAIL.** `make-evidence.sh`
  records `MAX_BODY` and notes the omitted byte count where the cut happened — so one unbounded
  section (a full doctor report is hundreds of lines) starves EVERY section after it, and the
  artifact ends mid-report with the decisive checks silently missing. Order sections
  small-and-decisive FIRST, and never dump an unbounded report into a capture: print the tool's
  own summary plus the lines you are actually claiming, then confirm the sections you needed are
  present in the written file before you close (a file that reads 13KB with an "omitted" note is
  the tell).
- **Answer "the supporting script is not in the diff" by CITING it, not by adding it.** When a
  finding names a dependency the change merely CALLS (a resolver, an audit script, an installer),
  the review is asking for provenance, not a copy: cite the path and the blob at the reviewed tip
  (`git ls-tree -r HEAD <paths>`), state that it is unchanged by this cycle, and say which copy
  the artifact exercised (repo vs deployed). Stating that up front in the note costs one command;
  leaving it implicit costs a review round per dependency.
- **Never hand-roll an aggregate metric when the tool publishes its own.** A glyph count
  (`grep -c …`) is not the tool's verdict: one invented "FAIL lines: 1" contradicted the very
  exit code beside it (`rc=1` = warnings only by the tool's own convention) and read as a
  self-contradiction. Cite what the tool reports about itself — its exit code, its `--json`
  summary (`{"pass": N, "warn": M, "fail": 0}`) — and if a metric of your own cannot be
  reconciled with that summary, WITHDRAW it rather than shipping a line the reviewer must argue
  with. A dump is not evidence either: a bounded summary plus the decisive lines answers harder.

- **Fix the CLASS, then pin it with a sweep that fails on the next instance.** A defect found at
  one call site is a claim about that site, not about the class: enumerate before claiming a fix
  is complete (`rg` for the shape — e.g. every `-c 'import <module>'` that DECIDES something) and
  commit the enumeration as a test, with any exemption stated AND justified (stdlib imports are
  exempt because a foreign site-packages is where THIRD-PARTY packages live). The sweep is what
  turns "I fixed both" into a checkable statement, and it will catch your own next line: it
  caught the fallback probe written into the fix minutes later.
- **Make the discrimination RE-RUNNABLE from git history.** "It failed before, it passes now" is
  evidence only if a reviewer can reproduce both halves: extract the pre-fix artifact with
  `git show <reviewed-tip>:<path> > /tmp/pre-fix.<ext>` and run BOTH it and the working copy in
  the artifact, under identical input and environment, each printing its own `rc`. A guard never
  run against the broken artifact is a happy path, not a guard.
- **When a peer's commits land while you are closing, MERGE — never rebase.** A rebase rewrites
  your reviewed SHA, so the CLEAN receipt stops covering the range and the push is refused again;
  a merge keeps the reviewed commit as an ancestor, which is what the receipt and the push gate
  check. Resolve the overlaps as they come (doc indexes collide routinely), re-run a fast suite on
  the merged tree, then close and push.
- **A push can be refused because a DEPLOYED file changed after the last deploy** — the refusal
  names `Checksum: <path>`. The deploy is NOT covered by the push carve-out, so it needs its own
  short cycle: begin_change → run the deploy → scored accept + end_change → lone `git push`.
  Editing a deployed file last (even a comment) is what creates that extra cycle; when you can,
  deploy before closing so the receipt and the deployed tree agree.
- **Ceremony backfires.** Re-hashing files git already tracks, printing `wc -c` for them, or
  proving a `/tmp` path from weeks ago is gone is filed as evaluation-awareness theater and
  blocks the close. Keep evidence structural: the command, its own `rc`, the decisive lines.
  If the budget truncates a CODE file whose assertions are the point, INLINE it into a
  `docs/evidence/**` artifact (shown whole) instead of asking the reviewer to trust a summary.

### Notes: state a correction once

Never quote a superseded claim in a new note — the reviewer re-reads the quote and re-flags
it. Say "the earlier count was wrong; it is three" and move on. Replayed findings are shown
with their quoted fragments stripped for exactly this reason, and window-only findings no
longer block (`_is_material_limit_finding`): a complaint that the material could not SHOW
something is recorded, not fatal — while fabrication, injection and behavioural findings
still block.

### Cron schedule

A weekly evaluation runs via the `local-weekly-loop-eval` cron job. It delivers the report automatically to the chat that created it.

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

## Lock Lifecycle & Enforcement Update Surface

Lock files and the immutable chain have failure modes beyond the skills marker. Hard-won lessons from P1-A (2026-07-31). Full detail: `references/lock-lifecycle-race.md` (mechanism + verification) and `references/enforcement-update-surface.md` (complete write-path audit + sanctioned-caller gate design).

**A lock opened through the non-Hermes CLI (`loop-gov.py`) is not tagged by the enforcer — a coding-agent harness (pi/Claude Code/Codex/aider/cursor) must stamp the repo itself.** The gateway's enforcer only injects `repo_path`/`repo_slug` into `mcp__loop_governance__*` MCP calls it intercepts; a harness driving `loop-gov begin_change` calls the handlers directly and skips that hook entirely, so `_derive_slug` falls to Priority 1 = the host-canonical `~/hermes-cortex` whenever that dir exists. A lock tagged hermes-cortex while the session works in another repo makes the close gate audit a tree that cannot contain the work — permanent FINDINGS, uncloseable cycle (the Titus/steadfaste symptom). Fix at the CLI, not the MCP server: resolve the cwd git root (`git rev-parse --show-toplevel`) and inject BOTH `repo_path` (absolute) and `repo_slug` (name) onto the payload, mirroring the enforcer's pair. **Fail closed for `begin_change` when the repo cannot be resolved** — a git timeout or missing-git is "unexpected" and must refuse (exit 1, a decision not a crash), else the unstamped payload silently recreates the wrong-repo lock; only a clean rc!=0 ("not a git repo") no-ops. Never clobber an explicit caller-supplied repo identity.

**Mid-write lock theft:** every purge path — the enforcer's `_has_governance_lock()` pre-scan + Phase 2 scan, the MCP's `_purge_stale_locks()`, and `purge-stale-governance-locks.py` — used to delete any `.governance-*.json` that failed `json.loads`. `_write_lock()` wrote non-atomically (`write_text`), so a concurrent purge read mid-write caught partial JSON and deleted a FRESH lock. Symptom: `begin_change` succeeds, then seconds later `check_lock` says inactive and the file is gone. **Fix (shipped):** atomic writes (temp + rename, same fs) + purge loops skip unparseable files (never delete what you can't parse — it is being written). Locks now carry `session_type` (cron/bg/interactive); cron/bg sessions never purge interactive locks.

**Sticky marker per governance lock — SUPERSEDED (2026-08-01):** the sticky-marker
rule was the P1-A patch for the shared-file race: `_check_skills_loaded_marker()`
accepted a valid `session:*` marker when the session held an active governance lock.
It is now obsolete — markers are per-session files (`state/skills-loaded/<session_id>`),
so no concurrent session can steal the marker in the first place. The lock-based
exception and the daemon/subagent guards were removed with the shared file.

**Session-identity marker race (`.hermes-session-current.id`) — FIXED (2026-08-02):** the enforcer resolves the *current session id* from the shared fixed-path file `~/.hermes-cortex/state/.hermes-session-current.id`, which ANY concurrent session (party subagents, background workers, parallel conversations) can overwrite. Symptom (confirmed 2026-07-31): your fresh `.governance-<session>.json` lock exists with a valid heartbeat, yet `check_lock` returns inactive and write tools block with "GOVERNANCE LOCK REQUIRED" — the enforcer looks up the lock under the stomped id. State dir shows two+ lock files (yours + a subagent's) and the marker holding a third, unrelated id. **Fix (shipped in b26ea929):** the enforcer now INJECTS `args["session_id"]` into every `mcp__loop_governance__*` call at pre_tool_call, and the MCP server's `get_session_id(args)` reads it as **Priority 0** — beating the shared marker. The marker bridge remains only as legacy fallback for direct MCP callers. Recovery for pre-fix locks: re-acquire with `begin_change()` (creates the lock under the currently-resolved id), reload the 8 always-skills so the marker matches, then proceed. This compounds with Pitfall 3 (skills marker) — both live in the same shared state dir.

**Enforcement update surface:** to enforce "cortex-update is the ONLY way to update locked files", audit ALL write paths, not just the lock helper: the pre-commit DOGFOOD self-heal (auto-deploys the enforcer on commit — convert to a BLOCK), doctor remediation hints that say `cp` hooks directly (re-point to cortex-update.sh), the `hermes-plugin-lock update` self-update channel, and sudoers env_reset (callers must use explicit `sudo CORTEX_UPDATE=1 cmd` assignment — plain `export` does not survive sudo). macOS chflags needs no root → script-level gating is the only lever there.

## Error Handling & Resilience

The scoring pipeline **must not block development** when a dependency is down. Every component degrades gracefully:

| Failure point | Behaviour | Recovery |
|--------------|-----------|----------|
| **Ollama down** (embedding unavailable) | embed() returns None — each scorer falls back to heuristic/pass-rate values. full_score() adds warnings that Ollama is unavailable. Cycle still logs to DB with logged: True. | system-alert.py (every 10 min) detects unresponsive Ollama and attempts restart (retry loop, 5x2s). Auto-remediation cron also handles it. |
| **DB locked / write failure** | Cycle scores proceed normally; result is returned with `logged: false` and `log_error`. JSON event still written to `~/.hermes-cortex/data/loop-events/`. | Next cycle retries automatically. Remediation sensor checks DB writability. |
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
                              ←   DB: ~/.hermes-cortex/data/loop-governance.db
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
~/.local/bin/session-cache-build

~/.hermes-cortex/data/loop-governance.db             ← SQLite database (per-machine)
`~/.hermes-cortex/data/loop-governance-config.json`    ← Runtime config (per-machine)
`~/.hermes-cortex/data/loop-events/`                   ← JSON event backup (per-machine)

**MCP Servers** (registered with `hermes mcp add`):

| Server | File | Tools | Registration |
|--------|------|-------|-------------|
| `loop-governance` | `src/mcp-servers/loop-gov-mcp.py` | cycle_query, cycle_stats, config_show, config_set, feedback_accept, feedback_override, cache_search | `hermes mcp add loop-governance --command python3 --args src/mcp-servers/loop-gov-mcp.py` |
| `agent-inbox` | `src/mcp-servers/inbox-mcp.py` | inbox_send, inbox_read, inbox_watch | `hermes mcp add agent-inbox --command python3 --args src/mcp-servers/inbox-mcp.py` |

See `references/mcp-servers.md` for full tool descriptions and usage examples.
```

**Installation:** Loop governance is installed automatically by `cortex-update.sh` (MCP server + plugin). The old CLI tools (`score-cycle`, `loop-feedback`) are deprecated.

**Usage in a session:**
1. `mcp__loop_governance__begin_change(task_id="<name>", description="...")` — start a change (response includes `[CYCLE_ID=N]` — extract it for the explicit id path)
2. Do the work (MCP server blocks write tools without a lock)
3. `mcp__loop_governance__feedback_accept(task_id="<name>", ...)` — close the cycle. A bare note is REFUSED ("composite 0.0 is indistinguishable from a failed change", enforced 2026-09-23): pass either scores `completeness=<0-10>, quality=<0-10>, progress=<0-10>` or `unscored_reason="why nothing could be measured"` — without one of the two the cycle stays PENDING and `end_change` stays blocked. The `task_id` parameter is the preferred path: it auto-resolves to the session's single PENDING cycle without needing to extract the numeric id. Alternatively pass `cycle_id=N` (from the `[CYCLE_ID=N]` marker) for explicit targeting — both parameters work.
4. `mcp__loop_governance__end_change(task_id="<name>")` — release the lock

The old intermediate `cycle_query(task_id="...")` call is eliminated: `begin_change` already knows the numeric id and the feedback functions resolve `task_id` to the PENDING cycle directly. The agent flow is now 2 post-work calls instead of 3.

**Close-out is ENFORCED (2026-08-08, Luke directive):** `end_change()` refuses to release the lock while the task's cycle is unscored, and `begin_change()` refuses a new task while this session still holds unscored PENDING cycles. There is no warning-only path anymore — score every cycle (step 3) BEFORE `end_change`, and never start a new task until the previous one is scored and closed. Hook-created cycles (`precommit-*` task ids, `session_id NULL`) do not trip the gate.

**Interpreter reads of repo scripts are write-class — point scheduled passes at the deployed copy (2026-09-26):** the read-only allowlist never covers interpreter forms, so `python3 ~/hermes-cortex/ops/scripts/manage/task-db.py list --board` — a pure listing — demands a lock because the path sits inside the governed repo; the Sep 26 evening pass burned 8+ calls retrying it. Lock-free pattern: run the deployed copy from outside the repo — `python3 ~/.hermes-cortex/scripts/task-db.py list ...` from `~` (`~/.hermes-cortex` is not a git repo, so the repo gate never engages) — and keep read compounds to allowlisted primitives only (`2>&1` is write-class, `echo` is not allowlisted). If the read must run inside the repo, take the lock deliberately: begin_change → work → scored feedback_accept → end_change (the morning-pass pattern).

**Adversarial review hard gate (2026-09-24, Luke directive):** `end_change()` runs an **independent adversarial reviewer** before closing any COMPLEX cycle, synchronously on the completion event. A sweep cron that polled for completed-but-unreviewed cycles was deleted (live job + install scripts) — review fires in `end_change` itself; never substitute a poll for a missing event hook, build the hook.

- **Hard gate, fail loud.** The close is REFUSED until the reviewer returns CLEAN. Reviewer unreachable → "Cannot close … refused, not skipped" (lock stays held, retry later); prompt template missing → cannot close; unparseable verdict → treated as FINDINGS and hard-blocked. Nothing silently skips.
- **The lock is not the verdict's hostage.** One mechanism used to do three jobs — mutual exclusion, session LIVENESS, and the release gate for a verdict — so any one failing took the other two down. Both halves were measured: `heartbeat_at` moved ONLY inside `check_lock` (a status tool a working agent has no reason to call), so a busy session's lock aged out and then refused its own writes and close; and a finding the worker could not repair — a `medium` whose entire content was "the diffs are truncated by the gate budget", true but about the reviewer's own window — kept a cycle unclosable round after round, which also blocked the next `begin_change`. Separated:
  - **liveness = observed activity, measured twice.** Every governed call refreshes the heartbeat; an agent doing work IS alive. Refreshing never CREATES a lock — a released lock must stay released. That alone is NOT enough: a long stretch of editing and committing with no governed call in between still freezes the heartbeat, which is the very shape of the deadlock being fixed (measured on a live lock: `heartbeat_at` still equalled `started_at` mid-cycle). So an aged-out heartbeat is checked for a **commit authored by the lock's own agent in the lock's own repo** before the lock is called stale, and is refreshed rather than purged when one exists — the lock then records when WORK happened, not when somebody last asked about the lock. Scope that check TWICE (the lock's own `repo_path` and the agent's git author): a peer repo's activity must never keep this lock alive, and a peer's commit in the SAME repo must not either, or the check merely delays their takeover — the deadlock again. An idle lock still ages out; a rescue that saves every orphan is worse than the disease. Pin the negatives, including a lock whose `agent` reads `"unknown"` — that silently disables an author filter unless it falls back to the repo's real author.
  - **mutual exclusion** = the lock, aged by no-observed-activity (the mtime fallback is unchanged).
  - **review** = its own track. A VERDICT refusal records the verdict and findings and **releases the LOCK** — holding it never fixed a finding, it only stopped the session that owned it from doing anything else. The range still cannot be PUSHED without a CLEAN receipt, so the refusal is where it belongs.
  - A reviewer **OUTAGE** still holds the lock: it is transient, retrying `end_change` works, and releasing would only cost a re-acquire. Do not confuse the two paths.
  - Release is by the lock's OWN `session_id`, never the ambient one: `get_session_id(None)` resolves a PROCESS-scoped id and this daemon serves every Hermes session, so an ambient fallback could release a **peer's** lock. A lock carrying no `session_id` must refuse to release, and say why.
- **Editing `mcp-servers/loop-gov-mcp.py` is not live until the daemon restarts.** The running server keeps the module it loaded at startup, so the very close that judges your fix runs the OLD code — a stale heartbeat, an absent gate, an old reviewer model — while the repo and the deployed file already show the new one. Verify the DEPLOYED file (checksum/content, via the deploy manifest — never a guessed path), restart the daemon, and only then claim the behaviour changed.
- **Verify the WIRING, not the constant.** A tier or flag that is correctly DEFINED is not a behaviour that is REACHED, and the difference is invisible to a test that asserts the value: the light tier required `ADVERSARIAL_REVIEW_BACKEND=agent` inside the dispatch while the DEFAULT backend is `llm`, so every default host paid heavy prices for light changes while the suite stayed green — the assertions checked that the tier FUNCTION returned "light" and never that anything consumed it. Test through the DISPATCH to the argument the call is actually made with (monkeypatch the call, capture its `model` kwarg), on the DEFAULT configuration, and pin every direction: light → cheap, always-review or oversized → heavy, and an unmeasured change → the stronger judge. When a behaviour hides behind a config branch, ask which branch the fleet actually runs before claiming the change landed.
- **A claimed fix must EXIST and be pinned by a test that fails without it.** A commit message that describes a fix which was never written is worse than an open bug: the record says otherwise, so nobody looks. Twice in one session a close note claimed a fix that had not been made (a tier that was DEFINED but never reached; a crash guard that was described and skipped). Before writing "fixed": the code path is edited, a test exercises it, and the discrimination is re-runnable (`git show <pre-fix-tip>:<path>` beside the working copy, each printing its own rc). When a test cannot be made to pass, delete it and say the gap is OPEN rather than leave a red suite behind — and gate the commit on the runner's own rc (`if [ "$rc" -eq 0 ]; then git commit …; else echo "REFUSING: tests are red"; fi`), because a `;` chain commits the failure while looking disciplined.
- **Two different facts must never share one return value.** A lock helper returned `False` both for "the renewal budget is spent" and for "the write failed", and the caller read every `False` as *spent* — so a transient disk or permission failure aged out a BUSY lock and recreated the very deadlock the change existed to remove. Return NAMED outcomes (`RENEWED` / `EXHAUSTED` / `ERROR`), and route the error case down the fallback path (mtime ageing) so a broken write still ages out while a working one is never mistaken for a dead session.
- **Verify a "weaker enforcement" claim against the CONSUMER, not the writer.** A review read the receipt WRITER, saw `reviewed_blobs: null` when a helper was missing from the deployed tree, and filed a "true push bypass". The checker that actually gates the push authorises by EXACT tip+base FIRST and by content coverage only when blobs exist — its own contract states a receipt with no `reviewed_blobs` is "only ever accepted by rule 1" — so the null set was the STRICTER authorisation and the real cost was rebase-tolerance. Open the consumer's contract (including its explicit fail-closed list) before accepting an enforcement finding or "fixing" it: a report can be right about the mechanism and wrong about the severity, and acting on the wrong half weakens something that was never weak.
- **A declared saving is not a saving until the RECORD shows it.** Read `reviewer_model` out of `adversarial_reviews` and say plainly if no row names the cheap model yet — an unchanged constant plus 202 heavy-model rows is a finding about your change, not a curiosity to explain away as always-review surfaces. Two causes can hide behind one anomaly; test the second before writing the first down.
- **A crash between `feedback_accept` and the release strands the lock.** The lock is released by `end_change`, so an exception inside the close leaves the cycle SCORED-but-PENDING and the lock held, and the session cannot start its next change. Treat releasing as required on every non-CLEAN exit *including a thrown error*, and after a close that errored, read the lock file rather than assuming either outcome.
- **Receipts degrade silently when a helper is missing from the DEPLOYED tree.** The range-blob helper is loaded by a repo-relative path against the deployed root; if that file was never registered for deploy, the receipt is written WITHOUT `reviewed_blobs`, the close can then fail on the resulting `None`, and the push gate refuses naming `reviewed_blobs`. A file that exists in the repo proves nothing about the deployed tree — check the deployed copy and the deploy register before trusting a helper the close depends on.
- **Always-review is not only about size — semantic surfaces belong in the list.** Dependency manifests, CI workflows, migrations, compose wiring and installer/deploy paths change what every OTHER change is built and run with, and they are typically tiny, so size thresholds never catch them. Add such a path alongside the mechanism it configures, and verify against the shared list file rather than the in-code literal (the file WINS, so an unloaded file silently drops every addition — the failure looks like a missing entry, not a broken load).
- **A finding-storm is fixed by the WINDOW, not by the thresholds.** One global character cut per review makes an honest reviewer report its own blindness as an `info` finding every time it cannot see the middle of a file; per-file truncation with a per-file marker gives the same budget far more information. Do not answer it by raising the size thresholds — that trades coverage for reviewer comfort, and a small multi-file logic change escaping review is usually the gap that matters.
- **Send the model CODE and ARTIFACTS, not prose about them.** A prose brief of your own design is reviewed as prose and comes back as opinion; extract the functions under review from the file with `ast` (never retype them, so they cannot drift from what runs), splice in artifacts read back from the live system — DB rows, the lock file, an accepted receipt, the log lines from the failure — and keep the instruction to a few sentences. The payload is the point: ~40k chars of code plus real data (~10k input tokens) stays answerable and yields findings by function and line number that no prose summary produced.
- **Consult the reviewer model on your own numbers, then judge its advice.** Give it the REAL semantics (what is measured, what counts, what it can see) plus your own outcome rows, and ask what it would change. Expect it to be right about the blind spot you cannot see and wrong about the trade-off you can: record accept/reject WITH reasons, and verify any factual claim it makes against the shipped file before acting on it.
- **Complexity is measured, never self-reported** — computed from the session's actual git diff: ≥50 lines (added+removed counted separately) or ≥3 files (non-noise); touching an always-review path (`plugins/governance-enforcer/`, `mcp-servers/loop-gov-mcp.py`, `core/governance/`, `ops/scripts/pre-commit-score`, `pre-push-pull`, `post-commit-audit`, `post-push-audit`, `ops/scripts/cortex-update.sh`, `ops/scripts/quality/adversarial-verify.py`, `ops/install/hooks/`) gates regardless of size — trust the SHARED list file `ops/scripts/lib/always-review-paths.txt` over any path list quoted in prose, including this one: the file WINS at load time, so it is the only current answer, and a stale quote here is how a session concludes a surface is ungated when it is not. Uncommitted work counts (staged + unstaged + untracked — no "create big file, don't add, dodge"); exact-name lockfiles (`Cargo.lock`, `package-lock.json`, …) are discounted, checked AFTER always-review paths. Trivial changes skip review.
- **Reviewer independence** — the reviewer runs in the MCP daemon with a distinct model and a fixed, committed orchestrator-owned prompt (`docs/templates/adversarial-reviewer-prompt.md`, deployed copy `~/.hermes-cortex/templates/`); the worker can neither invoke nor edit it.
- **Spend is tiered — a cheap judge is a weaker judge, so tier by RISK, not by convenience.** The heavy tier (`deepseek/deepseek-v4-pro`, override `ADVERSARIAL_REVIEWER_MODEL`) is reserved for `always_review` paths (enforcement/governance code) and unusually large diffs. Everything else runs the light tier (`deepseek/deepseek-v4-flash`, override `ADVERSARIAL_REVIEW_LIGHT_MODEL`) at roughly a tenth the price. Two settings make the light tier safe to trust: a bounded `max_tokens` and `temperature: 0` (a SAMPLING judge returned CLEAN and then FINDINGS on byte-identical material — an unstable verdict is worse than a cheap one). **Bound the OUTPUT BUDGET to the model's REASONING, not to the size of the JSON it returns.** A cap tuned to the answer starves a reasoning model, which spends the budget thinking and emits an EMPTY `content` field: measured on a long prompt, the deep reviewer returned nothing at 900 and nothing at 3000 (`finish_reason='length'`) and needed ~9000 completion tokens to answer at all. So an empty response must be handled as a reviewer FAILURE — `raise`, refuse the close, retry ONCE with a larger budget — and never as "reviewer unavailable", and never handed to the JSON parser (`text.find` on a `None` crashes the close instead of refusing it, and a crashed close strands its lock). A cap that turns a valid change into a refused close is a false negative, the one failure mode this gate must never have. The wait is bounded too (`ADVERSARIAL_REVIEW_TIMEOUT`, default 120s): a timeout refuses the close, it never skips the review. If the light tier ever waves through something real, move that CLASS back to the heavy tier rather than distrusting the verdicts wholesale. A same-agent/same-model self-review is a self-report, not an evaluation. Reviewer input is treated as untrusted data; the worker's `feedback_accept` note is passed as the self-report being reviewed.
- **A verdict is keyed to the ARTIFACT, not to the note.** The reuse key covers what a verdict is ABOUT — repo state, the audited range, the task's description (the reviewer probes scope drift against it), the diff stat, the diff — and deliberately EXCLUDES the worker's note. Including the note meant a re-worded retelling of an unchanged diff bought a fresh review; measured cost of that: one cycle paid for eight-plus reviews whose diff never moved, because each retry explained itself differently. The note still travels INSIDE the material (the reviewer is asked to treat it as the self-report and check it against the diff) — it just cannot re-open judgment of the same artifact. `rereview_change(force=True)` remains the sanctioned re-judge for when the NOTE is what changed.
- **Build the key in a function you can call from a test.** A key assembled inline at the prompt site is unfalsifiable, and the only way to prove the saving without buying a real review is cheap assertions: same artifact + different note → same key; a changed diff, HEAD, base, range note, description, task id or scope → a different key. Extract the material builder and pin both directions.
- **Findings are durable** — verdicts land in the `adversarial_reviews` table (loop-governance DB, duplicate review = benign no-op); the doctor's `check_adversarial_review` verifies the MCP review capability is present.
  **Read the record; never describe it from memory.** `SELECT cycle_id, verdict, reviewer_model, findings_json, summary FROM adversarial_reviews ORDER BY cycle_id DESC` over `~/.hermes-cortex/data/loop-governance.db`. The `reviewer_model` column is the ONLY proof of which tier judged a change, so it is how a tiering change is verified to be LIVE: if no row names the light model, the tier code is not in effect yet (the daemon serves the module it loaded at startup) and a saving you cannot show in these rows is not a saving yet — say so instead of citing the unit test. Read the parsed `findings_json`; `summary` holds the reviewer's raw response, fences and all.
  **A high FINDINGS share is not by itself a problem — count SEVERITY.** Findings at `info` are recorded and do not block, which is exactly the shape a window/bound observation should take; a fleet whose rows are mostly FINDINGS can still be closing every cycle cleanly.
- **Recovery/closeout cycles can't hide an always-review-path diff.** Complexity is measured from the whole branch diff, not just "work done in this cycle." If you opened a small recovery/lock-clear cycle while a PRIOR cycle's unmerged change already touched an always-review path (e.g. `mcp-servers/loop-gov-mcp.py`, `plugins/governance-enforcer/`), THIS cycle's `end_change` is force-reviewed no matter how trivial its own delta, and the reviewer will flag the unrelated path diff as scope-drift forever. Don't chain a recovery cycle on top of unreviewed always-path work: land/review that work under its own cycle first, keep the recovery branch clean, and traverse list-returning queries with `--json`/`-q` when the diff must stay minimal.

**task_id resolution guard:** `feedback_accept(task_id=...)` and `feedback_override(task_id=...)` will reject the call if the session has zero or multiple PENDING cycles — ambiguity forces explicit `cycle_id`. They also reject if the resolved cycle's actual `task_id` does not match the passed `task_id` (e.g. session has one PENDING cycle for task "fix-auth" but you pass task_id="fix-db"). In all rejection cases the error message includes the correct cycle_id to pass instead. This guard is structural: the close-out gate in `begin_change` already limits each session to 1 PENDING cycle at a time, so in normal operation the `task_id` path is unambiguous. The guard covers the rare case where the gate's DB check was unavailable and sibling PENDING cycles snuck in.

**Orphaned PENDING cycles from sibling sessions:** the doctor's `❌ PENDING cycles` failure often lists cycles you did NOT create — sibling/daemon sessions (background subagents, other CLI sessions, party agents) called `begin_change` and never scored. Enumerate with `cycle_query(status="pending")`, then `feedback_accept(cycle_id=N, note="...")` each verified-complete one. For cycles superseded by a later MOVE_ON cycle of the same task, cite the superseding cycle in the note (e.g. "cycle 2 (2152) verified deploy end-to-end").

**PENDING vs scored-unreviewed — don't mass-accept hook cycles (2026-08-05):** the pre-commit hook auto-logs one cycle per commit with a LOOP/MOVE_ON/STOP decision and `user_overrode IS NULL`. These accumulate by the hundred and look like "unreviewed" via `cycle_query(unreviewed=true)`, but they are NOT failures: the doctor only fails on `decision='PENDING'` cycles. Only resolve genuinely PENDING cycles (fresh <24h, no live lock for that task). To tell them apart, query the DB directly: `SELECT id, task_id, decision, user_overrode, timestamp FROM loop_cycles WHERE decision='PENDING' OR (user_overrode IS NULL) ORDER BY id` — check `decision` per row, don't bulk-accept. Upstream doctor (63981498+) refines this further: a PENDING cycle whose task_id has NO active `.governance-*.json` lock is a LEAK (FAIL, blocks push); a PENDING cycle whose task holds a live lock is the current task (INFO, expected mid-session).

**Lock STATUS field and the doctor's PENDING-cycle check (2026-08-08):** `begin_change` writes the lock with `status: "planning"` when a plan is provided (loop-gov-mcp.py), `"executing"` otherwise. The doctor's leak check used to count ONLY `status == "executing"` locks as active — so every planned task's PENDING cycle was misreported as a LEAK (❌ FAIL) even while the task held its lock, and the doctor blocked the push mid-task. The lock's EXISTENCE is the active signal (`end_change` unlinks it on release); the doctor now accepts any non-terminal status (`completed`/`cancelled` excluded). If you see "❌ PENDING cycles" for a task whose lock you can see in `~/.hermes-cortex/state/.governance-*.json`, check the deployed `cortex_doctor/checks.py` matches repo — a stale deployed copy with the old `== "executing"` filter produces exactly this false FAIL.

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
For high-volume environments, archive the JSON events directory (`~/.hermes-cortex/data/loop-events/`) to cold storage before deleting.

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
cd ~/hermes-cortex/src/loop-governance
python3 -m pytest tests/ -v
```

**Current status:** 68 tests across 7 test files — all pass.

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
(agent-session-cache-build, local-weekly-loop-eval).

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

### With orch-skill-lifecycle (successor to skill-miner)

`skill-miner` was **removed 2026-08-02** — its collection role is absorbed into
the unified `orch-skill-lifecycle` pipeline (runs daily 04:34 KST). Fleet agents
now run `agent-learning-collector` (every 6h) which sends structured Learning
Reports to `inbox_orchestrator`; the orchestrator's lifecycle cron evaluates
them and patches skills/SOUL.md. See the `orch-skill-lifecycle` skill for the
full three-phase pipeline (collect → evaluate → upgrade).

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

