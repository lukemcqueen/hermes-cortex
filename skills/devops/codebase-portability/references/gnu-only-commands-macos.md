# GNU-only commands that break a macOS/BSD caller

Path assumptions are half the portability surface. The other half is a COMMAND whose flag or
semantics differ on BSD/macOS, or that does not exist there — and that failure is worse than a wrong
path, because several of these are silent.

## The inventory and its portable form

| GNU form | macOS/BSD behaviour | Portable form |
|---|---|---|
| `stat -c FMT file` | `illegal option -- c` | `stat -c FMT file 2>/dev/null \|\| stat -f FMTBSD file` |
| `date -r <path>` | `-r` takes SECONDS since epoch, so a PATH is silently read as a number and means something else | hash or compare in Python; use `stat` for mtime |
| `sed -i 's/a/b/' f` | BSD `sed` requires a SUFFIX after `-i`; the bare form errors | `sed -i.bak 's/a/b/' f` — accepted by both GNU and BSD |
| `sha256sum` | absent (perl `shasum` is present) | `sha256sum f 2>/dev/null \|\| shasum -a 256 f`, or hash in Python |
| `readlink -f` | no `-f` | `cd "$(dirname f)" && pwd`, or `os.path.realpath` |
| `grep -P` | absent; a caller that ignores exit status reports ZERO MATCHES and the scan never ran | `grep -E` with POSIX classes (`[[:space:]]`, `(?:` → `(`) |
| `timeout N cmd` | the binary is `gtimeout` (brew coreutils) | probe `command -v timeout \|\| command -v gtimeout`, and NAME the gap if neither exists |
| `nproc`, `free -m` | absent | `sysctl -n hw.ncpu`, `vm_stat` |
| `ps -o etimes` | absent (BSD `ps` has no `etimes`) | `ps -o lstart=` and parse it |

Scan with the same parallel-grep discipline as the path scan:

```bash
grep -rn 'stat -c ' . | grep -v '.git/'
grep -rn 'date -r ' . | grep -v '.git/'
grep -rn "sed -i '[^-]" . | grep -v '.git/'     # bare -i, no suffix
grep -rn 'sha256sum\|readlink -f\|grep -P\|nproc' . | grep -v '.git/'
```

Pay attention to the SILENT ones. `grep -P` exiting 2 into an unchecked pipeline is a portability
bug that reads as "nothing found", and `date -r <path>` produces a number that looks plausible.

## A doc or a skill is a recipe the agent EXECUTES

A GNU-only command inside a SKILL.md breaks the agent following it on that platform, not merely a
script — so recipes are Tier 1 for this class, not Tier 3 ("docs"). Put the portable form INLINE at
the recipe; a footnote elsewhere is not read at the moment of use.

The same rule covers a stale METHOD, which fails more quietly: a verification step still teaching an
mtime comparison after the real method became a content hash gives a confidently wrong answer with
no error at all. When a method changes, every recipe that teaches the old one is a defect in the
same sweep.

## Sweeping many files safely

Bulk-editing prose across a doc tree is where a sweep quietly makes things worse. Drive it as a
SCRIPTED exact-substring replacement, not a series of fuzzy patches:

- **Assert a match count of exactly 1 per edit before writing anything.** A script that raises when
  `text.count(old) != 1` catches the rename that would have silently hit three places — or none. The
  batch becomes one auditable step instead of N chances to drift.
- **Never hand-craft a parenthetical inside inline code.** Wrapping a command mid-line
  (`cmd (macOS: other`) leaves an UNBALANCED backtick: it breaks rendering and, worse, yields a
  recipe that still reads as valid. Use a whole-line fallback (`a 2>/dev/null || b`) or a note on its
  own line.
- **Re-grep to prove zero remaining, in the same pass**, and state the number — "I fixed them all"
  is a claim the re-run settles.
- **Read back the first file's diff before applying to the rest.** One corrupted line replicated
  across seventeen files is seventeen times the cleanup.
- **Leave the teaching mentions alone.** Text that MENTIONS `grep -P` or `date -r` as a hazard, and a
  portability table that documents the difference, are not recipes — sweeping them out destroys the
  warning that prevents the bug.
