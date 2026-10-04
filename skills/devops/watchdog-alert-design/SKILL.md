---
name: watchdog-alert-design
description: Fix periodic health watchdogs that alert without flapping.
version: 1.0.0
category: devops
author: Hermes Cortex
license: MIT
metadata:
  hermes:
    tags: [watchdog, health, cron, alert, debounce, reachability]
    related_skills: [cortex-bus, cron-quality-gate, approval-gate-debugging, watchdog-flapping-diagnostics]
---

# Watchdog Alert Design (health / bus / reachability crons)

## When to Use

- Writing a new periodic health / bus / reachability watchdog cron.
- Debugging a recurring warn→recover→warn flapping pair from an existing watchdog.
- Reviewing an alert cron that never stays quiet.

A periodic no_agent checker that warns on state changes is only worth deploying if
it stays quiet when nothing is actually wrong. Every rule below is a failure mode
seen in real fleet watchdogs.

## Rules

### 1. Silent-when-clean — no output = no notification
Healthy state produces ZERO stdout. Collect the whole report first, then print
only if there is a signal. Never emit "✅ all clean".

### 2. Debounce BOTH transitions, not just one
- Alert only after **N consecutive** failed probes.
- Declare recovery only after **M consecutive** successful probes.

A path that alerts on its FIRST failure and recovers on its FIRST success turns
any single transient probe blip (one slow timeout, one nginx hiccup, one dropped
connection) into an **alert+recovery flapping pair** — recurring spam on every tick
as the blip re-occurs. Works defaults that hold up: **N=2** for the alert,
**M=3** for the recovery.

### 3. Trace flapping to the branch missing the debounce
When a watchdog flaps warn→recover→warn, the broken branch is the one with no
consecutive-count gate. Its sibling role/state branch almost always has one
(a standby orchestrator path already requires 3 failures + elapsed time before it
acts) — mirror that sibling's threshold onto the under-debounced branch instead of
designing a new number.

### 4. Real outages still report (once)
Debounce must not hide a genuine outage. With N consecutive failures the alert
still fires once and then stays quiet while the condition holds; recovery needs M
consecutive successes so a one-tick recovery doesn't instantly flip back. A
debounce (count to threshold) is the right mechanism; a bare `last_state` toggle
is the bug.

## Testing watchdogs — make it host-independent

Watchdogs read role (orchestrator vs worker) and health-URL config from the host
at import, so running the drill on a host where the role short-circuits the logic
(Moses host → `IS_MOSES` returns silent) or where no health URLs are configured
(empty probe list → config-guard stands down) proves nothing. To test the state
machine on ANY host:

- Force the role: override the module's `IS_MOSES` / `IS_ORCHESTRATOR` to the
  non-actor (worker) value after import.
- Inject probe results: pass booleans for "primary up / backup up" into a
  `run_once(primary_up=..., backup_up=...)`-style seam instead of letting it hit
the network — this also makes the test hermetic and fast.
- Redirect the state file to a temp dir so the drill never touches live state.

Write the regression test FIRST (it should FAIL against the undebounced code:
assert a single blip emits zero output), then fix, then watch it go green.

## Pitfalls

- **A single-tick blip is real.** Treat any "unreachable→reachable" pair in the
  same cron delivery as the signature of a missing-debounce bug, not two separate
genuine events — the recovery line can only fire after the alert, and both come
from the probe result flipping twice across consecutive ticks.
- **Don't copy the alert threshold onto recovery.** They are independent: recovery
  should be at least as strict (more consecutive successes) than the alert
  threshold, so a blip that just crossed the alert line doesn't instantly clear it.
- **Empty health-URL list is "unconfigured", not "down".** A probe function that
  returns False for an empty/None URL list will scream "outage" for an unset env
  var. Fail closed the other way: stand down silently when nothing is configured.

## Seam note

The clean shape is a `run_once(...)`-style pure function that returns the report
lines and takes injectable probe booleans (production: HTTP adapter; test: injected
values). One real adapter + one test adapter justifies the seam; the module's I/O
(state file, config swap, notify) stays behind it so tests hit only the function.
