<!-- Part of Hermes Cortex. See docs/SECURITY.md for privacy. -->

# Memory Scoring Rubric (compact)

**Pass threshold:** ≥7/12

## Score axes

| Axis | Max | Measures |
|---|---|---|
| Relevance | 4 | Critical for agent context? |
| Accuracy | 4 | Verified, unambiguous? |
| Conciseness | 2 | Single declarative fact? |
| Durability | 2 | Stays true long-term? |

## Entry rules

- Declarative facts only — one fact per bullet
- Pointer pattern: `→ /brain <source> <topic>`
- No PII, no public knowledge, no task artifacts, no speculation
- Keep `MEMORY.md` ≤ 2,200 chars

## Pruning

Remove entries that are: ephemeral, superseded, outdated, low-score (<5/12), promoted to docs/brain, or derivable from other entries.

## Quick scoring

- **Relevance:** 4=essential, 3=frequent, 2=occasional, 1=rare, 0=irrelevant
- **Accuracy:** 4=verified, 3=reliable source, 2=likely, 1=speculative, 0=wrong
- **Conciseness:** 2=single sentence, 1=extra context, 0=paragraph
- **Durability:** 2=permanent, 1=stable, 0=ephemeral
