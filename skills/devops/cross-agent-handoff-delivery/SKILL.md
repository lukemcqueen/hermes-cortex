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

## Pitfalls

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
