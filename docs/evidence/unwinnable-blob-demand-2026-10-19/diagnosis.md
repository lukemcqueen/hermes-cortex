# DIAGNOSIS + FIX PLAN — the unwinnable per-blob class (cycle 13384)

**DeepSeek Pro reviewed this plan** (`adversarial_reviews`, cycle 13384, reviewer
`deepseek/deepseek-v4-pro`, verdict FINDINGS) and all three findings are resolved here:

- **ADV-13384-1 (medium)** — *the receipt must record each deleted path individually, not one shared
  entry for the sentinel.* Confirmed and now asserted: the receipt is keyed BY PATH with the sentinel
  as the value, and `tests/test_blob_deleted_scope.py` pins two deleted paths recorded separately,
  plus a real unjudged file NOT named as covered. The consumer compares `(path, value)` pairs, so one
  entry cannot authorise another path.
- **ADV-13384-2 (medium)** — *a blob whose recorded verdict is non-clean and whose content cannot
  change still stays in `remaining` for ever.* Correct, and NOT fixed by part A/B — this fix removes
  the class that made it unrecoverable in practice (absent-at-tip paths), but a real file whose fix
  the reviewer refuses remains. That is a JUDGEMENT problem, not a structural one, and its documented
  exits already exist: fix and commit a new blob, `rereview_change`, or a fresh base — an override is
  the last resort and stays operator-only. Recorded here rather than quietly claimed as covered.
- **ADV-13384-3 (info)** — *justify that the range review sees the deletion.* Pointer added at the
  call site: a receipt is written only from a permitted close, and for an always-review range that
  close already required the range verdict that saw the deletion (`_complete_push_range_blobs` →
  `_write_review_receipt`).

Reported by Titus (2026-10-19), verbatim symptoms:

> Three consecutive passes now report `reviewed this pass: 0` with all 9 still pending — the
> reviewer has stopped issuing verdicts for this cycle. Their findings are all of one form: "prove,
> from within this file's diff, that this test executes and its collaborators exist."
> The root cause is the stored range base `4de736d`: it predates the generator_v4 → generator
> rename, so the list contains 153 paths that no longer exist and omits the current ones.

## 1. What the code does (read, not guessed)

`ops/scripts/lib/review-receipt-check.py:42-62` — the blob set for a range:

```python
diff = subprocess.run(["git","-C",str(repo),"diff","--name-only",f"{base}..{tip}"], ...)
for path in [ln.strip() for ln in diff.stdout.splitlines() if ln.strip()]:
    rev = subprocess.run(["git","-C",str(repo),"rev-parse","--verify","--quiet", f"{tip}:{path}"], ...)
    sha = (rev.stdout or "").strip()
    out[path] = sha if sha else DELETED        # DELETED = "deleted"  (line 39)
```

So a path that the range changed but that does **not exist at tip** enters the set with the sentinel
`"deleted"`. A rename (`generator_v4/x` → `generator/x`) leaves every old path in the set across a
base that predates it — Titus's 153 phantom paths.

`mcp-servers/loop-gov-mcp.py:1341-1352` — how the pass treats them:

```python
for path, sha in sorted((blobs or {}).items()):
    if sha in covered:            # CLEAN or non-blocking findings
        verdicts[sha] = "CLEAN"; continue
    if recorded.get(sha):
        # Deliberately in BOTH lists: ... A skipped blob is not covered, so it must stay in
        # remaining or the receipt would claim a file nobody vouched for.
        already_judged.append(...); remaining.append(...); continue
```

Two consequences, and together they are the deadlock:

1. A blob whose content carries a **recorded non-clean verdict is never re-sent** to the reviewer —
   correct for identical content, but it stays in `remaining`. If the content can never change (a
   deleted or renamed-away path has no content at all), that path can **never** leave `remaining`:
   `reviewed this pass: 0`, all N still pending, for ever.
2. A path that does not exist at tip has no reviewable content, so no verdict can ever satisfy the
   demand — the reviewer's own demand ("prove from within this file's diff that X executes") is
   unsatisfiable BY CONSTRUCTION for such a path.

## 2. Proposed fix (two parts, both needed)

- **A. The DEMAND never includes a path that does not exist at tip.** In `_complete_blob_reviews`,
  drop entries whose sha is the `DELETED` sentinel before the pass runs, and disclose the count and
  a sample in the close message. A deletion is not unreviewed content; it is the absence of content,
  and the whole-range verdict still sees the deletion in the diff.
- **B. The RECEIPT still names them, as covered-by-deletion.** Otherwise the push gate (which queries
  the same blob set, including the sentinel) would keep refusing the range and the deadlock would
  simply move one step later. Covered-by-deletion is an authorisation fact ("this path is gone at
  this tip"), not a claim that anyone read content — and it must be labelled as such in the receipt.

Fail-closed direction is preserved: this only ever removes paths that CANNOT be judged, and every
path that exists is still demanded exactly as before. Nothing that exists becomes easier to close.

## 3. What I am NOT doing

Not changing the requirement that a real file's behaviour needs a committed, re-runnable proof — the
class Titus hit with "the renderer faithfully prints a raw principle; the sanitizer strips actions"
was a REAL finding, correctly raised, and his corrected test is the right answer. Only the
unsatisfiable-by-construction case changes.

## 4. Question for the reviewer

1. Is B (a receipt naming a deleted path as covered-by-deletion) an acceptable authorisation, or does
   it weaken the receipt in a way I have not seen? If it does, what is the correct alternative to the
   deadlock — refuse the close entirely while a stale base exists, and require a fresh base?
2. Is there a second deadlock of the same shape: any blob whose recorded verdict is non-clean and
   whose content cannot change (e.g. it is generated, or the file is gone from the working tree) —
   and should the pass distinguish "cannot be re-judged" from "has not been judged yet" in its
   message?
