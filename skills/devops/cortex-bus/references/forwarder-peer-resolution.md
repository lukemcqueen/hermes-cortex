# Forwarder Role-Aware PEER Resolution — 2026-08-03

## The bug

`orch-bus-forwarder.py` is deployed to BOTH orchestrators (Moses + Esther) via
`register_orch`. Its PEER (the "other" bus it mirrors) was resolved from
`CORTEX_BUS_FALLBACK_URL`:

```python
PEER_URL = os.environ.get("BUS_FORWARDER_PEER_URL",
           os.environ.get("CORTEX_BUS_FALLBACK_URL", ""))
```

On **backup-orchestrator's** host:
- `CORTEX_BUS_URL` = `https://bus-primary.example:13004` (primary — Moses)
- `CORTEX_BUS_FALLBACK_URL` = `https://bus-backup.example:14004` (backup's OWN external)

So PEER resolved to Esther's own URL → the forwarder mirrored Esther↔Esther.
Result:
- No Moses→Esther data mirror existed (the whole "warm standby" premise broken)
- Health probe to own URL with Bearer → 401 → `peer_ok=False` → **all sync skipped**
- `bus-forwarder-state.json` showed `peer_downed_at: 2026-07-31` stuck for days
- The 166/168 peer→local / local→peer counts were stale artifacts, not live sync

On **Moses'** host the default happened to work (`CORTEX_BUS_FALLBACK_URL` =
Esther `:14004` = the real peer) — which is why the bug hid until Esther
actually needed to be the backup.

## The fix

Role-aware resolution in BOTH the module-level constant and `main()`'s
config-file fallback (cron runs have no env, so `main()` re-resolves from
`cortex-bus.conf` — fixing only module level was NOT enough):

```python
# Peer = the OTHER orchestrator's bus:
#   on Esther  → CORTEX_BUS_URL (Moses :13004)
#   on Moses   → CORTEX_BUS_FALLBACK_URL (Esther :14004)
HOSTNAME = os.uname().nodename.split(".")[0]
if HOSTNAME == "moses":
    PEER_URL = os.environ.get("BUS_FORWARDER_PEER_URL",
               os.environ.get("CORTEX_BUS_FALLBACK_URL", ""))
elif HOSTNAME == "esther":
    PEER_URL = os.environ.get("BUS_FORWARDER_PEER_URL",
               os.environ.get("CORTEX_BUS_URL", ""))
```

`PEER_AUTH` also defaults to `CORTEX_BASIC_AUTH` (the nginx Basic creds) —
the external peer is behind nginx which accepts Basic only; Bearer → 401.

## Verification

```bash
cd ~/hermes-cortex && timeout 90 python3 ops/scripts/orch-bus/orch-bus-forwarder.py
# expect: ✅ [.. KST] Peer recovered — drained 0→local, 0→peer
python3 -c "import json; st=json.load(open('$HOME/.hermes-cortex/state/bus-forwarder-state.json')); print(st.get('peer_downed_at','CLEARED'), st['total_peer_to_local'], st['total_local_to_peer'])"
```

## Related: fleet server-version split

The 403-vs-200 ACL behavior differs per host because TWO server versions exist:

| File | ACL model | Where runs |
|------|-----------|-----------|
| `core/cortex_bus/server.py` | coarse boolean (`can_read`/`can_send` = bool) | deployed `~/.hermes-cortex/bus/server.py` (Esther :8903) |
| `core/cortex_bus/server.py` | per-queue arrays (`can_read` = queue list, `queue not in allowed_queues → 403`) | canonical (Moses' bus) |

Diagnose a 403 by diffing the two server files BEFORE assuming a config bug.
Commit `fc9aafdb` fixed the forwarder; commit `97c541a8` documented
`inbox_orchestrator` across fleet docs.
