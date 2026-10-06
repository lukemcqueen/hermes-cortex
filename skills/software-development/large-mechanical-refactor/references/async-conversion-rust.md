# Rust sync → async conversion recipe (wide ripples)

Recipe for converting a sync in-core API to `async fn` across a workspace, proven on a
single-file-then-delegate pass.

## The ripple map
- Changing `T::handle()`/`T::record()`/`T::dispatch()` to `async fn` forces EVERY internal
  caller in the same struct/impl to be `async fn` too (methods that call them: `advance`,
  `commission`, `dispatch_with_authority`, query methods that `record`).
- Every bin that drives the async API needs a runtime. Prefer a single cached current-thread
  runtime (a `static OnceLock<Runtime>`) created once and reused, not a per-call runtime.
- Every sync `#[test]` caller becomes `#[tokio::test] async fn name()`.

## Write-side conversions (the library)
- `pub fn handle(&mut self, ...) -> Result<_, E>` → `pub async fn handle(&mut self, ...) -> Result<_, E>`
  with `self.ledger.append(entry)?` unchanged (the in-memory ledger is sync and resolves now;
  the async seam is what a PgLedger will slot into). Document WHY it is async ("so a durable
  PgLedger can slot in without changing callers").
- Every internal `.handle(x)` / `.record(x)` call site in the same crate gains `.await`:
  `.handle(x).await?`, `.record(x)`. Return-position `?` stays.

## Test-side conversions
- `#[test] fn n()` → `#[tokio::test] async fn n()`.
- `.handle(...).unwrap()` → `.handle(...).await.unwrap()`  — await BEFORE the unwrap.
- Helper `fn`s that call any async method become `async fn`; their callers add `.await`.
- Methods that were NEVER converted stay sync (no await on them): `judgment`, `review`,
  `enforce`, lease methods, and read-only getters (`.state()`, `.ledger_len()`,
  `.ledger_entries()`, `.merkle_root()`, `.is_live()`, `.sweep()`, `.heartbeat()`, `.finish()`).
- Add `tokio = { version = "1", features = ["rt", "macros"] }` to the crate's `[dev-dependencies]`
  for `#[tokio::test]` to resolve.

## Verify per file
```bash
export PATH="$HOME/.cargo/bin:$PATH"
cd <workspace root>
cargo test -p <crate> --test <name> --no-run   # per test file
cargo test -p <crate> --test <name>            # run that file's tests
```
Then the full `cargo test --workspace` yourself before reporting green.
