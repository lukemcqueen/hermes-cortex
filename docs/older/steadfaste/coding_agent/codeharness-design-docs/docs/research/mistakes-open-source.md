# Open-Source Harness Mistakes — "Don't Repeat" Notes for Steadfaste

**Purpose.** Steadfaste is meant to be the *boring-stable* harness: a minimal frozen
core that developers, integrations, and consultants can depend on. These notes
extract the concrete failures of four open-source coding-agent harnesses so we
don't reproduce them. (Pi / OpenSwarm are already studied first-hand by the owner
and are deliberately out of scope here.)

**Lens (owner doctrine): ANTI-BLOAT.** Every lesson below is read through one
question — *what happens when a harness grows beyond a dependable core?* The
answer, consistently, is that the core stops being dependable and the people who
built on it get burned. The recurring design rule is therefore:

> **Minimal frozen core + plug-ins / config.** Others *plug into* steadfaste or
> *configure* it for a model (Claude, etc.). Steadfaste does not grow a large
> moving surface of its own.

---

## 1. OpenManus (FoundationAgents) — release churn / demo-grade prototype

**The mistake.** Built as a viral clone in three hours and kept shipping features
with no stability discipline. The README itself says "The prototype is launched
within 3 hours and we are keeping building!" and "It's a simple implementation."
Features arrive as *flag-marked unstable*: the multi-agent path is literally
`run_flow.py`, documented as "For unstable multi-agent version," the DataAnalysis
agent is an off-by-default bolt-on, and a whole second project (OpenManus-RL) was
spun off in parallel. External trackers summarize it as "insanely fast iteration,
many bugs/security vulnerabilities" vs. a single frozen pin (`v0.3.0`, April 2025)
that users are told to lock to in order to "avoid conflicts."

**Who made it.** FoundationAgents (MetaGPT lineage). A demo-first team optimizing
for adoption speed, not for a contract other software can lean on.

**Design rule for steadfaste.**
- A harness whose README advertises "unstable" entry points is a red flag. Never
  ship a feature into the main surface until it has a *stable, versioned,
  backward-compatible* contract — or keep it out of the core entirely.
- Release churn is a tax on every integrator. Pin a slow-moving core and make
  every fast-moving dependency (browser automation, etc.) an *isolated plug-in*
  outside the core — OpenManus only got this right retroactively, when it moved
  fast-moving Browser Use deps behind `uvx` isolation.
- "Launched in N hours" is a marketing signal, not an engineering one. Boring-
  stable means the opposite: deliberately not shipping.

---

## 2. OpenHands (All-Hands-AI) — large moving surface + self-hosted setup fragility

**The mistake.** OpenHands is the cautionary tale of *surface area as a
liability.* One repo contains: the agent loop, multiple sandbox runtimes
(Docker, Kubernetes, process/"local", remote, E2B), a web UI, an SDK, a server
API, cloud, and enterprise (Kubernetes + RBAC, license-gated). Because the whole
thing moved as one monolith, it had to undergo a wholesale **V0 → V1
architectural migration** (V0 scheduled for removal April 1, 2026), which broke
configuration and setup hooks that users had built on.

Concrete manifestations:
- **Dual configuration systems.** `config.toml` (V0) and `settings.json` (V1)
  coexisted; the project had an open issue *"Unify dual configuration systems
  (config.toml + settings.json)"* and eventually shunted the entire old
  `config.toml` / "runtime" reference into a "Legacy (V0)" section of the docs.
  Environment variables changed names and mechanisms (`RUNTIME=docker|process|remote`
  → new sandbox selection).
- **Self-hosted / Kubernetes fragility.** Deployments behind a reverse proxy or on
  Kubernetes needed a tangle of URL-pattern knobs to make the agent reach its own
  sandbox: `SANDBOX_CONTAINER_URL_PATTERN` / `OH_SANDBOX_CONTAINER_URL_PATTERN`,
  `AGENT_SERVER_USE_HOST_NETWORK`, `SANDBOX_VOLUMES`, `AGENT_SERVER_IMAGE_*`.
  Getting "agent can't connect to its runtime" right is a distinct, recurring
  support class.
- **Workspace / repo-layout assumptions that broke setup hooks.** Repository
  customization is driven by files OpenHands *discovers* in a specific layout —
  `.openhands/setup.sh` (runs every session), `.openhands/hooks.json`,
  `.openhands/pre-commit.sh`. The layout *changed*: `pre-commit.sh` was replaced by
  "Stop hooks" (`hooks.json` + `.openhands/hooks/*.sh`), so a repo's existing
  hooks silently stopped applying after upgrade. Hooks are resolved from
  `{project_dir}/.openhands/...`, and the workspace mount itself depends on
  `PROJECTS_PATH` / `SANDBOX_VOLUMES` being pre-created *before* the container
  starts — a mismatch that produces "workspace not displaying properly" issues.

**Who made it.** All-Hands-AI (formerly OpenDevin). A VC-backed platform team
whose product scope is "the open platform for cloud coding agents" — necessarily
everything at once.

**Design rule for steadfaste.**
- **Freeze the core; do not fold the runtime into it.** The sandbox/execution
  backend is a *plug-in point*, not a first-class citizen of the core. One runtime
  (or a tiny stable runtime interface) in the core; Kubernetes/Docker/remote as
  out-of-core plug-ins that can change without touching the core contract.
- **Never run two configuration systems at once.** One config schema, one loading
  hierarchy, one migration path. Renaming a config key or env var is a breaking
  change that must be versioned and migrated, not "moved to Legacy."
- **Self-hosted setup must be one command, not a knob farm.** Every URL-pattern /
  host-network / volume env var is a place a user gets "connection refused." Push
  complexity into defaults that work out-of-the-box; make the exotic case the
  plug-in's problem, not the core's.
- **Never discover behavior from magic file layout alone.** If a hook or setup
  script's activation depends on a repo having a specific directory layout, a
  layout change silently disables it. Version the hook *contract* and fail loud
  when a layout the contract promises is missing.

---

## 3. OpenCode — provider-agnostic default, but schema churn in config

**The mistake.** OpenCode's *default* is right (provider-agnostic, 75+ providers),
but its config surface moves. It ships a JSON schema with explicit auto-migration
notices: "Legacy theme, keybinds, and tui keys in opencode.json are deprecated and
automatically migrated when possible," and its MCP config went through a schema
change (server name moved inside `servers` — V1 → V2) that required users to
rewrite config. It labels features "may change, break, or be incomplete. Use at
your own risk." Config resolution is spread across three layers (global
`~/.config/opencode/`, `OPENCODE_CONFIG` env override, per-project `opencode.json`),
so the effective config at any moment is a merge a user has to reason about.

**Who made it.** opencode-ai (sst / anomalyco). A fast-moving CLI team for whom
config is an API surface that iterates.

**Design rule for steadfaste.**
- Provider-agnostic-by-default is a *stability feature* — a harness that works with
  any model (Claude, etc.) without code change removes a whole class of breakage.
  Steadfaste should adopt this and treat "configure for a model" as a config
  concern, not a fork.
- But config is a **contract**, not scratch space. A schema bump that silently
  migrates or silently drops keys is a broken contract. Freeze the config schema;
  when it must change, bump a version and refuse loudly with a migration path,
  never "automatically migrated when possible."
- Keep the config *hierarchy* boring: the fewer layers that merge, the fewer
  surprises. Explicit precedence beats clever layering.

---

## 4. Aider — the frozen minimal core works; its one clever heuristic is the cost

**The mistake.** Aider is the *counter-example within the cautionary set*: it has
stayed small, frozen, single-purpose (edit files in a git repo) and is the most
stable of the four precisely because of that. Its failures are all located in the
one place it got clever — the **repo map** — plus a hard environment assumption:

- **Hard git dependency.** Aider requires a git repo and fails with
  `fatal: not a git repository` (or misbehaves) otherwise; users must `git init`
  first. The harness refuses to run outside its one assumed repo layout.
- **Repo-map cleverness.** The repo map is a heuristic that compresses the whole
  repo into the prompt. On large repos it over/under-selects: context windows get
  exceeded (`--map-tokens` 1024 default, raised to 2048), the model edits the wrong
  file or makes unrelated changes, and `SEARCH/REPLACE block failed to match`
  errors are a standing support class. Users end up hand-tuning `.aiderignore`,
  `--no-map`, and token budgets — the cleverness offloads cognitive load onto the
  user.
- **Model-warning noise.** Unknown context window sizes for new models produce
  warnings, showing how model-specific knowledge leaked into the core.

**Who made it.** Paul Gauthier (aider). A solo author who kept scope minimal — the
*opposite* failure mode from OpenHands, and the useful signal is in the contrast.

**Design rule for steadfaste.**
- **A frozen minimal core *is* the stability strategy.** Aider's longevity is the
  proof: no big-rewrite migrations, no dual config, no runtime zoo. Steadfaste's
  core should look like this — one dependable job, done without churn.
- **Every clever heuristic in the core is a future support ticket.** The repo map
  is where all of Aider's complaints cluster. Keep heuristics out of the core; if
  one is needed, make it an opt-in plug-in with a stable off switch.
- **Never hard-depend on one repo/workflow layout.** Requiring "a git repo in
  exactly this shape" means the harness breaks the moment the workspace doesn't
  match. Steadfaste should degrade gracefully (or refuse loudly with a clear
  message) instead of assuming.
- **Don't let model-specific facts into the core.** Context-window/size tables for
  specific models are config data, not code.

---

## Cross-cutting top lessons (the five that matter)

1. **Anti-bloat is the whole ballgame.** Every failure above is a harness growing
   beyond a dependable core: OpenManus churned, OpenHands monolithed, OpenCode's
   config drifted, Aider's one heuristic cost it. The fix is one rule — **minimal
   frozen core + plug-ins/config.** Others plug into steadfaste or configure it
   for a model; steadfaste never grows a large moving surface of its own.

2. **The runtime/execution backend must be a plug-in point, never the core.**
   OpenHands' sandbox zoo (Docker/K8s/process/remote) is why it needed a V0→V1
   teardown. One tiny stable runtime interface in the core; exotic backends live
   outside and can change without touching the core contract.

3. **One config system, frozen schema, versioned breaking changes.** OpenHands ran
   `config.toml` + `settings.json` in parallel; OpenCode silently auto-migrated a
   schema. Both are config-contract breaks. One schema, one loading hierarchy,
   and a loud versioned migration when (rarely) it must change.

4. **Self-hosted setup is one command, not a knob farm.** The
   `SANDBOX_CONTAINER_URL_PATTERN` / `USE_HOST_NETWORK` / volume-mount tangle is a
   standing "connection refused" support class. Ship working defaults; make the
   exotic case the plug-in's problem.

5. **Never activate behavior from magic repo layout — and never hard-depend on
   one.** OpenHands' `.openhands/setup.sh` / `hooks.json` silently stopped applying
   when the layout changed; Aider hard-requires a git repo. Version the hook
   *contract*, fail loud on missing layout, and degrade gracefully on nonstandard
   workspaces.

---

## Appendix — source pointers

- OpenManus README (FoundationAgents/OpenManus): "launched within 3 hours,"
  "simple implementation," `run_flow.py` "unstable multi-agent version,"
  Browser Use moved behind `uvx` isolation.
- OpenHands docs (`docs.openhands.dev`): V0→V1 migration; "Legacy (V0)" config
  section; `config.template.toml`; V1 env vars (`SANDBOX_CONTAINER_URL_PATTERN`,
  `AGENT_SERVER_USE_HOST_NETWORK`, `SANDBOX_VOLUMES`); Repository Customization
  page (`.openhands/setup.sh`, `hooks.json`, Stop-hook migration from
  `pre-commit.sh`); issue #9531 "Unify dual configuration systems."
- OpenCode docs (`opencode.ai/docs/config`): three-layer config hierarchy; legacy
  theme/keybinds "automatically migrated when possible"; MCP `servers` schema
  change.
- Aider docs (`aider.chat/docs`): repo-map FAQ, `--map-tokens`/`.aiderignore`/
  `--no-map`, git-repo requirement, "File editing problems" (SEARCH/REPLACE match
  failures), "Model warnings."
