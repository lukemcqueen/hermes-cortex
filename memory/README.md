<!-- Part of Hermes Cortex. See docs/SECURITY.md for privacy. -->

# Memory Scoring Rubric

This document defines how memory entries are scored for admission into `MEMORY.md` and how they are pruned.

---

## Score Criteria (≥7/12 to write)

Each candidate fact is scored on four axes. **Total ≥ 7 out of 12** is required to write to memory.

| Axis | Max Pts | What it measures |
|---|---|---|
| **Relevance** | 4 | How critical this fact is for the agent's ongoing context and decision-making |
| **Accuracy** | 4 | Whether the fact is verified, unambiguous, and up to date |
| **Conciseness** | 2 | Whether the fact is a single, tight statement (not a paragraph or list) |
| **Durability** | 2 | How long the fact will remain true (stable facts score higher than transient ones) |

### Scoring guide

**Relevance (0–4)**
- 4 — Essential context; the agent needs this every turn (e.g. OS, project root, identity)
- 3 — Frequently referenced fact that improves response quality (e.g. tool preferences, architecture decisions)
- 2 — Occasionally useful but not critical
- 1 — Tangentially related; won't affect most turns
- 0 — Irrelevant to future interactions

**Accuracy (0–4)**
- 4 — Verified first-hand; no ambiguity; timestamped if time-sensitive
- 3 — Confirmed from a reliable source; minor uncertainty
- 2 — Likely true but unverified
- 1 — Speculative or outdated
- 0 — Incorrect or contradictory to known facts

**Conciseness (0–2)**
- 2 — Single declarative sentence with one fact
- 1 — More than one sentence or includes extra context
- 0 — Paragraph, list, or prose block not suitable for memory

**Durability (0–2)**
- 2 — Fact will remain true indefinitely (e.g. "Home dir is /Users/name")
- 1 — Fact is stable but could change (e.g. "Currently using Claude Sonnet")
- 0 — Ephemeral / single-session fact (e.g. "Running migration script X")

---

## Entry Format

Entries in `MEMORY.md` **must** be:

- **Declarative facts only** — state what *is*, not what *was done* or *will be done*
- **One fact per entry** — each bullet point contains exactly one atomic fact
- **Pointer pattern preferred** — `→ /brain <source> <topic>` instead of inline detail where full context lives in brain directories

### Good examples

```
- OS: macOS 12.7.6 — Darwin kernel
- Default model: deepseek-v4-flash
- Project root: ~/hermes-cortex
- → /brain m docker for Docker Compose service definitions
```

### Bad examples

```
- Ran apt update && npm install yesterday  ✗ (task artifact)
- I think the user prefers VS Code           ✗ (speculative)
- The capital of France is Paris              ✗ (public knowledge)
- Luke Smith's email is luke@...             ✗ (PII)
```

---

## Quality Rules

1. **One fact per entry** — never combine multiple facts in a single bullet
2. **No task artifacts** — completed tasks, command output, and session logs belong in `docs/` or brain, not memory
3. **No public knowledge** — general facts (API docs, language syntax, common definitions) that any agent already knows or could look up
4. **No PII** — real names (use handle/alias), email addresses, IPs, tokens, secrets, private domains, passwords
5. **No speculation** — every entry must be a verified, current fact
6. **Pointer dense** — use `→ /brain <source> <topic>` references to avoid bloat; keep `MEMORY.md` under 2,200 characters

---

## Pruning Guidelines

Prune `MEMORY.md` when it exceeds **2,200 characters** or when stale facts accumulate.

### Pruning criteria (remove entries that match any)

| Criterion | Example |
|---|---|
| **Ephemeral** | A fact tied to a specific session, run, or temporary state |
| **Superseded** | A newer fact replaces the older one (keep only the latest) |
| **Outdated** | The fact is no longer true (e.g. changed versions, moved paths) |
| **Low-score** | Entries that originally scored < 5/12 — these should never have been added; remove them on sight |
| **Promoted** | Fact has been moved to `docs/` or a brain directory; the pointer in memory is no longer needed |
| **Derived** | Fact can be inferred from other entries still in memory |

### Pruning process

1. **Scan by section** — review each section's entries top to bottom
2. **Score each candidate** — re-score against the rubric
3. **Remove low scorers** — drop anything < 7/12 or that matches a pruning criterion above
4. **Merge duplicates** — if two entries overlap, keep the more durable and concise one
5. **Rewrite pointers** — if a removed fact lives in brain, replace the inline text with a `→ /brain` pointer
6. **Trim to ≤ 2,200 chars** — keep the final file under the size limit

---

## Summary

| Rule | Value |
|---|---|
| **Pass threshold** | ≥ 7 / 12 |
| **Max file size** | ≤ 2,200 characters |
| **Entry style** | Single declarative fact per bullet |
| **Pointer pattern** | `→ /brain <source> <topic>` |
| **Prohibited** | PII, public knowledge, task artifacts, speculation |
