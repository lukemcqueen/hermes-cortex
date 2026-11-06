# The end_change blob-close loop — driving a large range to closure

The `end_change` close gate judges the push range's blobs in waves. For ranges with
dozens of files this is the long pole of the close; know its mechanics before starting.

## The loop

- Each `end_change` wave runs ~4 concurrent per-blob reviewer calls inside ONE 240s
  client window (the whole-range review is REFUSED for large own-diffs — over the split
  threshold — so a big range gets pure blob waves). A 350-file sweep ≈ 90 waves ≈ an
  hour-plus of serial `end_change` calls, each answering "Cannot close yet: N blob(s)".
  Budget for it; do not mistake the loop for a hang.
- Verdicts are keyed by blob CONTENT: a blob already CLEAN is never re-judged. Stacking a
  second sweep on an unclosed range only adds the NEW/changed blobs — the delta, not the
  whole range.
- The per-blob reviewer REFUSES the close on documentary stragglers: a prose line whose
  sibling on the same line was renamed, a docstring naming the pre-rename function. Each
  refusal is a precise fix — patch the named file (content change re-opens ONLY that
  blob), commit, `end_change` again. The loop surfaces stragglers one file at a time
  across the remainder; functional old-name references (shims, dual-accept regexes,
  restore utilities) pass untouched.
- The receipt mints when coverage completes: the session closes and
  `~/.steadfaste-fleet/state/.reviewed-<slug>-<tip>.json` appears; a LONE `git push`
  (nothing joined to it) is then receipt-authorised and prints the receipt path.

## Pitfalls

- **A subagent cannot grind the loop.** A child session's `end_change` with the parent's
  task_id finds no pending cycle in ITS session and mints one empty MOVE_ON cycle per call
  — ledger pollution, zero progress. The loop advances only from the lock-owning session.
- **Re-review material must be refreshed every round.** Re-submitting the same material
  whose claims the fixes superseded makes the reviewer file a "fabrication" finding
  against the stale text. Before `--re-review`, rewrite the material to name the committed
  artifacts (file paths, test names, the evidence doc) and the corrected numbers.
- **The reviewer needs `--reviewer-id` (the pro model) and `--material-file`** — a bare
  `--review` errors "requires --reviewer-id"; a material path passed as prose is refused
  as unverified; read the file with `--material-file`.
- **The advisory on a refused close is normal** — "close REFUSED ... nothing blocked"
  while the lock is held and the new commit stacks under it; fix the findings, then the
  next `end_change` re-opens judgment on the new blobs.
