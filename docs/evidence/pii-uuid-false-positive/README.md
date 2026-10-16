# Evidence — the PII gate refused canonical UUIDs as phone numbers

Provenance for this directory. No verdict is asserted here: `transcript.txt` is
the raw stdout of `probe.py`, and that is where the verdict lives.

- **What produced it**: `python3 probe.py`, run from the repo root on the host
  that owns the repo checkout. `probe.py` is read-only — it writes no governance
  state, touches no store, and mutates nothing.
- **What it compares**: the enforcer module as of the **pre-fix revision
  `4764289b`** (extracted from git history by the probe itself) against the
  module under test, which defaults to the repo working copy and can be
  overridden with `MODPATH=<path>`. Both revisions are loaded in ONE process and
  driven with the same inputs, which is the differential probe
  `enforcement-change-safety` Rule 23 asks for.
- **Why the baseline is a SHA and not `HEAD`**: the fix is committed in the same
  change as the probe, so `HEAD` would resolve to the fixed module and the
  before/after would be a tautology. `4764289b` is immutable.
- **Volatile by design**: the pytest duration in section 4 (normalised to `<t>`)
  and the wall-clock time of the run. Nothing else varies: the UUID sample is
  seeded (`random.Random(20261017)`), so the counts reproduce exactly.
- **Redaction**: this is a public file, so the probe prints sha256 *handles*
  instead of the UUIDs it found, labels instead of the assembled phone fixtures,
  and `$HOME` instead of host paths. The fixtures themselves are assembled at
  runtime from parts, because the gate scans the file it is written into.

## The defect this pins

The write-time PII gate's phone pattern includes a two-separator national form.
Inside a canonical UUID, the tail of one hex group plus the two groups after it
can align to that shape — so a *session identifier* was refused as a "phone
number", which is what forced the elision of the verbatim psql row in
`docs/evidence/backlog-run-2026-10-16-selection.md` (section 4, which records
the elision and why).

The fix removes canonical UUID tokens before the phone scan and changes nothing
else. Sections 1–3 of the transcript are the discrimination proof in both
directions: the pre-fix revision refuses the UUID inputs, the fixed module
refuses none, and every real phone format — plus a dash-joined digit run that is
NOT a UUID — still fires in BOTH revisions.

`tests/test_enforcer_pii_gate.py` carries the same comparison as a regression
test, pinned to the same revision.
