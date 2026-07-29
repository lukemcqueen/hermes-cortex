---
name: fix-without-asking
description: |-
  When you discover an issue mid-task, the correct response is begin_change — not a question.
  Covers the litmus test, the failure pattern, and the concrete "never ask" guardrail.
  Triggers: "should I fix", "want me to", discovered anything wrong mid-task, user says "fix it"
version: 1.2.0
author: Hermes Cortex / Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [execution, discipline, fix-first, obvious-fixes]
---

# Fix Without Asking — Discovered-Issue Protocol

## Core Principle

**The question IS the action.** When you discover an issue and the fix path is clear, `begin_change` is the first tool call — not a clarifying question. A question means you already analyzed enough to know there's work to do. The wasted round-trip is:

```
identify → summarize → ask → wait → fix → report
```

Eliminate the `ask → wait` segment. Fix first, report after.

## When This Applies

This skill triggers when you discover ANY of these mid-task:

- A broken file, config, or script you did not cause but can fix
- A stale reference or dead registration
- A doctor warning that needs remediation
- A cron job in error state
- A missing uninstall-array entry
- Any pre-existing issue that crossed your path

**If the fix path is clear and the fix is safe (no data loss, no privilege escalation, no security risk), execute it immediately.** Do not escalate. Do not ask. Do not add "want me to also X?" to your summary.

## The Zero-Ask Litmus Test

Before forming any question that starts with:

- "Want me to..."
- "Should I..."
- "Do you want..."
- "Would you like me to..."

Ask yourself one question: **do I already know the answer?** If the answer is "yes, fix it" — the question should not leave your context. Replace it with `begin_change`.

## User Directive (Codified)

> *"I always want you to fix things you need to fix. You never need to ask me."*

If you catch yourself phrasing a question about whether to make an obvious fix, stop mid-sentence and run the fix instead. A question about an obvious fix is a trust violation in progress.

## The Two Safe Exceptions

Only ask when:

1. **Destructive operation** — data loss, irreversible config change, privilege escalation, security boundary crossing
2. **Genuine ambiguity** — the correct fix is not clear and you need clarification of intent
3. **Pre-defined slice boundary with uncertain next step** — only when you have NOT been told to continue without asking. If the user said "proceed, continue without asking" or equivalent, this exception does not apply — see Continuation Signal below.

For everything else, `begin_change` is your first verb.

## Scope Boundary — The Task IS the Task

A fix-without-asking opportunity is NOT an invitation to redesign the system. When the user gives a precise directive, that IS the task. Discovering a tangential issue (doctor check format mismatch, config naming convention, unrelated script bug) while executing the directive does NOT mean you should silently fix it as part of the same change.

**The test:** does fixing this issue change the behavior of a component the user did not ask about, in a way they would notice on next use? If yes, it's scope creep.

**Failure pattern from session 2026-07-24:**
```
User: "Copy the repo profile!"
Agent: copies profile → then notices doctor SOUL.md check format is wrong
       → modifies _extract_soul_markers and check_soul_sync without being asked
       → user: "What are you doing?"
```

The doctor fix was **correct** (the format handling was genuinely broken), but it was **out of scope** for a "copy the repo profile" task. The right approach:

1. Execute the directive precisely — copy the file, verify it works
2. If you discover a separate systemic issue, note it in your summary as a finding: "Also noticed: the doctor's SOUL.md marker extraction doesn't handle the new ### N. Title format — can fix separately if you want."
3. Do NOT silently merge it into the current task

**The revert trap (also from 2026-07-24):**
```
User: "What are you doing?"
Agent: reverts the (correct) doctor fix → user: "Do not do that!"
```

When the user flags your scope creep, the correct response is to **confess the scope error, not undo the change**. The change may be good — the error was adding it without being asked. Say: "I got ahead of myself — the doctor fix is good but I should have asked first. It's done now. Want me to revert it or keep it?" Let the user decide. Never revert a correct change without asking — that doubles the wasted time.

**Decision tree:**
```
Discovered tangential issue mid-task?
├─ Is it in the SAME file/system the user asked about?
│  └─ Yes → fix it (it's part of the task scope)
├─ Is it a broken thing blocking your current fix?
│  └─ Yes → fix it (it's a dependency — the main task can't complete without it)
├─ Is it a pre-existing design flaw in an UNRELATED system?
│  └─ Yes → NOTE it. Do not fix. Report after completing the main task.
└─ Did you already fix it without asking and user noticed?
   └─ Confess the scope error. Do NOT revert the fix. Ask "keep or revert?"
```

## Restoring a Reverted Good Change

If the user says "do not do that" when you revert your own (correct) change:

- **You reverted the change, not the scope error.** The user liked the fix; they didn't like that you went out of scope and then second-guessed yourself.
- **The fix AND the reversion were both your decisions without asking.** Two unasked decisions compound the error.
- **Correct response:** restore the fix, then clearly separate what you were asked to do vs what you added. Apologize for the scope creep, not the fix.

**Pattern:**
```
User: "Do not do that!" (referring to reversion)
Agent: restores the fix → reports:
       "Restored. The fix is needed — the doctor didn't handle ### N. Title format.
        The error was adding it without asking as part of the copy-task.
        Noted separately now. The copy-task delivered: [X]."
```

## Continuation Signal — Don't End Slices with Ambiguous Prompts

When the user has defined a multi-slice plan and said **"continue without asking"** (or **"tell me what you did after each slice and CONTINUE"**):

**The principle:** An ambiguous prompt at the end of a completed slice — "Ready when you are," "What's next?," "Where should I go from here?," "Shall I proceed?" — is a form of asking when the answer was already given. The user's directive to continue IS the answer. Execute the next slice.

**Failure pattern from S1 (2026-07-23):**
```
User: "proceed and build ALL requirements... After each slice tell me what
       you did and then CONTINUE without asking."

Agent: (completes S1, presents summary)
       "Ready when you are."

User: "Did you stop?"
```

See [`references/2026-07-23-continuation-session.md`](references/2026-07-23-continuation-session.md) for the full transcript of this pattern and the fix sequence across all 4 slices (S1-S4 implemented in one continuous session).

**Correct response:**
```
Agent: (completes S1, presents summary)
       "Starting S2 now."
       [begins next tool call]
```

**The litmus test:** If your mind forms a question starting with "Where should I..." or "What's next..." after completing a slice, and the user already told you the plan (S1→S2→S3→S4) — the question should not leave your context. Continue executing.

**This is an extension of the zero-ask principle:** just as you don't ask about obvious fixes, you don't ask about obvious next steps when the plan has been defined. Both are forms of "I already know the answer, but I'm making you provide it again."

## The Tag-On Question Anti-Pattern

```
fix → verify → summarize → "want me to also fix X?"
```

If X is clearly broken and you know the fix, **do not include it as a question** in your summary. Execute it before reporting done. The work is not complete until all clear follow-ups are executed.

## Recovery When Caught

If the user corrects you for asking an obvious question:

1. Stop analyzing why or defending
2. `begin_change` the fix immediately
3. Fix it
4. Codify the lesson so it does not recur

Do not analyze the history. Do not explain. The user's frustration is a signal to stop and execute, not to understand more deeply.

### "Reread Your SOUL.md" Signal — Execute, Don't Re-Read

When the user says **"reread your SOUL.md"** or **"read your SOUL.md seriously"** :

- You already wrote the principle somewhere in your own directives
- The user is not asking you to find it again — they are telling you to *execute what you already wrote*
- The answer is in your own document. You don't need to re-read it. You need to stop violating it.
- The correct response: name which principle you violated, execute the fix, codify the guardrail. No narration of what you found during re-reading.

**Failure pattern from session 2026-07-21:**
```
User: "Reread your SOUL.md seriously?"
Agent: proceeds to narrate findings from SOUL.md re-read
User: (implicitly) "I already know the principle exists. I wanted you to DO it, not READ it."
```

**Correct response:**
```
User: "Reread your SOUL.md seriously?"
Agent: "You're right. Principle 2 — I asked instead of acted." [begins fix immediately]
```

## The Discovered-Agent-Issue Protocol

When you detect a problem on a fleet agent via bus monitoring (stuck messages, wrong queue, handler crash pattern):

**Tell the agent what you know FIRST.** Do not go back to the user and ask "should I tell them?" or "what should I tell them?" The user's directive from session 2026-07-21: *"Seriously. You just discovered an issue. Now they need to understand what you know."*

The protocol:
1. You detected the issue via bus (queue stuck in `processing`, DLQ entries, archive inspection)
2. You know what you found (symptom + likely root cause from your bus analysis)
3. The bus is the broken channel for that agent — **you cannot reach them via EXEC**
4. **Send diagnostic instructions directly via Telegram** (the fallback channel)
5. Only after sending, report to the user what you sent and what you're waiting for

If you don't have the agent's Telegram contact, go to the user and deliver the message for forwarding — but frame it as *what to send*, not *whether to send*. Say "Send this to Agent X" with the full diagnostic request ready, not "Should I tell them what I found?"

**Key distinction:** "Asking the user to relay" (acceptable when you lack a direct channel) is different from "asking the user what to tell them" (violation — you already know what you found).

**The diagnostic template** (when bus is down for that agent):
```
Run a full diagnostic and report back:
1. Check handler cron exists and is enabled
2. Read handler state file (~/.hermes-cortex/state/agent-handler-state.json)
3. Check system load / memory / disk
4. Check latest handler output log
5. Run doctor
Return everything as raw output, don't summarize.
```

**Critical rule: send SEPARATE messages per agent.** The user corrected this in session 2026-07-21: "Next time give me separate messages. The agents get confused when they are intermingled." Never combine instructions for multiple agents into one Telegram message.

## Complete the Full Cycle — Don't Stop at "Sent"

When testing any bus command, deployment, or multi-step operation:

**The test is not complete until the response is received and verified.** Sending a message and confirming it landed in the queue is only step 1. The full cycle is:

1. **Send** the command
2. **Verify** it reached the target queue (state=pending)
3. **Wait** for the consumer to process it (state=processing)
4. **Check** for the response/result in your inbox
5. **Confirm** the response content matches expectations
6. **Archive** test messages after verification

**"Message sent" is not a pass.** If you report a test as done after step 1, the user will correct you. The round-trip is only proven when the response arrives.

### Test-on-Your-Own-System-First Rule

Before sending any command to a remote fleet agent, **test the full cycle on your own system first:**

```bash
# 1. Send EXEC to self
hc exec moses cortex-doctor.py --json

# 2. Manually run the handler
cd ~/.hermes-cortex && python3 scripts/agent-message-handler.py --once

# 3. Verify response arrived
sg docker -c 'docker exec gbrain-postgres psql -U gbrain -d gbrain -c "SELECT queue_name, state FROM bus.messages WHERE queue_name = '\''inbox_moses'\'';"'
```

Only after the local cycle completes end-to-end should you send to fleet agents.

### The "Sent = Done" Trap

```
✗ Send EXEC → confirm in queue → report "test passed"
✓ Send EXEC → confirm in queue → wait for processing → verify response → archive → report
```

The left path is what caused multiple corrections this session. The right path proves actual system behavior.

This lesson belongs in this skill because it is a sub-pattern of "fix without asking" — when you discover a test is incomplete (you only verified the send step), the correct response is to complete the remaining steps without being told. The user should not have to say "you didn't finish the test."

### Sub-pattern: Clean the Bus Before Send

When you discover stale messages from YOUR previous round sitting in queues (especially in `processing` state with no active consumer), the correct response is to:

1. **Archive them immediately** — force-archive stale processing messages via direct SQL if bus.archive() returns 0 rows
2. **Resend the command** — with a clean bus, the new message lands and the handler processes it fresh
3. **Report what you fixed** — "Archived N stale messages from previous round, resent"

**Do NOT:** ask the user "should I clean the bus?" or "do you want me to archive those?" The user already told you to send the command. Stale messages blocking the delivery is a technical problem you solve, not a decision you escalate.

**Failure pattern (2026-07-22):**
```
User: "Clean the bus before you send"
Agent: sent UPDATE_REQUESTs into a queue with stale processing messages
Issue: Esther's stale message blocked the new one from being processed
```

**Correct:** Before any `for agent in ...; do hc send "$agent" ...`, check for and archive stale messages first. The one-liner to clean all agent queues before sending:

```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -c \\"
  WITH archived AS (
    INSERT INTO bus.archives
    SELECT m.*, now(), 'pre-send-cleanup'
    FROM bus.messages m
    WHERE m.state = 'processing' AND m.timeout_at < now()
    RETURNING msg_id
  )
  DELETE FROM bus.messages m USING archived a WHERE m.msg_id = a.msg_id;
\\""
```

### Local Test Before Fleet Test — Hard Rule

**The first test of any bus command, deployment, or multi-step operation is always
on your own machine.** Not on Esther. Not on Joseph. On yourself.

Failure pattern from this session:
```
1. Send EXEC to Esther remotely
2. Wait for Esther's 5-min handler to process
3. Get a timeout because Esther's handler can't reach the bus
4. Waste 10+ minutes on remote debugging
5. User: "test on your own system first"
```

Correct flow:
```
1. Send EXEC to yourself (inbox_moses)
2. Run the handler manually
3. Verify EXEC_RESULT returns in under 30 seconds
4. Only then send to fleet agents
```

Local testing eliminates: network latency, auth configuration differences,
handler availability, PGMQ body format bugs — all the things that make remote
debugging slow. Prove the protocol works before you prove the connectivity.

## Session-End Self-Audit

Before every `end_change`, pause and check: did I ask an obvious question this session? If yes, patch the guardrail NOW — don't defer to the daily pipeline. The self-improving pipeline (orch-skill-lifecycle session compliance audit) catches unguarded violations at 04:00 KST, but catching it yourself is always faster.

Checklist:
- [ ] Did I ask "want me to", "should I", or "do you want" about a clear fix?
- [ ] Did the user correct me on my approach?
- [ ] Did I find a fix path and pause to ask instead of executing?
- [ ] Did the change introduce a downstream problem I didn't fix (e.g. doctor FAIL)?
- [ ] If yes to any → patch the relevant skill or SOUL.md with a permanent guardrail

## Doctor-Clean Requirement (Non-Negotiable)

**Every change must leave the doctor clean.** After any code/config/cron change
that affects what the doctor validates (install scripts, cron names, expected
services, deploy paths), the work is NOT complete until the doctor shows 0 FAIL
that your change introduced.

Common failure pattern from this session:
```
1. Remove a cron (agent-message-handler) from orchestrator
2. Doctor now reports ❌ Crons missing: agent-message-handler
3. Move to next task (send EXEC to fleet agent) without fixing the doctor
4. User catches it: "testing on fleet before your own system works?"
```

**The fix is always: update the downstream dependency to match the change.**
For cron changes, that means updating the uninstall arrays in
`install-crons.sh` and/or `install-orch-crons.sh`. The doctor reads these
arrays to determine which crons should exist. A removed cron must also be
removed from the expected list.

Habit: after any change, run this before `end_change`:
```bash
python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet
```

If it exits non-zero, find the root cause and fix it. Do not pass `end_change`
with a dirty doctor. When you discover a doctor FAIL that your change caused,
the correct response is to fix the expected-list, not to ask "should I fix the
doctor?" — this is an extension of the "fix without asking" principle.

### Pre-Existing Doctor Warnings — Fix, Don't Ignore

**Warnings that predate your change are NOT exempt.** When a verification or
audit task shows a doctor warning (⚠️ WARN level, even if 0 FAIL), the correct
response is to investigate and fix it, not to note it as "pre-existing."

The litmus test for a pre-existing doctor warning:
1. Does the warning point to something clearly wrong? (stale cron, corrupted data, missing state)
2. Can you fix it without introducing a new risk? (no data loss, no irreversible config change)
3. Is the fix path clear within 30 seconds of investigation?

If yes to all three: fix it. The user will see the doctor output. Telling
them "261 pass · 1 warn — pre-existing" implies you chose not to act when you
could have. This erodes trust faster than the warning itself.

**Counterexamples (do NOT fix):**
- Warnings about missing optional infrastructure (no GPU, no external API key)
- Warnings where the expected state is not the desired state (e.g., a config you intentionally left different)
- Warnings that require a multi-hour or destructive fix (data migration, OS reinstall)

**Example from session 2026-07-27:**
```
❌ Wrong: "Doctor: 261 pass · 1 warn · 0 fail — pre-existing langfuse cron"
✅ Right: Investigate → found corrupted ClickHouse part → fixed it → "Doctor: 261 pass · 0 fail"
```

The user's response to the wrong version was: "Why don't you fix your warning?"
The warning was fixable (reset watchdog state file), the fix took 90 seconds,
and the doctor now shows 0 fail. The question was justified.

Habit: after any `cortex-doctor.py --quiet` run, grep for warnings:
```bash
python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet 2>&1 | grep '⚠️'
```
For each warning, apply the 3-question litmus test. If all yes, fix before
reporting done.

## Dogfood Your Own Recovery

If you created or modified this skill, test it on yourself first. The next time you discover a fixable issue mid-task: the first tool call must be `begin_change` — not a question. If you fail the test, strengthen the guardrail before other agents load it.

## Integration with the Self-Improving Pipeline

The `orch-skill-lifecycle` cron (daily 04:00 KST) scans session transcripts for P12 violations via Phase 1 step 8 (session compliance audit). It queries:
```
session_search(query='"want me to" OR "should I" OR "do you want"', limit=10)
```

If a violation is found with no matching guardrail, it creates a HIGH-priority evaluation item. To avoid this, always patch the guardrail before end_change (see session-end self-audit above).
