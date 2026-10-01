# PRODUCT — Critique of the Reference Architecture

> Role: PRODUCT in the architecture party. Anti-over-engineering voice.
> Target: `docs/party/architect.md`. Inputs: `README.md`, `docs/design-brief.md`,
> `docs/party/elicit.md`.
> Lens: a 1–2 person maintainer who wants "boring, stable, set-and-forget"
> and needs value from the harness *this month*, not a platform in 2029.

---

## 1. Does this deliver value fast and stay set-and-forget?

**Set-and-forget: mostly yes. Value fast: no — the value is buried under
platform ceremony.**

The stability engineering is genuinely good product work for this owner:
pinned deps, one config file, journal-as-source-of-truth, no telemetry, no
hot reload, restart-to-change. Those choices *reduce* future operator load,
which is the actual product for a 1–2 person team.

But look at what must exist before the first useful task completes under this
architecture: a daemon with an SSE endpoint and localhost HTTP ops API, a
supervisor with queue/leases, a plugin host with manifest schema + six
capability kinds, a `WorkerSpec` registration path, a template resolver with
layered lookup, a tool gateway, an Ink/React TUI with four tabs and a panel
registry, and an MCP client. That is a **platform**, and the user-visible
product — "give it a bugfix objective, come back to a verified commit and a
readable timeline" — is the last thing assembled on top of it.

**The MVP slice** (the thing that delivers 90% of the *value*, not 90% of
the architecture):

1. `core/`: store (exists), journal (`eventlog.ts`), config loader, tool
   gateway with permission check + `max_observe` truncation + timeouts.
2. The six built-in tools — with `edit.ts` semantics decided and tested
   (Q-404 is the single biggest quality lever in the product).
3. **One real LLM adapter** (Anthropic or OpenAI-compatible), with usage
   plumbed so budgets actually bind.
4. The own-agent loop, in-process, invoked directly by the CLI — behind the
   ABI types but NOT behind a plugin host yet.
5. Three CLI verbs: `codeharness run --template bugfix --objective "…"`,
   `codeharness status <id>` (JSON), `codeharness log <id> [--follow]`
   (the boring human timeline, which is just a fold over the journal).
6. Task templates as plain JSON files, whole-file override only.

That slice satisfies US-401, US-501, US-502 — the three stories that *are*
the product. Everything else is leverage on top of a working thing. Note the
elicitation already provides cover: F-106 (headless parity) says the TUI is
"a view, never the only access path" — so the CLI+journal MVP is not a
compromise, it is the architecture's own stated ground truth, shipped first.

---

## 2. Product value score: **6 / 10**

**Rationale.** The bones are exactly right for this owner (+): frozen tiny
ABI, journal-first visibility, one validated config file, six boring tools,
no auto-anything. The architecture is honest about trust boundaries and its
own biggest risk (own-agent re-acquiring privilege). If built as specified it
would genuinely sit unchanged for years.

Deductions (−): time-to-first-value is poor — roughly half the proposed
surface (daemon/SSE, plugin host with 6 capability kinds, TUI, MCP client,
panel API, event sinks, template layering) precedes or is orthogonal to the
first successful real task; the single most valuable component (a real LLM
adapter) is **absent from the file tree entirely**; the "90% out of the box"
claim is asserted, not tested (the architect concedes this in §7.4); and
several "defaults" contradict the zero-config promise (see §5). A design
that scoped v1 to the vertical slice and staged the platform would score 8–9.

---

## 3. SHOWSTOPPERS

- **S-1 — There is no real adapter in the architecture.** `core/adapter.ts`
  ships an interface and a fake. No `adapters/anthropic.ts` (or
  openai-compatible) appears anywhere in the proposed tree, and F-503 notes
  usage is currently hardcoded to zero. As specified, the system cannot
  perform its core function. This is the missing "90% default" — the one
  every single task touches.
- **S-2 — Zero-config is broken by the plugin allowlist.** NF-105/NF-202
  promise the stock install works with no config, but §2(e) makes
  `plugins.allow` an allowlist where "absent = disabled" — so a fresh
  install with no config file loads **no worker** and can run nothing.
  The 90% path requires config on day one. Direct contradiction.
- **S-3 — First-run value depends on the daemon.** The TUI, ops channel, and
  event feed all route through `daemon.ts` (SSE + HTTP). Q-102's "is there a
  daemon at all in v1?" was never answered — the architect silently answered
  "yes" and made it load-bearing. For one operator on one machine, a daemon
  is standing infrastructure to babysit (startup, crash, stale socket, port
  conflicts) — the opposite of set-and-forget.
- **S-4 — `edit_file` semantics undecided (Q-404) while the toolset is
  declared frozen.** Exact-match find/replace is named in the tree but never
  justified or tested. Edit-tool failure is the dominant failure mode of
  every coding agent in production; freezing the contract before validating
  the tool freezes the product's biggest weakness.
- **S-5 — Unbudgeted recurring maintenance disguised as features.** The
  price table (Q-504) goes stale monthly; the MCP client chases a spec that
  "itself still moves" (architect's own words, Decision 2); Ink/React is
  admitted as "the largest dependency in the whole system." Each is a
  standing tax on a 1–2 person team that was promised a maintenance fork,
  not an upkeep treadmill.

---

## 4. Mitigations

- **S-1:** Add `adapters/anthropic.ts` (or one OpenAI-compatible adapter
  covering many providers) to the v1 tree as a *named, tested deliverable*
  with usage reporting wired into `MODEL_REQUEST_FINISHED`. Acceptance: a
  real bugfix task completes end-to-end on a fixture repo with real tokens
  counted against budget.
- **S-2:** Ship a built-in effective default equivalent to
  `plugins.allow: ["own-agent"]`, overridable by config. Keep the allowlist
  semantics for everything *third-party*; first-party stock install must run
  with zero files written. Re-run the US-401 acceptance with no config
  present.
- **S-3:** v1 is `codeharness run` — one process per invocation, journal on
  disk, `log --follow` tails the file. The daemon + SSE become the v1.x
  upgrade that unlocks the TUI and concurrent supervision. The journal
  format (frozen) makes this staging free: every later consumer reads the
  same file.
- **S-4:** Before freezing Tool Contract v1's toolset, run the architect's
  own proposed task-corpus benchmark (§7.4) on 10–20 representative real
  tasks; decide find/replace vs. diff-apply from failure data, not taste.
  Cheap: the fake adapter can replay recorded tool sequences.
- **S-5:** Price table: make it user-maintained config with a checked-in
  starter (owner already controls config); no core release needed to update
  a price. MCP: defer entirely (see §5). TUI: keep, but as a separately
  versioned v1.x deliverable that the frozen SSE contract makes safe to
  slip.

---

## 5. Scope decision: over- or under-built?

**Over-built horizontally, under-built vertically.** The architecture
generalizes every surface for consumers that don't exist, while the one
vertical that makes the product real (real adapter → working edit tool →
verified commit → readable timeline) has gaps. For a 1–2 person stable
harness, every frozen contract is a 3-year *liability* — freezing an
interface nobody consumes is buying insurance on a house that isn't built.

**Speculative infrastructure with no concrete consumer — defer:**

- **Panel extension point (`PanelSpec` + registry + versioning).** Zero
  plugin panels exist or are planned. Elicitation scored it RICE 6.0 —
  the lowest-scored TUI requirement. Stock panels can be plain components;
  extract the registry when a second consumer appears.
- **`registerAdapter` / `registerTemplates` plugin slots.** No plugin
  contributes either in any story. Two of the six capability kinds are
  pure speculation; a "closed set" of capabilities should close around
  actual consumers: `worker`, `tool`, maybe `event_sink`. Three, not six.
- **MCP bridge (Lane A).** The six built-ins are *claimed* to cover 90%;
  no v1 story requires a seventh tool. The bridge imports a moving spec
  into a frozen system to serve a hypothetical. Defer until the first
  concrete "I need tool X" arrives — the gateway's registration point
  makes retrofitting cheap.
- **Event-sink plugin capability.** The only named consumer is an example
  Prometheus sink. NF-504 (grep-able JSONL) already answers every operator
  question at this team size. Journal first, sinks when a dashboard is
  actually wanted.
- **Template layering + version pins.** Layered user/plugin/builtin
  resolution with per-template semver and pins serves a template ecosystem
  of one user. Whole-file override in one user dir (elicit Q-301's lean
  option) covers the 10%; `extends`/pins can wait for demonstrated need.
- **Supervisor queue/leases at v1 scale.** Leases exist to arbitrate
  multiple workers/processes. v1 has one worker, one operator, one machine.
  Keep the *ABI vocabulary* (`lease_id` costs nothing) but the lease
  machinery can be a stub until concurrent supervision ships with the
  daemon.
- **Chat tab.** Q-103 flagged it; the architecture kept a `ChatPanel`
  anyway. Steering input: yes. Conversational transcript rendering (which
  drags message-format knowledge toward the core boundary): no.

**Genuinely missing "90% defaults" — add:**

- A **real adapter** (S-1) — the largest omission in the document.
- A **default-enabled own-agent** (S-2).
- **`codeharness init` / first-run path**: emit a commented `harness.jsonc`,
  check for an API key env var, validate. Discoverability is a north-star
  requirement (#4) and nothing in the tree serves minute one.
- **Retry/recovery policy defaults.** The README puts "Retry / recovery" in
  the core box; the architecture defines `TASK_RETRIED` as an event but
  never says when retries happen, how many, or with what backoff. For
  set-and-forget overnight runs this *is* the product; it needs a decided,
  boring default (e.g., one retry on worker crash, never on budget stop).
- **Permission vocabulary (Q-405).** Gating is a Must; the strings it gates
  on are still an open question. The tree implies `shell|fs.read|fs.write|git`
  — enumerate and freeze them, since they're de-facto ABI semantics.
- **The 90% benchmark itself.** A claim load-bearing for the entire scope
  ("six tools = 90%") with no measurement plan in v1.

**What the deferrals preserve:** nothing above touches `abi.ts`, the journal
format, or the tool contract. That's the point of the frozen-contract design
— it makes deferral *safe*. The architecture should exploit its own best
property and stage delivery instead of shipping the whole platform at once.

Recommended staging:
- **v1.0 (the product):** MVP slice from §1 — CLI, journal, gateway, six
  tools, real adapter, in-process own-agent, task templates, one config file.
- **v1.1 (the cockpit):** daemon + SSE + TUI (stock panels only, no panel
  API) + minimal plugin host (`worker`, `tool`) + neutrality fixture (F-209).
- **v1.2+ (on demand):** MCP bridge, event sinks, panel API, template
  layering — each when its first real consumer shows up.

---

## Summary

Ship first: the vertical slice — frozen ABI + store + journal + permission-
gated gateway with the six tools (edit-tool semantics benchmark-validated) +
**one real LLM adapter with usage plumbing** + the own-agent loop invoked
in-process by three CLI verbs (`run` / `status` / `log --follow`), task
templates as plain JSON with whole-file override, own-agent enabled by
default so a fresh install runs with zero config. Cut (defer, not delete)
everything whose consumer doesn't exist yet: the daemon/SSE and Ink TUI to
v1.1, and the MCP bridge, panel extension API, adapter/template/event-sink
plugin slots, template layering + version pins, lease machinery, and Chat
transcript rendering to v1.2-on-demand — the frozen journal and contracts
make all of it safely retrofittable, which is precisely why it shouldn't be
built before someone needs it. Score 6/10 as specified: right bones, right
freeze discipline, but the platform is scheduled ahead of the product and
the single component every task depends on (a real adapter) isn't in the
tree.
