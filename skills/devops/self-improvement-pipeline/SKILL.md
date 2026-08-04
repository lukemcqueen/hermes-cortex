---
name: self-improvement-pipeline
description: "Transform user corrections and system warnings into permanent guardrails. Covers zero-ask discipline, doctor-warnings-as-required, session-end self-audit, dogfooding, and the full correction-to-guardrail feedback loop."
version: 1.0.0
category: devops
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
---

# Self-Improvement Pipeline — Correction to Guardrail

> Every user correction is a permanent improvement waiting to happen. The pipeline from "user says stop" to "system enforces automatically" has 4 stages: **detect → guardrail → codify → verify**.

## Stage 1: Detect — Catch the Signal

User corrections come in two forms:

| Signal | Example | Action |
|--------|---------|--------|
| **Direct correction** | "Don't ask me, just fix it" | Add guardrail immediately |
| **Verbal frustration** | "This is not advisory", "CODIFY THIS PLEASE" | Add guardrail immediately |
| **Repeat violation** | Same correction twice | Structural guardrail (add to SOUL.md or governing skill) |
| **Process frustration** | "Don't do that!" when starting governance ceremony for a quick iterative fix the user is guiding | Skip begin_change/todo ceremony during rapid user-guided iteration. Do the work directly — don't set up infrastructure. Governance is for structured code changes, not debugging loops. |
| **System signal** | Doctor ⚠️ WARNING that keeps firing | Investigate root cause, don't dismiss |

**Key insight:** If the user's correction starts with "you always do X" or "stop asking" or "this is not Y" — it's a Stage 1 signal. Stop what you're doing and add the guardrail.

## Stage 2: Guardrail — Capture the Fix Immediately

When a correction is identified, the guardrail must be added **before continuing the current task**, not "next session" or "later":

1. Determine WHERE the guardrail goes:
   - **Behavior / tone / style** → SOUL.md Principle (in Tier 3 or Tier 5)
   - **Workflow / procedure** → applicable skill (update the skill that governs this task)
   - **System check / enforcement** → doctor or pre-commit hook
   - **Fleet-wide rule** → AGENTS.md or install script

2. Write the guardrail so the violation is IMPOSSIBLE, not just "try harder":
   - Textual principle: "Never ask permission" — weak (relies on willpower)
   - Concrete test: "Before any 'want me to' question forms, redirect to begin_change" — stronger
   - Structural: "Final Directive hard-codes the session-start ritual" — strongest

3. The user's exact words make the best guardrails. Quote them directly.

## Stage 3: Codify — Commit and Sync

A guardrail in your local SOUL.md helps only you. A guardrail in the repo helps the fleet:

1. Update the local copy (`~/.hermes/SOUL.md`)
2. Copy to the repo profile (`profiles/personal/agent-profiles/moses/SOUL.md`)
3. Update the relevant skill (repo copy under `skills/<category>/<name>/`)
4. Commit and push

**Dogfooding rule:** If the guardrail involves a pipeline other agents will use, test it on yourself first. Send a test message. Verify consumption. Only then push.

## Stage 4: Verify — Did It Work?

After the guardrail is in place:

1. Run the doctor to confirm no warnings that triggered the correction
2. Run the `orch-skill-lifecycle` pipeline (daily 04:00 KST) which now scans session transcripts for unguarded violations
3. Next time the trigger pattern occurs, the guardrail should fire before the user corrects you

**Session-end self-audit:** Before closing any governance cycle, pause and audit: did I violate any principle this session? If yes, the guardrail should be in Stage 2 already. If not, why not?

## Session-End Review — Active Skill Curation After Every Session

A session where you review the conversation and find nothing to update is a missed learning opportunity, not a neutral outcome. Every session with meaningful interaction should produce at least one skill update, even if small.

**Trigger:** Any of these signals fires the review:
- User gives a style/format/workflow correction
- User says "review the conversation and update skills"
- A non-trivial technique, fix, workaround, or tool-usage pattern emerged
- A loaded skill was wrong, missing a step, or outdated
- Session-end self-audit found no guardrails added

**Procedure — Session-End Skill Curation:**

1. **Scan for correction signals** — Look back through the conversation for:
   - Style/tone/format corrections ("stop doing X", "too verbose", "don't format like this", "just give me the answer", "you always do Y")
   - Workflow/approach corrections ("don't ask, just fix", "wrong order", "skip that step")
   - Technique discoveries (non-trivial debugging path, tool-usage pattern, workaround)
   - Skill gaps (a skill was loaded and found missing steps or wrong info)

2. **Route the update by signal type:**
   - **Style/format preference** → belongs in the SKILL.md body of the skill that governs that task, NOT just in memory. Memory captures "who the user is"; skills capture "how to do this class of task."
   - **Workflow correction** → add as pitfall or explicit step in the governing skill
   - **Technique discovery** → add as section or reference file under the relevant umbrella
   - **Stale skill** → patch it NOW with the missing steps

3. **Apply using the correct tier:**
   - **Tier 1:** Patch a currently-loaded skill (the skill that was in play when the correction happened)
   - **Tier 2:** Patch an existing umbrella skill identified by `skills_list()`
   - **Tier 3:** Add a support file (`references/`, `templates/`, `scripts/`) under an existing umbrella
   - **Tier 4:** Create a new class-level umbrella when no existing skill covers the class

4. **Naming rule** — New skills must be at the CLASS level. A name that only makes sense for today's task is wrong. If the only fitting name is "fix-X-20260723", fall back to Tier 3 (add a reference file) or Tier 2 (extend an existing umbrella).

5. **Protected skills check** — Before attempting to patch, call `skill_view(name)` and check if `created_by` is `None` in the YAML frontmatter. If the skill record shows `created_by=None`, it is a manually-authored/bundled skill and `skill_manage(action='patch')` will be rejected with \"manually authored skills are off-limits.\" Fall back to:
   - Tier 3: Add a reference file under an editable umbrella skill
   - Tier 2: Extend an existing editable umbrella that covers the same class
   - Create a new skill if no umbrella exists
   Do NOT retry the patch on the protected skill — it will fail the same way.

6. **Session signal examples (2026-07-23):** Signals that fired this session:
   - "No. Refactor. Do it right" → workflow correction → updated **repo-health-review** skill with full-refactor pattern
   - "Make agent know what to clean up" → asked for structural guardrail → added `clean_stale_deploys()` + doctor `check_stale_deploys()`
   - "Can we have install/update automatically run doctor" → system integration → added auto-doctor to install.sh and cortex-update.sh
   - "Make it modular" → code architecture → split doctor into 8-module `cortex_doctor/` package
   - Protected `change-checklist` can't be edited → updated `repo-health-review` instead (same task class, editable skill)

**What NOT to capture:**
- Environment-dependent failures (missing binaries, fresh-install paths) — user can fix these
- Negative claims about tools ("browser tools don't work") — hardens into false refusals months later
- One-off task narratives — not a class of work
- Transient errors that resolved — capture the retry pattern instead

**"Nothing to save" is a real option but NOT the default.** Say "Nothing to save" only when the session had zero corrections, zero new techniques, and zero skill gaps discovered.

## Anti-Pattern: Suppressing Instead of Fixing

**The mistake:** Doctor shows ⚠️ "SOUL.md sync" warning. Instead of syncing the file, agent uses `touch -r` (timestamp mtime hack) to silence the warning without actually fixing it. User catches this and says: *"Are you just suppressing visibility of the problem? I don't want you to suppress, I want you to sync/fix."*

**The rule:** Never silence a doctor warning with a timestamp hack. Always fix the root cause:
- Warning "SOUL.md is stale" → actual copy/merge from template
- Warning "skills.yaml template is newer" → actual `diff -q` + content-level copy
- Warning "AGENTS.md is stale" → run cortex-update.sh which does content-based sync

**Checklist:**
1. Read the doctor message — what exactly is stale/missing?
2. Fix the actual content — copy, merge, or deploy the right file
3. Verify — re-run doctor and confirm ⚠️ is gone
4. Make it permanent — if cortex-update.sh doesn't already auto-sync this file, add it

**The litmus test:** If the user saw your fix, would they say "you fixed it" or "you hid it"? If the latter, your fix is wrong.

## Anti-Pattern: "task-start loads the always skills" is False

The most common trust violation: agent calls skill_view(task-start), then immediately calls begin_change, believing the always skills are loaded. The old session-start ritual said "The task-start skill loads survey-before-action, agent-flow, reasoning-patterns..." This is false. task-start describes the sequence but does NOT execute it. Each always skill requires its own separate skill_view() call.

Structural fix (2026-07-23): SOUL.md MANDATORY SESSION-START RITUAL rewritten as numbered tool calls 1-8. begin_change is step 8, not step 2. The numbered list replaces the false equivalence ("task-start loads these") with explicit one-by-one loading.

Checklist before calling begin_change:
- Have I called skill_view() on ALL eight always skills?
- Or did I only call task-start and assume the rest are loaded?
- If yes to the second question: STOP. Load each skill separately.

## Tenet 9: Fix Root Causes, Not Symptoms

When the user says "fix this" or "address the issues," identify whether you're treating a **symptom** or the **root cause**. A symptom fix removes the visible problem but leaves the underlying design flaw. A root-cause fix changes the system so the problem can't recur.

**The symptom-trap pattern from this session (2026-07-21):**

> **Problem:** Skill reports stacking in `inbox_orchestrator`, blocking EXEC commands. Handler took 40+ min per command.
>
> **My symptom fix:** "Idempotency loop bug — archive on skip." Loop stops, but core problem remains.
>
> **User's correction:** "You have to actually address the issues. The bus and all messages are your responsibility."
>
> **Root cause:** Moses shouldn't run `agent-message-handler` at all. Orchestrator handles inbox in-session (tools) and out-of-session (`cortex-bus-*` LLM crons). Handler is for fleet agents.
>
> **True fix:** Remove handler cron from orchestrator.

**The litmus test:** "If I fix this, will the same class of problem recur tomorrow with a different message type, queue, or agent?" If yes, find the architectural reason and fix THAT.

## Tenet 10: Prove the Full Orchestration Cycle — or It Didn't Happen

When testing a bus or inter-agent feature, the test is incomplete until you prove the **full send→process→respond→read cycle**.

| What I tested first | What Luke wanted |
|---|---|
| "The handler ran the command" | "Prove you can read the response from your own inbox" |
| "Telegram API returned ok" | "Prove the notification arrived in DM" |
| "I sent EXEC to a fleet agent" | "Test on your own system FIRST" |

**6 checkpoints — all must be verified:**
1. **Send** → message exists in target queue (pending, has subject/correlation_id)
2. **Consume** → message transitions pending → processing → archived
3. **Process** → command output captured in handler logs
4. **Respond** → EXEC_RESULT appears in inbox_moses with matching correlation_id
5. **Read** → orchestrator queries its inbox, extracts structured result (exit_code, stdout, success)
6. **User-verify** → Telegram notification content matches what happened

## The 10 Tenets

1. **Zero-ask litmus:** Before forming any "want me to" / "should I" / "do you want" question: if the answer is yes, don't ask — execute. The question IS the action.
2. **Doctor warnings are blocking failures — NOT optional:** Every ⚠️ or ❌ in the doctor output must be RESOLVED before end_change(). Never call a warning "advisory" or dismiss it without resolution. The user's exact words: "You need to make this mandatory, not optional." A doctor warning you leave unfixed is a trust violation. If you suppress it with a timestamp hack (`touch -r`) instead of fixing the content, the user will catch this and escalate.
3. **Session-end self-audit:** Before end_change, check for violations and add guardrails.
4. **Dogfood before deploy:** If other agents use it, test it on yourself first.
5. **User quotes are guardrails:** The user's exact words ("I always want you to fix things you need to fix. You never need to ask me.") should be embedded verbatim.
6. **Integration completeness:** When told to "integrate X like Y" or "wire X everywhere Y is referenced", map ALL touchpoints before starting — `search_files()` for every file referencing Y. Verify the count: N files referencing Y → N files must also reference X. Partial integration (80% done, 5 files left) is not done.

**Real-world example (2026-07-21):** User said "wire cortex-preflight as deeply as survey-before-action." First pass got ~8/14 touchpoints. Missed AGENTS.md, change-checklist, doctor, and several other files. Only when user said "be thorough" and "you need to make this mandatory" did every file get patched. The correction: map ALL touchpoints before the first patch, not after.

8. **Ordering is structural: skills before lock.** The session-start ritual is not a suggestion — it is a numbered sequence. begin_change must be the LAST step, not the second one. Every always skill must be loaded via its own skill_view() call. The belief that "task-start loaded these" is the most common trust violation.

**Checklist before begin_change:**
- Eight skill_view() calls completed: agent-flow, reasoning-patterns, reflexion-check, change-checklist, survey-before-action, cortex-preflight, agent-contract
- task-start was called first, then each skill was loaded separately
- No shortcut: "I already called task-start, that covers it" is always wrong

7. **Template is the single source of truth:** When you modify a deployed copy (agent profile, config, or SOUL.md), the canonical template in `docs/templates/` MUST be updated too. Deployed copies sync FROM the template. Other agents copy the template — if it's stale, they get wrong instructions. The doctor's SOUL.md/AGENTS.md sync checks enforce this: if the template has content the deployed copy doesn't, the doctor FAILS.

**Checklist before end_change:**
- [ ] Did I change something that lives in `docs/templates/`? → Update the template
- [ ] Did I change a template? → Sync runtime: `cp docs/templates/XXX ~/.hermes/XXX`
- [ ] Did I change an agent profile? → Is this change structural (goes in template) or agent-specific?
- [ ] Run doctor — SOUL.md sync and AGENTS.md sync must both PASS

**Real-world warning (2026-07-21):** User asked "Why didn't you update the SOUL template?" after Moses updated the moses profile without updating `docs/templates/SOUL.md`. The template is the canonical source of truth — it must stay in sync.

8. **Fix completely the first time — don't make the user escalate:** When the user says "fix this" or "resolve this warning," do it fully on the first pass. A partial fix (silencing the symptom without fixing the root cause) forces the user to escalate from "fix this" → "no, really fix it" → "this is costing wrong turns." Each escalation wastes trust. Complete the full cycle: identify → fix root cause → verify → make permanent — all before reporting done.

**The escalation pattern to avoid:**
1. User says: "Fix the doctor warnings"
2. Agent does a partial fix (copies one file, leaves the root cause)
3. User says: "No, make it mandatory — not optional"
4. Agent does a more permanent fix (adds to update script, but uses mtime hack)
5. User says: "Are you suppressing? I want sync/fix"
6. Agent finally does the real fix (content-based sync, pre-commit enforcement)
→ All 6 steps should have happened in step 2.

**Guardrail:** When the user says "fix X", before reporting done ask: "Is the root cause fixed? Is it permanent? Will it happen again? If the user looked at my fix, would they say 'fixed' or 'band-aid'?"

## Tenet 11: Survey Before Creation — Extend Existing Before Creating New

**The mistake (2026-07-23):** Agent created 2 new `local-*` crons (`local-cron-cost-report`, `local-trace-quality-watchdog`) without surveying existing cron infrastructure. A single existing cron — `agent-scoring-activity-watchdog` — could have absorbed both features with ~50 lines of code.

**User's exact words:** *"Why didn't you survey before action? You have tons of crons to choose from to improve/add to, why make more? I need you to make survey before action PERMANENT."*

**The rule:** Before creating any new cron, script, mechanism, or file:

1. `search_files()` with 3+ different terms covering the problem domain
2. `cronjob(action='list')` — check ALL existing crons for ones at similar cadence or covering the same domain
3. `skills_list()` for the relevant category — check for existing skills that could absorb the work
4. **If any existing system can absorb the new capability: EXTEND IT.** Do not create a parallel system.
5. Document the survey result in your feedback note: *"Surveyed: found X, chose to extend"* or *"Surveyed: nothing matched, creating new"*

**Rationale:** Every new file compounds debt — review time, merge conflicts, doc drift, deploy registrations, future confusion. Extending an existing system costs one patch. Creating a new system costs 5+ touchpoints plus ongoing maintenance. The user will notice and correct you.

**Real-world test:** Before creating any new cron, ask:
- Is there an existing cron that runs at a similar time?
- Does an existing script in `ops/scripts/` handle the same domain?
- Does an existing skill cover this and just needs a new section?
- Is this really a new class of work, or am I too lazy to find the existing system?

**Guardrail:** "A new creation when an existing extension was possible is a structural violation." Record your survey findings in the feedback_accept note.

## References

- Session lesson reference: `references/2026-07-21-session-lessons.md` (5 corrections captured, including zero-ask, SOUL sync, dogfooding, codify-please, and todo persistence)
- Session lesson reference 2: `references/2026-07-21b-session-lessons.md` (template sync, suppress vs fix, integration completeness)
- Session lesson reference 3: `references/2026-07-23-session-lessons.md` (always-skills ordering enforcement, Langfuse observability pipeline, config.yaml protection, Langfuse API limitations)
- Session lesson reference 4: `references/2026-07-23b-session-lessons.md` (survey-before-creation enforcement, extend-before-create pattern, propagate to all agents, cost tracking patches, fleet data pipeline)
- Session lesson reference 5: `references/session-reengagement-bridge.md` (interrupted session re-engagement, "what's next?" status-inquiry pattern, health-scan fallback protocol)
- Doctor severity philosophy: `references/doctor-severity-philosophy.md` (2026-07-25: SOUL.md/AGENTS.md must FAIL, not WARN — identity documents are non-negotiable)
- Integration completeness: `references/integration-completeness-2026-07-21.md` (map all touchpoints before starting)
- Multi-source research synthesis: `references/research-synthesis.md` (scan companion repos before writing PRDs; failure: 2026-07-23, missed 5 companion repos)
- Post-change verification: `references/post-change-verification.md` (doctor warnings are blocking failures, deployment chain checklist)
- SOUL.md Principle 12a-d (Zero-Ask Litmus)
- SOUL.md Principle 14 (Dogfooding)
- SOUL.md Principle 37 (Cross-Session Todo Persistence — file-level mechanism, not just tool)
- SOUL.md Final Directive (Mandatory Session-Start)
- cortex-doctor.py check_soul_sync() (content-based verification)
- orch-skill-lifecycle Phase 1 step 8 (session compliance audit)
