# Trigger Phrase Mapping — TDD & Scoring Default Rules

## The Default (Rule #11)

TDD/scoring/governance is ALWAYS on. Every code change assumes
RED-GREEN-REFACTOR + SCORE. This is not optional.

## Opt-Out Phrases (these bypass the loop)

| User says | What I do |
|-----------|-----------|
| `"don't test, just X"` / `"skip tests"` | Code change only, still score it |
| `"only review..."` / `"read-only"` | Read-only investigation, no code change, no scoring |
| `"throwaway prototype"` / `"spike"` | Write disposable code, discard after, no tests |
| `"just check..."` / `"look at..."` | Read-only investigation |
| `"Can you check Z?"` | Read-only unless code change needed |

## Ambiguous Phrases (these DO trigger the full loop)

`sure`, `go ahead`, `do it`, `sounds good`, `ok`, `proceed`, `build it`,
`implement`, `fix`, `create`, `add`, `write`, `make`, `update`, `patch`,
`go for it`, `sure go for it`, `let's do it`, `yes`, `yep`, `👍`

## Discovered Issues Rule (Rule #12)

When finding a pre-existing bug/problem during other work:
1. Document as `todo(pending)` — specific file path + what's wrong
2. Complete current slice first — do NOT fix inline
3. Return to documented follow-ups in priority order
4. Never silently skip — undocumented = forgotten

## The Full Loop (5 steps)

```
LEARN → RED → GREEN → REFACTOR → SCORE → [repeat/next]
```

LEARN: `mcp_loop_governance_cache_search(query="task description")`
RED: failing test first
GREEN: minimal implementation
REFACTOR: clean up while green
SCORE: `score-cycle` per change, `feedback_accept/override` per cycle
