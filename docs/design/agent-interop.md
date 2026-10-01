# Agent interoperability — the abstraction layer

> **Standing constraint (Luke, 2026-10-02):** *"fix things for interoperability
> with different coding agents. always be thinking this."* Treat any agent-facing
> capability as something **N heterogeneous coding agents** will consume — Pi,
> Hermes, Claude Code, Codex, steadfaste-tui, and whatever appears next.

Why a written contract: the failure is not "no design", it is **each host
growing its own version** of the same capability. That is exactly what happened
here — `mem_context` existed in both the Hermes plugin and the MCP server, so
whichever the runtime resolved, the other **silently did not exist**. An agent
diagnosed "memory is broken", fell back to raw SQL, and reported the backend as
the working path.

---

## The three layers

```
   ┌─────────────────────────────────────────────────────────────┐
   │ CONTRACT   ops/services/mycortex-mem/context_tools.py        │
   │            TOOLS (metadata) · HANDLERS (behaviour)           │
   │            dispatch(name, args) -> JSON string               │
   │            Never raises · never host-specific                │
   └───────────────▲─────────────────▲─────────────────▲─────────┘
                   │                 │                 │
        ┌──────────┴──────┐ ┌────────┴───────┐ ┌───────┴──────────┐
        │ ADAPTER: MCP    │ │ ADAPTER: CLI   │ │ ADAPTER: plugin  │
        │ MCP-native      │ │ anything that  │ │ Hermes Memory-   │
        │ harnesses       │ │ shells out     │ │ Provider         │
        └─────────────────┘ └────────────────┘ └──────────────────┘
           Hermes, Claude     Pi (+ any)         Hermes
           Code, Codex
```

- **CONTRACT** — one module, host-neutral. It may not import a harness.
- **ADAPTER** — per host, thin, **no semantics of its own**. It converts the
  host's calling convention to `dispatch()` and nothing else.
- **HOST-LOCAL EXTRAS** — allowed only when a capability is *inherently*
  host-bound, and they must say so. Today there is exactly one:
  `mem_reasoning` needs the host's own LLM, so it lives in the Hermes adapter and
  is explicitly excluded from the contract.

**A new host means a new ADAPTER, never a new implementation.**

---

## The rules (each one is a bug we actually hit)

1. **One implementation per capability.** Two implementations of one tool *name*
   is worse than none: the runtime silently picks one and the other becomes a
   phantom. Enforced by test.
2. **The contract may not import a harness.** If it needs Hermes, the capability
   is not host-neutral yet — either extract it or declare it a host-local extra.
3. **Schemas are derived, never hand-written.** A hand-written schema list *is* a
   second definition, and it drifts the moment either side changes.
4. **Report failure loudly; never substitute a fallback implementation.** A
   fallback is how the duplicate surface starts. Fail-open is for *availability*
   ("carry on without memory"), never for *semantics*.
5. **`dispatch()` must not raise.** A host must not die because the store is
   unreachable. It returns a message the host can ignore.
6. **Identity is resolved in ONE place** (`args → env → git`), so a session
   written by one host is restorable by another.
7. **Verify the host's own API before writing its adapter** — never infer it.
   Pi's first adapter failed twice *silently*: the handler's first parameter is
   the event (not a ctx), and injection is the return value (not a ctx method).
8. **Never let the model own a lifecycle guarantee.** The trigger (`turn_end`,
   a stop hook, a cron) belongs to the host. "Remember to save" is not a
   mechanism.

---

## Adding a coding agent (the checklist)

```bash
# 1. Declare it — the registry is the single source
python3 ops/install/harnesses/generate-harnesses.py \
    --add <name> --layer mcp|cli-extension|cli-hook|none --surface '<what you wire against>'
# 2. Fill in why / install / verify in registry.yaml, then:
python3 ops/install/harnesses/generate-harnesses.py && \
python3 ops/install/harnesses/generate-harnesses.py --check
```

Then, for a **new** capability (not just a new host):

| Step | Do |
|---|---|
| 1 | Implement it **once** in the contract, with metadata in `TOOLS` |
| 2 | Wire every existing adapter to it — helpers: MCP + CLI + plugin |
| 3 | Add it to the Pi extension's `registerTool` list |
| 4 | Prove it from **two different hosts** before claiming interop |
| 5 | Add the drift guard (below) in the same cycle |

**If the capability cannot be host-neutral** (it needs a specific harness's
runtime), ship it as a **declared host-local extra** naming the reason — like
`mem_reasoning`. Never fork the shared tool under the same name.

---

## Drift guards (tests, not intentions)

`tests/test_context_harnesses.py` enforces the invariant:

- every adapter references the contract and reaches the store via `dispatch()`;
- the plugin may not carry a hand-written schema list;
- the Pi extension may only register tool names the contract actually has;
- `mem_reasoning` is the *only* host-local exception, and it must state why.

A rule with no test is a preference. These are enforced.

---

## Checklist before shipping anything agent-facing

- [ ] Does it work from **at least two different harnesses**?
- [ ] Is the semantics in **one** place, with adapters that add none?
- [ ] Are schemas/metadata **derived**, not duplicated?
- [ ] Does an unreachable dependency **fail open with a visible message** (never
      a silent empty result, never a fallback implementation)?
- [ ] Does it work on **Linux and macOS**?
- [ ] Is there a **drift guard**, not just a doc?
- [ ] Would a *new* agent discover it? (registry + skill + generated README)
