---
name: governance-closeout
version: 1.0.0
category: devops
description: "Use when a governed change will not close."
author: Hermes Cortex curator
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [governance, loop-governance, adversarial-review, lock, close-out]
    related_skills: [loop-governance, governance-lock-lifecycle, two-hard-rules]
---

# Governance Close-out

**Class of task:** closing a governed change — `feedback_accept` then `end_change` —
and everything that can refuse it: an unscored cycle, an unclosable cycle, an
adversarial review returning FINDINGS, or a fix to the close-out path that is not live
yet.

> The normative governance rules live in the repo (AGENTS.md, the loop-governance
> skill). This skill is the CLOSE-OUT procedure and the traps that cost time.

## The procedure

```text
cycle_query(status="pending")                  # every cycle for this session
feedback_accept(cycle_id=…, completeness=…, quality=…, progress=…, note="…")
end_change(task_id=…)                          # refuses while the cycle is unscored
```

A bare note is refused: pass scores, or an explicit `unscored_reason`. Decisions are
compared by CLASS, so a `LOOP` result still closes.

## The adversarial review gate

A COMPLEX change cannot close without a CLEAN verdict. Complexity is MEASURED from the
diff (≥50 lines, ≥3 files, or any always-review path such as `plugins/`,
`mcp-servers/`, `ops/scripts/cortex-update.sh`, `pre-commit-score`) — never
self-reported, and uncommitted work counts.

The reviewer runs with a DIFFERENT model and the verdict is durable. It is a sampling
model, so re-running it on byte-identical material can return the OPPOSITE verdict.
The verdict is therefore stored once per cycle and pinned by a fingerprint of the exact
material it judged (note + diff):

- `end_change` honours a stored verdict whose fingerprint matches the current
  material — CLEAN proceeds, FINDINGS blocks with the recorded findings.
- Material that moved after a review is judged again, so a CLEAN cannot be carried
  over a later, unreviewed change.
- A stored verdict with NO fingerprint is not reused.

### Working the findings

- **FINDINGS → fix, then `rereview_change` with a NEW note.** An unchanged note is
  refused: re-review exists to re-judge a FIXED change, not to re-roll a verdict.
- **Put the evidence in the repo, not in the closing note.** The reviewer sees the
  note and the diff and cannot re-run a terminal, so output pasted into a note reads
  as an unverifiable self-report. Commit the proof as a runnable test; keep the note
  descriptive and free of instructions to the reviewer.
- **Answer a false finding with a measurement, not with prose.** Findings can be
  wrong. State the measurement that refutes one and leave the code alone rather than
  "fixing" a non-defect.

## Verifying the gate actually RAN — a pass is not evidence of a review

A close that succeeds may mean the review passed, or that the review never ran.
Only the gate's own log separates those, and the gate writes **two** places:

- **`~/.hermes-cortex/logs/loop-governance.log`** — the cortex-owned record
  (bounded: rotates at 5 MB, 3 backups). **Read this one first**: it is ours, it
  sits with the other cortex logs, and it does not depend on Hermes's rotation.
- `~/.hermes/logs/mcp-stderr.log` — stderr, captured by the harness. Useful for
  live debugging, and it interleaves every gateway-spawned server, so prefer the
  cortex log when asking "what did the gate decide".

| Line | What actually happened |
|---|---|
| `self-adversarial review: cycle N simple (L lines, F files) — skip` | The change was BELOW the complexity threshold. No reviewer, no triage, no findings. A clean close here says **nothing** about review quality. |
| `self-adversarial review: cycle N stored <verdict> but all LOW (n) — not blocking` | A review ran and every finding was classified administrative and lowered, so it annotated instead of blocking. |
| findings listed with severities | MEDIUM+ findings blocked the close. |

Cheap check before claiming "the gate passed": `search_files` for
`self-adversarial review: cycle` (or `triage:`) in
`~/.hermes-cortex/logs/loop-governance.log`. The triage layer also logs
`triage: judgement status=…` and `reviewer severities stand` when the judge is
unreachable — silence there means triage never ran, not that it approved.

**A skipped review is silent by design**, so the log is the only evidence. Never
report a gate as "passed adversarial review" without it.

## Pitfalls

- **A fix to the close-out path is not live until the MCP daemon restarts.** The
  loop-governance MCP server is a LONG-LIVED process that loads
  `~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py` once — the same
  "deploy ≠ load" trap as the gateway holding the old enforcer. The CLI
  (`ops/scripts/loop-gov.py`) imports the server module fresh on every call, so it
  runs the repo code right now: use it to verify a close-out fix without waiting.
- **The CLI is a subprocess with no harness session.** Run from a plain shell it finds
  no session and answers `No active governance lock`. Pass `session_id` explicitly in
  the payload — the documented priority-0 override.
- **One lock per logical change.** `begin_change`'s description is fixed for the life
  of the cycle and must NEVER be hand-edited (that is fabricated governance state).
  The reviewer diffs the window from the lock's `started_at`, so stacking a second
  unrelated change under one lock leaves the description not matching the diff: the
  reviewer flags it, `rereview_change` cannot resolve it, and the cycle is unclosable.
  Only the orchestrator can clear such a cycle.
- **Score before you investigate.** A cycle left PENDING with no live lock is a doctor
  FAIL that blocks every push, so scoring an orphaned cycle is the first move, not the
  last.
- **Test a verdict-recording helper BOTH ways.** One exercised only by re-recording an
  existing row never runs its insert path — assert the first record into an EMPTY
  cycle too, or the insert half can be silently broken while the suite is green.
