# Forwarder failure diagnosis — worked example (2026-08-07)

Session: user forwarded the `orch-bus-forwarder-sync` alert
`⚠️ [09:24 KST] LOCAL→PEER: 1 failed • inbox_orchestrator/ee8d75afb2` and asked why.

## Timeline (KST, all on the primary/moses bus)

| Time | Event |
|---|---|
| 09:22:07 | kustos sends `📝 PROPOSAL: Register tasks schema v003+v004 in cortex-update.sh deploy map` → pending in `inbox_orchestrator` |
| 09:22:58 | forwarder tick: POST to peer (esther `:14004`) fails → alert #1 |
| 09:24:59 | retry fails again → alert #2 (only 2 of 50 ticks today alerted) |
| 09:25:09 | esther's message-handler consumes the proposal directly from moses's bus and archives it (`archived_by='esther'`) |
| 09:27:00+ | queue empty → forwarder silent, no recurrence |

## Identifying the message (the non-obvious part)

1. Read cron outputs: `~/.hermes/cron/output/<job_id>/*.md` — grep for
   `failed|unreachable|recovered` across ALL ticks to measure how isolated the
   event was.
2. Searching `bus.messages` AND `bus.archives` for the literal `ee8d75afb2`
   returns **0 rows** — the ID is a runtime hash suffix, never stored.
3. `bus.archives` (last 6h) showed esther archiving a real (non-doctor-e2e)
   message from `inbox_orchestrator` at 09:25:09 — the only candidate.
4. Recompute the forwarder's dedup key over that body (exact script logic):

```python
import json, hashlib

def parse(raw):                       # mirrors _parse_body in orch-bus-forwarder.py
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            p = json.loads(raw)
            if isinstance(p, dict):
                return p
        except Exception:
            pass
    return {"raw": str(raw)}

b = parse(body)                       # body = archived row's jsonb body
corr = b.get("correlation_id") or ""
if corr:
    dkey = f"corr:{corr}"
else:
    canonical = json.dumps(b, sort_keys=True, default=str)
    dkey = f"hash:{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"
print(dkey)          # hash:9101141dbf41789e1a6f15ee8d75afb2
print(dkey[-10:])    # ee8d75afb2  → MATCH with the alert
```

## Conclusion

Mirror race, not a broken pipeline: the forwarder kept retrying a message that
esther consumed directly from the shared `inbox_orchestrator` 3 minutes after
enqueue (the backup-orchestrator visibility design). The 2 send failures were
the only anomaly in 50 ticks, with 1,336 successful LOCAL→PEER mirrors
overall — systemic ACL/auth is ruled out. Residual cause is either a transient
peer-endpoint rejection or a per-queue ACL gap on the peer for
`inbox_orchestrator`; the alert cannot distinguish them because it omits the
HTTP status.

## Improvement (APPLIED 2026-08-07, commit cfc313bf)

`orch-bus-forwarder.py` `_send_bus()` now returns `(success, reason)` and
`_sync_direction()` appends it to error entries — alerts read
`• inbox_orchestrator/<tail> (403 Agent 'x' does not have write access...)` for
4xx/5xx (status + API detail) or `(<urlopen error ...>)` for transport
failures, so 403 vs 5xx vs timeout is visible in the alert instead of
requiring a DB investigation. Shipped via governance cycle; verified with
`_send_bus` against a dead port (`Connection refused`) and a bad token on the
live bus (`401 Invalid or expired token`). (NOTE: the 2026-08-07 git commit
corruption incident — concurrent sibling commits truncating
`next-index-*.lock` temp indexes — briefly blocked the normal hook-enabled
commit; see the `git-forensics` skill's concurrent-commit-corruption
reference for the diagnostic and escape hatch.)
