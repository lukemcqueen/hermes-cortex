# Adversarial Review Brief — how to REQUEST a review so it does not cost a cycle

> **Who this is for: whoever is asking for the review.** The reviewer's own instructions are
> `docs/templates/adversarial-reviewer-prompt.md` (orchestrator-only) and are appended verbatim
> below the `=== REVIEWED MATERIAL ===` marker. This file is about the material YOU write above it.
>
> The reviewer sees only what you paste, it has no terminal, and it judges what you assert. Most
> friction in this pipeline is not the reviewer being harsh — it is a brief that made a checkable
> question unanswerable, or that handed over the answers.

## 1. Lead with OPEN QUESTIONS — never with your own hypotheses

Measured (2026-10-18): a brief whose "author's own suspicions" section listed five suspected gaps came
back with **six findings, every one of them a restatement of those five** — the evidence fields
literally began *"Author's own suspicions: …"*. The review confirmed and sharpened the list and
**discovered nothing new**. That is what leading with your own conclusions buys you: an expensive echo.

Write it in this order:

1. **What changed**, with the code inline.
2. **The question per axis** — explicit, e.g. "does this BREAK, DEGRADE, or WORK on macOS? Name the
   line and the concrete failure."
3. **What you already know you cannot verify** (optional) — but do not dress a hypothesis as a
   suspicion list. If you have a hypothesis, state it as a *question*: "does `_push_base` resolve at
   all when the default branch is `master`?"

## 2. Paste evidence, not descriptions of evidence

Every word you spend paraphrasing is unverifiable. Include:

- the diff or the changed hunks (code, not a summary of the code);
- the commands you ran and their output, verbatim;
- the test files, or their names plus the commit that carries them.

A brief that says "tests pass" gets `unverified-claim` — correctly.

## 3. Assume the reviewer cannot see: siblings, your terminal, the store, the past

| It cannot see | So give it |
|---|---|
| a sibling file in the same range | the path, the commit that provides it, its contract |
| your terminal | the output, pasted, verbatim |
| the governance store | cycle id, event number, or evidence path — a POINTER |
| history | the cycle id or evidence file where the measurement was recorded |
| a helper used at both ends of the range | nothing — the range did not change it; demote to a note |

## 4. Ask for failures per axis, and say what "broken" looks like

"Review this" produces style notes. "Does this break on macOS, on a non-Hermes agent, in a repo with
several concurrent sessions, and in a repo that is not this one? Name the line and the concrete
failure" produces findings you can act on.

## 5. What you may NOT ask it to do

- **Confirm a design you have already decided.** That is a request for approval, not a review.
- **Compare against a standard you did not state.** The reviewer applies the prompt it was given;
  if your repo has an extra convention, paste that convention.
- **Approve.** Only the gate closes a cycle, and only on what the reviewer can see.

## 6. After the review

Fix what is real, and **say plainly when a finding is wrong** — with the measurement, in the same
turn. A confidently-worded finding can still be false (measured: a HIGH claiming a shell one-liner
left `$?` at 0; `f() { return 3; }; out=$(f 2>&1) && rc=0 || rc=$?` yields 3). Editing working code to
satisfy a wrong finding is worse than pushing back, because it hides the error from the next reader.
