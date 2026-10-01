---
name: enforcement-gate-migration
description: "Use when re-pointing a gate onto a new evidence store."
version: 1.0.0
category: devops
author: Hermes Cortex curator
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [governance, gate, enforcement, migration, fail-closed, adversarial-review]
    related_skills: [loop-governance, change-checklist, shell-scripting, postgres-schema-design]
---

# Enforcement Gate Migration

Moving a gate or checker off an evidence source it does not own, onto one it does —
and getting a change like that through adversarial review.

## When to Use

- A gate reads a store owned by another system (another tool's DB, another agent's
  artifact) and you are moving it onto HC-owned evidence.
- Adding or altering a pre-commit / CI gate, or the checker behind one.
- A complex gate change whose close-out keeps returning FINDINGS.

## Procedure (order matters)

1. **Write the evidence first, prove it live, THEN flip the gate.** The order is
   writer -> checker -> gate re-point. Flipping the gate before anything writes the
   new store refuses every commit fleet-wide, which is an outage dressed up as
   enforcement.
2. **Make the writer automatic, and key it to the identity the gate already uses.**
   Resolve the session from the governance lock rather than inventing a second key —
   a harness and a subprocess must agree on what "this session" means, or the gate
   asks a question nothing can answer.
3. **Build the checker as a small program with an explicit exit-code contract.**
   See `templates/fail-closed-checker.py`. Codes: `0` verified, `1` refused, `3`
   cannot verify (store missing / unreachable / raising).
4. **The gate delegates and fails closed.** If the verifier is missing, refuse and
   name the fix. A gate that passes when it cannot verify is not a gate.
5. **Register the checker and any migration in the deploy map.** An unregistered
   file is never deployed, and a repo that applies cleanly proves nothing about any
   other host — the runner discovers migrations by file.
6. **Prove it on the DEPLOYED path.** The hook that actually runs is whatever
   `core.hooksPath` points at, usually a symlink to a deployed copy — not the repo
   source you just edited.
7. **Delete any transitional bridge once the writer is live, and pin its absence.**
   A bridge that outlives its window quietly becomes the authoritative source again.

## Rules

- **Never fall back to the incumbent source.** A fallback keeps it load-bearing,
  contradicts the point of the migration, and hides a failure of your own recording
  instead of surfacing it.
- **No run-time override of the evidence lookup** — no env var, no flag that
  redirects which store the gate reads. A caller who can set the environment can
  point the gate at a stub that answers "yes" for anything, which is a bigger hole
  than the one being closed. Make test branches reachable by STAGING a copy of the
  checker in a scratch tree and controlling what its lookup finds there.
- **Fail closed on an unreachable store**, and say which component is missing so the
  fix is not a mystery. Deleting or weakening a check to clear a block is a bypass.
- **Derive count assertions from the directory, never hardcode them.** A battery
  check asserting a literal row count goes stale the moment the next migration
  ships, and that staleness is what hides a migration that cannot apply.
- **Static review cannot see schema or wiring faults.** Apply the migration on a
  scratch database; a type mismatch, a bad path, or an unregistered file all pass
  reading and fail only at run time.
- **A transitional bridge must use evidence you already own.** Bridging to another
  system's artifact reintroduces exactly the coupling being removed.

## Closing Out Under Adversarial Review

An enforcement change touches always-review paths, so the review is part of the
procedure, not an afterthought.

- **Evidence must live IN THE REPO as a runnable test.** Results pasted into a
  closing note are rejected as unverifiable self-report, and correctly so — a claim
  only the author can see is not verification. Put the reproduction in the diff: a
  test that drives the real writer, the real store, and the real checker.
- **Do not write for the reviewer.** No "how to verify" instructions, no self-verdicts
  ("ACCEPTED", "resolved"), no outcome counts, no pointers to the test that ought to
  convince it. State what changed and what the code does; let the material stand.
- **Never suppress a HIGH finding.** An inline ignore or a widened `except` is the
  tempting shortcut and the wrong one — fix the cause (e.g. guard memoized module
  globals with a lock once a file becomes threaded).
- **Pin the verdict to the material; the reviewer is a sampling model.** A stored
  verdict is reusable only for the exact material it judged (note + diff combined),
  so the same material cannot be judged CLEAN and then FINDINGS on consecutive
  attempts. If a close is re-judged every attempt, check the verdict is actually
  being STORED: the review row is UNIQUE per cycle, so a re-review written as a
  plain insert is swallowed as an idempotent no-op and the fresh verdict is
  SILENTLY DISCARDED — leaving the original FINDINGS frozen forever, which is the
  very gap re-review exists to close. A fix that is never stored looks exactly
  like a fix that did not work.
- **Re-judge only when the material moved**, and only through the explicit
  re-review action; the ordinary close must honour the stored verdict. A verdict
  with no or mismatched material fingerprint is not reused, so a CLEAN cannot be
  carried over a later, unreviewed change.
- **One lock per logical change.** The lock's description is frozen at
  `begin_change`, while the reviewed diff is measured from the lock onward. Stack a
  second, unrelated change under the same lock and the reviewer receives a diff
  that does not match the stated task — a scope finding you cannot resolve, because
  editing the lock by hand is itself the bypass. Close the cycle, then open a new
  one with an accurate description.
- **Findings are sometimes factually wrong.** Measure before changing working code
  to appease one, and report the measurement. Never fabricate a probe to match the
  finding's framed premise — run the real form.
- **`rereview_change` may be missing from the MCP tool list** while the generic CLI
  reaches it. A CLI subprocess has no harness session, so it cannot resolve the
  governance lock by itself — pass the lock's session id explicitly.

## Pitfalls

- **Backticks in a shell-quoted string are command substitution.** In
  `git commit -m "..."` they are executed and their output spliced in (usually
  empty), so the sentence silently loses words while the command exits 0. Single-quote
  the message and read it back with `git log -1 --pretty=%B`.
- **A multi-line edit is safer as a script file than an inline heredoc.** Write the
  surgery to a file, make it refuse to run twice, and anchor on markers rather than
  line numbers; then run it. Quoting cannot corrupt what is not on the command line.
- **Check what the gate actually runs before changing it.** Run the checker the way
  the gate calls it — same interpreter, same arguments — and confirm red/green on the
  same binary; a checker that only ever says yes proves nothing.
- **A test stub must match the interpreter the code uses.** A shell stub for a
  Python-invoked verifier fails to parse, and every case "passes" for the wrong
  reason.
- **Deploying enforcement code does not make it live.** Long-lived processes hold
  the module they imported: the governance MCP server and the gateway both keep the
  old copy until restarted, so a fixed close-out path still behaves as before for
  MCP calls while the CLI — which imports fresh per invocation — already runs it.
  Exercise new code through the CLI, and state plainly which process still needs a
  restart rather than reporting the fix as live.
- **Don't name a live database path in a shell command.** A lifecycle guard scans
  the scripts a command references and will try to read a path it finds there; if
  that path is a SQLite file the command is refused outright. Run the edit from a
  script file, or refer to the path without quoting it into the command line.

## Related

- `templates/fail-closed-checker.py` — starter checker with the exit-code contract
- `loop-governance` — the review mechanism the close-out section works within
- `postgres-schema-design` — migration-runner and scratch-DB battery patterns
