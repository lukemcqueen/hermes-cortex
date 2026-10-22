---
name: adversarial-finding-fix-patterns
description: "Fix adversarial-verify.py findings with real handling."
version: 1.0.0
category: software-development
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [adversarial, verification, findings, security, quality]
    related_skills: [adversarial-verifier, change-checklist, agent-contract]
---

# Adversarial Finding Fix Patterns

How to fix findings from `adversarial-verify.py` (the A2/A4 gate that runs on
every script change in this fleet) so the gate passes with real handling, not
no-ops. Complements the pinned `adversarial-verifier` skill — that one defines
the process; this one has the concrete fix patterns for findings agents
actually hit. Discovered 2026-08-08 while hardening
`ops/scripts/lib/telegram_notify.py` (task-lifecycle S2).

## When to Use

- `adversarial-verify.py --file X --level A2 --gate` reports medium findings
- The pre-commit hook blocks a commit with "critical/high findings"
- You're about to "fix" a finding by adding `pass` or a comment (STOP — read
  the empty-except rule below)

## Fix Patterns

### 1. Empty-except cheat detection — regex behavior

The cheat-detection regex
(`except\b[^\n:]*:\s*(?:\n[ \t]*)?(?:pass|#.*)`) flags an `except X:` whose
body is `pass` **or a comment-only first line**, and even an inline comment
on the except line itself:

```python
# ❌ FLAGGED — comment is the first line of the body
except OSError:
    # fallback comment
    sys.stderr.write(...)

# ❌ FLAGGED — inline comment on the except line counts as the "body"
except Exception as e:  # network error
    handle(e)

# ✅ NOT flagged — first body line is real code, comment comes after
except OSError:
    sys.stderr.write(...)  # fallback — never raise
```

**Rule:** never start an except body with a comment line, and never put an
inline comment on the `except` line. Put the comment after the first real
statement.

### 2. Input fuzzing on exception constructors

The fuzzer passes `None`, `''`, `-1` to constructor params. A
`f"{value:.0f}"` format string crashes on `None`. Coerce + clamp inside
`__init__` so every input is safe:

```python
class _RateLimited(Exception):
    def __init__(self, retry_after: float = 2.0):
        try:
            retry_after = float(retry_after)
        except (TypeError, ValueError):
            retry_after = 2.0
        self.retry_after = max(0.0, min(retry_after, CAP_S))
        super().__init__(f"rate limited (retry in {self.retry_after:.0f}s)")
```

Verify empirically after the fix: instantiate with `None`, `-5`, `'abc'`, and
a huge number; confirm all produce sane clamped values. `float(None)` raises
TypeError, which the try/except turns into the default — the finding is then
stale, and running the values proves it.

### 3. Context-manager `__exit__(*exc)` "finding" is a false positive

`input-fuzzing` flags `__exit__()` with `*exc -> None`. That IS the context
manager protocol — on clean exit Python calls `__exit__(None, None, None)`.
Verify by instantiating the manager in a `with` block; if it exits cleanly,
the finding is protocol behavior, not a bug. Document that in the delivery
evidence rather than contorting the code.

### 4. Extracted/copied code inherits the source's findings — verify baseline, don't re-fix

When you extract or copy a module into a new file and the gate flags findings
on it, those may be **inherited from the source**, not introduced by your
change. Before "fixing" anything, run the SAME gate level on the ORIGINAL
file:

```bash
python3 ~/.hermes-cortex/scripts/adversarial-verify.py --file <original>.py --level A4
```

- **Identical findings** (same technique + target + parameter) → baseline.
  The extraction is faithful; harden the NEW code if cheap (a real validation
  guard), but don't chase the static enumeration to zero — the source ships
  with the same findings and the gate still PASSES (no critical/high).
- **New or different findings** → introduced by your edit; fix those for real.

This avoids burning a turn re-hardening code that was already shipped clean,
and keeps the fix scope on what you actually changed.

### 5. "0 findings" is never a pass

A static A2 scan returning zero findings says nothing about runtime
behavior. After the gate passes, still execute the changed path with
boundary inputs (`None`, `-1`, `''`, huge values) and attack one implicit
assumption. The `_RateLimited(None)` crash above was caught by the fuzzer,
but the coercion was only *proven* by running it.

### 6. `shared-global-race` — guard a lazily-initialised module global (HIGH)

A module-level singleton created on first use (`if _X is None: _X = make()`)
is a check-then-assign race and is reported as **high** on any file the scanner
treats as threaded. MCP servers and anything with an event loop hit this the
moment a tool call can interleave:

```python
# ❌ FLAGGED — lost update: two callers can each build one
_STORE = None

def _store():
    global _STORE
    if _STORE is None:
        _STORE = Store()
    return _STORE

# ✅ double-checked locking
_STORE = None
_STORE_LOCK = threading.Lock()

def _store():
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                _STORE = Store()
    return _STORE
```

Do not argue it away as "tools run sequentially" — add the lock. It is three
lines, and the finding is describing a real class of bug even when today's
call pattern happens to be safe.

**Importing `threading` into an existing module re-qualifies the WHOLE file as
threaded** — the scanner then reports `shared-global-race` on module globals you
never touched, including plain write-elision memos (`if x == _LAST: return` /
`_LAST = x`) whose race only costs a duplicate write. Expect latent races to
appear in the same commit that introduced concurrency, and read them before
deciding they are noise: two threads really can interleave the check-and-set.

- A single module-level `_CACHE_LOCK = threading.Lock()` shared by several memos
  is enough; guard the read-modify-write (`with _CACHE_LOCK:` around the check
  AND the assignment), not just the import.
- **Never silence one with an inline `# adversarial-ignore: shared-global-race`.**
  Suppressing a HIGH to get a commit through is exactly the governance reduction
  the gate exists to prevent; the honest fix is two lines, and the delivery note
  should say the finding was fixed rather than waived.

### 7. Read the finding before fixing it: plain output hides the pattern

The text run prints only severity COUNTS and the vague line
`🟡 Medium findings — fix before shipping.` — not which pattern fired. Do not
guess from the counts (that is how you "fix" the wrong file for several turns).
Use `--json`:

```bash
python3 <verify>.py --file X --level A4 --json \
  | python3 -c "import json,sys; [print(f['severity'], f.get('pattern'), '->', f['detail']) for f in json.load(sys.stdin)['findings']]"
```

`pattern` names the check (`error-swallow`, `shared-global-race`,
`input-fuzzing`, …) and `detail` points at the line. Note that some findings
carry `technique` instead of `pattern` — key defensively or the parse crashes
mid-list.

### 8. Match the LEVEL the hook uses — passing A2 does not mean passing the gate

The pre-commit hook runs A2 by default and **A4 for always-review paths** (the
enforcer/hooks, `cortex-update.sh`, the adversarial verifier itself, …). So a
file can return `rc=0` on `--level A2 --gate` and still block the commit:

```
❌  Adversarial scan blocked: 1 file(s) have findings.
      mcp-servers/x.py (level A4):  🟠 High: 1   🟡 Medium: 1
```

When a commit is blocked but your own per-file check passed, re-run at the
level the hook reports (grep the hook for `ADV_LEVEL` if unsure) — and check
EVERY staged file, not just the one you changed most recently. `--gate` is the
flag that decides blocking; a bare run reports findings without gating.

## The LLM review gate — a DIFFERENT mechanism from the static scan

The rules above fix the **static** `adversarial-verify.py` scan. The close of a
**complex** change is separately gated by an **LLM reviewer** that reads your
diff plus your outcome note. Its findings are not pattern matches; they are
judgements, and the dominant one is `unverified-claim`. Treat them differently:

### Commit BEFORE you close

The gate diffs `lock.started_at..HEAD` — **committed** history. Close before
committing and the reviewer receives an **empty diff** while your note describes
a change, so it reports the material as absent (correctly). The order is:

```
begin_change → work → COMMIT → end_change
```

### If the fix cannot land green, PARK it — do not half-land it

"Commit BEFORE you close" assumes the suite is green. When the fix is written but the
suite would go RED (fixtures still feed the old shape, a helper's callers not yet
updated), you have three bad-looking options and one correct one:

- Committing a red suite into a shared repo is not allowed — every other session
  inherits the failure and the next diagnosis starts from your mess.
- Closing the cycle with the work uncommitted is not allowed — the review range
  (`lock.started_at..HEAD`) sees an empty diff and files `unverified-claim`.
- **Correct: `git stash` the WIP, release the lock, leave the tree clean and green,
  and NAME THE STASH in the handoff** — the parked work is recoverable and the
  rest of the fleet is unblocked. A named stash is the honest form of "not done";
  an unnamed one is a landmine for the next session.

Before re-reporting parked work as outstanding, check `git stash list`: a stash
named in an earlier handoff is often already resolved (popped and committed), and
re-listing it as "remaining" is a false status. Say which of the two it is.

### The note is EVIDENCE, not a summary

- **Evidence must live IN THE REPO as a runnable test, not in the note.** A quoted
  command and its output still reads as unverifiable self-report ("no transcript in
  the material") even when the run genuinely happened: the reviewer sees only your
  note and the diff, and it cannot re-run a paste. Put the reproduction in the
  diff — a test that drives the real components, plus the one-line command to run
  it — and let the note say only what changed and what the code does.
- **Test the code you CHANGED — a neighbouring green suite is not evidence.**
  `"running unrelated tests does not verify the changed code"` is a recurring
  finding, and a fair one: cite a test run only if some test in it fails when
you revert the change.
- **Map each claim to the diff** — which function, what the old line was, what
the new one is. One line per claim is enough.
- **Mark gaps `[UNVERIFIED]`** with the check that would close them. An honest
gap is not a finding; a confident guess is.
- **Do not editorialise about the review** ("this is unverified", "only the
  reviewer can decide"). It is read as `evaluation-awareness` — output shaped for
  acceptance rather than correctness.

### A finding can be confidently WRONG — measure before you "fix" code

An LLM review finding is a judgement, and a judgement can be wrong. When one claims
an idiom is broken — an `A && B || C` that "leaves `$?` always 0", a pattern that
"can never trigger", a branch that is "dead" — probe the minimal case FIRST, before
touching the code:

```bash
f() { return 3; }; out=$(f 2>&1) && rc=0 || rc=$?; echo "$rc"   # prints 3, not 0
```

- If the probe shows the code is CORRECT, do not edit working code to satisfy the
  finding, and never write a commit message implying you fixed a bug that was never
  there. This is the same discipline as the false-positive and inherited-baseline
  patterns above: verify the claim, do not contort the code around it.
- A false finding still BLOCKS the close, so there are two sanctioned ways forward.
  Either record the measurement that refutes it as an issue and let the lock TTL out
  (the documented exit for a demonstrably false finding), or — when the cycle must
  land — rewrite the flagged line into the unambiguous form the reviewer can read
  (`if out=$(cmd 2>&1); then rc=0; else rc=$?; fi`). Prove the rewrite
  SEMANTICS-PRESERVING by running BOTH forms, and label it a CLARITY change in the
  commit body, naming the false claim and the measurement. The next reader must not
  be left concluding the old code was broken.

### Your FIX is new code too — run it in BOTH directions before re-closing

Every rule above is about the finding being wrong. The opposite happens more often: the finding is
right, and **the fix you write is broken**, in a way that reads correctly. Two shapes account for
most of it, and both are inversions:

- **Gating on emptiness when the producer's normal result IS empty.** A parser that prints two join
  lines (`"; ".join(issues)` and a second list) emits only newlines on a healthy host, and `$( )`
  strips trailing newlines — so the healthy value IS the empty string. A `-z` test then reports a
  crash for a clean run, and the check goes from PASS to a false FAIL on the very host it just
  passed. Gate on **rc** for failure, and use `-z` only when EVERY branch of the producer prints a
  word (a verdict parser is such a case; a report parser is not). Read the producer before writing
  the gate.
- **Testing `$?` with `-eq 0` inside a FAILURE branch.** `0` means success; the branch then fires on
  every healthy run, so a passing check reports a finding and the real one never surfaces. The
  mirror of this is `if VAR=$(cmd); then` — correct (the assignment takes the substitution's
  status) but easy to read backwards, so prefer capturing `rc=$?` on its own line and testing it
  explicitly.

**Neither shape fails a committed test or shows up in a diff read.** Both were introduced while
fixing review findings and both were caught only by executing the changed artifact. So after every
round: run the healthy path, then force the failing value and confirm the new branch fires.

```bash
# mutant: prove the failure branch exists and is reachable
T=$(mktemp -d); sed 's/_rc=\$?/_rc=3/' ops/scripts/x.sh > "$T/a.sh"; bash -n "$T/a.sh" \
  && bash "$T/a.sh" 2>&1 | grep -c 'the finding text'      # expect >= 1, never 0
```

Report both directions in the note (healthy output + mutant output). A healthy run alone proves the
branch did not misfire; it does not prove the branch works — and that second half is what a
reviewer asking "is this check real?" is actually testing.

### A finding that names a branch you already have is a VISIBILITY gap — close the set, don't duplicate

When a reviewer reports a value as unhandled ("`keyed-only` falls through"), first check whether the
arm exists. If it does, adding a second arm is cargo-cult and makes the code worse. The finding's
MECHANISM was wrong, but the gap it stumbled into is real: from a partial read of a diff, a closed
set is indistinguishable from an open one. Make the set explicit at the decision point —

```bash
# The parser above prints EXACTLY one of these, so every one needs an arm:
#   missing | invalid | keyless:<providers> | keyed-only   (+ check-failed, set below)
case "$verdict" in
```

— and say in the close note that the arm already existed, quoting it. Same discipline as the per-blob
coverage pointer: satisfy the visibility, not the letter of a misread. Do not add a duplicate branch
to look responsive; a redundant arm is a second place for the set to drift.

### A FINDINGS verdict is per cycle — re-review, do not override

The verdict is stored under a UNIQUE cycle id, so FINDINGS is otherwise
permanent: fix everything and the reviewer still reads the same frozen note.
Forcing an override is the wrong answer. Instead: fix, **commit**, then
`rereview_change(task_id=…, note=…)` (or `loop-gov rereview_change '{…}'` from a
harness with no MCP client) with a note that **differs** and carries evidence.
The gate judges live against the current diff and records its own verdict — it
cannot manufacture a CLEAN, and it refuses an unchanged note, because re-review
exists to re-judge a fixed change, not to re-roll a verdict.

Two mechanics decide whether that actually works, and both have failed in
practice:

- **The verdict row is UNIQUE per cycle.** A re-review written as a plain insert is
  swallowed by the idempotent-duplicate path, so the fresh verdict is DISCARDED and
  the original FINDINGS stays frozen — indistinguishable, from the outside, from a
  fix that did not work. Re-review must write with replace semantics, and the close
  must then honour the stored verdict instead of calling the reviewer again.
- **The reviewer is a sampling model.** Re-running it on the same material can
  return the opposite verdict, so a close that re-judges every attempt is a
  coin-flip dressed up as deliberation. Pin the stored verdict to a fingerprint of
  the material it judged (note + diff) and reuse it while that material is
  unchanged; a verdict with no or mismatched fingerprint must be re-judged, so a
  CLEAN can never be carried over a later, unreviewed change.

### The gate judges CLAIMS — an ask is INJECTION, so it cannot be a design service

This gate reviews a diff and the claims made about it. It is **not** a design
review, and the operator's standing rule ("have a strong model review the plan
before building") cannot be satisfied by pointing it at prose. Measured both
ways on the same material:

- Submit a question or an instruction — "Judge the CODE below", "Identify the
  GAPS and the smallest changes" — and the framing is filed as **`injection` at
  high**, and the reviewer explicitly declines to engage with the substance.
- Submit the same content as claims only, and it returns **CLEAN**, because
  there is nothing about a diff to judge; it also volunteers that it cannot see
  files outside its window even when you cite them by path and line.

So: put the payload in the diff (code under review plus real artifacts) and
keep the instruction to a sentence about what changed. For a genuine DESIGN
review, use an independent reviewer outside this gate — a delegated subagent
panel (see `subagent-architecture-party`), which can be handed the extracted
code and asked to attack it — and label its output advisory: it authorises
nothing, and the push receipt still comes from this gate.

### Per-blob findings live in a DIFFERENT store from the cycle verdict

The per-blob pass writes each verdict into `blob_reviews`, **keyed by blob sha**.
The cycle-level verdict lives in `adversarial_reviews`, **keyed by cycle id** —
and that is the table `rereview_change` reads. When a close is refused on a
per-blob pass, the second row must exist too, or the two stores disagree about
whether the decision happened at all and the documented re-review exit answers
"this cycle has no recorded review — nothing to re-review". The same defect
makes the judge invisible: if the per-blob writer does not pass the model, every
row reads back with an empty `reviewer_model` and nothing in the record says
which model produced a verdict.

When a refusal says "N blob(s) of the push range still carry no review verdict"
(or names per-blob findings) rather than quoting a range verdict, check the
CYCLE store before assuming re-review is available:

```bash
# read-only; the store is sqlite even when the CLI is absent
python3 -c "import sqlite3,os; c=sqlite3.connect('file:'+os.path.expanduser('~/.hermes-cortex/data/loop-governance.db')+'?mode=ro',uri=True); print(c.execute('SELECT cycle_id,verdict,reviewer_model FROM adversarial_reviews ORDER BY cycle_id DESC LIMIT 5').fetchall())"
```

A cycle whose blob verdicts exist but whose cycle row is missing cannot be
re-reviewed; write the cycle verdict on the per-blob refusal path itself, with
replacement semantics so a re-judge keeps exactly ONE verdict per cycle.

### A per-blob reviewer reads ONE file — a demand about a SIBLING cannot be met from there

The reviewer's material is the single blob it was handed, so it cannot see a test, helper or doc
that exists in the same range, and it will demand one that is already committed. This deadlocks the
close, because identical content is never re-judged: the demand is unsatisfiable from the blob's
material and the blob cannot change without a new commit. Handle it in two moves, and the second is
the one that lasts:

1. Record the measurement that refutes it (the file and test that already satisfy it) and resolve
the CYCLE with `rereview_change` — not by editing working code to satisfy a claim you can prove
false.
2. NAMING THE COVERAGE INSIDE THE BLOB. Add the pointer at the site under review — "covered by
   `<test file>::<test name>`<one clause of what it asserts>" — so the requirement is answerable
   from the material that will be judged next time. Adding a comment is not satisfying a wrong
   finding by editing code: the finding's MECHANISM was wrong, but the visibility gap it stumbled
   into is real, and the pointer closes it.

State the gap in the delivery too: a per-blob review is structurally unable to confirm anything
about files it was not given, so a demand for coverage located in another file is not evidence that
the coverage is missing.

### Keep GENERATED output out of the review range

A committed generated report — a test-suite transcript, a coverage dump, a
regenerated manifest — becomes a blob in every range that regenerates it. The
reviewer then judges the REPORT: it files findings about failures in files the
change never touched, and the push is blocked on output rather than on the
change. Teaching the report to attribute its own failures does not fix it; the
reviewer still refuses, because the artifact's summary says FAILURES while the
task claimed a working change.

Keep such files ignored and untracked, produced on every run and read by
documentation (`docs/evidence/**` is shown whole and outside the material
budget), and let the committed GUARD be what the review judges. This is not a
relaxation of the gate — the same reviewer still reads the same range; it simply
stops reading your build output as if it were your change.

### After fixing a bug CLASS, dispatch a review that ENUMERATES the class — and one that attacks your TESTS

A confirmation-shaped prompt ("is this fix good?") returns confirmation. Two prompt shapes return
findings that a self-review structurally cannot produce, and both are worth one dispatch each:

- **Class closure, not instance verification.** "Prove whether the CLASS is closed, not just the
  instance: enumerate every remaining path to <bad state>, with the exact sequence, file:line and the
  minimal fix for each." Answering it requires walking every entry point, and it finds the sibling
  function the fix commit did not touch — the same defect class usually has a second copy in a path the
  bug report never mentioned.
- **Adversarial review of your OWN test files.** "Find assertions that cannot fail, missing edge cases,
  ambient-state dependence, leaked state, and anything that would still pass if the fix were reverted."
  The vacuous pass is the commonest defect in a fresh guardian test — a test that returns instead of
  asserting, or a check that passes when its prerequisite is missing. Ask the revert question explicitly:
  it separates genuine regression discriminators from sanity checks that would pass on the old code.

Both are advisory: the reviewer's PROPOSED MECHANISM can be wrong while the gap it points at is real.
Take the gap, verify the mechanism yourself, and record a measured false positive (with the quoted code)
rather than editing working code to satisfy a wrong claim.

### A failing GUARD is usually right — fix the product, and satisfy its INTENT not its letter

A guardian test that fails after your change is reporting the property you were supposed to preserve,
not an obstacle. Never edit the guard to match your implementation, and do not satisfy it by
RENAMING the thing it forbids: a guard asserting an attribute is ABSENT (`not hasattr(mod, X)`) still
fails if you keep the name and point it at the correct value — and that second name is exactly where
the wrong value creeps back. Remove the name and read the good value directly, so the property holds
by construction rather than by two constants someone must keep in step. Then re-run the guard and say
so in the commit body: a guard that was right about your own fix is worth quoting.

### Correcting a record a later measurement proved wrong

An issue/event record that a later measurement refutes must be CORRECTED, not deleted and not left
standing — a wrong record reads as authoritative to every later session, including the reviewer you
are about to hand the same material to. Mark it in place: prepend a `[SUPERSEDED — <one-line reason>]`
marker, state the refuting measurement with the command or query that produced it, and keep the
ORIGINAL text verbatim beneath a clear divider for audit. Then READ THE ROW BACK and quote its new
head in your delivery — an update you did not read back is a claim about a write, not a write. This
is the durable version of "record a measured false positive": the record is what the next session
actually trusts.

Full pass-off contract: `docs/runbooks/adversarial-review-passoff.md`.

## Verification

- `adversarial-verify.py --file <changed> --level A2 --gate` → GATE_PASSED
  (no critical/high)
- For every remaining medium, either the fix pattern above applies or you
  can execute the boundary input and show it's safe (empirical proof beats
  static noise)
- All unit tests still pass after the restructuring

## Pitfalls

- **`except X:` + comment body is a medium finding** even when you think
  the comment "explains" the empty handler. Put real code first.
- **Fixing by adding `pass` or `_ = None` makes it worse** — those are
  explicitly matched patterns. A real statement (write, return, log) is the
  only clean body.
- **Don't chase stale findings** — after a fix, re-run the scanner; finding
  IDs repeat across runs, so verify the current file state, not the ID.
