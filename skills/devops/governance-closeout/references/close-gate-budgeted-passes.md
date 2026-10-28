# The close gate reviews in budgeted passes — end_change continues, it does not restart

A close on a large range refuses with `close refused (REVIEW_INCOMPLETE/REVIEW_PENDING)`
and reviews a per-call budget (15 blobs / 240s) of unreviewed blobs, then answers "cannot
close yet: N blob(s) not covered … closing again continues from here". Call end_change
AGAIN — each call continues from the last verdict instead of redoing the judged blobs.
The reviewer runs with a socket-timeout fallback when SIGALRM cannot fire (not the main
thread) — that line in the output is noise, not a failure.

Verdicts are keyed by blob CONTENT, not commit SHA, so a content-preserving rebase keeps
receipts valid: an always-review range still pushes under its old receipt after the rebase.
A `marker written to the lock` note on a REVIEW_INCOMPLETE refusal is the loop working, not
an error.

## The CLI fallback when the governance MCP tools die mid-cycle

Renaming or removing the review MCP server takes the gateway child with it, and THIS
session's `mcp__<old>__*` tools (begin_change/end_change) vanish — they do not come back
without `/reload-mcp` (a user command) or a gateway restart. Close the CURRENT lock through
the harness CLI instead:

```bash
python3 ops/scripts/loop-gov.py feedback_accept \
  '{"cycle_id": 13922, "completeness": 10, "quality": 10, "progress": 10,
    "task_id": "<task>", "note": "…"}'
python3 ops/scripts/loop-gov.py end_change \
  '{"task_id": "<task>", "session_id": "<the lock's session id>"}'
```

- The `session_id` of the lock must be passed EXPLICITLY — without it the CLI resolves its
own harness session (the non-Hermes fallback path) and answers "No governance session
active. Nothing to release."
- `feedback_accept` from the CLI needs the scores inline; a note-only call is refused as
  unscored.
- The CLI CANNOT start the replacement cycle either: its `begin_change` is also classified
  write-class, and with no lock held the enforcer refuses it. Recovering the MCP tools is a
  user action (/reload-mcp or restart) before the next cycle can begin.
- The doctor's close gate still runs its review on the CLI end_change path (budgeted passes
  as above), so the close completes in as many CLI calls as the range needs.
