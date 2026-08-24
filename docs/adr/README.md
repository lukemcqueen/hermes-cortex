# Architecture Decision Records (ADR)

**Convention added 2026-08-24 (Dexter Horthy, 12-Factor Agents, factor-3 +
gist: "Files on disk are free context — every future session starts
smarter.")** Before this, important fleet decisions lived in chat history
and session notes — invisible to fresh sessions, costing tokens to
re-derive. Now every durable decision gets a numbered ADR.

## Why

- A fresh session should read the ADRs and know WHY the system is shaped
  this way — without re-deriving it from code or asking the user.
- Decisions recorded at the moment they're made, with consequences, beat
  post-hoc archaeology.

## File format

```
docs/adr/NNNN-<slug>.md
```

- `NNNN` — zero-padded sequence (0001, 0002, ...). Never reuse a number.
- `<slug>` — kebab-case short name (`model-contract-pricing`).
- One decision per file. Never rewrite an ADR — supersede it with a new
  one and link back.

## Template (copy docs/adr/TEMPLATE.md)

```markdown
# ADR-NNNN: <Title>

- Status: accepted | superseded-by-ADRNNNN | rejected
- Date: <YYYY-MM-DD>
- Author: <agent or human>

## Context
<the problem, constraint, or force that triggered this decision>

## Decision
<what we decided, in plain language — the model/user must be able to
reproduce the reasoning>

## Consequences
<what this enables, what it costs, what breaks if changed>
```

## Rules

1. **Record, don't duplicate.** If a decision already lives in code with a
   clear comment chain, the ADR references it — it doesn't copy it.
2. **Verifiable facts only.** Numbers (pricing, caps) come from the live
   source (cost_store.py, config.yaml) — never from memory.
3. **Never secrets.** ADRs go in the public repo — env VALUES stay in
   `.env`; ADRs cite env var NAMES only.
4. **Record at decision time.** When a non-obvious choice is made during
   implementation, add the ADR in the same commit (Rule 13: fix stale
   references now — same energy).
5. **Supersede, don't edit.** Changed your mind? New ADR, status
   `superseded-by-ADRNNNN` on the old one.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| 0001 | [DeepSeek model contract + pricing](0001-model-contract-pricing.md) | accepted |
| 0002 | [MAX_COST preflight guard (O6-S1)](0002-max-cost-guard.md) | accepted |
| 0003 | [Agent Bus API /v2 policy](0003-bus-api-v2-policy.md) | accepted |
