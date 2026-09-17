# PROMPT ENGINE — Focused Design (surface 6)

> Design pass closing the open question from `decision.md` §"Open questions"
> item 1. Read against: `decision.md` (frozen-core shape), `architect.md`
> (§0 layout, §3 templates), `security.md` (§1.8, §1.9), `sre.md` (§5.7,
> §5.14), `qa.md` (§5.6). This doc designs INTO the decided shape: out-of-
> process stdio worker (ABI v1), journal-as-truth, single JSONC config,
> permission-gated tool gateway, provider-agnostic adapter + usage accounting.

---

## 1. Verdict: CORE — a small pure library, with all churn pushed into data

**The prompt engine is CORE** (`core/prompt.ts`), frozen with core 1.x.
It is **not** a plugin.

Rationale, weighed as asked:

- **Cacheability is a core invariant.** The byte-stable prefix, the
  prefix-hash provenance record, the tainted-variable refusal, and the
  cached-token accounting are *enforcement and accounting* — the same class
  of thing as the permission gate and the audit ledger. `decision.md` already
  puts "Template resolver (layered, deterministic, versioned)" and "Adapter
  interface + usage accounting" in core, and pre-freeze fix 11 mandates the
  prefix contract. A plugin cannot enforce an invariant on itself; security
  §1.9 is explicit that a compromised engine must be *contained by the core*
  (budget caps and journal writes are core-side regardless). If the contract
  lives in a plugin, every worker reinvents it and the conformance suite has
  no single door to test.
- **Per-model assembly looks peripheral — but it's data, not code.** The
  churny part (provider cache styles, message shapes, context windows, which
  system prompt a model gets) lives entirely in **model profile files and
  template files**. Adding Claude-next in 2028 is a JSON profile + a template
  drop — zero core code. So freezing the engine does not freeze provider
  knowledge. This resolves the tension: the *mechanics* are core, the *model
  knowledge* is peripheral data.
- **It stays freezable because it is pure.** `assemble()` is a pure function
  (QA §5.6 precondition): no fs, no clock, no network, no provider SDKs.
  ~300 lines. Purity is what makes a 3-year freeze credible.
- **Reconciliation with decision.md line 90** ("prompt engine … is a plugin
  or peripheral"): that line predates this pass and conflated the engine with
  the own-agent's *use* of it. The corrected split: the engine (contract +
  assembly + accounting fold) is core; whether a given worker *uses* it is
  peripheral. Workers are out-of-process, so they import `core/prompt.ts` as
  a library in their own process — what core freezes is the contract, plus
  core-side verification of the journaled records. A future Pi worker may
  render prompts its own way — the core still accounts its usage and journals
  whatever prefix hash it declares (or `prefix_hash: null`, which simply
  forfeits cache accounting). No worker is privileged; ours just gets the
  library for free.

---

## 2. The TypeScript interface — `PromptEngine` (Prompt API v1)

```ts
// core/prompt.ts — Prompt API v1 (frozen, additive-only)
import type { LlmMessage } from "./adapter";
import type { Task } from "./abi";

export type Taint = "trusted" | "tainted";

export interface PromptVar {
  value: string;
  taint: Taint;
  /** provenance, folded into vars_hash journal record */
  source: "config" | "core" | "operator_template" | "task_input"
        | "tool_output" | "rag" | "repo";
  // task_input / tool_output / rag / repo are ALWAYS tainted; the factory
  // (promptVar()) enforces it — you cannot construct a trusted var from them.
}

export interface ModelProfile {
  id: string;                       // "anthropic-like"
  version: string;                  // semver; pinnable
  context_window: number;
  reserved_output_tokens: number;
  message_shape: "openai" | "anthropic" | "plain";
  cache: {
    style: "breakpoint" | "implicit" | "none"; // anthropic | openai | local
    min_prefix_tokens?: number;     // don't mark tiny prefixes cacheable
  };
  templates: {                      // TemplateRef names → core/template.ts
    system: string;                 // e.g. "system/worker-base"
    skills?: string;                // e.g. "system/skills-frame"
    agents_frame?: string;          // frame only — repo AGENTS.md CONTENT
  };                                //   is tainted, see §5
  tokenizer: string;                // pinned estimator id, e.g. "est/chars4@1"
  pricing?: { input_usd_per_mtok: number; output_usd_per_mtok: number;
              cached_usd_per_mtok: number };
}

export interface ResolvedTemplate {
  name: string; version: string;
  layer: "builtin" | "user" | "plugin";   // NEVER "repo" for prefix templates
  contentHash: string; source: string;    // text already read at attempt start
}

export interface AssembleInput {
  task: Task;
  profile: ModelProfile;
  /** snapshot resolved ONCE at attempt start (TEMPLATES_RESOLVED) */
  templates: ResolvedTemplate[];
  vars: Record<string, PromptVar>;
  toolSchemas: ToolSchemaLite[];    // gateway-registered, operator-approved only
  history: LlmMessage[];            // volatile; never touches the prefix
}

export interface PromptPlan {
  /** byte-stable for the whole attempt; the provider-cacheable region */
  prefix: string;
  prefixHash: string;               // sha256 hex of prefix bytes
  suffix: LlmMessage[];             // AGENTS.md envelope + plan + history + tool results
  templateVersions: ResolvedTemplate[];  // provenance, journaled
  varsHash: string;                 // sha256 over sorted trusted var names+values
  tokenEstimate: { prefix: number; suffix: number };
}

export interface PromptEngine {
  /** PURE: same inputs → byte-identical output. No fs/clock/net. */
  assemble(input: AssembleInput): PromptPlan;   // throws TaintViolation |
                                                //        ContextOverflow (typed)
}

export function createPromptEngine(): PromptEngine;
export function estimateTokens(text: string, tokenizer: string): number;
```

Adapter change (additive, per QA §5.6):

```ts
// core/adapter.ts — LlmUsage gains one optional field
export interface LlmUsage {
  input_tokens: number;
  output_tokens: number;
  cached_tokens?: number;   // provider-reported cache-read tokens
}
```

Accounting fold (pure, journal-in → report-out):

```ts
// core/prompt-accounting.ts
export interface CacheReport {
  requests: number; hits: number; hitRate: number;
  cachedTokens: number; uncachedTokens: number;
  savedCostUsd: number;             // cached × (input rate − cached rate), per profile pricing
  invalidations: { seq: number; oldHash: string; newHash: string }[];
}
export function foldCacheReport(events: JournalEvent[]): CacheReport;
```

---

## 3. Module / file layout

```
core/
  prompt.ts               ★ Prompt API v1: types + assemble() + prefix hashing
                          #   + taint enforcement (~300 lines, pure)
  prompt-accounting.ts    ★ foldCacheReport() + per-request cache record shape
  adapter.ts              ★ (existing) + cached_tokens on LlmUsage (additive)
  template.ts             ★ (existing, architect §3) — prompt.ts consumes its output
templates/
  profiles/                 # model profiles — DATA, peripheral, versioned files
    openai-compatible.json  # v1 ships exactly these two
    anthropic-like.json
  system/
    worker-base.md          # (exists per architect §3)
    skills-frame.md
    agents-frame.md
schema/
  profile.schema.json     ★ validates profile files at load (unknown keys = error)
test/core/
  prompt-engine.test.ts     # QA §5.6 suite: byte-stability, volatility partition,
                            #   golden prefix hashes, per-profile structure goldens,
                            #   monotone token budget, taint refusal, accounting fold
test/fixtures/prompt/
  golden-prefixes.json      # (template version, profile) → prefixHash
```

Nothing under `plugins/`. Profile files layer exactly like templates
(user dir > plugin dir > builtin, pinnable) via the existing resolver — no
second lookup mechanism.

---

## 4. Config surface (in the ONE `config/harness.jsonc`)

```jsonc
{
  "prompt": {
    // which profile a task uses when model_policy doesn't name one
    "default_profile": "openai-compatible",
    // extra profile layer (same precedence rules as templates.dir)
    "profiles_dir": "~/.codeharness/profiles",
    // pin profile versions, same shape as templates.pins
    "pins": { "anthropic-like": "1.0.0" },
    // SRE §5.7: rolling cache-hit alarm → CACHE_DEGRADED journal event
    "cache_hit_alert_below": 0.5,
    "cache_hit_alert_window": 20      // requests in the rolling window
  }
  // templates.* block already exists (architect §3e) and is reused as-is
}
```

Unknown keys are a startup error (decided config rule). No env vars.

---

## 5. The cacheable-prefix contract

**IN the prefix** (all resolved and rendered ONCE at attempt start, in this
fixed order, then hashed and frozen):

1. Rendered system prompt — from the profile's `templates.system`, resolved
   from **trusted layers only** (`builtin` | `user` | `plugin`; the repo-local
   template layer is refused for prefix templates — security §1.7/S-4).
2. Rendered skills frame (same trust rule).
3. AGENTS.md **frame** — the trusted instructions *about* how to treat repo
   conventions; never the repo file's content (see NOT list).
4. Tool schemas — gateway-registered, operator-approved, sorted by tool name
   (deterministic order; a reorder is a cache invalidation and the golden test
   catches it).
5. Trusted template variables only — the closed, documented dictionary
   (`workspace`, `tool_names`, `model_id`, …). Anything not in the dictionary
   is tainted by default.

**NEVER in the prefix** (frozen list, security §1.9):

- Secrets / API keys (provider-side caches store and replay them verbatim).
- Task-specific data: `objective`, file contents, usernames (cross-task
  leakage under cache mis-keying).
- Anything tainted: tool output, RAG chunks, repo-local files **including the
  repo's actual AGENTS.md content**, MCP tool descriptions not operator-
  approved, task input.
- Per-run entropy: timestamps, uuids, counters (breaks determinism AND
  silently defeats caching, hiding the poisoning signal).

**How per-model templatization composes with byte-stability:**

- The profile selects *which* templates; `core/template.ts` resolves versions
  **once at attempt start** and the core journals
  `TEMPLATES_RESOLVED{[name@version, layer, content_hash]}` (SRE §5.14).
  `assemble()` receives that snapshot — it never reads disk. All `{{var}}`
  resolution happens **before** the cache boundary.
- Swapping the system prompt per model = a different profile = a different
  (individually stable) prefix per model. Swapping mid-conversation is
  impossible by construction: the snapshot is per-attempt.
- Mid-attempt disk edits (e.g. the running task writes a skill file) do NOT
  re-render. The prefix hash is recomputed before each model request; a
  changed hash is journaled as `PREFIX_CHANGED{old_hash, new_hash, cause}`
  and **hard-fails the attempt** — mutation is a security event, not a cache
  miss (security §1.9). Template changes take effect at the *next attempt*,
  where the new hash + version set is journaled as the cause of the expected
  first-request MISS.
- Replay re-assembles from the *pinned* journaled versions
  (`TEMPLATES_RESOLVED` + `templates.pins`), reproducing the prompt byte-for-
  byte; the first post-replay request is an expected, journaled MISS
  (SRE §5.7 — replay correctness never depends on cache warmth, only cost).

## 6. Taint escaping

- Every variable enters as `PromptVar{value, taint, source}`. The factory
  forces `taint: "tainted"` for sources `task_input`, `tool_output`, `rag`,
  `repo` — a caller cannot launder them.
- **Hard rule (thrown, not warned):** a tainted var referenced by any prefix
  template → `TaintViolation` → attempt fails with a journaled
  `TAINT_VIOLATION{template, var, source}`. Tainted vars may never appear in
  the prefix or in any template that names tools/permissions/approvals.
- In the **suffix**, tainted values render only inside the untrusted-content
  envelope:

  ```
  <untrusted source="tool_output:shell" sha256="…">
  …value with template delimiters ({{ }}) and envelope delimiters neutralized…
  </untrusted>
  ```

  Never bare, never in instruction position. Same envelope as tool results
  and RAG chunks (security M-6) — one escaping mechanism, not three.
- A template variable is **data**: rendered text can never add a tool, widen
  a permission, or waive approval — tool availability and gates are
  core/gateway state, never parsed from render output. The conformance suite
  keeps the hostile-template fixture proving it (security §1.8).

## 7. Cache / cost accounting contract

Measurement (truth = provider-reported usage, never engine self-report):

- The adapter maps provider usage fields into
  `LlmUsage{input_tokens, output_tokens, cached_tokens?}` on
  `MODEL_REQUEST_FINISHED`. Budget caps are enforced core-side on this record
  — a lying engine hits the cap anyway (security §1.9).
- At attempt start, the core journals
  `PROMPT_RENDERED{prefix_hash, template_versions, profile_id@version,
  vars_hash}` (NF-301 provenance; hashes in the journal, prompt content out).
- Per model request, the journal record carries
  `cache: {prefix_hash, hit: boolean, cached_tokens, uncached_tokens},
  cost_usd`. `hit` = `cached_tokens > 0`; cost from the profile's pricing
  block.
- `PREFIX_CHANGED` (see §5) marks explicit invalidation; `foldCacheReport()`
  surfaces it as a `cache_invalidated` marker in the fold (QA §5.6).
- Rolling hit-rate below `prompt.cache_hit_alert_below` over
  `cache_hit_alert_window` requests → `CACHE_DEGRADED` journal event (SRE's
  3am cost-spike detector; worst case still bounded by `budget.max_cost_usd`).

Surfacing — the boring log (SRE §5.1), derived purely from the journal, no
second write path:

```
12:00:02 prompt: system/worker-base@1.2.0 → anthropic-like@1.0.0  (PROMPT_RENDERED)
12:00:05 model req #1  cache MISS (first request)
12:00:41 model req #1 done 1.2k in / 3.4k out / 0 cached  $0.031
12:01:05 model req #2  cache HIT 91%   (cached 8.1k / uncached 0.8k)
03:07:12 cache degraded — hit rate 0.31 over 20 reqs  (CACHE_DEGRADED)
```

CLI: `codeharness cost <task_id>` prints the `CacheReport` fold (per-task and
rolling hit-rate, saved cost, invalidation list).

## 8. MVP slice

Smallest thing that delivers model/cache-aware value (fits the vertical MVP,
decision.md §MVP):

1. `core/prompt.ts` — `assemble()` with prefix/suffix partition, prefix
   hashing, taint enforcement, single char-based token estimator
   (`est/chars4@1`; relations-only tests per QA's anti-change-detector rule).
2. Two profiles: `openai-compatible.json` (implicit caching) +
   `anthropic-like.json` (breakpoint) — data files, schema-validated.
3. `cached_tokens` plumbing through the one real OpenAI-compatible adapter
   (pre-freeze fix 4) into `MODEL_REQUEST_FINISHED`.
4. Journal records: `PROMPT_RENDERED`, per-request cache record,
   `PREFIX_CHANGED`, `TAINT_VIOLATION` + the boring-log line shapes above.
5. `foldCacheReport()` + `codeharness cost`.
6. The QA §5.6 test file: byte-stability, volatility partition, golden prefix
   hashes, taint refusal, accounting fold on fixture journals.

Deferred (safely retrofittable — the journaled hashes make it so): pinned
per-family tokenizer fixtures, multiple cache breakpoints (anthropic
multi-block), `CACHE_DEGRADED` alert wiring, suffix compaction strategies,
skills-directory scanning, the soak-stage live-provider cache check
(promotion pipeline, not CI — QA §5.6).

## 9. Open questions

1. **AGENTS.md second breakpoint.** Repo AGENTS.md content is tainted →
   suffix, but it is *stable within an attempt*; providers with multi-
   breakpoint caching could cache it separately. Worth a second breakpoint in
   v1.1? (Needs measured cost data first.)
2. **Foreign-worker accounting.** A Pi/Claude worker that doesn't use
   `core/prompt.ts`: require it to journal a `prefix_hash` (even opaque) to
   participate in cache accounting, or accept `null` = unaccounted? Leaning:
   accept `null`, log it visibly — ABI stays neutral.
3. **Pricing tables.** Cost-per-token lives in the profile today; a provider
   price change then requires a profile bump. Alternative: a separate
   `pricing.jsonc` layer. Decide when the second real adapter lands.
4. **Tokenizer estimator accuracy.** chars/4 is fine for budgeting margins at
   MVP; decide the trigger (a real ContextOverflow incident?) for vendoring
   per-family vocab fixtures.
5. **Trusted-variable dictionary freeze.** The closed dictionary
   (`workspace`, `tool_names`, …) becomes part of the frozen contract — the
   final list needs one pass against the own-agent loop implementation before
   ABI freeze.
