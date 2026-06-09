# Inline Comment Templates

Standardized finding formats so the PR author gets clear, actionable feedback.

## Format

```
file:line|LABEL: One-line description
```

Where:
- `file` = relative path from repo root
- `line` = line number in the new version of the file
- `LABEL` = CRITICAL, WARNING, SUGGESTION, PRAISE
- Description = specific, actionable, includes "why" + "how"

## Security Templates

| Pattern | Body |
|---------|------|
| SQL injection | CRITICAL: User input interpolated into SQL query at {{line}}. Use parameterized queries: `cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))` |
| Hardcoded secret | CRITICAL: Hardcoded credential detected. Use environment variables or a secrets manager. |
| eval/exec on input | CRITICAL: `eval()`/`exec()` called with potentially user-controlled data. Remove or switch to a safe parser. |
| Shell injection | CRITICAL: `os.system()` / `subprocess(shell=True)` with dynamic input. Use `subprocess.run([...])` with arg list. |
| XSS (innerHTML) | CRITICAL: Setting `innerHTML` with user input allows XSS. Use `textContent` or a safe template. |
| Path traversal | WARNING: File path constructed from user input. Validate with `os.path.realpath()` and prefix check. |
| pickle.loads | WARNING: Unpickling untrusted data can execute arbitrary code. Use JSON or a schema-validated format. |

## Architecture Templates

| Pattern | Body |
|---------|------|
| Shallow module | WARNING: {{file}} is mostly re-exports ({{ratio}}% of lines). A "deep module" hides complexity behind a small interface. Either add real logic or inline the exports at the call sites. |
| Layer violation (action) | WARNING: {{file}} is an action/handler but contains significant domain logic ({{count}} branches). Move business rules to a service layer; actions should orchestrate, not implement. |
| Layer violation (service) | WARNING: {{file}} is a service but contains policy decisions (auth, notification, routing). Services own HOW (mechanics), actions own WHY (policy). Extract the policy check to the caller. |
| Duplicate function | WARNING: `{{func}}` in {{file}} also exists in {{dupes}}. Consolidate to avoid drift. |
| Large file | SUGGESTION: {{file}} is {{lines}} lines. Consider splitting into smaller modules by concern. |
| High complexity | WARNING: {{file}}:{{line}} has {{count}} branches/loops. High cyclomatic complexity makes testing hard. Extract helper functions for each branch path. |

## Database Templates

| Pattern | Body |
|---------|------|
| N+1 query | WARNING: {{file}} potentially has an N+1 query — fetching items in a loop. Use eager loading (select_related, prefetch_related, JOIN) or batch query. |
| Missing index | SUGGESTION: Query on {{column}} without an index will be slow at scale. Add a database index. |
| Missing transaction | WARNING: Multiple writes without a transaction. Wrap in BEGIN/COMMIT so partial failures roll back cleanly. |
| Raw SQL | SUGGESTION: Raw SQL at {{line}}. Consider using the ORM for consistency and type safety. |

## Testing Templates

| Pattern | Body |
|---------|------|
| Untested file | SUGGESTION: {{file}} has changes but no corresponding test file. Add tests for the new behavior. |
| Missing edge case | SUGGESTION: No test for {{condition}}. Add one for {{example}}. |
| No test changes | SUGGESTION: PR adds {{additions}} lines but no tests. Consider adding at least a happy-path test. |
| Regression | CRITICAL: Test suite passes on `main` but fails on this branch. At least one existing test broke. |

## Logging/Debug Templates

| Pattern | Body |
|---------|------|
| Leftover debug print | SUGGESTION: Debug print/console.log left at {{line}}. Remove before merge. |
| TODO/FIXME | SUGGESTION: `TODO`/`FIXME` at {{line}}. Resolve or file an issue before merge. |
| Commented-out code | SUGGESTION: Commented-out code at {{line}}. Delete dead code instead of leaving it commented. |

## Performance Templates

| Pattern | Body |
|---------|------|
| Loop in loop | WARNING: Nested loop at {{line}} — O(n²) complexity. Consider dict-based lookup or early exit. |
| Sync in async | WARNING: Blocking call (`{{call}}`) inside async context at {{line}}. Use the async variant or run_in_executor. |
| Missing cache | SUGGESTION: {{operation}} is called frequently but not cached. Consider adding a cache layer. |
| Large payload | WARNING: Returning all records without pagination at {{line}}. Add limit/offset or cursor-based pagination. |

## Concurrency Templates

| Pattern | Body |
|---------|------|
| Race condition | WARNING: Check-then-act pattern at {{line}}. Use a lock, atomic operation, or compare-and-swap. |
| Shared mutable state | WARNING: Multiple threads/tasks mutate shared state at {{line}}. Use a mutex or channel. |
| Missing timeout | WARNING: External call without timeout at {{line}}. Set a timeout to prevent hanging. |
