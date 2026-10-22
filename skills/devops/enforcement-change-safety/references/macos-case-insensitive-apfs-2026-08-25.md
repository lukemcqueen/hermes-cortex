# macOS Case-Insensitive APFS vs Git Repos (2026-08-25)

macOS default APFS is case-insensitive (case-preserving): a repo cannot hold
two paths differing only in case, and `git pull`/checkout FAILS on macOS when
an incoming commit introduces such a pair — or when the working tree already
has a file whose on-disk case differs from the tracked name.

Fleet symptom (Titus 2026-08-25): "can't update hermes at the moment (macos
case-insensitive apfs conflicts with hermes repo somehow)". `cortex-update.sh`
ran fine but the checkout stayed at the old commit — because `cortex-update.sh`
DEPLOYS, it does not pull. The pull is what the case conflict blocks.

## Detection (run on a Linux/CI host — case-sensitive FS can hold the pair)

All use `git ls-tree -r --name-only <rev>` (or `git ls-files` for the working
tree). Casefold the full paths; a collision is any duplicate lowercase key
whose originals differ.

1. **Same-tree case dups** (two tracked paths differing only in case):
   ```python
   dup = collections.defaultdict(list)
   for p in paths: dup[p.lower()].append(p)
   for lc, pl in dup.items():
       if len(pl) > 1: print("COLLISION:", " vs ".join(pl))
   ```
2. **Case-only renames between two commits** (same lowercase, different case —
   the classic `git mv Foo foo` that works on Linux then breaks macOS pulls):
   ```python
   old = {p.lower(): p for p in paths(old_rev)}
   new = {p.lower(): p for p in paths(new_rev)}
   for lc in old:
       if lc in new and old[lc] != new[lc]: print(f"{old[lc]} -> {new[lc]}")
   ```
3. **File-vs-directory case clashes** (tracked file `Docs` + tracked dir
   `docs/`): split each path into ancestor prefixes; a clash exists when a
   casefolded prefix equals some OTHER path's casefolded full name.
4. **Incoming-tree check** (what a pull would try to create): run checks 1-3
   against `origin/main` and against the local→remote case-rename set.

## Interpretation

- **Repo content clean** (no collisions at HEAD or in the incoming tree) → the
  conflict is HOST-side: a working-tree file/dir with wrong case, or a stale
  directory remnant from a rename. Fix on the host: `git status` + `git clean -nd`,
  or run `git pull` and read the named conflicting path in the error.
- **Durable host fix:** move the checkout onto a case-sensitive APFS volume
  (`hdiutil create -size 10g -fs "Case-sensitive APFS" -volname cortex ~/cortex.dmg`,
  mount, move repo, symlink old path → new mount).
- **Durable repo fix:** a pre-push case-collision gate (none exists today in
  `secret-leak-detector.sh` / `pre-commit-score` / `adversarial-verify.py` —
  verified 2026-08-25).

## The 18-commit-behind trap (same session)

`cortex-update.sh` output "Updated: 0932eef5 → 0932eef5" — the SAME SHA means
the checkout never advanced; the deploy ran from a stale checkout. Always check
`git merge-base --is-ancestor <local> origin/main` and `git log --oneline
<local>..origin/main` to see what a pull would bring. A stale checkout silently
ships old governance (Titus was missing the review-queue sweep, deployed-gate
smoke check, and TOON fix).
