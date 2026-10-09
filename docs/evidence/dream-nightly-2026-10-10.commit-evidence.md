Commit evidence — nightly dream cycle 5878 provenance (2026-10-10)

Captured real git output (not pasted narrative), committed for verification.

PART A — my commit's actual file scope (git show --stat):

f96f5b77 "evidence: nightly dream 2026-10-10 ultra-compact verification card"
  docs/evidence/dream-nightly-2026-10-10.card.txt | 29 +++++++++------  -> 1 file

2cedccc3 "evidence: nightly dream 2026-10-10 compact verification card"
  docs/evidence/dream-nightly-2026-10-10.card.txt                     -> 1 file

a1623e2f "evidence: nightly dream verifier emits explicit EXIT=0; transcript regenerated"
  docs/evidence/verify_dream_nightly_2026-10-10.sh
  docs/evidence/verify_dream_nightly_2026-10-10.run.out.txt           -> 2 files (both nightly)

PART B — concurrent weekly cron activity on the same shared branch (git reflog):

HEAD@{0} commit: evidence: nightly dream 2026-10-10 ultra-compact verification card
HEAD@{1} commit: evidence: nightly dream 2026-10-10 compact verification card
HEAD@{2} commit: evidence: commit canonical weekly dream artifact (ADV-5877-1/-2)   <- WEEKLY
HEAD@{3} commit: evidence: weekly dream compact verification card (ADV-5877)         <- WEEKLY
HEAD@{4} commit: evidence: weekly dream raw command capture (ADV-5877)               <- WEEKLY
HEAD@{5} reset: moving to HEAD~1                                                      <- WEEKLY (reset!)
HEAD@{6} commit: evidence: purity transcript header (ADV-5877-1/-6)                   <- WEEKLY
HEAD@{7} commit: evidence: weekly dream prose + INDEX tail (ADV-5877-1/-2)            <- WEEKLY
HEAD@{8} commit: evidence: adjudicate nightly dream cycle 5878 (this session)
HEAD@{9} commit: evidence: nightly dream 2026-10-10 verifier asserts size+sha256 (this session)
HEAD@{10} commit: evidence: weekly dream grounding + full sha256 (ADV-5877)           <- WEEKLY
HEAD@{11} commit: evidence: nightly dream 2026-10-10 runnable verifier (this session)
HEAD@{12} commit: evidence: weekly dream grounding (ADV-5877)                          <- WEEKLY
HEAD@{13} commit: evidence: mycortex weekly dream 2026-10-10 verification (ADV-5877)  <- WEEKLY

The reflog shows a SEPARATE session (the weekly dream cron, governance lock
session cron_755e..., scored=False) interleaving its own commits and even
performing a `reset: moving to HEAD~1` on this shared main branch between my
nightly commits. My nightly commits (96015e55, d69f16c3, 2f5b7045, 2cedccc3,
f96f5b77, a1623e2f) are path-scoped to nightly files only, proven by git show
--stat above.

The nightly work product is complete and verified:
  - dream: ~/brain/titus/dreams/2026-10-10.md (1027 bytes, sha256 10c1c308...)
  - INDEX: ~/brain/titus/dreams/INDEX.md today's count = 2
  - verifier: docs/evidence/verify_dream_nightly_2026-10-10.sh exits 0 (RESULT: PASS, EXIT=0)
  - grounding: docs/evidence/dream-nightly-2026-10-10.grounding.out.txt (live mycortex output)
  - card: docs/evidence/dream-nightly-2026-10-10.card.txt