# Gateway envelope verification — the consumer-side trust boundary

> **Status:** design (CR7) — proposed, awaiting owner approval to build.
> **Pairs with:** `cortex-gateway.md` (the signer) · `messaging-gateway.md` (ADR-0005) · `component-hermes-separation.md` (S2b).
> **Audience:** builder, orchestrator, owner.
> **Extends:** `docs/older/steadfaste/coding_agent/codeharness-design-docs/docs/party/telegram-bus-visibility.md`

## Problem

The gateway HMAC-signs every inbound user envelope (`gateway_sig` +
`kind: user_message`) so a consumer can prove the text came from the gateway
and not from anything else that can write `inbox_<agent>`. **Nothing calls
`verify_signature` in production.** The signature is declared but unenforced:
the producer is built, the verifier has no caller. Until a consumer refuses
unsigned/forged user text, the protection is theatre.

## Requirement

Enforce verification **once per consumer class**, and make it general enough
that the same rule covers:

- **Hermes agents** (this repo) — consume `inbox_<agent>` via the bus MCP.
- **Coding agents** (Codex, Claude Code, …) — consume via `agent-shim.py`.
- **Pi** (a coding-agent TUI) — same shim/spec.
- **steadfaste-tui** (a separate Rust project) — spec + golden vectors, or
  the CLI verifier.

Constraints: language-neutral (Python, Rust, TS), no gateway code in the
consumer, no per-harness bespoke implementation, fail-closed.

## Mechanism

### 1. Typed trust — only one class needs a signature

The bus carries ordinary agent traffic (EXEC, PING, PROPOSAL) **and**
gateway-relayed human text. Only the latter is untrusted-user material, so
only it must be signed. The rule is therefore **typed**, not global:

| Envelope | Meaning | Consumer rule |
|---|---|---|
| `kind: "user_message"` + valid `gateway_sig` | gateway-relayed human text | ACCEPT as **DATA**, never directives |
| `kind: "user_message"`, no/invalid sig | forged or tampered | **REJECT** → DLQ |
| no `kind` | ordinary agent traffic | ACCEPT opaquely (no user-text trust granted) |
| malformed | schema violation | **REJECT** → DLQ |

### 2. One decision function (`gateway_envelope.accept`)

A single consumer-side entry point so a caller cannot "forget" to verify:

```
accept(envelope, secret) -> Decision
    Decision.ok            # bool — may the caller trust this as DATA?
    Decision.kind          # "user_message" | "bus" | "malformed"
    Decision.reason        # why rejected (for the DLQ record)
```

It composes the existing `validate()` (shape) and `verify_signature()`
(authenticity), so shape-only validation can never masquerade as trust.
Python is the reference implementation.

### 3. One enforcement point per consumer class

Both funnel through the same decision — no divergence:

| Consumer class | Artifact | Change |
|---|---|---|
| Coding agents, **Pi**, **steadfaste-tui** | `agent-shim.py` `poll_inbox()` | verify before returning a message; on reject → archive to DLQ, return nothing |
| **Hermes** agents | `cortex-bus-mcp.py` inbox read | verify before surfacing a `user_message`; on reject → surface an explicit rejected marker, never the body |
| Any harness, any language | `gateway-envelope-verify.py` (CLI) | `--envelope -` → exit 0 accept / 1 reject; the shell-out bridge |

Why the shim is the right seam: ADR-0005 already establishes it as **ONE
standard shim, generated per agent, never hand-written bespoke per agent**.
Verification rides the artifact that every non-Hermes harness already uses —
so Pi and steadfaste-tui inherit it without gateway code.

### 4. Language-neutral spec + golden vectors

`docs/design/gateway-envelope-verification.md` §Recipe below is the normative
spec; `tests/vectors/gateway_envelope_v1.json` holds known-answer vectors
(secret, envelope, expected `gateway_sig`, expected accept/reject). A Rust
(steadfaste) or TS (Pi) implementation is correct iff it reproduces the
vectors. This is what makes the mechanism general rather than Python-shaped.

#### Normative recipe (v1)

1. `unsigned = {k: v for k, v in envelope.items() if k not in ("gateway_sig", "kind")}`
2. `canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), default=str)`
   — **key-sorted, no insignificant whitespace**.
3. `sig = HMAC-SHA256(key=secret.encode("utf-8"), msg=canonical.encode("utf-8")).hexdigest()`
4. accept iff `hmac.compare_digest(sig, envelope["gateway_sig"])` **and**
   `envelope.get("kind") == "user_message"`.
5. The secret is a shared symmetric key — identical on signer and every
   verifier. Empty secret ⇒ reject everything (never verify against a key
   that authenticates nothing).

### 5. Fail-closed

A consumer with no `GATEWAY_SECRET` configured must **refuse user messages**,
not accept them unverified. Missing secret is an operator error surfaced
loudly, not a silent downgrade — the same rule the signer now enforces
(daemon refuses to start without it).

## Non-goals

- No new transport, no gateway-owned inbox, no re-implemented harness.
- No per-harness bespoke verifier — the shim + spec are the only additions.
- Not a replacement for the bus ACLs; signature verification is orthogonal to
  transport authorization.

## Slice plan

| Slice | What | Deliverable |
|---|---|---|
| **CR7a** | `accept()` decision fn + typed-trust rules in `gateway_envelope.py` | code + unit tests |
| **CR7b** | Golden vectors + the normative recipe in this doc | `tests/vectors/gateway_envelope_v1.json` + a vector-driven test |
| **CR7c** | `gateway-envelope-verify.py` CLI (shell-out bridge) | script + tests |
| **CR7d** | Enforce in `agent-shim.py` `poll_inbox()` (covers coding agents, Pi, steadfaste-tui) | shim change + tests |
| **CR7e** | Enforce in the Hermes inbox read path (`cortex-bus-mcp.py`) | MCP change + tests |

CR7a–c are additive and safe to land first; CR7d–e change live consumers and
should land behind the spec + vectors so any regression is caught by parity.
