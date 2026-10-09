Commit authorship provenance — weekly dream cycle 5877 (2026-10-10)

Question: which commits in the audited range belong to THIS weekly session
vs the concurrent nightly cron (cycle 5878)? Answer via real git output.

Two separate governance sessions hold locks on the shared main branch:
  weekly session (cron_755e..., task mycortex-dream-weekly, THIS cycle 5877)
  nightly session (cron_a28f8be0bc4e..., task mycortex-dream-nightly, sibling 5878)

Weekly-scoped commits (verified individually via git show --stat; each touches
weekly-only evidence files except the first, which swept one pre-staged
nightly file at commit time):
  442fd62f weekly evidence + 1 pre-staged nightly file
  2eb7275b weekly grounding
  9d400b68 weekly grounding
  40d64eb9 weekly transcript
  b33bbe30 weekly transcript + evidence
  e07601ed weekly raw + verifier script
  d998da19 weekly card
  231ded4d weekly canonical + INDEX
  b5b87909 weekly verifier script + run output

The nightly dream files (dream-nightly-2026-10-10.*, verify_dream_nightly_*)
are authored by the sibling nightly session (cycle 5878) and are documented
in dream-nightly-2026-10-10.provenance.md. They are NOT this cycle's
deliverables; they share the audit range because both dream tiers run as
concurrent crons on the same host. This cycle's commits are path-scoped to
weekly-only evidence.

Weekly deliverable (cycle 5877) complete and verified:
  dream ~/brain/titus/dreams/2026-10-10-weekly.md (1627B, sha256 pinned
  in committed raw capture; canonical.md committed byte-identical to the
  brain file; verifier verify_dream_weekly_2026-10-10.sh exits 0, RESULT
  PASS, 9/9 checks: sha+size, INDEX append, prose 268 words, prior refs,
  grounding keywords, canonical-identity, live INDEX).