# Review-cost optimization — advisory input (verbatim)

> **Provenance: advisory.** Source: ChatGPT (external advisor), supplied by Luke, 2026-10-29.
> Recorded verbatim below as the input to our own plan. It carries no authority here: the
> savings figures are directional, not measurements of this fleet, and nothing in this file
> authorises a change. Our mapping of these levers onto the live close-gate — with the measured
> numbers from this host — is `docs/design/review-risk-routing.md`. The governed close review
> remains the review of record.

## 1. Highest-impact cost optimizations

| Technique                      | Implementation                                                                                  | Potential savings         |
| ------------------------------ | ----------------------------------------------------------------------------------------------- | ------------------------- |
| Selective Pro review           | Review only high-risk changes, failed tests, architectural changes, and uncertain Flash outputs | Very high                 |
| Delta-only reviews             | Send diffs, relevant contracts, and test results instead of entire files                        | High                      |
| Constrained Pro output         | Require structured verdicts and actionable findings, not explanations                           | Medium–high               |
| Prompt caching                 | Keep stable system instructions and project context in reusable cached prefixes                 | High for repeated context |
| Adaptive context compression   | Summarize at context-growth thresholds, not every N turns                                       | Medium–high               |
| Review batching                | Review related changes together at integration boundaries                                       | Medium–high               |
| Local deterministic validation | Run lint, type checks, tests, security rules before expensive review                            | High                      |
| Local small-model triage       | Use a cheap/local model to decide whether escalation is warranted                               | Variable                  |

These are directional savings opportunities, not additive or guaranteed percentages.

## 2. Change your review architecture

Instead of:

Flash → Pro review → Flash → Pro review → ...

Use:

Flash implements development slice

Automated validation

Lint · Types · Tests · Static analysis · Contract checks

S1 risk/complexity/uncertainty router

Low risk

Accept after checks

Medium risk

Flash review

High risk

Pro review

The key is Pro reviews should be triggered by risk, not slice completion.

## 3. Aggressively reduce Pro output tokens

For review requests, use a contract like:

```
Review the supplied diff for correctness, security,
regressions, and contract violations.

Return JSON only:
{
  "verdict": "PASS|FAIL|UNCERTAIN",
  "findings": [
    {
      "file": "...",
      "line": 0,
      "severity": "critical|high|medium",
      "issue": "...",
      "fix": "..."
    }
  ]
}

Maximum 3 findings.
Omit praise, summaries, explanations, and
low-confidence speculation.
If no actionable findings, return PASS.
```

Additional optimization: ask Pro to identify defects, not rewrite code. Let Flash implement the fixes.

Set a low max_output_tokens and use minimal reasoning effort where supported. Note that output limits don't necessarily cap internal reasoning-token costs.

## 4. Context engineering: use four memory layers

| Layer       | Contents                                           | Refresh           |
| ----------- | -------------------------------------------------- | ----------------- |
| L0: Stable  | Coding standards, architecture, project rules      | Only when changed |
| L1: Task    | Current objective, acceptance criteria, interfaces | Each task         |
| L2: Working | Relevant files, diffs, failing tests               | Each slice        |
| L3: History | Decisions, unresolved issues, previous failures    | Event-driven      |

Avoid feeding conversation history directly into Pro. Construct its context from these layers.
For summarization, trigger when:

- Context exceeds a token budget.
- A task or architectural decision is completed.
- Repeated context is detected.
- A development phase changes.

Store decisions, invariants, unresolved issues, and file references. Discard repetitive discussion and obsolete intermediate reasoning.

## 5. Maximize caching

Caching is particularly valuable when using long-lived coding agents.

- Put stable system prompts, coding rules, and architecture first.
- Put variable task descriptions, timestamps, and diffs last.
- Preserve exact prefix bytes between calls.
- Reuse provider-supported cache keys or explicit cache controls.
- Track cached-input tokens separately from ordinary input tokens.

For frequently reused repository context, consider content-addressed summaries keyed by Git commit and file hashes. Rebuild only summaries affected by changed files.

Important: Provider prompt caches are generally prefix-sensitive and have expiration rules. A local semantic cache is a different mechanism.

## 6. Add an economic controller to your S1 router

Your S1 model already routes by reasoning and code complexity. I'd extend it to optimize expected total cost, including rework.

Use:

C_total = C_generation + C_review + P_failure × C_rework

Track five additional signals:

1. Change blast radius (number and importance of affected modules).
2. Test coverage and validation confidence.
3. Security/data integrity sensitivity.
4. Prior failure rate for this task category.
5. Confidence and disagreement among cheap validators.

A high-complexity task with strong tests may not need Pro review. A trivial-looking authentication change might.

Calibrate thresholds against a dataset of reviewed changes; don't treat raw S1 confidence as a reliable probability until calibrated.

## 7. Practical rollout

I'd implement this in three stages.

Stage 1 — Immediate: Delta-only reviews, JSON verdicts, capped outputs, deterministic checks, and stable prompt prefixes.

Stage 2 — Next: Risk-triggered Pro reviews, adaptive summaries, and cached repository context.

Stage 3 — Optimization: Log cost and quality outcomes, run randomized Pro-review audits on skipped slices, and tune routing thresholds using actual defect escape rates.

Your primary dashboard should measure:

| Metric                                 | Why                      |
| -------------------------------------- | ------------------------ |
| Dollars per accepted development slice | Actual productivity cost |
| Pro calls per 100 slices               | Review efficiency        |
| Cached-input percentage                | Context reuse            |
| Pro output tokens per review           | Output discipline        |
| Escaped defects per 100 slices         | Quality guardrail        |
| Rework dollars per slice               | Hidden cost              |

## My recommendation

The most promising architecture is:

Flash execution + deterministic validation + S1 risk routing + sparse Pro review + event-driven context compression + cache-aware prompts.

I would specifically experiment with reducing Pro review frequency from 100% to 20%, then 10%, while measuring escaped defects against a fully reviewed control sample.

That can potentially deliver much larger savings than shaving another 20% off prompt length, without sacrificing code quality—provided your automated tests and review-routing recall are strong.

The most important distinction: optimize cost per correctly completed task, not cost per model call. A cheap implementation that requires three rounds of rework is not cheap.
