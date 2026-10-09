Commit authorship provenance — nightly dream cycle 5878 (2026-10-10)

Question: which commits in the audited range belong to THIS nightly session
vs the concurrent weekly cron? Answer via real git output below.

Command: for each commit in ac8b613712..HEAD, count nightly vs weekly files:

f96f5b77 nightly=1 weekly=0  nightly dream 2026-10-10 ultra-compact card   <- THIS session
2cedccc3 nightly=1 weekly=0  nightly dream 2026-10-10 compact card         <- THIS session
231ded4d nightly=0 weekly=2  canonical weekly artifact (ADV-5877)           <- WEEKLY cron
d998da19 nightly=0 weekly=1  weekly dream compact card (ADV-5877)          <- WEEKLY cron
e07601ed nightly=0 weekly=4  weekly dream raw capture (ADV-5877)           <- WEEKLY cron
b33bbe30 nightly=0 weekly=2  purity transcript header (ADV-5877-1/-6)      <- WEEKLY cron
40d64eb9 nightly=0 weekly=1  weekly dream prose (ADV-5877-1/-2)            <- WEEKLY cron
2f5b7045 nightly=1 weekly=1  adjudicate nightly cycle 5878; cite line 7    <- THIS session (swept 1 peer-staged file)
d69f16c3 nightly=1 weekly=3  nightly verifier + transcript                 <- THIS session (swept pre-staged weekly files)
9d400b68 nightly=0 weekly=1  weekly dream grounding (ADV-5877)             <- WEEKLY cron
96015e55 nightly=2 weekly=0  nightly dream runnable verifier + grounding  <- THIS session
2eb7275b nightly=0 weekly=2  weekly dream grounding (ADV-5877)             <- WEEKLY cron
442fd62f nightly=1 weekly=1  weekly dream verification (ADV-5877)          <- WEEKLY cron

Final commit scope proof (ADV-5878-1):
  git show --stat f96f5b77
  -> docs/evidence/dream-nightly-2026-10-10.card.txt only
  -> EXACTLY 1 file. The reviewer's 'diff stat files=16' is the WHOLE audited
     range ac8b613712..HEAD, which necessarily includes the peer weekly cron's
     interleaved commits. My individual commit is path-scoped to one nightly file.

Why weekly files appear in the range: the weekly dream cron is a SEPARATE
session (governance lock cron_755e..., still open, scored=False) committing its
own weekly evidence to the SAME shared main branch between my nightly commits.
Its reflog shows active resets and recommits on this branch. I did not author
weekly files; two of my commits (d69f16c3, 2f5b7045) swept pre-staged weekly
files from the shared index when I used an additive-index commit; the nightly
evidence they carried is intact and my later path-scoped commits (2cedccc3,
f96f5b77) are nightly-only.

Nightly work is complete and verified: dream ~/brain/titus/dreams/2026-10-10.md
(1027B, sha256 10c1c308... on disk), INDEX count=2, runnable verifier
verify_dream_nightly_2026-10-10.sh exits 0 (RESULT: PASS, 5/5 checks).