---
version: 1.0.0
name: build-check-split
category: software-development
description: "Use when driving a task list tagged BUILD vs CHECK."
---

# Build/Check Split + Autonomous Delegation

## The core split (the whole idea)

Two kinds of task, tagged on every row of the map:

- **BUILD** = mechanical shape/wiring. The compiler plus a happy-path test
  catch the errors. Safe to hand to a subagent.
- **CHECK** = a security/conformance guarantee (byte-parity, tamper detection,
  stop enforcement, secret redaction, deterministic replay). Silent-when-wrong
  — the test passing says nothing about whether the promise is *actually*
  kept. The strongest available model writes **and** verifies these. Never hand
  a CHECK to a weak model alone.

Memorize the split before touching anything. A CHECK that a weak model
"implements" silently becomes a false green — the exact failure a conformance
suite exists to prevent.

## Drive autonomously

- Work the frozen task map **strictly top-to-bottom**, never out of order.
- The operator should need only **"continue"** between turns — not a
  re-specification of each task. Pull the next task yourself, execute it fully,
  report, and tee up the next one.
- One task = one file + one test + one RED→GREEN cycle. Never batch.

## Every task closes with edge cases + an adversarial review

Standing rule (operator directive): **every** task — BUILD and CHECK alike,
and including subagent output you accept — must end with two things before it
is "done":

1. **Edge-case tests**, not just the happy path. Probe the boundaries: empty
   input, extremes (u64::MAX / i64::MIN), malformed input, wrong types,
   reordered/duplicate data, and whatever a hostile peer could send. For the
   steadfaste core, the canonicalization and hash boundaries are the hot spots
   (float notation like `-0`, `1e2`, `1.0`, `u64::MAX+1` → all float forms that
   must be rejected; key byte-order; unicode non-normalization).
2. **An adversarial review** — attack the implementation's assumptions, not
   just re-read the diff. Prefer probing real library behavior with a scratch
   test over reasoning from memory (serde_json's `-0`→f64 quirk was only found
   by probing). Findings either become fixes (a panic path, a lenient parse) or
   pinned tests (a documented fail-closed behavior).

Do NOT delegate a BUILD task and accept its "done" without adding edge cases
and attacking it yourself — subagent self-reports are not verification.

## Delegation rules

- **BUILD → `delegate_task` subagent**, one task per subagent, parallel only
  when the tasks share no files (independent leaves).
- **CHECK → do it yourself**, with conformance rigor: golden fixtures, byte
  parity, fuzz the negative cases, no mocks where the promise is mechanical.
- Give each subagent **self-contained context** — it knows nothing of your
  conversation: the exact file path, the spec section, the test command, the
  TDD instruction (failing test first, watch it fail), and that writes are
  governance-gated (it opens and closes its own cycle).
- Subagents cannot call `delegate_task`, `clarify`, `memory`, or `cronjob`.
  They can open/close governance cycles — require that in the goal.

## Verify every subagent result

A subagent's "done" is a **self-report, not a verified fact**. Before you
accept it: run the test yourself, read the diff, confirm scope (no unrelated
churn), and re-run the full suite. For external side effects, demand a
verifiable handle (URL, ID, path), never the subagent's word.

## Pitfalls (proven)

- **A formatter pollutes the diff.** `cargo fmt -p <crate>` reformats the whole
  crate, touching files outside your task. Revert out-of-scope files and keep
  the commit minimal — "one task = one file" applies to the commit, not just
  the work.
- **A conformance test can expose a real contract divergence** — the code
  violates the spec (e.g. it rejects where the spec says "ignore"). That is the
  test working. Fix the code to match the frozen spec (watch RED first), never
  weaken the test to make it pass.
- **Open the governance cycle before the first terminal command** — even
  `git status` — when the repo enforces it. Read-only tools stay unlocked.
- **Stop before each CHECK** to hand it to the strong model, unless the
  operator explicitly assigns it to you (then treat it as an override and
  execute with conformance rigor, noting the override).
