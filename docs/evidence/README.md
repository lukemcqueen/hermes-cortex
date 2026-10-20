# docs/evidence/ — the run-evidence store

**What this is.** Where a cycle commits the *evidence a reviewer can read and
re-run*: not prose about what happened, but the transcript that shows it. A claim
in a close note is unverified until the output sits here — the reviewer reads the
diff, not your terminal.

This store is browsed **by directory**, not from a row-by-row table in
`docs/DOCS-INDEX.md` (that table went stale on every run, so it now carries one
row for the store instead). Find things with:

```bash
ls docs/evidence | head -40                       # by name/date
find docs/evidence -newermt 2026-10-10 | sort     # by when it landed
git log --oneline -- docs/evidence/<dir>/         # who committed it, when, why
```

## What belongs here

| Kind | Shape |
|---|---|
| Captured run | a command beside **its own exit code** and its real output (`*-2026-10-14.txt`) |
| Runnable verifier | a script that re-checks one landed change and exits non-zero on a failed claim, plus its captured run as `.txt` beside it |
| Provenance / summary | what produced the artifact, which revisions it compares, which fields are volatile by design |
| Phase capture | a per-phase record for a long run (plans, polls, retries) |

## What does NOT belong here

- Prose documentation → `docs/` (index it in `docs/DOCS-INDEX.md`).
- Design docs, ADRs, PRDs, runbooks → `docs/design/`, `docs/adr/`, `docs/prd/`, `docs/runbooks/`.
- A dated record that has stopped being about current behaviour → `docs/older/`.
- Anything a current doc links to as its source of truth.

## Rules

1. **Read-only generators.** An evidence script never repairs what it measures —
   a capture that regenerates the artifact it is comparing can never report it stale.
2. **Redact at the generator.** This repo is public: no `/home/<user>` paths, host
   names, chat ids or tokens on any emitted line. One normaliser in the generator,
   never a hand-patched committed copy (the two drift).
3. **Name the revision.** Record the baseline and the tip (resolved SHAs) when a
   capture claims a before/after; a baseline recorded as "HEAD" is unrepeatable.
4. **State provenance on anything that presents itself as a review.** A file that
   reads as a review must carry `provenance: advisory` (commentary, authorises
   nothing) or `recorded-in: adversarial_reviews review_id=<id>` for a row that
   exists. The doctor's `Review provenance` check FAILs — and blocks every push on
   the host — on an undeclared one (`ops/scripts/quality/review-provenance-check.py`).
5. **Byte-identical snapshots across dates are intentional.** A pair like
   `MEMORY.before-2026-10-19.md` / `MEMORY.after-2026-10-19.md` being identical to
   each other *is* the measurement ("nothing changed that day"), and a repeat of a
   previous date's snapshot means the same thing. They are the record, not
   accidental copies — do not "dedupe" them.
6. **Nothing is deleted to tidy the directory.** Dated captures keep their path and
   name; when a capture stops describing current behaviour it moves to
   `docs/older/` like any other historical record.
