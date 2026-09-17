# Rust audit recipe — run when finishing a Rust change

## Lint (0 warnings is the target)

    rustup component add clippy   # once, if missing
    cargo clippy --workspace --all-targets

Clippy catches real smells: a `.last().expect("just pushed")` panic path, and a
manual loop counter that a `zip` refactor fixes. Its `explicit_counter_loop`
can be a false positive when the "counter" is actually a verification-state
variable comparing a data field — but the `(1u64..).zip(entries)` suggestion is
still an equivalent, cleaner fix, so apply it rather than `#[allow]` it.

## Scan for invariant breaches (want zero / exactly one)

    # panic paths in production src — want zero
    grep -rnE "expect\(|unwrap\(\)|panic!|unreachable!|todo!|unimplemented!" <crate>/src/

    # single-writer: the mutation method must have exactly ONE call site
    grep -rn "\.append(" <crates>/src/

    # unsafe blocks — want zero (a doc-comment hit is a false positive)
    grep -rn "unsafe" <crates>/src/

## Cargo.lock must be committed for a binary

A `.gitignore` with `*.lock` swallows `Cargo.lock`, which a bin crate must
commit for reproducible builds. Negate it:

    *.lock
    !Cargo.lock

## Canonicalization / hashing

A float in hashed content makes two honest nodes disagree, so reject every f64
in content that feeds a hash. serde_json parses `-0`, `1e2`, `1.0` all as
floats — the guard must test those spellings, not just `1.5`. Serialize
canonical bytes from a single shared function (sorted keys, compact, no float)
so the ledger hash and any payload hash cannot drift apart.
