---
name: documentation-consolidation
version: 1.0.0
category: software-development
description: "Use when reorganizing, pruning, or merging a docs corpus."
tags: [docs, consolidation, pruning, merge, archive, docs-index]
related_skills: [documentation-auditing, repo-health-review, doc-size-budget, skill-curation]
platforms: [linux, macos]
---

# Documentation Consolidation

Restructuring a documentation corpus — splitting it by currency, pruning
redundancy, merging overlapping docs — without losing provenance or breaking
links. This is the **reorganize** counterpart to `documentation-auditing`,
which only *finds* stale references.

## When to Use

- "Clean up all the documents", "be thorough, prune where you can, merge where you can"
- "Organize into current and older docs areas"
- Two docs cover the same topic, or one subtree looks duplicated
- The corpus has outgrown what a reader can scan, or the index no longer matches disk

## Always-On Rules

1. **Archive, never delete.** A doc that stops being *true* is **moved**, not
   removed — an old decision still needs its provenance, and git history is not
   browsable. Deletion is reserved for provably redundant content: files that
   are byte-identical duplicates of a surviving copy.
2. **Split by currency, not by topic.** `docs/` = current; `docs/older/` =
   historical. **Preserve the relative path** on the move
   (`docs/<path>` -> `docs/older/<path>`) so a doc's origin stays obvious.
3. **Diff before deleting a suspected duplicate.** A subtree that *looks*
   duplicated frequently carries files that exist nowhere else. Establish the
   unique set first, merge those up, and drop only the byte-identical copies.
4. **One document per topic.** Two docs each holding half a topic is a merge
   waiting to happen — pick the canonical filename and fold the other in.
5. **Never move without sweeping references in the same cycle.** A dangling
   link is a worse outcome than the untidy layout you were fixing.
6. **The index is part of the change.** A restructure that leaves the index
   describing the old layout is only half done.

## Classification — what belongs in the "older" area

| Signal | Kind of doc |
|---|---|
| A date in the filename | completed plan, incident record, session note |
| Header says deprecated / superseded / replaced by X | superseded design |
| The work it describes already shipped | plan that is now provenance, not instruction |
| It records a move ("we went from A to B") | migration record — read once, then historical |
| It documents a failure mode absent from current code | stale troubleshooting |
| Design material for a *different* project, kept for reference | foreign-project archive |

**Keep in current:** anything a live doc links to as the source of truth,
operational runbooks, references, ADRs, PRDs, templates, and any design doc that
still describes live behaviour. When a live doc points at a predecessor, moving
that predecessor is fine — just repoint the link.

The archive area ships its own `README` stating what belongs there, what does
not, and the move procedure. Readers arrive there by accident far more often
than by intent.

## Procedure

### 1. Survey before touching anything

```bash
find docs -name '*.md' | wc -l            # corpus size
du -sh docs/*/ | sort -rh | head -20      # where the weight is
find docs -name '*.md' -printf '%s %p\n' | sort -rn | head -20
```

List the whole set by path and classify it before moving a single file — the
"older" set is a judgement call, and seeing the flat list is what makes the
duplicated and half-overlapping pairs jump out.

### 2. Split current vs older

```bash
mkdir -p docs/older
move() { mkdir -p "docs/older/$(dirname "$1")"; git mv "docs/$1" "docs/older/$1"; }
move some-dated-record.md
move design/superseded-thing.md
```

Then `rmdir` every directory the moves emptied — they linger otherwise and
re-invite stray files.

### 3. Prune duplicated subtrees — establish unique-vs-copy first

```bash
# how many .md files are byte-identical to another?
find docs -name '*.md' -exec md5sum {} + | awk '{print $1}' | sort | uniq -d | wc -l

# which files exist ONLY inside the suspected copy?
find <copy>/ -name '*.md' | while read -r f; do
  rel=${f#<copy-prefix>/}
  [ -f "$rel" ] || echo "UNIQUE: $rel"
done
```

Merge the unique files up into the canonical tree (creating parent dirs), then
remove the copy subtree. Re-run the duplicate-hash count afterwards: the only
acceptable result is `0`.

### 4. Merge half-documents

A tell-tale: a file titled "X Reference" that contains **none** of X, while the
real content sits in a differently-scoped file. Confirm the split by grepping a
few known names from each half against the other:

```bash
for v in NAME_A NAME_B NAME_C; do echo "$v: $(grep -c "$v" docs/x.md)"; done
```

Fold one into the other under the surviving filename, delete the source, and
repoint every reference to it. Prefer the filename a reader or another doc
already treats as canonical.

### 5. Sweep references

Grep each moved or deleted path across every consumer type **before** committing:

```bash
grep -rn 'docs/<moved-path>' --include=*.md --include=*.py --include=*.sh --include=*.txt .
```

Repoint every hit, including references from `skills/`, `AGENTS.md`, and
scripts — docs are read by agents, so a stale path there misleads all of them.

**Exempt the docs that deliberately document the removed path.** Migration
runbooks and ADRs describe the *old* layout on purpose; a blanket replace
corrupts exactly the files that must keep it.

### 6. Make the index honest

- Add the new area to the index's header note (what `docs/` vs `docs/older/` mean).
- Correct any index entry whose description no longer matches the file.
- Every entry must resolve — verify, do not eyeball.

### 7. Verify, then commit -> deploy -> push

Run the verification block below. Then the normal shared-repo chain:
`commit` -> `cortex-update.sh` (deploy) -> `push`. The pre-push gate compares the
deployed copy against the repo, so **editing a deployed script shows as a
checksum FAIL until you deploy** — that is a pending deploy, not breakage; do
not "fix" it by reverting the edit.

## Pitfalls

- **A path sweep rewrites MESSAGE STRINGS, not just paths.** A checker whose
  *output* names a bad path (e.g. reporting a `stray <path>`) gets rewritten to
  name the **good** path — the detection logic still works, but the message now
  misreports which path is wrong. After any sweep, re-read every check that
  mentions the swept path and separate the *logic* from the *message*; fix the
  message, leave the logic.
- **`git mv` on a directory fails when it holds tracked-but-deleted paths**
  (`fatal: bad source`). Stage the deletions first (`git add -A <dir>`), then
  re-run the move — or `mv` and let `git add -A` detect the renames.
- **`git rm` refuses a file with local modifications** — a path sweep usually
  leaves uncommitted edits. Either commit the sweep first or use `git rm -f`;
  never let the refusal tempt you into leaving both copies.
- **A file blocklisted by `.gitignore` (e.g. a name matching `*secret*`) cannot
  be committed under that name** — rename it rather than weakening the ignore.
- **Emptied directories linger** — `rmdir` them; a stray empty dir re-invites
  files that belong in current.
- **Don't re-litigate a settled classification.** Once a doc is in the archive,
  leave it there; re-deriving the same decision is churn, not thoroughness.
- **Deleting is the one irreversible act here.** Confirm byte-identity (hash,
  not eyeball) before removing any file that has no surviving copy.

## Verification

```bash
# 1. index integrity — every path it cites must exist
python3 - <<'EOF'
import re, pathlib
root = pathlib.Path('.')
idx = (root/'docs/DOCS-INDEX.md').read_text()
bad = [m.group(1) for m in re.finditer(r'`((?:docs|ops|skills)/[^`]+\.(?:md|py|sh))`', idx)
       if not (root/m.group(1)).exists()]
print('broken:', len(bad)); [print('  MISSING:', b) for b in bad[:15]]
EOF

# 2. no duplicate content left
find docs -name '*.md' -exec md5sum {} + | awk '{print $1}' | sort | uniq -d | wc -l

# 3. no stale references to the moved paths (excluding the exempt docs)
grep -rn '<old-path>' --include=*.md --include=*.py docs/ skills/ AGENTS.md | grep -v '<exempt-doc>'

# 4. current vs archived counts
find docs -name '*.md' -not -path 'docs/older/*' | wc -l
find docs/older -name '*.md' | wc -l

# 5. doctor clean after deploy
python3 ops/scripts/manage/cortex-doctor.py 2>&1 | grep -iE 'Overall'
```

Acceptance: `broken: 0`, duplicate count `0`, stale refs `0`, doctor `0 fail`.

## Reporting

Lead with the numbers (current count, archived count, duplicates dropped,
references fixed), then the one or two judgement calls worth a human's review —
which subtree was a near-duplicate rather than a duplicate, and which doc you
merged into which. Flag anything you deliberately left alone and why; a
reviewer needs to know the difference between "clean" and "not looked at".
