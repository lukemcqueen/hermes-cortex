# PII Content Gate — scope surfaces and the home-folder hole

How to keep a write-tool PII gate leak-proof when the leak is not in the shared
surface. The gate's job is to block uniquely-personal identifiers wherever they
could reach the public repo — including the home folder.

## Two PII classes, two block scopes — do not mix them

1. **Uniquely-personal identifiers (the deny-list: operator surname, WAN
   address, full personal names) are path-INDEPENDENT — block on ANY write
   target.** A home-folder write (`~/.hermes`, `~/.steadfaste-fleet/` deploy
   copy, memory, brain, notes, scratch) is one `skill_manage` / `cortex-update`
   deploy / `git add` away from the public repo, so these terms must never be
   written anywhere. The exact hole is an early `if not content or not shared:
   return None` that skips ALL PII checks for a non-shared-surface path — move
   the deny-list check BEFORE that branch so it runs regardless of path.

2. **Real emails / phone numbers / private server URLs stay shared-surface
   scoped only** (repo + `~/.hermes/skills`). Client and private operational
   files legitimately carry real addresses, ports, hosts and formatted numbers;
   blocking them everywhere breaks legitimate non-public work. Gate those
   checks on `_is_shared_surface_path`, not the deny-list.

## A git commit is NOT a write tool

A write-tool gate intercepts `write_file`/`patch`/`skill_manage` only. A
multi-file `git commit` bypasses it entirely and relies on the pre-commit
secret-leak detector. When a deny-listed identifier reaches a repo commit,
investigate BOTH the commit-time detector AND the write-gate scope: the write
gate may be structurally scoped to shared paths, so a deny-listed term written
into the home folder then committed was never seen by either layer.

## Testing the deny-list without ever restating the real PII

- Inject a SYNTHETIC term into `_PII_SENSITIVE_DIGESTS` (monkeypatch) to
  exercise the mechanism end-to-end without touching the real identifiers.
- Derive one REAL deny-list value from an already-public source (the repo's own
  GitHub URL owner handle parsed from README) — it is the one real value
  exercisable without restating anything.
- Assemble PII-shaped fixtures at runtime from concatenated string parts so the
  test file itself never contains a literal the gate would block (Rule: a
  scanner that scans its own source cannot restate its fixtures).
- Assert the URL-context allowlist still works on a NON-shared path (the
  sanctioned repo URL is allowed even in the home folder).
- Assert emails/phones in the home folder are still ALLOWED — this proves the
  fix blocked the deny-list without over-blocking legitimate operational
  writes.
