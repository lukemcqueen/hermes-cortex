---
name: state-orchestrator
version: 1.0.0
category: software-development
description: >
  Information routing decision matrix for Hermes Cortex agents. Defines when to
  consult live context vs session history vs memory vs docs, with explicit
  priority ordering, staleness handling, confidence scoring, and cross-reference
  chaining patterns for multi-source state resolution.
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [state, orchestration, routing, decision-matrix, context, memory, docs, session, resolution]
    related_skills: [session-manager, memory-architecture, agent-contract, agent-flow]
---

# State Orchestrator — Information Routing Decision Matrix v1.0.0

> **When you need to resolve a question about system state, behaviour, or history,
> where do you look, and in what order?** This skill provides a decision matrix
> that maps each information source to its appropriate use case, with priority
> ordering, staleness handling, confidence scoring, and cross-reference chaining
> patterns for resolving conflicts or filling gaps.

---

## Table of Contents

1. [Information Source Map](#1-information-source-map)
2. [Priority Order](#2-priority-order)
3. [Decision Matrix](#3-decision-matrix)
4. [Staleness Handling](#4-staleness-handling)
5. [Confidence Scoring](#5-confidence-scoring)
6. [Cross-Reference Chaining](#6-cross-reference-chaining)
7. [Conflict Resolution](#7-conflict-resolution)
8. [Anti-Patterns](#8-anti-patterns)
9. [Version History](#9-version-history)

---

## 1. Information Source Map

There are four distinct information sources available to a Hermes Cortex agent.
Each has a different purpose, trust profile, and freshness guarantee.

| Source | Symbol | Definition | Best For | Limitations |
|--------|--------|-----------|----------|-------------|
| **Live Context** | `[LC]` | Current tool outputs, file reads, command results, and any state observable via direct inspection in this session | Ground truth — what the system *actually* looks like right now | Ephemeral; lost when session ends |
| **Session History** | `[SH]` | Prior messages, tool calls, and outputs within the current conversation turn / session | Continuity — what was just said or done moments ago | Noisy; contains intermediate exploration; not curated |
| **Memory** | `[M]` | Persistent files (MEMORY.md, USER.md, checkpoints, recovery files) stored across sessions | Long-term recall — decisions, blockers, user preferences, past completions | Can go stale; requires manual checkpoint discipline |
| **Docs** | `[D]` | Static reference: SKILL.md files, official docs, READMEs, man pages, API specs, third-party sites | Understanding — what a tool, library, or protocol *can* do | Describes intent/design, not actual state |

---

## 2. Priority Order

When answering a question or making a decision, consult sources in this order.
**Higher priority always wins unless there is evidence of staleness or unreliability**
(see §4 Staleness Handling).

```
   Live Context  ────  Highest Priority
       │
   Session History   ────  Immediate Past
       │
   Memory           ────  Persistent Knowledge
       │
   Docs             ────  Reference (lowest priority for state questions)
```

### 2.1 Priority Rule

> **The closer the source is to the current observable system, the higher its
> priority.** Live context tells you what *is*. Session history tells you what
> *just happened*. Memory tells you what *was decided*. Docs tell you what *was
> designed*.

### 2.2 When to Defer to a Lower-Priority Source

Even though priority is hierarchical, there are cases where you should skip or
not fully trust a higher-priority source:

1. **Live context is missing** — the file doesn't exist, the command errored,
   the tool returned nothing. Defer to session history or memory.
2. **Live context is noisy** — a command produced 10,000 lines of output and you
   only need the configuration intent. The `[M]` checkpoint may be more useful.
3. **Session history contradicts live context** — the user said "I just changed
   X" but live context shows X is unchanged. **Live context wins.**
4. **Memory is stale** — the checkpoint says "using port 8080" but `lsof` shows
   port 8080 is free and 9090 is in use. **Live context wins.**
5. **Docs describe a default that memory overrode** — the `write_file` doc says
   it auto-creates directories, but memory notes a custom wrapper that disabled
   this. **Memory wins over docs for custom behaviour.**
6. **All sources conflict** — use the conflict resolution procedure (§7).

---

## 3. Decision Matrix

This matrix tells you which source (or combination) to use for common situations.
The **Primary** column is where you should look *first*. The **Fallback** column
is where to go if the primary is insufficient, stale, or contradictory.

| Situation | Primary | Fallback | Rationale |
|-----------|---------|----------|-----------|
| **"What does this file contain right now?"** | `[LC]` read_file | `[SH]` last tool output if file was read earlier this turn | Files change; always verify live |
| **"What did we just do?"** | `[SH]` last 2-3 exchanges | `[M]` latest checkpoint | Session history is immediate; checkpoints are summarised |
| **"Why did we choose this approach?"** | `[M]` checkpoint or MEMORY.md | `[SH]` discussion leading to decision | Memory curates the rationale; session history is raw |
| **"How does this tool/library work?"** | `[D]` SKILL.md or official docs | `[LC]` try `--help` flag | Docs describe intended behaviour; live flags confirm presence |
| **"Is this dependency installed?"** | `[LC]` which/where/import check | `[M]` install notes | The only way to know is to check the actual system |
| **"What has been done so far today?"** | `[M]` progress list or checkpoint | `[SH]` full session log | Memory is curated; session history is thorough but verbose |
| **"What are the user's preferences?"** | `[M]` USER.md | `[D]` Hermes docs (defaults) | User preferences override defaults |
| **"Did we already try this approach?"** | `[M]` memory of recent attempts | `[SH]` tool call history | Memory is summarised; session history has the raw errors |
| **"Is there a security concern here?"** | `[D]` SECURITY.md, docs | `[M]` any prior security notes | Security policy lives in docs; past incidents live in memory |
| **"What version of X is running?"** | `[LC]` version command | `[M]` install log | Live check trumps any recorded value |
| **"How did our last session end?"** | `[M]` SESSION_RECOVERY.md or checkpoint | `[SH]` (not available across sessions) | Recovery files are designed for this |
| **"Is the system healthy?"** | `[LC]` health check command | `[M]` baseline health metrics | Compare live output to known-good baseline |
| **"What is the project structure?"** | `[LC]` ls or search_files | `[D]` README.md | Actual filesystem is ground truth; README may be out of date |
| **"What did the user *really* mean?"** | `[SH]` user's exact words | `[M]` user's known concerns/goals | User's latest message is primary; memory provides context |
| **"Should I trust this memory entry?"** | `[LC]` verify key claims live | `[M]` the entry itself | Verify before acting on potentially stale memory |

---

## 4. Staleness Handling

A source is **stale** when its content no longer reflects the current system state.
Stale data can lead to incorrect decisions, repeated work, or confidence in wrong
assumptions.

### 4.1 Staleness Tiers by Source

| Source | Typical Half-Life | Staleness Indicators | Check Before Use? |
|--------|------------------|---------------------|-------------------|
| **Live Context** | Seconds — real-time | Tool error, empty output | No — it's live by definition |
| **Session History** | Minutes — within the turn | A later tool call contradicted it | No — but cross-check with LC if in doubt |
| **Memory (checkpoint)** | Hours — one working session | Timestamp older than last `git commit`, last file write | Yes — verify key assertions with LC |
| **Memory (USER.md)** | Days to weeks | User behaviour contradicts preferences | Yes — re-confirm with user if it feels off |
| **Memory (MEMORY.md)** | Days | Timestamp suggests pre-session | Yes — always verify claims about file state with LC |
| **Docs (SKILL.md)** | Weeks to months (versioned) | Version mismatch; file references changed | No — but cross-reference with LC for system-specific details |
| **Docs (third-party)** | Months to years | Deprecation notices, version drift | No — but be aware of potential drift |

### 4.2 Staleness Resolution Procedure

When a source is identified as potentially stale:

```
1. IDENTIFY  ────  Which source has the claim? What is its timestamp or version?
                       │
2. ASSESS    ────  How old is it relative to the last known state change?
     ┌──────────────────┴──────────────────┐
     ▼                                     ▼
  Likely fresh (>90% confidence)     Likely stale (<50% confidence)
  ─────────────────────────────     ─────────────────────────────
  Use the source directly.          Proceed to step 3.
                                       │
3. VERIFY    ────  Use [LC] to check the key claim. E.g.:
   • If memory says "port 8080" → run `lsof -i :8080`
   • If memory says "Python 3.11" → run `python3 --version`
   • If memory says "file X has config Y" → run read_file on X
                                       │
                          ┌────────────┴────────────┐
                          ▼                         ▼
                     Confirmed                  Contradicted
                     ──────────                ────────────
                     Confidence    Update memory with new value
                     restored.     Use the live value going forward.
                     Proceed.      Log the update.
```

### 4.3 Freshness Notation

Use these qualifiers when citing a source:

| Label | Meaning |
|-------|---------|
| `[LC]` | Current turn, just fetched |
| `[SH: -N]` | Session history, N exchanges ago |
| `[M: YYYY-MM-DD]` | Memory entry from a specific date |
| `[D: vX.Y]` | Docs at a specific version |
| `[LC verified M]` | Memory claim confirmed by live check |
| `[LC overrode M]` | Live context contradicted memory; live wins |

---

## 5. Confidence Scoring

Every piece of information routed from a source carries an implicit **confidence
score** that you should use when weighing competing claims.

### 5.1 Base Confidence by Source

| Source | Base Confidence | Reasoning |
|--------|----------------|-----------|
| **Live Context** | 95% | Direct observation of current state. 5% deduction for tool limitations (e.g., read_file might truncate) |
| **Session History** | 85% | Direct observation, but may be superseded by later LC. Reduce to 70% if >10 exchanges ago |
| **Memory (checkpoint just written)** | 90% | Just saved, still fresh. 10% deduction for human error in checkpoint content |
| **Memory (MEMORY.md)** | 75% | Curated but may be hours/days old. Deduction increases with age |
| **Memory (USER.md)** | 80% | User-defined preferences, relatively stable |
| **Docs (SKILL.md)** | 85% | Versioned, maintained, but describes intent not state |
| **Docs (third-party)** | 70% | May describe different version or environment |

### 5.2 Confidence Adjustments

Apply these adjustments to base confidence:

| Condition | Adjustment |
|-----------|-----------|
| Source was just verified by `[LC]` | +10% (capped at 99%) |
| Source contradicts another source | -15% per conflicting source |
| Source is >24h old (memory) | -10% |
| Source is >7d old (memory) | -25% |
| Source has version mismatch (docs) | -20% |
| Source was written by the current session | +5% |
| Source is a third-party doc with known deprecations | -15% |
| Source is a recovery file from an interrupted session | -10% (may be incomplete) |

### 5.3 Thresholds

| Score Range | Action |
|-------------|--------|
| **≥ 90%** | Act on the information directly. |
| **70–89%** | Use the information but cross-reference if it will lead to a destructive action. |
| **50–69%** | Do not act without live verification. Flag as uncertain. |
| **< 50%** | Discard the source or ask the user. Do not use for decision-making. |

### 5.4 Multi-Source Consensus

When multiple sources agree, confidence is **boosted**:

```
2 sources agree:    base + 5%
3 sources agree:    base + 10%
4 sources agree:    base + 15%
Any source            -20% per dissenting source
strongly dissents:
```

---

## 6. Cross-Reference Chaining

Cross-reference chaining is the practice of following a link from one source to
another to resolve a question or fill a gap. This is especially valuable when a
primary source is insufficient.

### 6.1 Standard Chain Patterns

```
6.1.1  Gap Fill Chain
       ──────────────
       [D: SKILL.md] mentions a technique
           → but the technique requires a specific tool version
           → [LC: tool --version] to check version
           → if missing, [M: install notes] for how to upgrade

6.1.2  State Verification Chain
       ─────────────────────────
       [M: checkpoint] says "port 8080 is configured"
           → [LC: lsof -i :8080] to verify
           → if not found, [SH: last session] for discussion about port change
           → if not in SH, [M: MEMORY.md] for any port migration notes

6.1.3  Decision Recovery Chain
       ────────────────────────
       Why was X chosen?
           → [M: decision log in checkpoint]
           → if ambiguous, [SH: conversation excerpts around decision time]
           → if still unclear, [D: comparative analysis of alternatives]
           → final resort: ask the user

6.1.4  Bug Diagnosis Chain
       ────────────────────
       Something broke.
           → [LC: error output or traceback]
           → [M: what changed recently?] (checkpoint diff, git log)
           → [D: error documentation]
           → [SH: what was the last thing that worked?]
           → [LC: reproduce with minimal test case]

6.1.5  Preference Resolution Chain
       ────────────────────────────
       How should I format output?
           → [M: USER.md] for explicit preferences
           → if not present, [D: Hermes docs defaults]
           → if platform-specific, [LC: check platform from env]
           → if still uncertain, [SH: user's past messages for stylistic hints]
```

### 6.2 Chain Termination Rules

A cross-reference chain terminates when:

1. **Live context confirms the answer** — you have direct evidence of current state.
2. **The user provides a definitive answer** — the agent asks and the user responds.
3. **A confidence threshold is crossed** — you have ≥ 90% confidence from multi-source agreement.
4. **All sources are exhausted** — no more sources to consult; report a blocker.

### 6.3 Chain Recording

When you execute a cross-reference chain, record it in memory for future sessions:

```markdown
## Cross-Reference Chain — YYYY-MM-DD HH:MM UTC

### Question
Why is the API returning 503 errors?

### Chain
1. [LC] `curl -I https://api.example.com/health` → 503
2. [M] Checkpoint from yesterday: "Deployed new auth middleware at 14:00"
3. [SH] Prior discussion: "The new middleware requires a Redis connection"
4. [LC] `redis-cli ping` → Could not connect
5. [D] Internal docs: "Auth middleware v2 requires Redis 6.x"
6. [LC] `redis-server --version` → Redis 5.0 (too old)

### Resolution
Upgrade Redis to 6.x. Confidence: 95% (LC + D + M all agree).
```

### 6.4 Chain Length Guidelines

| Chain Depth | Use Case | When to Stop |
|-------------|----------|-------------|
| 1–2 hops | Simple fact check, version query | After LC confirms or contradicts |
| 3–4 hops | Debugging a known issue, restoring context | After root cause identified |
| 5+ hops | Complex multi-source investigation | After chain converges (≥90% confidence) or all sources exhausted |

---

## 7. Conflict Resolution

When two or more sources disagree, use this procedure.

### 7.1 Conflict Detection

A conflict exists when:

- `[LC]` contradicts `[M]` on a factual claim (e.g., file content, version, port).
- `[M]` and `[SH]` disagree on what was decided.
- `[D]` describes behaviour that `[LC]` disproves.
- Multiple `[M]` entries from different times give conflicting accounts.

### 7.2 Resolution Rules

| Conflict | Resolver | Rationale |
|----------|----------|-----------|
| `[LC]` vs `[M]` | **LC always wins** | Live state is ground truth; memory may be stale |
| `[LC]` vs `[D]` | **LC wins** for *state* questions; **D wins** for *behaviour/design* questions | LC tells you what is; D tells you what should be — different questions |
| `[SH]` vs `[M]` | **M wins** if checkpoint was written after the SH event; **SH wins** if the event hasn't been checkpointed yet | A newer snapshot overrides a raw event; raw events override older snapshots |
| `[M]` vs `[M]` (different dates) | **Newer wins** — check timestamps | Explicit versioning of memory |
| `[M]` vs `[D]` | **M wins** for *custom/local decisions*; **D wins** for *default/standard behaviour* | Local overrides take precedence over defaults |
| `[SH]` entry contradicts itself | Discard the earlier part; keep the later | Latest statement in a session is the most current intent |
| User says X, `[M]` says Y | **User wins** — always | User is the ultimate authority on their own intent |

### 7.3 Conflict Logging

After resolving a conflict, log it:

```markdown
## State Conflict — YYYY-MM-DD HH:MM UTC

### Conflicting Claims
- [M: 2025-06-07] "API key is stored in ~/.secrets/api-key"
- [LC] read_file("~/.secrets/api-key") → File not found

### Resolution
LC overrode M. API key has been moved or deleted since the memory entry.
→ Checked [M: install notes] — no migration record found.
→ Checked [D: docs] — default location is ~/.config/app/api-key
→ [LC] read_file("~/.config/app/api-key") → "sk-<key-found>"

### Action Taken
Updated [M: MEMORY.md] with new path. Confidence: 97%.
```

---

## 8. Anti-Patterns

- ❌ **Asking docs for state** — don't read the SKILL.md to find out if something
  is running. Check live context.
- ❌ **Trusting memory blindly** — always verify memory claims that affect
  destructive operations (file writes, deletes, restarts).
- ❌ **Ignoring session history when it's relevant** — if you just ran a command
  3 exchanges ago, don't re-run it. Use session history.
- ❌ **Over-chaining** — don't follow a cross-reference chain beyond 5 hops
  without asking yourself whether a direct LC check would be faster.
- ❌ **False consensus** — don't treat `[M] + [D]` (2 sources) as strong
  consensus if both ultimately derive from the same source (e.g., both were
  written from the same meeting notes).
- ❌ **Confidence inflation** — don't add the multi-source bonus if all sources
  ultimately trace to the same original observation.
- ❌ **Never checking memory** — some agents operate entirely in live-context
  mode and lose all continuity across sessions. Use memory for persistence.
- ❌ **Ignoring staleness in docs** — third-party tutorials and even first-party
  docs can describe APIs that were deprecated. Cross-reference version numbers
  with live context.

---

## 9. Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2025-06-08 | Hermes Agent | Initial release — full decision matrix, staleness handling, confidence scoring, and cross-reference chaining patterns |
