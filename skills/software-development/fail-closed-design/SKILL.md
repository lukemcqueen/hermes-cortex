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
