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
