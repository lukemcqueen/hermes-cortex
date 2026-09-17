---
version: 1.0.0
name: robust-code-design
category: software-development
description: Use when hardening code against adversarial failure modes.
---

# Robust Code Design — make failure modes unrepresentable

## The one idea

A guarantee that lives only in a comment or a test can silently regress. The
highest-value hardening is to make the wrong behavior *unrepresentable in the
type*, so the compiler refuses it — then the test only confirms what the type
already enforces.

## Always-on rules

### Make the invalid state unrepresentable

Prefer a closed enum whose variants are exactly the legal actions, and omit the
dangerous variant rather than adding it and "never using it": a stop-action
enum has no `AllowlistUpdate` (only connection teardown), no
`KillProcessGroup` beside `KillTree`, a control-status enum has no "operating"
state. The compiler then rejects the wrong call; a doc note does not.

### Evict/remove by key only if the value still matches

Removing `map[key]` when retiring an *old* record corrupts a *newer* record
that reused the key. Guard every removal with
`if map.get(key).is_some_and(|cur| cur == id) { map.remove(key); }`. This is a
lease stall sweeping a live lease, or a cache evicting a freshly-written entry
— one bug shape, and it only shows up when the sweep runs after the re-issue.

### Fail closed on anything unrecognized

Exact-match the known set; every unknown value (unknown enum variant, wrong
case, empty string, a typo'd capability name) maps to the SAFE default — not an
error, not a best-guess. An unknown freeze capability degrades to `KillTree`,
never a claimed "can freeze"; an unknown tier degrades to the least trust.

### No panic paths in the writer

The single write path must not contain `expect`/`unwrap`/`panic`. Capture an
index before the push (`let idx = v.len(); v.push(..); &v[idx]`) rather than
`.last().expect("just pushed")`.

## References

- `references/rust-audit.md` — the concrete scan recipe (clippy, panic-path /
  single-writer / unsafe greps, `Cargo.lock` under `*.lock`) to run when
  finishing a Rust change.
