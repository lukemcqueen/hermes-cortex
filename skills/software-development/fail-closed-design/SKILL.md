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
