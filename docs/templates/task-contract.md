# Task Contract Template

**Purpose:** Define success criteria, constraints, and checkpoints BEFORE execution begins. This prevents scope creep, silent failures, and verification gaps.

**When to use:** Any task with 3+ steps, any code change, any configuration modification, any multi-step workflow.

---

## Task Contract

**Task ID:** `[auto-generated: YYYYMMDD-HHMMSS]`

**Goal:** [Single sentence — what "done" looks like]

**Success Criteria:**
- [ ] [Verifiable outcome 1]
- [ ] [Verifiable outcome 2]
- [ ] [Verifiable outcome 3]

**Constraints:**
| Type | Specification |
|------|---------------|
| Files I may touch | `[list or pattern]` |
| Files I must NOT touch | `[list or pattern]` |
| Patterns to follow | `[link to convention or skill]` |
| Patterns to avoid | `[known anti-patterns]` |

**Assumptions:**
1. [Assumption 1 — verify before proceeding]
2. [Assumption 2 — verify before proceeding]

**Checkpoints:**
| Step | Verification Required Before Proceeding |
|------|----------------------------------------|
| 1 | [ ] [specific check] |
| 2 | [ ] [specific check] |
| 3 | [ ] [specific check] |

**Conflict Detection:**
- [ ] Multiple patterns detected in codebase? → Surface conflict, await pattern choice
- [ ] Ambiguous requirements? → Ask clarifying questions before coding
- [ ] Missing context? → Read related files before writing

**Rollback Plan:**
If verification fails at any checkpoint:
1. [Rollback action 1]
2. [Rollback action 2]
3. [Notify user with specific failure details]

---

## Post-Task Verification

**Completed:** `[timestamp]`

**Actual files touched:**
- `[list]`

**Success criteria met:**
- [ ] Criterion 1 — `[evidence: test output, screenshot, log]`
- [ ] Criterion 2 — `[evidence]`
- [ ] Criterion 3 — `[evidence]`

**Deviations from plan:**
- `[any changes to original contract and why]`

**Lessons learned:**
- `[what to capture for future tasks]`

---

## Example: Fix Authentication Bug

**Goal:** Fix 401 errors on /api/users endpoint when valid token provided.

**Success Criteria:**
- [ ] All existing tests pass
- [ ] New test for valid token + 401 scenario passes
- [ ] Manual curl test returns 200 with valid token
- [ ] No regressions in /api/admin or /api/settings endpoints

**Constraints:**
| Type | Specification |
|------|---------------|
| Files I may touch | `ops/auth/middleware.py`, `tests/test_auth.py` |
| Files I must NOT touch | `ops/auth/token.py` (being refactored in parallel branch) |
| Patterns to follow | `skills/software-development/change-test-loop/SKILL.md` |
| Patterns to avoid | Do not add new dependencies, do not modify config schema |

**Assumptions:**
1. Token validation logic is in `middleware.py` — verify via grep before editing
2. Test suite uses pytest — verify test command before running

**Checkpoints:**
| Step | Verification Required Before Proceeding |
|------|----------------------------------------|
| 1 | [ ] Confirmed token validation location via `grep -r "validate_token"` |
| 2 | [ ] Existing tests pass before making changes |
| 3 | [ ] New test fails before fix (red phase) |
| 4 | [ ] New test passes after fix (green phase) |
| 5 | [ ] All existing tests still pass (regression check) |

**Conflict Detection:**
- [ ] Found both class-based and function-based auth patterns → Surface conflict, ask which to follow
- [ ] Token validation logic split across 3 files → Document finding, ask if refactor is in scope

---

## Usage

1. **Copy this template** to `.hermes-cortex/sessions/task-contract-[timestamp].md`
2. **Fill in BEFORE starting work** — the discipline is in the upfront thinking
3. **Reference in session state** — add contract path to `current.md`
4. **Update post-task** — fill verification section with evidence
5. **Archive** — move to `.hermes-cortex/sessions/archive/` with session

**For cron-driven tasks:** Contract is auto-generated in session state by `update-session-state.sh`

**For delegated subagents:** Contract is passed in `context` field, subagent fills verification section
