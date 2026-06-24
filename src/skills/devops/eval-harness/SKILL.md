---
name: eval-harness
description: "Systematic evaluation framework for agent capabilities — capability tests, regression suites, failure analysis"
version: 1.0.0
author: Moses
metadata:
  tags: [eval, testing, reliability, autonomous-agents, quality-gates]
---

# Eval Harness — Systematic Agent Evaluation

## When to Use

- Before deploying new agent behaviors or workflows
- After model upgrades to verify no regression
- Weekly regression testing on holdout test sets
- When debugging recurring failure patterns
- Before promoting experimental features to production

## Core Principles

**Eval-driven development** turns agents from demos into production systems:

1. **Define success BEFORE building** — what "done" means must be explicit
2. **Outcomes > outputs** — verify real results, not just generated text
3. **Deterministic + model-based grading** — use code for objective checks, LLM for nuance
4. **Read transcripts** — metrics tell WHAT failed, transcripts tell WHY
5. **Out-of-sample gating** — survivors must pass on unseen data before deployment

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Eval Harness                              │
├─────────────────────────────────────────────────────────────┤
│  1. Task Definitions (YAML/JSON)                            │
│     - Input scenarios (20-50 representative cases)          │
│     - Expected outcomes (verifiable criteria)               │
│     - Grading rubric (deterministic + LLM)                  │
│                                                              │
│  2. Execution Engine                                        │
│     - Runs agent on each task                               │
│     - Captures full trace (Langfuse)                        │
│     - Applies graders                                       │
│     - Aggregates results                                    │
│                                                              │
│  3. Analysis Layer                                          │
│     - Pass/fail metrics                                     │
│     - Failure clustering                                    │
│     - Transcript sampling                                   │
│     - Trend tracking                                        │
└─────────────────────────────────────────────────────────────┘
```

## Eval Types

### Capability Evals

**Purpose:** Measure what the agent CAN do (new feature, new skill)

**Characteristics:**
- Start low (baseline performance)
- Improve over iterations
- Focus on specific capability

**Example:** "Agent can deploy a Next.js app behind nginx with SSL"

### Regression Evals

**Purpose:** Ensure agent MAINTAINS learned tasks

**Characteristics:**
- Should stay near 100% pass rate
- Run on every change
- Include historical failure cases

**Example:** "Agent still correctly installs cron jobs without duplicates"

### Stress Evals

**Purpose:** Test boundaries and edge cases

**Characteristics:**
- Ambiguous requirements
- Conflicting patterns in codebase
- Missing context
- Resource constraints

**Example:** "Agent handles 404 from API gracefully with retry logic"

## Workflow

### Step 1: Define Eval Tasks

Create `evals/<capability-name>.yaml`:

```yaml
name: cron-installation
description: Verify cron jobs are installed correctly without duplicates

tasks:
  - id: fresh-install
    description: Install crons on fresh Hermes setup
    input: "Set up cron jobs for a new Hermes Agent installation"
    expected:
      - 9 cron jobs created
      - No duplicates in jobs.json
      - All scripts exist and are executable
    grading:
      deterministic:
        - cron_count == 9
        - no_duplicates_in_jobs_json
        - all_scripts_executable
      llm_rubric: |
        - Agent verified scripts exist before creating crons
        - Agent checked for existing jobs before adding
        - Agent provided troubleshooting commands

  - id: existing-install
    description: Install crons when some already exist
    input: "Run cron installation on existing system"
    expected:
      - Existing jobs preserved
      - Missing jobs added
      - No duplicates created
    grading:
      deterministic:
        - existing_jobs_preserved
        - no_duplicates_created
      llm_rubric: |
        - Agent detected existing crons
        - Agent skipped already-present jobs
        - Agent reported what was skipped vs created

  - id: force-reinstall
    description: Force recreate all crons
    input: "Recreate all cron jobs from scratch"
    expected:
      - All old jobs removed
      - All new jobs created
      - No orphaned jobs
    grading:
      deterministic:
        - all_jobs_recreated
        - no_orphaned_jobs
```

### Step 2: Run Eval Suite

```bash
# Run specific eval
python3 ~/.hermes/scripts/run-evals.py --eval cron-installation

# Run all regression evals
python3 ~/.hermes/scripts/run-evals.py --suite regression

# Run with transcript capture
python3 ~/.hermes/scripts/run-evals.py --eval cron-installation --capture-traces

# Run against holdout set (pre-deployment gate)
python3 ~/.hermes/scripts/run-evals.py --eval cron-installation --holdout
```

### Step 3: Analyze Results

**Metrics output:**

```
━━━ Eval Results: cron-installation ━━━

Overall: 78% pass (23/30 tasks)

By category:
  Deterministic: 92% (23/25)
  LLM rubric:    60% (18/30)

Failures:
  - existing-install: duplicate detection failed (2/5 runs)
  - force-reinstall: orphaned job cleanup incomplete (3/5 runs)

Transcripts flagged for review:
  - eval-run-20260619-143022-existing-install-trace-7.json
  - eval-run-20260619-143022-force-reinstall-trace-3.json
```

### Step 4: Read Transcripts

**Critical practice:** Metrics tell you THAT it failed, transcripts tell you WHY.

```bash
# Open specific transcript
cat ~/.hermes/evals/traces/eval-run-20260619-143022-existing-install-trace-7.json | jq

# Or view in Langfuse UI
open https://langfuse.local/project/.../traces/eval-run-20260619-143022-existing-install-trace-7
```

**What to look for:**
- Where did the agent go wrong?
- What context was missing?
- Did the agent make assumptions without verifying?
- Did the agent blend conflicting patterns?
- Did the agent stop too early or loop forever?

### Step 5: Iterate

Based on transcript analysis:

1. **Fix root cause** — not just the symptom
2. **Update eval** — if the eval didn't catch the failure mode
3. **Re-run** — verify fix + check for regressions
4. **Promote to regression** — if capability eval passes consistently

### Step 6: Gate on Holdout

Before deploying:

```bash
# Run on holdout set (unseen test cases)
python3 ~/.hermes/scripts/run-evals.py --eval cron-installation --holdout

# Must pass 90%+ on holdout to deploy
```

**Why holdout matters:** Prevents overfitting to known test cases.

## Grading Implementation

### Deterministic Graders

```python
# evals/graders/cron_graders.py

def cron_count_equals(expected: int, trace: dict) -> bool:
    """Verify expected number of cron jobs created."""
    jobs = trace.get('final_state', {}).get('cron_jobs', [])
    return len(jobs) == expected

def no_duplicates_in_jobs_json(trace: dict) -> bool:
    """Verify no duplicate job names in jobs.json."""
    jobs = trace.get('final_state', {}).get('cron_jobs', [])
    names = [j['name'] for j in jobs]
    return len(names) == len(set(names))

def all_scripts_executable(trace: dict) -> bool:
    """Verify all referenced scripts exist and are executable."""
    scripts = trace.get('final_state', {}).get('scripts', [])
    return all(s['exists'] and s['executable'] for s in scripts)
```

### LLM Rubric Graders

```python
# evals/graders/llm_rubric.py

from langfuse import Langfuse

def grade_with_rubric(trace: dict, rubric: str) -> dict:
    """Use LLM to grade trace against rubric."""
    client = Langfuse()
    
    score = client.score(
        trace_id=trace['id'],
        name="llm-rubric-grade",
        value=0.0,  # Will be updated by LLM
        comment=rubric,
        # Use LLM to evaluate
        source="LLM"
    )
    
    # Run LLM evaluation
    response = client.llm().chat.completions.create(
        model="claude-sonnet-4",
        messages=[
            {"role": "system", "content": "You are an eval grader. Grade the agent trace against the rubric."},
            {"role": "user", "content": f"Rubric:\n{rubric}\n\nTrace:\n{trace['observations']}"}
        ]
    )
    
    # Parse LLM response for score
    # Expected format: {"score": 0.8, "reasoning": "..."}
    
    return {
        "score": parsed_score,
        "reasoning": parsed_reasoning,
        "passed": parsed_score >= 0.7
    }
```

## Failure Analysis

### Weekly Failure Report

```bash
# Cron job: weekly-failure-analysis (Monday 7am)
python3 ~/.hermes/scripts/analyze-failures.py --week last
```

**Output:**

```
━━━ Weekly Failure Analysis — Week 24, 2026 ━━━

Total failures: 47
Unique failure modes: 8

Top failure modes:
1. Missing context (12 failures)
   - Agent assumed file structure without reading
   - Agent didn't verify script existence before creating crons
   
2. Silent pattern blending (9 failures)
   - Agent mixed class-based and function-based patterns
   - Agent didn't surface conflict, picked one silently
   
3. Premature completion (8 failures)
   - Agent said "done" before verification step
   - Agent skipped regression tests
   
4. Token overflow (7 failures)
   - Context exceeded model limits mid-task
   - Agent lost track of earlier decisions

Recommended fixes:
- Add read-before-write hook to agent-contract skill
- Add conflict surfacing requirement to task contract
- Add checkpoint verification before "complete" status

Full report: ~/.hermes/evals/reports/weekly-failure-2026-W24.md
```

### Failure Clustering

```python
# Cluster failures by pattern
from sklearn.cluster import KMeans

def cluster_failures(failures: list) -> dict:
    """Group failures by common patterns."""
    # Embed failure traces
    embeddings = [embed_trace(f['trace']) for f in failures]
    
    # Cluster
    kmeans = KMeans(n_clusters=8)
    labels = kmeans.fit_predict(embeddings)
    
    # Group by cluster
    clusters = {}
    for i, label in enumerate(labels):
        clusters.setdefault(label, []).append(failures[i])
    
    # Analyze each cluster for common patterns
    patterns = {}
    for cluster_id, cluster in clusters.items():
        patterns[cluster_id] = {
            "count": len(cluster),
            "common_features": extract_common_features(cluster),
            "sample_traces": cluster[:3],  # Review these
        }
    
    return patterns
```

## Integration Points

### Langfuse Integration

All eval runs are traced in Langfuse:

- **Trace name:** `eval-run-<timestamp>-<task-id>`
- **Tags:** `eval`, `<eval-name>`, `capability|regression|stress`
- **Scores:** Attached to each trace (deterministic + LLM rubric)
- **Observations:** Full agent trace with tool calls, outputs, decisions

### Session State Integration

Eval runs update session state:

```markdown
## Current Eval Run

**Eval:** cron-installation
**Started:** 2026-06-19 14:30 KST
**Progress:** 23/30 tasks (77%)
**Current task:** force-reinstall
**Status:** in_progress
```

### Cron Integration

```bash
# Daily regression (6am)
hermes cron create \
  --name "eval-daily-regression" \
  --schedule "0 6 * * *" \
  --prompt "Run daily regression eval suite using eval-harness skill. Report failures only." \
  --skill "eval-harness" \
  --deliver "origin"

# Weekly failure analysis (Monday 7am)
hermes cron create \
  --name "weekly-failure-analysis" \
  --schedule "0 7 * * MON" \
  --prompt "Run weekly failure analysis using eval-harness skill. Cluster failures, identify top 3 patterns, create GitHub issues." \
  --skill "eval-harness" \
  --deliver "origin"
```

## Metrics to Track

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Capability eval pass rate | Improve over time | <50% after 3 iterations |
| Regression eval pass rate | ≥95% | <90% |
| Holdout pass rate | ≥90% | <80% (block deployment) |
| Mean time to detect failure | <24 hours | >48 hours |
| Failure recurrence rate | <10% | >20% (same failure twice) |

## Anti-Patterns

### ❌ Vibe-Driven Development

**Wrong:** "The agent feels better after the change"

**Right:** "Regression eval pass rate improved from 87% to 94%"

### ❌ Overfitting to Eval

**Wrong:** Agent learns to pass specific eval tasks without generalizing

**Right:** Holdout set catches overfitting, force generalization

### ❌ Skipping Transcript Review

**Wrong:** "All metrics look good, ship it"

**Right:** "Metrics show 92% pass, but reviewing 5 failed traces reveals a pattern we need to fix"

### ❌ Eval as Afterthought

**Wrong:** Build feature, then write evals to prove it works

**Right:** Write evals first, build to pass evals

## Files

| Path | Purpose |
|------|---------|
| `src/skills/devops/eval-harness/SKILL.md` | This skill |
| `src/scripts/run-evals.py` | Eval execution engine |
| `src/scripts/analyze-failures.py` | Weekly failure analysis |
| `evals/` | Eval definitions (YAML) |
| `evals/graders/` | Grader implementations (Python) |
| `~/.hermes/evals/traces/` | Captured eval traces |
| `~/.hermes/evals/reports/` | Generated reports |

## Related Skills

- `change-test-loop` — RED-GREEN-REFACTOR for individual tasks
- `code-review` — Pre-commit review with quality gates
- `lesson-aware-agent` — Inject lessons from past failures
- `auto-remediation` — Auto-fix detected issues
