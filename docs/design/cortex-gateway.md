# cortex-gateway — the decoupled Hermes-cortex gateway

> **Status:** in build — CR1 ✅ CR2 ✅ CR3 ✅ CR4 ✅ (transport, backend seam, daemon + hermes backend, systemd unit + config + doctor) · CR5 pi ✅ (generic `command` kind — no gateway code change; live on @Esther0001Bot) · CR6 steadfaste pending.
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
| CR3 | `cortex_gateway/daemon.py` + `hermes_backend.py` — poll_bot + drain_outbound + dispatch/reply step; hermes (bus) adapter first | ✅ |
| CR4 | `cortex-gateway.service` systemd user unit + `gateway.yaml.example` + deploy-map + doctor check; independence proof vs hermes-gateway.service (offline: no hermes dep; live cutover = S2d window) | ✅ |
| CR5 | pi backend adapter | ✅ — as a `command` SPEC, not an adapter: `ops/scripts/gateway-pi.example.yaml` (`kind: command`), live on @Esther0001Bot. The seam needed no code; the four reply-path defects it exposed (truncation, a wedged chat, a silent failed turn, no typing prompt) are fixed in the daemon/backend and tabled in `cortex-gateway-parity.md` |
| CR6 | steadfaste backend adapter (blocked until steadfaste gateway is complete — Luke) | pending |

## Fail-closed guarantees

- **`GATEWAY_SECRET` is mandatory.** The daemon refuses to start (`SystemExit`) when a backend is configured and the secret is empty; `sign_payload` raises on an empty key and `verify_signature` returns `False`. An empty HMAC key still yields a `gateway_sig` — but a forgeable one — so an unset secret would silently reduce "agents MUST verify" to theatre. Set it with `openssl rand -hex 32`; the same value must reach every verifying agent.

## Anti-bloat

No multi-transport fan-out, no gateway-owned inbox, no re-implemented Hermes
agent loop. The package reuses `msg-gateway.py`'s transport and the PGMQ bus
for reply collection; nothing else. Tests are the contract: extraction is
proven by **parity** (new adapter output == msg-gateway.py output, same input),
and the seam by a structural-conformance interop test (three backends, one call
shape).
