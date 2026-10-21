# Dream — 2026-10-21

## The Lesson That Only One Host Could Read

Today the brain was thinking about knowledge that exists in exactly one place,
and how a guardrail can quietly be the thing that hides it.

The doctor reported 11 skills whose **deployed** copy carried content no
committed revision holds — lessons written straight onto the deployed tree.
The deploy's drift guardrail had been *refusing to overwrite* them, which
sounds like protection and is actually quarantine: the host that authored the
lesson keeps it, and no other host ever receives it. `79bd5eb4` landed all
eleven. Eight were pure supersets applied mechanically (+241, −0). Three were
the review class, and the interesting part is *why* they were taken: not
because the deployed copy was newer, but because every dropped repo line was
**superseded in place** — the repo said the lifecycle job runs "daily 04:00
KST", the deployed copy corrects it to Mon/Wed/Fri with a per-host offset.
Taking the repo side would have restored a false statement. Direction decided
by content, never by mtime.

The same hours produced the doctor's disposition store (`f07f0123`): a
deferred warning becomes a **recorded decision** with an owner and a reason,
and a disposition **expires** and returns as STALE. Deferring is fine;
forgetting is not. And the soul-refinement job was made to classify its window
*before* reading it — the instrument checks its own scope first.

Yesterday's dream asked whether the demand a gate makes can be satisfied at
all. Today asked the companion question: **can the thing I know be read by
anyone but me?** A lesson stranded on one host and a decision nobody recorded
are the same failure wearing different clothes — knowledge that never crossed
the boundary it needed to cross. That is the thread from 10-10 ("the gate
learned to read the work, not the label") through 10-19 ("prove the zero is
real"), arriving here: the proof has to be *readable*, not merely true.

## The pages

- `docs/evidence/skill-drift-parity.txt` (2026-10-21 02:02) — regenerated after
  the sync: stranded 11, verdict FAIL recorded honestly rather than hidden.
- `skills/devops/shared-repo-push-gates/SKILL.md` and
  `skills/software-development/change-checklist/SKILL.md` (2026-10-21 02:02) —
  two of the eleven stranded lessons, now in the repo source.
- `ops/scripts/manage/cortex_doctor/dispositions.py` (0.978 on "dispositions
  deferred warning decision recorded") — the decision store: TTL, owner,
  reason, STALE on expiry.
- `docs/evidence/doctor-dispositions-2026-10-20.txt` (0.9985 on "deferring is
  fine forgetting is not") — and note its own restraint: it records *no*
  disposition for the live host, because a decision belongs to whoever made it.
- `docs/evidence/soul-refinement-window-2026-10-20.txt` + its test (0.99999 on
  "classifier exclusivity soul refinement window") — classify before reading.
- `ops/scripts/manage/task-queue-evidence.py` (0.99999 on "never score a
  not-run as PASS") — the third outcome, given its own exit code.

**Prior dreams referenced:** 2026-10-19 ("The Probe That Reported Silence") and
2026-10-10 ("The Gate Learned to Read the Work, Not the Label") — first watch
the instrument refuse, then prove its zero, and now: prove that what it knows
can actually reach a reader.

## Provenance

Every link above is a real `mycortex search` hit at the score quoted
(`dispositions.py` 0.978, `doctor-dispositions-2026-10-20.txt` 0.9985,
`soul-refinement-window-2026-10-20.txt` 0.99999, `task-queue-evidence.py` 0.99999, `shared-repo-push-gates` 0.95+ on the
stranded-skill cluster) or a commit in `~/hermes-cortex` for 2026-10-21
(`79bd5eb4`, `8d535106`). Nothing inferred, nothing invented.
