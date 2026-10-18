---
version: 1.0.0
name: fail-closed-design
category: software-development
description: "Use when writing fail-closed security-critical code."
---

# Fail-Closed Design

The governing idea: in security-critical code, make the wrong outcome
**unrepresentable**, not just discouraged. A type checker enforces what a doc
comment only suggests.

## Encode a guarantee as an unrepresentable state

When a wrong action must be impossible, omit it from the enum. No
"allowlist update" variant (connection-level teardown is the only egress
action); no "process-group SIGKILL" variant (atomic tree-kill is the only
kill); no "operating" state for a control with zero evidence (Verified /
Unverified only). The absent variant cannot be constructed; the comment that
says "don't do this" can be ignored.

## Order the escape-hatch check before the refute check

In a verdict function with an "inconclusive / indeterminate" arm, test it
FIRST. A non-deterministic result that happens to mismatch must return
inconclusive — never a false refute. Check determinism before comparing hashes
or statuses. The ordering is load-bearing: swapping it turns an ambiguity into
a false accusation.

## No panic paths in the single-writer / security path

`vec.last().expect("just pushed")` after a push is "provably safe" but still
panics. Return the index instead (`let i = v.len(); v.push(..); &v[i]`) or
propagate a `Result`. A provably-unreachable panic is a landmine for the next
refactor. Scan: `grep -rn 'expect(\|unwrap()\|panic!\|unreachable!\|todo!\|
unimplemented!' crates/*/src/`, drive to zero in the writer/security path.

## Fail closed on the unknown

Exact match, never fuzzy. An unknown enum value, a malformed capability
string, a case typo — degrade to the SAFE fallback (deny / kill / unrouted /
undecidable), never to the permissive one. "Unknown" is evidence of a
mismatch, and a mismatch is denied.

## The completion audit

A build can be 100% green while the deliverable the spec NAMES is never
assembled: all library crates and no `main.rs` / `[[bin]]`, a persistence
adapter that exists only as DDL, a trait modeled as decisions but never wired
to a live process. Before declaring done, grep for `fn main(` / `[[bin]]` and
for the adapter/impl the spec promises, and report the gap honestly as "next
phase" rather than calling it complete.

**A security primitive is not complete when the PRODUCER is built — prove the
enforcement half has a caller.** Signing code, a `verify_*` function, and a
green test suite can all coexist while nothing in PRODUCTION ever calls the
verifier: the producer signs, the tests pass, and the guarantee is decorative
because no live consumer refuses the unverified input. Grep for the verifier's
callers OUTSIDE the test tree; if the only hits are tests, the protection is
declared, not enforced — say so plainly instead of reporting the feature done.
Then name one enforcement point per consumer class (which artifact reads the
untrusted input and must reject it), all funnelling through the SAME decision
function so classes cannot diverge. Prefer a single `accept(input, key) ->
Decision` that composes shape-validation and authenticity in one call over two
functions a caller can wire up wrong or forget entirely. When consumers span
several languages or harnesses, ship the rule as a language-neutral spec plus
KNOWN-ANSWER vectors rather than a library — a reimplementation is correct iff
it reproduces the vectors.

## A disabled check and a masked exit code are the same hole

The fail-closed rule applies to the CHECK as much as to the guarded action: an
enforcement point that silently stops enforcing is indistinguishable from one
that is satisfied.

- **A loader that cannot bring in the checker must say so.**
  `try: mod = load(path)` / `except Exception: mod = None` removes the check
  entirely and the run reads green. Fail LOUD: emit an explicit
  "unavailable — COULD NOT VERIFY" finding naming the missing file, and keep the
  rest of the run alive. Silence is the permissive fallback.
- **Never `|| true` an exit code that carries a verdict.** A wrapper that
  discards the status of a verifying tool converts a failure into a success at
  the process level. Capture it (`${PIPESTATUS[0]}` for a pipeline, not `$?`
  which is the LAST stage's) and dispatch on it. Distinguish warning-only from
  failure when the tool's codes do (`2` failures, `1` warnings, `0` clean):
  propagate the failure, report the warning — a deploy that aborts on warnings
  is unusable, one that ignores failures is a false green.
- **Do not discard a cleanup's stderr.** `2>/dev/null` on a step whose failure
  leaves the system in the state the step existed to prevent hides the one
  signal that explains the next failure; capture it and report it.

## Fail closed WITHOUT dead-ending anyone — pick the disposition per caller

"Fail closed" is not one behaviour: the SAFE direction depends on who is waiting on
the resource when the decision cannot be made. Two callers of the same cleanup can
therefore need OPPOSITE dispositions, and unifying them breaks one of them.

- **A caller with a live user waiting must not be dead-ended.** If the guard cannot
  be satisfied (the store is unreadable), the operation still completes and the
  residue is reported loudly, because a refusal the caller cannot get past pushes
  them to a force/bypass route — the worst outcome. The residue is repaired by the
  recovery tooling, not by refusing.
- **An unattended sweeper should keep the resource.** Nothing is waiting on it, so
  leaving a stale item in place costs nothing while a forced removal creates the
  broken state the guard exists to prevent. Retry next sweep.
- **Justify each by what its alternative costs, and write the reason down** at both
  sites — otherwise the next agent reads the pair as an inconsistency and "fixes"
  it into a bug.

### A gate that cannot resolve its SCOPE must not become a lockout

The dead-ending above also happens one level earlier: a gate that governs "the repo",
"the tree", "the project" must first DECIDE which one, and a refusal at that step is a
lockout, not enforcement. Resolve scope from the CALL's own arguments FIRST — the path-shaped
fields of the tool input, and any absolute path named inside a shell command (a `cd <tree> && ...`
prefix is the caller telling you exactly what it means) — then an explicit env pin, then the
process cwd. A gate that consults only env + cwd deadlocks every session launched outside the
tree, and the command that would PROVE the scope is itself the write being blocked, so there is
no way out of it from inside.

- **A doc comment stating the precedence is not the implementation.** A comment reading
  "args → env → git" sat above a function that implemented only env → git, and the missing leg
  was the whole bug. Read the function against the comment whenever the contract is a resolution
  ORDER, and make the order explicit in the code so it cannot drift again.
- **The refusal must name a REACHABLE escape** — the parameter that works (`workdir=<tree>`), the
  env var to set, or the read-only command that locates the tree. "Acquire a lock" is an
  impossible demand when no scope resolves, and impossible demands are what train an operator to
  reach for force/bypass.
- **Keep the ORIENTATION path open.** Read-only primitives must pass unconditionally: they are how
  the caller discovers the scope it is required to name. A gate that blocks a plain directory
  listing because it could not resolve a scope has blocked its own remedy.
- **The same concept implemented per harness WILL drift.** A rule enforced by both a host plugin
  and a CLI-agent extension is two independent scope resolvers; fixing one leaves the other
  deadlocked for that harness's users. Fix both, and check the second against the first.

### A resolution failure must carry its own diagnosis

A gate that refuses because it could not DETERMINE something owes the caller the evidence, not only
the verdict: "not found" is a dead end when the truth may be "the detector itself is missing".

- **"Could not run the detector" and "the answer is no" are opposite diagnoses — never collapse
  them.** One needs a PATH/binary fix, the other a different folder. Keep the subprocess's stderr,
  exit code and message, and print every path the lookup tried, so the next attempt says which it
  was (an ENOENT means the tool is unreachable, NOT that the answer is negative).
- **`catch { return null }` around a lookup is the same hole as a masked exit code.** Discarding the
  error makes a fail-closed refusal unfixable from the outside — the caller cannot act on it and
  reaches for a bypass — and it guarantees the same report arrives again unchanged.
- **Do not depend on the tool you are DETECTING with.** Find where a repo or tree STARTS by walking
  up for its marker entry (`.git`, a project file) with filesystem calls; shelling out makes the gate
  depend on exactly the binary a stripped PATH removes from launchers and services, so the lookup
  fails while the tool works in the operator's own shell. Use the external tool only for layouts a
  walk cannot see, and only for READING the tree.

### A fail-closed outcome needs a distinct exit code, or it is just noise

A path that keeps/refuses and only prints a line has no operator interface: a cron
that always exits 0 turns a permanently broken store into background noise, which is
how a repairable state becomes permanent. Give "I could not do my job" its own
non-zero code with an explicit operator-action message, and reserve the codes so a
caller can dispatch (0 clean, non-zero = act). The same applies to a retry-safe
default that stops being safe once it persists: a state excused as "a race in
progress" (an unparseable file, a half-written record) must be AGE-BOUNDED — past a
small multiple of its expected window it is corruption, and it must be surfaced for
cleanup rather than skipped silently on every run forever.

## An empty credential authenticates nothing — guard it explicitly

An unset/empty secret does NOT make the crypto fail: HMAC with an empty key
returns a well-formed signature, so the caller sees a "signed" message that
anyone can forge. The same shape hides in password checks (empty stored
hash), JWT secrets, API keys, and allowlists keyed on a blank id — the wrong
outcome is representable and silently permissive. Guard at EVERY layer the
value passes through, not just one:

- **the primitive** — sign raises / verify returns False on a falsy key;
  never compute a signature with an empty key, never validate against one.
- **the object** — the client/backend constructor rejects an empty secret.
- **the wiring** — the daemon/CLI refuses to START (`SystemExit` with
  remediation text) when the feature is configured but the secret is empty.
  Fail at start-up, never mid-request: a raise inside the message loop kills
  the service on the first live message, while a start-up refusal is
  operator-visible and immediate.

Skip the start-up guard only when the feature is genuinely absent (no
backends/consumers configured ⇒ nothing signs ⇒ no secret needed). Make the
message name the fix and the env var (`set GATEWAY_SECRET; e.g. openssl rand
-hex 32`) so the operator is not left guessing.

## An empty value in a COMPARISON guard authorises the MOST, not the least

The same missing guard hides in equality checks, where it fails in the opposite
direction to the credential case: a token/range validator written as
`if receipt["base"] != base: return False` **accepts** a receipt whose field is
empty whenever the query's field is also empty — so the check passes for an
UNBOUNDED range, which is exactly what the guard existed to prevent. An empty
value is not a match, it is a MISSING VALUE.

- **Test truthiness on BOTH sides before any equality**:
  `if not tip or not base: return False`, then compare. `"" == ""` must never
  read as authorisation.
- **Guard BOTH ends when producer and consumer live in different files** — the
  producer refuses to emit a half-filled artifact, and the consumer refuses to
  accept one, so neither half is load-bearing alone.
- **Assert the regression test was RED before the fix.** A test for this written
  after the patch can pass vacuously; run it against the unfixed check once and
  see it fail, or you have not shown the hole existed.
- Ask the same question of every field in an authorisation artifact, not just
  the SHA-shaped one that broke: name the fields a validator compares, and for
  each ask what an empty or default value compares EQUAL to.
