# Verdict-store diagnostics

The close-time review store answers "what still blocks my close" directly, and it is the
only place that can distinguish a finding about YOUR work from a verdict recorded by
someone else's pass. Read it before reworking anything.

## Open it the way the component does

Resolve the store through the module's own accessor and open it READ-ONLY:

```python
import importlib.util, sqlite3
from pathlib import Path
src = Path.home() / ".hermes-cortex/tools/loop-governance/loop-gov-mcp.py"   # the DEPLOYED copy
spec = importlib.util.spec_from_file_location("lg", src)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)          # import-time write is its own log file, nothing else
con = sqlite3.connect("file:%s?mode=ro" % mod.LOOP_DB, uri=True)
```

Two reasons this shape matters. `mode=ro` means a diagnostic can never be mistaken for a
write. And the accessor is the only route that RUNS: a script (or command) that names the
store FILE by path can be refused outright by the execution guard, which must scan a
script's referenced paths and cannot scan a file over its cap — the accessor is both the
sanctioned route and the one that executes.

## Tables worth knowing

| Table | Grain | Columns you will use |
|---|---|---|
| `loop_cycles` | one row per cycle | `id, task_id, decision, composite, completeness, quality, progress, session_id, timestamp, unscored_reason, outcome_note, user_overrode` |
| `blob_reviews` | one row per blob CONTENT (sha), shared by every session | `blob_sha, verdict, findings_json, summary, reviewer_model, ts` |
| `adversarial_reviews` | whole-range verdict per cycle | `cycle_id, findings_json` |

`timestamp` on `loop_cycles` is the row's CREATION time: the scoring UPDATE writes
completeness/quality/progress/composite/decision/outcome_note and never the timestamp. It
cannot be used to time a score or to argue ordering.

There is no `cycles` table and no `blob_path` column — the verdict is keyed by content, so
a path is not stored with it. Probe first, then quote:
`SELECT name FROM sqlite_master WHERE type='table'`.

## One query: what still blocks the close

Map the CURRENT push range's blobs to their verdicts and print the blocking severities:

```python
blobs = mod._push_range_blobs(repo)                  # {path: blob sha} for base..HEAD
rows = {r[0]: r[1] for r in con.execute(
    "SELECT blob_sha, findings_json FROM blob_reviews")}
for path, sha in sorted(blobs.items()):
    fj = rows.get(sha)
    print(path, "NO VERDICT" if fj is None else "judged")
    # a blob with no row still needs a verdict before the receipt can cover the range
```

A receipt may name only blobs that are COVERED: a `CLEAN` verdict, or a `FINDINGS` verdict whose
findings are all below blocking. Two values are NOT coverage — `FINDINGS` with an EMPTY findings
array, and the absence of a row. `UNJUDGED` is not a verdict at all: the pass never writes it (so the
content stays retryable) and it credits nothing if a row somehow exists. "NO VERDICT" here is exactly
the coverage the next close has to earn — not a finding to fix.

## Telling a FOREIGN verdict from your own

A verdict is written by whichever session's pass reached that blob first, and the pass
embeds the CALLING cycle's task in the material it sends. So a `scope-drift` finding whose
evidence quotes a task you never ran was recorded by another session's close over the same
unpushed range. It is not fixable from your side (the complaint is that your work is not
their task), and it will read as blocking to your close.

- Confirm the judging cycle: `SELECT id, task_id, session_id, timestamp FROM loop_cycles
  WHERE id = <the id in the finding_id>`. A `session_id` starting `cron_` is an unattended
  close, which happens while your range is unpushed.
- The way out is NEW content on those paths: a fresh sha is judged by YOUR pass under YOUR
  context, and the row is overwritten (`INSERT OR REPLACE` on the sha). That is also why a
  real finding and a foreign one look identical from the outside — both are cleared by
  changing the content, so read the evidence text before deciding which one you have.

## Content keying decides what can be fixed WHERE

`blob_reviews` is keyed by sha and the pass SKIPS content that already has a recorded verdict, so two
consequences decide whether a range can close at all:

- **A blocking verdict is cleared only by NEW CONTENT on that path.** Edit the file, commit, and the
  new sha is judged fresh under your own context.
- **When the fix belongs in a DIFFERENT file** (the reviewer wanted a sibling test, or a pointer to an
  artifact), the blocked file must still CHANGE — its frozen verdict is skipped forever otherwise, and
  the range can never close. Give it a real edit (a comment naming the new test, a docstring naming
  the artifact), not a whitespace touch, and commit both paths in the same range.

Read the state per blob instead of guessing which file is holding the range:

```sql
SELECT blob_sha, verdict, findings_json FROM blob_reviews WHERE blob_sha IN (<the range's shas>);
```

`findings_json = '[]'` is the not-coverage shape described above, and a `UNJUDGED` row should not exist
at all — if one does, a writer is recording non-verdicts and that writer is the bug.

## Where the numbers live when you cite them

`blob_reviews.summary` holds the reviewer's own summary text and `findings_json` the
findings array. Quote them the way they are stored — a `grep` of an artifact is not the
same thing as the store's row, and a claim about either belongs in a committed artifact
if you intend the close reviewer to check it.
