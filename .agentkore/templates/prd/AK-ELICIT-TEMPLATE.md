# Product Requirements Document: <Project Name>

## Metadata

| Field | Value |
|---|---|
| Project | <name> |
| Version | <semver> |
| Date | <YYYY-MM-DD> |
| Status | `draft` → `reviewed` → `approved` |
| Mode | `deep` / `fast` |
| Author | <name or role> |

## 1. Problem Statement

<One paragraph. What problem does this solve? For whom? Why now?>

## 2. Goals & Non-Goals

### Goals
- G1: <measurable outcome>
- G2: <measurable outcome>

### Non-Goals
- NG1: <explicitly out of scope>
- NG2: <explicitly out of scope>

## 3. Stakeholders

| Role | Interest | Sign-off? |
|---|---|---|
| <role> | <what they care about> | Y/N |

## 4. Prioritization Framework

Chosen framework: **MoSCoW / RICE** (delete one)

| Requirement | Priority | RICE Score (if applicable) |
|---|---|---|
| FR-1: User login | Must | 4.2 |
| FR-2: Export CSV | Could | 1.1 |

## 5. Functional Requirements

### FR-1: <Short name>
- **Priority:** MoSCoW (M/S/C/W) or RICE: <score>
- **Description:** <what the system must do>
- **Acceptance Criteria:**
  - Given <context>, When <action>, Then <result>
  - Given <context>, When <action>, Then <result>
- **Dependencies:** <FR-IDs this depends on>

### FR-2: <Short name>
_(same structure)_

## 6. Non-Functional Requirements

### NFR-1: <Category> (e.g., Performance)
- **Priority:** MoSCoW
- **Description:** <constraint or quality attribute>
- **Measured by:** <metric, threshold>

### NFR-2: <Category> (e.g., Security)
_(same structure)_

## 7. Out of Scope (Explicit)

- <Feature or concern explicitly deferred>
- <Feature that someone might expect but is not planned>

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| <risk> | H/M/L | H/M/L | <plan> |

## 9. Open Questions

| # | Question | Owner | Status |
|---|---|---|---|
| 1 | <question> | <name> | open/resolved |

## 10. Assumptions

- <Assumption: ...>
- <Assumption: ...>

## 11. Acceptance Criteria Summary

- [ ] All must-haves have passing criteria
- [ ] Edge cases documented (empty state, error state, permission denied)
- [ ] Performance envelope defined

## 12. Recommended First Slice

<Smallest testable step — scoped to one implementation loop>

## 13. Completion Checklist

- [ ] All sections filled
- [ ] Each AC in Given/When/Then format
- [ ] Assumptions explicitly labelled
- [ ] At least one acceptance criterion per must-have
- [ ] First slice is implementable in one loop
- [ ] Prioritization framework chosen and documented
- [ ] Domain question bank consulted (relevant domains)

## 14. Appendix

- Related docs: <links>
- Glossary: <domain terms>
- Domain questions reviewed: <list of domains consulted>

---

## Integration with AgentKore Planning Pipeline

| Step | Artifact | Skill |
|---|---|---|
| Elicitation | This PRD | `ak-elicit` (optional-skill) |
| Architecture Review | Tradeoff + risk register | `ak-party` (optional-skill) |
| Story Slicing | Story map | `story-slicing` (optional-skill) |
| Task Breakdown | Task cards | `prd-to-tasks` (optional-skill) |
| Execution | Tickets/commits | `task-executor` (core) |

_AgentKore planning pipeline traceability: FR-ID → Story-ID → Task-ID chain is documented in `references/traceability-chain.md`._
