---
name: large-mechanical-refactor
description: >-
  Use when a wide refactor ripples across many files.
version: 1.0.0
author: Moses
license: MIT
metadata:
  hermes:
    tags: [refactor, async, signature, delegation, verification]
    related_skills: [test-driven-development, subagent-driven-development, survey-before-action]
---

# Large Mechanical Refactor — safe execution of a wide API/signature change

## When to Use
A refactor changes a signature (or makes an API async, sync, callback, etc.) and the change
ripples across many files in one repo — so wide it cannot be proven by the compiler alone and
must land as one compiling commit (an intermediate HEAD won't build). Trigger on: converting an
API to async across call sites, renaming a symbol tree-wide, or a signature change used in many
files. The failure shape is doing this by hand across dozens of files, or delegating it blind.

## The discipline

1. **Baseline the suite first.** Capture the true count `cargo test --workspace -- --list | grep -cE ': test$'`
   BEFORE touching anything. A wide refactor cannot be measured against a broken baseline — a
   stray missing-import compile error in an unrelated test file surfaces here as the blocker it
   is, and you fix it as a separate commit BEFORE your refactor so your diff is clean.
2. **Map the full blast radius, not just the named methods.** A sync→async conversion on three
   core methods forces every internal caller chain async too (helpers that call them), plus a
   runtime in any bin, plus each sync `#[test]` caller must become `#[tokio::test] async fn`
   with `.await`. Grep for the SYMBOL across the whole tree (`.handle(`, `.record(`, `.dispatch(`)
   so you know every file and call-site count before writing the first patch — hand-rolled mocks
   and sibling helpers silently re-implement the old shape and fail on a shard you did not run.
3. **Prove the recipe on ONE small instance by hand.** Pick the smallest affected test file,
   apply the full conversion by hand, watch it compile and pass. This locks the exact pattern:
   marker becomes `#[tokio::test] async fn`, `.await` goes BEFORE `.unwrap()`
   (`x.handle().await.unwrap()`), helper `fn`s that call async methods become `async fn` and all
   their call sites gain `.await`. Encapsulate this in the delegation context.
4. **Delegate the bulk to a subagent with the proven recipe.** The remaining files are the same
   mechanical transformation, independent per file. Hand the subagent the exact recipe (steps,
   the `.await`-before-`.unwrap()` ordering, which symbols become async vs stay sync, an
   explicit DON'T-TOUCH list, and the per-file verify command `cargo test -p <crate> --test <name> --no-run`)
   plus the ONE already-converted file path as a forbidden-to-edit reference. Tell it not to
   git add/commit and not to run the full suite.
5. **Verify the full suite YOURSELF — the subagent's `--no-run` pass is a claim, not proof.**
   After it returns, run the full workspace suite and confirm the count you captured at step 1
   holds (or grew exactly as expected). Never report green without your own real output.
6. **Commit and verify often.** This user prefers small, frequent, verified commits over one
   giant dump. One atomic commit per logical slice (baseline-fix commit, then the refactor
   commit, each verifiable), never batch unrelated edits.

## Pitfalls

- **Do not re-derive call sites from memory** — `search_files` the symbol every time; a
  refactor targets what the compiler and the grep agree on, never what you remember.
- **Ignore linter "async fn not permitted in Rust 2015" on an edition-2021 workspace** — the
  lint tool reads the default edition and misreports; cargo is the source of truth, not the
  inline linter.
- **A compile-breaking refactor must land green or not at all** — either it lands as one
  compiling commit or the committed HEAD fails the suite; an intermediate HEAD that doesn't
  build is not a checkpoint.
- **Keep unrelated rustfmt diffs out of the commit** — a whole-crate `cargo fmt` reformats
  pre-existing files and turns `git status` into noise. Revert files you didn't otherwise touch;
  confirm a remaining diff is pre-existing via `git stash` + `cargo fmt --check` + `git stash pop`.
- **A new doc that reuses a numbered vocabulary claimed by an earlier plan in the same repo
  collides corpus-wide** (two plans each with their own "Story 0–7" / "Story 0–9").
  `search_files` the corpus for the planned label before naming new stories/slices; if the
  number is taken, namespace the new set with a thematic prefix (`SS0`–`SS9`) and carry both
  the slice code and the story id in the ownership table so the owning plan is unambiguous.

See `references/async-conversion-rust.md` for the explicit Rust sync→async recipe.
