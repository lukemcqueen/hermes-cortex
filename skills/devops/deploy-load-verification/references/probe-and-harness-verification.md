## Verify through the PRODUCT's own builders, not a hand-built harness

A harness that rebuilds the product's invocation by hand tests the harness, not
the product — and its failures look exactly like product bugs. Two false FAILs in
one session came from a verification script while the product was correct both
times:

- The script built `[command, "--session-id", id, prompt]` directly instead of
  calling the backend's own `_argv`/`_child_env`. It therefore omitted
  `CORTEX_SESSION_KEY` — and that env var, not the argv, was the real isolation
  seam. Every session shared one checkpoint, so the new session "remembered" the
  old secret and the report read **"/new leaks memory"**. The product was fine.
- The script then used a FIXED probe id, so its second run resumed the sessions
  its first run had left behind — the same false failure, for a different reason.

Rules:

- **Drive the code under test through its own API** (`backend._argv(prompt, sid)`,
  `backend._child_env(inbound, sid)`) — never re-implement its argument or env
  construction. A hand-built equivalent silently drops whatever field the real
  builder adds next. The same rule governs PRODUCTION helpers, not just test
  harnesses: before adding an internal utility, grep the module for an existing
  one (`grep -n 'def .*git\|rev-parse' <module>`), because a parallel helper
  splits one capability across two implementations that then diverge — and,
  if the reason you wanted a new one is that the existing helper swallows
  errors, fix the existing helper for every caller while leaving its return
  values unchanged. Never write "checked" in a docstring unless you actually
  ran the check.
- **Assert on the isolation KEY, not just the visible id.** When the artifact that
  actually scopes state is an env var / checkpoint key, test THAT follows the
  change (`CORTEX_SESSION_KEY` before != after). A correct argv with a constant
  key is the trap: a fresh transcript that still resumes the old checkpoint.
- **Make every probe UNIQUE per run** (`os.urandom`), and clean it up after.
  A fixed probe id makes run 2 inherit run 1's leftovers; a committed evidence
  script then fails intermittently and looks like a regression.
- **Run the acceptance script TWICE.** Determinism is part of the claim: one
  PASS can be a leftover; two consecutive PASSes on a cold probe is evidence.
- **Place the fixture where the code's CONTRACT expects it.** A resolver that maps
  a name to `HOME/<name>` cannot be exercised by a fixture at `HOME/sub/<name>` —
  it correctly falls back and your probe reports a false failure. Read the contract
  before choosing the temp layout, and treat a fallback/unexpected result as a
  probe-placement question FIRST. Also record how deep the contract reaches: a
  name-based resolver silently stops working for anything nested below the level it
  scans, which is a real (fail-safe) boundary worth stating, not hiding.
  **And place it where it cannot POLLUTE the host.** A fixture repo under `HOME` is not
  neutral: any `~/<name>/.git` makes the doctor treat it as a dev repo and warn about it,
  and a decoy sharing a basename with a real checkout can be mistaken for one. Keep
  fixtures in the scratch/TMPDIR tree (`tempfile.mkdtemp`) and remove them in a `finally`.
  Cleanup is the trap — deleting from `HOME` is a destructive command that needs operator
  approval, and if that approval never arrives the fixture stays and every later doctor run
  reports it.

Two probe bugs that read as code bugs and are worth naming, because the code was
correct every time they fired:

- **Build a fixture by CLONING a real artifact and mutating it — never by
  inventing one from the fields you think matter.** A hand-built fixture that
  omits fields the system itself validates (a TTL, a start time) is discarded by
  the staleness/validation pass BEFORE it ever reaches the code under test, so
  the code reports "not found" and the probe blames it. Copy a live artifact,
  then change only the fields the probe is about.
- **To test a SECONDARY or fallback path, use an input that CANNOT satisfy the
  primary path.** Reusing the subject's own canonical value lets the primary
  check succeed and short-circuit, so the fallback branch never runs and the
  probe proves nothing while appearing to exercise it. Also re-check that your
  probe extracted the identifier correctly — a truncated id (taking the last
  underscore-separated segment of a composite key) looks exactly like a
  cross-session refusal.
- When a probe fails, spend the FIRST cycle asking what the probe "assumes"
  rather than what the code does. Four consecutive probe defects in one session
  each presented as a product bug.

When your own harness reports a failure, suspect the harness first — a false FAIL
costs the same as a missed bug and sends you editing correct code.
