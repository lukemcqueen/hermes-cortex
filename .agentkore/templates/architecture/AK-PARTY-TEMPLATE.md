# ADR <NNN>: <Title>

## Metadata

| Field | Value |
|---|---|
| ADR Number | <NNN, sequential> |
| Date | <YYYY-MM-DD> |
| Status | `proposed` → `accepted` → `superseded` |
| Deciders | <who decided> |
| Council Phase | `elicit` / `tradeoff` / `finalize` |

## Cost/Complexity Snapshot

| Dimension | Estimate | Confidence |
|---|---|---|
| Implementation effort | X–Y person-weeks | H/M/L |
| Infrastructure cost/mo | $Z | H/M/L |
| Maintenance burden | Low/Med/High | H/M/L |

## Context

<What forces are at play? What constraints, assumptions, and priorities drive this decision?>

## Decision

<What are we doing? One sentence.>

### Options Considered

| Option | Pros | Cons | Effort | Risk | Cost/Mo |
|---|---|---|---|---|---|
| A: <name> | <pros> | <cons> | <S/M/L/XL> | <R1, R2> | <$> |
| B: <name> | <pros> | <cons> | <S/M/L/XL> | <R3> | <$> |
| C: (status quo) | <pros> | <cons> | 0 | <R4> | <$> |

### Recommendation

**Chosen:** Option <X> — <rationale, 1-2 sentences>

## Decision Criteria Scoring

| Domain | Option A | Option B | Option C |
|---|---|---|---|
| Product (40%) | 4 / 1.6 | 3 / 1.2 | 2 / 0.8 |
| Architecture (35%) | 3 / 1.05 | 4 / 1.4 | 2 / 0.7 |
| Security (50%) | 5 / 2.5 | 3 / 1.5 | 3 / 1.5 |
| Data (35%) | 4 / 1.4 | 3 / 1.05 | 2 / 0.7 |
| DevOps (40%) | 3 / 1.2 | 4 / 1.6 | 2 / 0.8 |
| QA (40%) | 4 / 1.6 | 3 / 1.2 | 2 / 0.8 |
| **Total** | **9.35** | **7.95** | **5.3** |

## Conflict Resolution

| Conflict | Viewpoints | Cost of Delay | Risk Score | Resolution |
|---|---|---|---|---|
| <description> | Product: speed, Security: audit | 6 (Med) | 8 (High) | Priority — full governance review needed |

## Tradeoffs

| Concern | Winner | Why |
|---|---|---|
| Developer velocity | Option X | <reason> |
| Operational cost | Option Y | <reason> |
| Security posture | Option A | <reason> |
| Scalability | Option B | <reason> |

## Risk Register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | <risk> | H/M/L | H/M/L | <plan> |
| R2 | <risk> | H/M/L | H/M/L | <plan> |
| R3 | <risk> | H/M/L | H/M/L | <plan> |
| R4 | <risk> | H/M/L | H/M/L | <plan> |

## Consequences

- **Positive:** <what gets better>
- **Negative:** <what gets worse, short-term>
- **Neutral:** <what changes but doesn't improve/worsen>

## Related Decisions

- ADR <NNN>: <related>
- FR-IDs affected: <list>

## Post-Implementation Review

_Complete 3 months after shipping._

| Question | Actual | OK? |
|---|---|---|
| Assumptions still valid? | | ☐ |
| Performance meets projections? | | ☐ |
| Security posture holds? | | ☐ |
| Maintenance cost in expected range? | | ☐ |
| Any decision that should be reversed? | | ☐ |

---

## Integration with AgentKore Planning Pipeline

| Step | Artifact | Skill |
|---|---|---|
| Elicitation | PRD | `ak-elicit` (optional-skill) |
| Architecture Review | This ADR | `ak-party` (optional-skill) |
| Story Slicing | Story map | `story-slicing` (optional-skill) |
| Task Breakdown | Task cards | `prd-to-tasks` (optional-skill) |
| Execution | Tickets/commits | `task-executor` (core) |

_AgentKore planning pipeline traceability: FR-ID → Story-ID → Task-ID chain is documented in `references/traceability-chain.md`._
