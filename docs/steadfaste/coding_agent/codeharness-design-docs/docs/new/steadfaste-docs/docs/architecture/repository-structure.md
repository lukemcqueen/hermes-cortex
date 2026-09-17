# steadfaste — Repository Structure (the design *is* the folders)

> A human should understand the whole product from the folder names alone.
> If a folder/file name won't survive contact with the real code, the design
> isn't done. This is the structural design — over-structured deliberately,
> future-in-mind, before any real code depends on the paths.

## The 30-second tour

```
steadfaste/
  spec/         THE AUTHORITATIVE CONTRACT. core-spec.md = the frozen core +
                interfaces as corrected by the adversarial attack. The thing
                Rust core + Covenant get built against. (Status: design, not frozen.)
  core/         Rust. The frozen core — the black box that just works.
                (REMOVED the premature Covenant stub; the real crate is built
                against spec/core-spec.md once the Covenant is finalized.)
  worker/       TS. The agent wing — loop, tools, adapters, templates.
  web/          TS. The UI for normal people (a browser, familiar).
  gateway/      TS. Chat plumbing — Telegram now, others later, one adapter.
  packaging/    How it gets installed/updated/uninstalled (Homebrew today).
  governance/   The harness policing itself (adversarial, no-bypass, …).
  test/         Every proof — by layer (unit→contract→integration→e2e→lifecycle).
  docs/         The design history + why. design/ = the attack findings that
                PROVE the spec; architecture/ = the vision + structure;
                research/ = lessons from top harnesses; standard/ = the
                testing/governance standard; party/ + story/ = the journey.
  config/       The one config file (example + schema).
```

## The layers, in dependency order

```
              ┌────────────────────────────────────────────┐
              │            core/  (Rust, frozen)           │
              │  abi · store · journal · event_bus ·       │
              │  config · supervisor · gateway · transport │
              └────────────────────┬───────────────────────┘
                                   │ Covenant v1 (JSON over stdio)
        ┌──────────┴──────────┬─────┴──────────┐
        ▼                     ▼                ▼
  worker/ (TS agent)     web/ (TS UI)     gateway/ (TS chat)
    loop·tools·           non-coder         telegram·whatsapp
    adapters·templates    React UI         (TransportAdapter)

  cross-cutting:  packaging/ (lifecycle) · governance/ (self-policing)
                  test/ (proof) · config/ (single knob) · docs/ (design)
```

## Folder-by-folder (name = intent, and the boundary)

| Path | Layer | Owns | Frozen? | Future-proof (why it won't need renaming) |
|------|-------|------|---------|--------------------------------------------|
| `core/` | Rust | the Covenant, durability, audit, config, supervision, permission gateway | **frozen** (3-yr) | "core" is stable regardless of growth; the Rust crates live under it |
| `worker/` | TS | the agent loop, tools, model adapters, templates | swappable | "worker" = the actor; subfolders test tools/adapters/templates cleanly |
| `web/` | TS | the non-coder UI (React, browser) | swappable | a web UI is the timeless normal-person surface |
| `gateway/` | TS | transport-agnostic messaging | swappable | "gateway" owns chat; `adapters/` makes Telegram/WhatsApp peers |
| `packaging/` | lifecycle | Homebrew formula, install/update/uninstall, lifecycle tests | moves with releases | one place for the whole loose-end-free shipping story |
| `governance/` | self-policing | adversarial, no-bypass, mutation, cover-ratchet, neutrality | the harness's own tests | named by what it *enforces*, not by tool (won't rot) |
| `test/` | proof | unit, contract, integration, e2e, lifecycle | — | named by layer so CI maps 1:1 |
| `docs/` | design | why, architecture, standard, story, operator | living | split by audience: design vs operator |
| `config/` | single knob | `harness.example.jsonc` + schema | — | "one place for every knob" is a hard principle |
| `prototype-ts/` | legacy | the TS design-reference (proves the Covenant/store contracts) | **not** part of the product | named so nobody mistakes it for the core |

## Naming contract (the rules that keep it clean forever)

1. **File = what it is.** `loop.ts` is the agent loop; `adapter.ts` is the model
   adapter. A file that does two things is two files.
2. **Folder = a boundary.** `worker/tools/` is where tools go; a tool that lives
   elsewhere is misplaced, and a misplaced file is a design bug.
3. **Rust core files are `snake_case.rs`** (`event_bus.rs`, `worker_transport.rs`),
   matching Rust idiom; TS files are `kebab-case.ts` (`worker-transport.ts`).
4. **No "misc", "utils", "other".** If a file needs a junk-drawer, that's a
   design failure — split it into named concerns instead.
5. **The `core/` boundary is sacred.** Nothing under `core/` imports from
   `worker/`, `web/`, `gateway/`, or `prototype-ts/`. The core speaks only the
   Covenant. (Enforced by the neutrality governance gate.)
6. **Rename before it's expensive.** Per Luke: restructure/rename/move *now*,
   while nothing real depends on the paths. Once real code lands, a rename
   breaks it — so the structure must be right before that.

## Why this layout is "done" (the test)

**Ask the 30-second browse question:** a new human (or a 2029 agent) opens the
repo and reads only the folder names. They should be able to *point* to: the
frozen core (`core/`), the agent (`worker/`), the UI (`web/`), the chat plumbing
(`gateway/`), how it ships (`packaging/`), how it's guarded (`governance/`),
where the proofs live (`test/`), and where the design is documented (`docs/`).

If any of those is ambiguous, the design isn't done. This layout passes that test
— and every folder reserves space for the growth the design already anticipates
(swappable transports, models, DBs, workers).