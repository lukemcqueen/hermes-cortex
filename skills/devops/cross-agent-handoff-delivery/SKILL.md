---
name: cross-agent-handoff-delivery
description: "Verify a cross-agent handoff is usable, not just delivered."
version: 0.1.0
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [cross-agent, handoff, bus, delivery, verification, messaging]
    related_skills: [cross-agent-design, bus-inbox-check, agent-fundamentals]
---

# Cross-Agent Handoff Delivery

Ensures a handoff sent to a peer agent's inbox is genuinely usable by the
recipient — not merely accepted by the Send API. Prevents the "I sent it, why
is nothing happening?" failure where the notification lands but the content
does not.

## When to Use

- Sending a handoff, diff, patch, or work product to the orchestrator inbox
  (`inbox_orchestrator`) or another agent, expecting them to act on it.
- Closing out a session and claiming "handoff sent / done" to the user.
- Debugging why a peer reviewed a summary but could not act on the work.

## Core Principle

**A handoff is only delivered when the content is in the message (or a
recipient-reachable ref), not when the Send API returns ok.**

The `msg_id` / `status: ok` returned by `bus_send` proves the queue accepted
the message. It proves nothing about whether the recipient can act on it. A
message whose body names a local-only branch (never pushed to origin) or omits
the actual diff is not a usable handoff — the peer opens it, finds nothing, and
the work stalls until they chase you.

## Procedure

### Make the handoff self-contained
1. Attach the actual content to the body: full `git diff --cached` output,
   artifact, or patch text. OR push the branch to a remote the recipient can
   reach. Never name a local-only branch as the handoff.
2. Reuse the original `correlation_id` when resending a correction so the
   recipient can thread it to the first message.

### Verify it landed AND is usable
After the send, confirm the delivery side:
- Send returned a `msg_id` with `status: ok`.
- Recipient queue depth incremented: `bus_list_queues()` → depth of the
  target queue went up. (Non-orchestrators cannot read/peek `inbox_orchestrator`
  — a 403 on peek is the expected send-only ACL, not an error.)

Then confirm the BODY arrived whole — the peek display is not the payload:
- `hc inbox <agent>` cuts the body after a line or two, so a plausible display proves
  nothing about what the queue holds. Read it programmatically and compare against the file
  you sent:

  ```python
  from cortex_bus import bus_peek          # non-destructive — never bus_read
  msgs = bus_peek("inbox_<agent>", limit=20)
  body = json.loads(m["body"]) if isinstance(m["body"], str) else m["body"]
  text = body.get("text") or body.get("body") or ""
  assert len(text) >= len(open(payload).read())        # whole, not truncated
  assert "<a distinctive heading from the payload>" in text
  assert "<another>" in text
  ```

- The MARKERS matter as much as the length: a byte-count match with different content is a
  different message. Pick strings that exist only in the real payload.
- Use the peek, never `bus_read`: a read pops the message into `processing` and steals it
  from the recipient's handler, which is how an inspection drains a queue the peer needed.
- **A task ROW is not a delivered task.** A custom subject is archived as unknown and the
  body never reaches the peer — only the task-creating subjects produce a row it can claim
  (`fleet-commands`). And a row can be stored at a NARROWER scope than you asked for when its
  content trips the PII/scrub gate (a `fleet` request silently stored as `personal`). Re-read
  the row's own scope, assignee and status before reporting that the task was handed over.

After any write, verify the content itself was pushable/attachable:
- `git rev-parse HEAD origin/main` — if equal, you have 0 commits ahead; the
  staged work is un-pushed.
- `git ls-remote origin | grep <branch>` — empty means the branch your message
  names is invisible to the recipient.
- `git diff --cached | wc -l` — the actual size of what you attached.

### Read your OWN inbox for the peer's follow-up before declaring done
The blocker often shows up as a pending/critical message in YOUR inbox
(`inbox_titus`), not in any Send log. Before telling the user "handoff sent /
done," check:
- `bus_archives("inbox_<you>", since_minutes=...)` for recent peer replies.
- Peek your own pending inbox (`inbox_<you>`) for urgent/critical follow-ups
  (e.g. "BLOCKER: branch is NOT on origin, resend the patch").

## Evaluating an INBOUND patch before applying it

A patch set another agent asks you to apply is a handoff in the other direction, and it is
only as good as its measurements. Never `git apply` it blind, and never relay it un-reviewed.

1. **`git fetch` BEFORE judging the base it names.** A stale remote-tracking ref makes a
   correct base look wrong, and every verdict you publish inherits the error.
2. **Check each patch against the base it names, in a throwaway worktree**
   (`git worktree add --detach /tmp/base <base>`), so the verdict is about the patch and not
   about your working tree. Report the per-patch exit code: `0` applies; `1` does not apply —
   a patch pasted through a renderer loses backticks and wrapped lines, so this can mean the
   TRANSPORT mangled it rather than that the author's file was broken; `128` corrupt — the
   hunk header disagrees with its own body, so count the body's context/added/removed lines
   against the header before explaining it. Remove the worktree afterwards.
3. **Re-measure every claim and every count** from the artifact or the live system. A count
   inherited from an earlier note is stale until measured, and a "why" can be wrong while the
   patch is right — check the claimed SYMPTOM (does the tool actually fail, or does it merely
   under-check?) before accepting the fix's premise.
4. **Review the INTENT even when the patch applies.** A fix that verifies a value and then
   still writes the value it just proved wrong is the original bug wearing the fix's clothes;
   a fallback chain testing file EXISTENCE has re-implemented the defect it exists to remove.
5. **Reject a patch whose referenced target does not exist** — a doc, a service, a path.
   Applying cleanly is not evidence the target is real; search the repo for it.
6. **Deliver the evaluation, not just the fix**: per patch, what you measured, what you
   rejected and why, which of the sender's claims do not hold — and any claim of your OWN you
   had to retract.

## Pitfalls

- **Blind-applying an inbound patch.** "The orchestrator can apply each patch directly" is the
  sender's belief about their own artifacts: verify per patch against the base they named, and
  confirm the files they target still hold the content they describe.
- **Claiming "done" off a Send API response.** The `msg_id` proves delivery to
  the queue, not usable content. Always combine send-ok with a content-usable
  check before reporting done.
- **Naming a local-only branch as the handoff.** The recipient cannot `git
  checkout` a branch that doesn't exist on their remote. Attach the diff or
  push first.
- **Reading the wrong queue.** You can read `inbox_<you>`; you get 403 (or the
  orchestrator gives 403 on artifacts) reading `inbox_orchestrator` as a
  non-orchestrator. Use your own inbox + archives for the follow-up signal.

## Verification

- [ ] Body carried the actual content or a recipient-reachable ref (not a
  local-only name).
- [ ] Send returned `msg_id` + `status: ok`.
- [ ] Target queue depth incremented.
- [ ] Own inbox checked for a peer follow-up before declaring done.
- [ ] Content-usable check run: 0-ahead, branch on origin, diff size captured.
