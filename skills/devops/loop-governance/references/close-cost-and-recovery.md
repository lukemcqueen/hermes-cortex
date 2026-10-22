# Closing under the per-blob regime — cost, driving the loop, and recovery

Depth for the close gate once a change is wide enough that the whole-range review
re-routes. Read this when a close is taking many rounds, when a lock looks
unclosable, or when the reviewer's identity is in question.

## 1. The cost model: one client call judges ONE blob

The close is bounded by the MCP CLIENT's tool-call window, not by the reviewer's
goodwill. The shipped arithmetic (constants in `mcp-servers/loop-gov-mcp.py`):

- one client window is ~300s;
- the close's own budget is `CLOSE_TOTAL_BUDGET_S` (~240s) so a pass cannot reach the ceiling;
- ONE blob review call measures 180–220s.

`CLOSE_BLOBS_PER_WINDOW` blobs are judged per pass, and they are issued **concurrently**
(`BLOB_REVIEW_CONCURRENCY`, default 4). Elapsed time is the SLOWEST call, not their sum — four
~200s calls issued together all land inside the same 240s window, where four issued one after
another would need ~800s and fit only the first. A sequential pass judges exactly ONE blob, which
is what made a 15-blob range cost 15 `end_change` calls.

**DO NOT RAISE THE CLIENT CEILING.** The window is a bound the operator set in so many words
(recorded in the module: reviews stay shorter than 300s, and the window is never raised).
`mcp_servers.<name>.timeout` looks like the obvious lever and is a contradiction of that
requirement — if you catch yourself recommending it, you are solving a different problem. There is
exactly one legitimate way to fit more work in the window: judge more of it SIMULTANEOUSLY. Do not
"fix" the cost by lowering thresholds, shortening the reviewer's budget, or skipping blobs; those
trade coverage for wall clock, which is exactly backwards.

**A "this was already fixed" report can be about an ADJACENT symptom — check which problem the
landed commits address.** The window work (one close, one client window — a close always returns a
verdict) is genuinely fixed and its own history says so; the per-pass blob COUNT is a separate
quantity it never touched. Before repeating the claim or concluding the reporter is wrong, read what
the commits changed (`git log -S <constant>` on the file that holds the number) and say which
symptom is closed and which is still open. Two different defects in one area read as one, in both
directions.

### Making bounded work concurrent — the rules the review will demand

The pattern is a WAVE, and each rule below is one a reviewer filed as a real finding when it was
missing:

- **Enforce the deadline AFTER issuing, not only before.** A pre-wave check runs once, and the
  wave's cost is its slowest call — so a wave started with little window left can still outrun it
  and be killed by the client at the ceiling, writing NO receipt and losing the whole pass. Await
  each future only until an absolute deadline, and treat a call that has not answered by then as
  FAILED (never credited), so the pass still refuses and the next one retries it.
- **Shut the pool down WITHOUT waiting** (`shutdown(wait=False)`) and cancel futures that never
  started, or a straggler holds the pass past the window. That is safe only while the worker does
  nothing but CALL: every write — the verdict row, the findings — must stay in the pass loop, for
  outcomes it COLLECTED. Say so at the call site and pin it with a test asserting a timed-out blob
  leaves ZERO rows in the store.
- **A worker must never raise out.** Wrap the call so a failure returns as data, and read every
  result inside `try/except` — an exception escaping `future.result()` aborts the whole pass
  instead of failing one blob.
- **Process results in SORTED ORDER**, whatever order the calls finish in, or the verdicts, the
  outage decision and the logs depend on which reviewer answered first.
- **Keep `workers=1` reproducing the old sequential behaviour** and assert it: the change must not
  alter the one-at-a-time path.
- **A failing worker never credits its blob** (it lands in both `failed` and `remaining`) while its
  siblings are still judged — progress, never stop-on-first. The consecutive-failure cap still
  means the reviewer is DOWN and defers the rest by name.
- **Assert what the DESIGN guarantees, not an imagined count.** With an outage cap of N
  consecutive failures, a wave stops early, so "all four are in `failed`" is the wrong assertion;
  assert that something was recorded failed and NOTHING was credited.
- **A test budget smaller than the cheap setup work tests nothing.** When the pass spends its budget
  on lookups before reaching the wave, a tiny budget defers everything and the branch under test is
  never entered — pick a budget that is past the setup and well short of the call.

## 2. Driving the close loop

`end_change` is resumable by design: verdicts are keyed by blob CONTENT, so a pass
that judged one blob leaves the rest recorded as still unreviewed and the next call
CONTINUES from there rather than redoing it. So the loop is:

1. call `end_change`;
2. read what it reports — `reviewed this pass`, `CLEAN in the range`, and the
   remaining list;
3. repeat until it either returns a receipt or returns FINDINGS.

Expect up to `CLOSE_BLOBS_PER_WINDOW` blobs per pass, budget ~1–3 minutes each; do not treat a
partial pass as a dead end and do not re-run a "failed" close — it succeeded at judging a wave.
A blob marked `already judged, not clean` will NOT be re-reviewed: identical content
cannot produce a different verdict, so the fix is to change the FILE and commit it
(the new content is a new blob).

**That rule creates a deadlock when the finding is about a SIBLING file.** A per-blob reviewer reads
ONE file, so it can demand something that already exists elsewhere in the same range — a test, a
helper, a doc the blob cannot see — and the close then refuses forever: the demand is unsatisfiable
from the blob's material, and the blob is never re-judged because its content has not changed.
Record the measurement that refutes it and resolve the CYCLE (`rereview_change` with a note naming
the file and test that already satisfy it), then remove the recurrence by NAMING that coverage
INSIDE the blob under review. Adding the pointer is the honest fix — it makes the demand answerable
from the material, rather than leaving the next reviewer to raise it again.

## 3. Recovering a lock whose task has no cycle

Symptom — a session holds a LIVE lock and every exit names the other exit's
precondition:

- `end_change` → "Cannot release lock: no governance cycle found for this task";
- `begin_change` → "A governance session is already active … use force=True";
- `feedback_accept` → "No PENDING cycle found";
- `resume_from_interrupt` → "No active governance lock" while the lock file is live;
- a bare `check_lock()` reports `active: false` (it cannot resolve the session —
the lock FILE is the truth).

Cause: a task that RENAMED the lock's task_id (a sub-task created by
`request_interruption`) without creating the corresponding `loop_cycles` row. Every
cycle is created by `begin_change`, which the second message refuses, so the
instruction in the first message is not followable and the only named exit is an
override.

**Recovery that does not override.** Reconstitute the missing row with the module's
own helper, then score and close it like any other cycle:

```bash
cd <repo>
python3 - <<'PY'
import importlib.util, json
spec = importlib.util.spec_from_file_location("m", "mcp-servers/loop-gov-mcp.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
task = "<the task_id in the lock file>"
sid  = json.loads((m.GOVERNANCE_STATE_DIR / ".governance-<session>.json").read_text()).get("session_id", "")
m._create_pending_cycle(task, sid, "Reconstituted: the lock's task had no cycle")
PY
```

Then `feedback_accept(cycle_id=…)` with the real work's evidence, then `end_change`.
The lock is released by the close, the push receipt is written normally, and nothing
was forced. A missing row is the MECHANISM failing, not a verdict to override —
recording the work honestly is the repair.

## 4. Which store holds the verdict

- `blob_reviews` — one row per blob SHA (per-blob pass). The authoritative record
  for "was this CONTENT judged".
- `adversarial_reviews` — one row per CYCLE id. This is what `rereview_change`
  reads, and the table the docs mean by "findings are durable".

A per-blob FINDINGS refusal must write BOTH, or re-review is unreachable. Check
which one a refusal came from before telling anyone the exit exists.

## 5. Making the judge visible

Every recorded verdict should name the model that produced it. Read it rather than
inferring it, and prefer the rows written most recently:

```bash
python3 -c "import sqlite3,os; c=sqlite3.connect('file:'+os.path.expanduser('~/.hermes-cortex/data/loop-governance.db')+'?mode=ro',uri=True); print(c.execute('SELECT blob_sha,verdict,reviewer_model,ts FROM blob_reviews ORDER BY ts DESC LIMIT 5').fetchall())"
```

An empty `reviewer_model` in RECENT rows means the writer is not receiving it, and
a tiering or default-model change cannot be verified from the record — which is how
a weak-model default can sit unnoticed on a fleet that documents a strong one.
Changing a default in `mcp-servers/loop-gov-mcp.py` is NOT live until the daemon is
restarted: check the process start time against the deployed file's mtime before
claiming the behaviour changed.

## 6. Regenerated reports must not be review material

A committed generated report becomes a blob in every range that regenerates it, and
the reviewer then files findings about failures in files the change never touched.
Keep such output ignored/untracked (it is still produced and still read) and let the
committed GUARD be what the review judges — see `adversarial-finding-fix-patterns`,
"Keep GENERATED output out of the review range".
