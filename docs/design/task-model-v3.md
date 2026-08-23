# Task Model v3 — Orchestrator-Intelligence / Worker-Execution

**Date:** 2026-08-24 · **Author:** Esther · **Status:** Draft v1
**Stakeholders:** Luke (fleet owner), all 6 agents
**Supersedes:** role-locked execution (agents execute only "their" domain)

---

## 1. Why this exists (Luke directive 2026-08-24)

> "I'd like Esther/Moses (orchestrators) to be able to do all the heavy
> lifting for intelligence, and all the other agents to be able to execute on
> almost any slice or task. We still need to update the system to accommodate
> this and intelligently complete tasks properly. I'd like: 1) visibility for
> the tasks easily viewable and understandable, 2) agents working truly
> autonomously and efficiently — building, researching, refactoring."

**The current model is role-locked and push-only:**
- Each agent has a fixed role (Titus=build, Joseph=infra, Gisu=comms…)
- Tasks arrive via bus commands and the *receiving* agent executes them
- No worker can autonomously claim a pending slice

**The target model:**
- **Orchestrators (Esther/Moses) = the intelligence layer** — strategy,
  decomposition, research synthesis, planning, verification, case-study authoring
- **Every other agent = a general worker** — can execute *any* slice (build,
  refactor, research, docs, infra) regardless of historical role
- **Pull-claim for routine work + orchestrator dispatch for urgent/prioritized**
- **Visibility: daily digest + on-demand board query**

---

## 2. The model

### 2.1 Role simplification

| Tier | Agents | Responsibilities |
|---|---|---|
| **Orchestrator (intelligence)** | Esther, Moses | Decompose stories → slices; assign priority; dispatch urgent work; verify completions; research/strategy/QA/case-study authoring; fleet governance |
| **Worker (execution)** | Titus, Joseph, Kustos, Gisu (+ orchestrators when idle) | Claim pending slices from the queue; execute; report done; any domain |

**Capability principle:** a worker may execute anything in its toolset. If a
slice needs a tool it lacks (e.g. cron tooling is orchestrator-only), the
slice's plan says so and the worker returns it with a note — no fake progress.

### 2.2 Two work paths

**Path A — Pull-claim (routine):**
```
Orchestrator decomposes story → slices land pending (with plan field)
Worker polls task_pending → sees claimable slice → CLAIM (atomic:
pending→in_progress, assignee=<me>, single transaction)
Worker executes → reports result → orchestrator verifies → completed
```

**Path B — Dispatch (urgent/prioritized):**
```
Orchestrator creates slice with priority 2-3 + explicit assignee
→ notifies the worker via bus TASK_REQUEST (existing path)
Worker executes → reports → verified → completed
```

### 2.3 Intelligent completion (the "properly" part)

- **Plan field on slices:** orchestrator writes discrete steps into each
  slice (checklist) so a worker executes, not improvises strategy.
- **Verification loop:** worker's "done" is not trusted — orchestrator
  verifies against the plan (test output, evidence) then marks completed.
  Failed verification → re-slice with the gap named (never silent redo).
- **Re-slicing:** a slice found too big mid-execution → worker returns it,
  orchestrator splits into 2+ slices, re-queues. No half-done lumps.
- **Capability-aware routing:** orchestrator knows each worker's toolset
  (from the agent registry) and dispatches to workers that can actually
  execute; unknown tool needs → orchestrator records the gap in the slice.

### 2.4 Compete mode — parallel candidates, best solution wins (Luke OOB 2026-08-24)

> "In some circumstances, I'd like agents to try 2 different ways and compete
> with one another — best evaluated solution/development wins. There must be
> a process that does this, right?"

**Yes — and the fleet already has the evaluation half.** The pattern is
**parallel candidate generation + deterministic judging**, never "pick the
prettier answer."

**Existing fleet tooling that makes this possible:**
- `delegate_task` (parallel batch) — spawn 2+ subagents, each with a
  *different approach* to the same slice, isolated contexts
- `adversarial-verifier` — attempts to break each candidate; the one that
  survives with no critical/high findings wins
- `golden-parity-harness` — known-answer parity: each candidate must match
  the golden output; winner = best parity
- `llm-judge-scorer` — LLM-as-judge *trace quality* scoring (used for
  evaluating conversation quality, NOT for solution judgment)
- `eval-harness` — systematic capability evaluation

**The compete protocol (deterministic, consistent with O4 rules):**

```
1. Orchestrator marks slice `compete=true` + writes the ACCEPTANCE CRITERIA
   (tests the winner must pass) and the APPROACH SPECS (2+ distinct
   approaches, e.g. "path A: build it; path B: buy/integrate").
2. Orchestrator spawns N subagents in parallel — each gets the same slice +
   acceptance criteria but a DIFFERENT approach spec (isolated contexts).
3. Each candidate runs the acceptance tests itself and reports:
   pass/fail per criterion + evidence (test output, not prose).
4. Orchestrator (or the verifier) runs adversarial-verify on each candidate
   — any critical/high finding disqualifies.
5. Winner = best score on: acceptance criteria met (mandatory) → fewest
   adversarial findings → lowest cost/tokens (tiebreak) → fastest.
6. Winner's solution is merged; losers' diffs are archived with a one-line
   "why not" (they become the next iteration's reference).
7. The whole compete is logged as a task event (approach A vs B, scores,
   winner) — the audit trail IS the case-study material.
```

**Cost guard:** compete mode is opt-in per slice (`compete=true` flag) and
orchestrator-authorized — it costs 2-3× a single attempt, so it's reserved
for slices where the approach choice genuinely matters (architecture forks,
make-vs-buy, refactor-vs-rewrite). Routine slices run single-track.

**The honest rule:** competing candidates must be judged by *executable
acceptance criteria + adversarial findings + measured cost* — never by "which
one sounds better." That's the difference between engineering competition and
a vibes contest.

---

## 3. Schema changes (v009 — minimal)

### 3.1 `claim` write path (the security-critical piece)

**Constraint:** current RLS = "workers stay read-only on fleet rows." The
claim must be a **narrow, deliberate write**, not a blanket grant.

```
CREATE OR REPLACE FUNCTION tasks.claim_slice(p_id UUID, p_assignee TEXT)
RETURNS boolean AS $$
  -- Atomic: pending → in_progress + assignee, only if still pending
  -- SECURITY INVOKER: RLS applies (caller must be a known agent)
  -- Guard: p_assignee must equal profile_of(current_user) — an agent can
  --        only claim FOR ITSELF, never assign work to others.
  UPDATE tasks.tasks
     SET status = 'in_progress',
         assignee = p_assignee,
         status_changed_at = now()
   WHERE id = p_id
     AND status = 'pending'
     AND p_assignee = tasks.profile_of(current_user)
  RETURNING true;
$$ LANGUAGE plpgsql;
```

- Atomicity: the `WHERE status='pending'` + single UPDATE = no double-claim
- Least privilege: an agent claims only for itself; no cross-assignment
- Events: check_transition fires on the status change → Telegram notify
  (existing lifecycle machinery reused)

### 3.2 `plan` column (v009)

```
ALTER TABLE tasks.tasks ADD COLUMN plan TEXT;
-- Orchestrator-written checklist; worker executes; verifier checks against it
```

### 3.3 `assignee` becomes authoritative

Currently metadata-only. With claim + dispatch both setting it, `assignee`
becomes the "who owns this now" field. No schema change needed — the
semantic shift is in the CLI/MCP.

---

## 4. Tool surface changes

### 4.1 task-db.py / task-mcp.py additions

| Command | Effect |
|---|---|
| `claim <id>` | Atomic pending→in_progress+assignee=me (calls claim_slice). Refuses if already claimed. |
| `unclaim <id>` | Return to pending with reason (mid-task blocker, tool gap). in_progress→pending, clear assignee. |
| `list --claimable` | Show pending slices with no assignee + their plans (the queue view). |
| `list --board` | One-view board: pending/in_progress/completed counts + per-agent in_progress. |
| `report <id> --result <evidence>` | Worker's completion claim with evidence — sets a 'ready_for_review' marker (pending_review status or flag), NOT completed. |
| `verify <id>` | Orchestrator-only: marks completed after checking evidence (verify is orchestrator-privileged). |

**New status (v009):** `review` (worker-done-awaiting-verification). The
transition matrix gains: pending→in_progress (claim/dispatch),
in_progress→pending (unclaim), in_progress→review (report),
review→completed (verify), review→in_progress (verify-failed, reason).

### 4.2 Visibility

**Daily digest (zero-token no_agent cron, 08:30 KST):**
```
📋 Task Board — YYYY-MM-DD
Open: 12 (5 pending · 4 in_progress · 3 review)
In progress: Esther:1 · Titus:2 · Joseph:1
Pending (claimable): 5 — top 3 by priority
In review: 3 — oldest first
Stale: 1 flagged (>24h in_progress, manual task)
```

**On-demand query:** `TASK_REQUEST` via bus with `action=board` → any agent
can answer "what's open" — or a Telegram bot command mapping to the same
digest script.

---

## 5. Autonomy loop (how it runs without handholding)

1. **Orchestrator morning pass (07:00 cron):** decompose new stories →
   slices with plans → priority. Dispatch urgent (Path B).
2. **Workers poll (per-session restore + periodic check):** `task_pending`
   → claim highest-priority claimable slice → execute → report → next.
3. **Orchestrator verification pass (evening):** verify all `review` slices
   → completed or re-slice. Close the loop daily.
4. **Stale handling:** existing sweep (1h bus / 24h manual) + new `review`
   stale (>24h in review → re-flag orchestrator).

**Efficiency rule (from the cost work):** workers batch — claim one slice,
execute fully, report once. No thrash loops, no re-derivation (SOUL #4).

---

## 6. Agent behavioral updates (SOUL/AGENTS)

- SOUL local principles gain: "Worker mode — claim, execute, report, verify;
  never improvise strategy on a slice with a plan; return unclaimable work
  with the tool gap named."
- Orchestrator SOUL gains: "Intelligence layer — decompose before dispatch;
  verify every completion against the plan; never trust a self-reported done."
- AGENTS.md execution-contract gains the claim/verify protocol.

---

## 7. Implementation slices (task story: task-model-v3)

| Slice | Scope | Owner |
|---|---|---|
| T1 | Schema v009: plan column, review status, claim_slice function + tests | Esther |
| T2 | task-db.py + task-mcp.py: claim/unclaim/list-claimable/list-board/report/verify + tests | Esther |
| T3 | Transition matrix + stale-sweep for review status | Esther |
| T4 | Daily board digest cron (no_agent, zero-token) + Telegram bot command | Esther |
| T5 | Orchestrator morning/evening passes (cron prompts) | Esther |
| T6 | SOUL/AGENTS behavioral updates + fleet deploy | Esther |
| T7 | Compete mode: `compete=true` flag, parallel-candidate runner (delegate_task + adversarial-verify judge), result logging | Esther |
| T8 | Dogfood: run a real engagement (The Client Brand) through the new model; measure | Esther |

## 8. Explicit non-goals

- No new transport (task rows stay per-host until the git-backed transport
  roadmap — same as today; claim works on the local DB).
- No LLM-judged task classification (deterministic claim/verify only —
  consistent with O4 autonomy rules).
- No auto-completion (verify is always an orchestrator action).

---

## 9. Acceptance criteria

- [ ] Worker can `claim` a pending slice atomically; double-claim fails
- [ ] Worker can `unclaim` with reason; slice returns to pending
- [ ] `report` sets review; only orchestrator `verify` → completed
- [ ] Daily board digest delivers to Telegram (zero-token, coverage-aware)
- [ ] On-demand board query works via bus
- [ ] Orchestrator decompose→dispatch→verify loop runs a full The Client Brand slice end-to-end
- [ ] Compete mode: 2 candidates on one slice → deterministic winner by AC + adversarial findings; loser archived with reason
- [ ] Doctor green; transition matrix tests pass
