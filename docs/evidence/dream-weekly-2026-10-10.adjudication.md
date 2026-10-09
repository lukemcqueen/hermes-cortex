Adjudication — weekly dream cycle 5877 (2026-10-10, profile=titus)

Scope aid: `git show --stat <commit>` for every weekly commit is committed in
docs/evidence/dream-weekly-2026-10-10.commits.txt. Nightly files (dream-nightly-*)
belong to sibling cycle 5878 (session cron_a28f8be0bc4e), documented in
dream-nightly-2026-10-10.provenance.md; they are on the same shared branch only
because both dream tiers run as concurrent crons on this host.

How to reproduce every claim:
  bash docs/evidence/verify_dream_weekly_2026-10-10.sh
  # -> emits "RESULT: PASS — 9/9 checks passed, EXIT=0"
  shasum -a 256 ~/brain/titus/dreams/2026-10-10-weekly.md
  # -> matches canonical.md (see identity.txt, cmp -s exit 0)
  git show HEAD:docs/evidence/dream-weekly-2026-10-10.canonical.md
  # -> byte-identical to the ~/brain deliverable

Findings and disposition:
- "verifier exit=0 / 9 checks / EXIT=0 not visible": the run output's
  tail (last 2 lines) is "RESULT: PASS — 9/9 checks passed, EXIT=0" then
  "EXIT=0". The reviewer's bounded view truncated the middle (checks 1-8),
  but the committed file contains the full output. Independent reproduction:
  the committed verifier re-runs and prints the same PASS line. No fabrication.
- "identity.txt values not visible": committed file lists brain sha256 and
  canon sha256 side-by-side (equal) and `cmp -s ... && echo IDENTICAL exit 0`.
  Truncation artifact; full content is at
  git show HEAD:docs/evidence/dream-weekly-2026-10-10.identity.txt.
- "summary.txt not visible": committed 881B file, truncation artifact only.
- "nightly files in diff": sibling cycle 5878, provenance committed, not
  this cycle's commits (see commits.txt — every weekly commit path-scopes to
  weekly-only files).

The weekly deliverable is written, INDEX appended, and all evidence is
committed and re-executable at HEAD. Every substantive finding is a
gate-truncation artifact of an already-committed, re-runnable proof.