# The close-gate review — measuring and cutting its spend

Depth behind the SKILL.md section of the same name. The governed close review is
often the single largest LLM line item on an agent fleet: every change that
crosses the gate's complexity bar pays for a full model call, and a looping cycle
pays it repeatedly. Treat it as a cost surface in its own right, not as fixed
overhead.

## 1. Read the gate's DECISION, not its declared tiers

**A tier that changes transport or wait budget but resolves the SAME judge model is
a no-op for spend.** Before proposing "route the cheap cases to the cheap judge",
open the resolver the tier actually calls:

```
_tier(cx)                        -> "heavy" | "light"      # decides depth
_call_reviewer(...)              -> the tier picks a TRANSPORT
_light_reviewer_model()          -> what the light tier JUDGES with
```

If the light tier's model resolver returns the canonical (expensive) model unless
an operator explicitly overrides it, then every non-trivial close pays full price
and the tier names are describing latency, not money. Two checks catch this in a
minute: grep the resolver's default, and grep for a second constant holding a
cheaper default (a stray duplicate is where a cheap default creeps back).

## 2. Find where the verdicts are recorded, then count them

The review verdicts land in the loop-governance store as one row per reviewed
blob:

- table `blob_reviews` — `blob_sha`, `verdict`, `findings_json`, `summary`,
  `reviewer_id`, `reviewer_model`, `ts`, `rules_rev`
- table `loop_cycles` — one row per governance cycle, `timestamp` is the CREATION
  time (a later scoring update does not touch it)

**Resolve the store path; do not assume it.** A deployed state directory can hold
a 0-byte stub of the same filename while the live store sits under the component's
`data/` directory — assert the file is non-empty (`-s`) and has the expected
tables before quoting anything from it, and prefer the component's own accessor
(`mod.LOOP_DB`) over a hand-built path.

**Query it read-only, with python when the `sqlite3` CLI is absent:**

```python
import sqlite3
con = sqlite3.connect("file:<abs path>?mode=ro", uri=True)   # never write
con.row_factory = sqlite3.Row
for r in con.execute("select coalesce(nullif(reviewer_model,''),'(empty)') m,\n"
                     "count(*) n, min(ts) first, max(ts) last\n"
                     "from blob_reviews group by 1 order by 2 desc"):
    print(dict(r))
```

**Two artefacts to expect in the answer and not misread:**

1. An `(empty)` model bucket is a *date-bounded* artefact of the writer not always
   naming the judge — it is not a second review class, and rows from that window
   are not missing. Sum by day when you want a total; group by model when you want
   to know who judges today.
2. One close can issue several blob verdicts, and a verdict is cached by blob
   CONTENT, so verdict rows and cycle rows are related, not equal. Report both
   columns per day and say which is which.

## 3. A size-triggered gate is a poor proxy for risk

A gate that decides "review or not" by line/file counts, and depth by a second
pair of counts, spends on arithmetic rather than on risk: a 50-line prose edit buys
a full review while a 45-line rewrite of a security check may not. Two things follow
for the cost work:

- **Enumerate the classes the reviewer adds least to, and bound them with a cheap
  computed predicate** (every changed path is documentation; the range carries no
  executable artifact). Prose has no runtime behaviour for a reviewer to falsify;
  the deterministic checks are the whole gate there.
- **Never let a worker declare its own class.** Compute it from the version-control
diff (paths and line counts), never from a note the worker writes — a
self-declared "docs only" is a bypass, and the same computed predicate is what
keeps every exclusion honest.

**A commit census is a legitimate proxy for how much of the work is that class**
(count commits whose every changed path is documentation, over a window), and it
is cheap. State its limit in the same breath: the review table carries no path
column, so review spend cannot be joined to it — the census motivates the class, it
does not predict the saving.

## 4. Fail-closed rules that keep a skip-class from becoming a hole

1. Unknown path, unresolvable identity, unresolvable diff state ⇒ the DEEP path.
2. Any always-review/protected path in the range ⇒ the DEEP path, checked FIRST.
3. Uncommitted code still counts (never let the class be reached by leaving edits
   unstaged).
4. Every skip is RECORDED as a decision — class plus the predicate's own inputs on
   the cycle row — so a reader can recompute why no judge ran. A skip with no
   recorded reason is treated as deep.
5. Union coverage on push is untouched: no class removes anything from what the
   receipt gate requires.

## 5. Two caps that look like savings and are not

- **Shrinking the reviewer's output-token cap below its reasoning budget is a false
  negative, not a saving.** A reasoning model can spend the whole cap thinking and
  return EMPTY content, which the gate reads as "reviewer unavailable" and uses to
  refuse an otherwise valid close — the expensive outcome (a refused close costs a
  full re-review) dressed as thrift. Size the cap past the reasoning budget, and
  measure before tightening.
- **Trimming what the reviewer reads past the point where it can judge manufactures
  findings.** A reviewer that cannot see the middle of a file reports "content not
  visible", which no edit can answer; each such round is a paid review that buys
  nothing. A bounded window is right; a window too small to contain the change is a
  finding generator.

## 6. Prove a class is safe before widening it

Route a sample of the closes you now skip through the deep judge anyway, record its
verdicts, and tune the class boundaries from the observed defect-escape rate — never
from a model's confidence about its own routing. Until that sample exists, hold the
predicate at its strictest reading (pure documentation, nothing else) and say which
boundary is provisional.