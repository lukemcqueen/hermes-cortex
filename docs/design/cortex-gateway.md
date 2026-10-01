# cortex-gateway — the decoupled Hermes-cortex gateway

> **Status:** in build — CR1 ✅ CR2 ✅ (transport + backend seam) · CR3 daemon · CR4 systemd · CR5 pi · CR6 steadfaste pending.
> **Pairs with:** `component-hermes-separation.md` (S2b) · `messaging-gateway.md` (ADR-0005, the in-process incumbent).
> **Audience:** builder, orchestrator, owner.

## Why

`hermes-gateway.service` runs the agent loop **inside** the Hermes process
(`python -m hermes_cli.main gateway run`). That is the migration **source**:
an in-process gateway whose restart kills the agent loop, the cron scheduler
(the O1-S3 lesson), and every platform session at once. cortex-gateway is the
**target**: a standalone daemon that owns the full **poll → dispatch → reply**
loop with zero Hermes-agent import, so the agent backend is swappable and the
gateway survives independently.

## The two seams (both swappable, per Luke)

1. **Transport seam** — how we talk to messaging apps. `TransportAdapter`
   (start/stop/parse/send/health); `TelegramAdapter` is the reference
   (long-poll getUpdates, per-bot offset, enqueue-then-ack). Extracted
   verbatim from `msg-gateway.py` — identical behavior, no daemon/agent coupling.
2. **Backend seam** — which agent answers. `BackendAdapter`
   (start/stop/dispatch/health): `dispatch(envelope) -> reply envelope | None`.
   hermes is the first adapter; pi and steadfaste plug into the **same** seam.
   Swapping the agent is a new adapter; the gateway and routing table never change.

Routing lives in the gateway (`gateway.yaml`: channel_user_id → agent), never
in a transport or a backend. The reply must round-trip through
`gateway_envelope.validate`.

## Build slices

| Slice | What | Status |
|---|---|---|
| CR1 | `cortex_gateway/transport.py` — transport extraction from msg-gateway.py (parity-proven) + `__init__.py` | ✅ |
| CR2 | `cortex_gateway/backend.py` — BackendAdapter ABC + structural `__subclasshook__` | ✅ |
| CR3 | `cortex_gateway/daemon.py` — poll_bot + drain_outbound + dispatch/reply step; hermes adapter first | pending |
| CR4 | `cortex-gateway.service` systemd user unit + deploy-map + doctor check; independence proof vs hermes-gateway.service | pending |
| CR5 | pi backend adapter | pending |
| CR6 | steadfaste backend adapter (blocked until steadfaste gateway is complete — Luke) | pending |

## Anti-bloat

No multi-transport fan-out, no gateway-owned inbox, no re-implemented Hermes
agent loop. The package reuses `msg-gateway.py`'s transport and the PGMQ bus
for reply collection; nothing else. Tests are the contract: extraction is
proven by **parity** (new adapter output == msg-gateway.py output, same input),
and the seam by a structural-conformance interop test (three backends, one call
shape).
