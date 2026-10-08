---
name: deploy-load-verification
version: 1.0.0
category: devops
description: "Use when a config change isn't live — verify what loaded."
platforms: [linux, macos]
author: Esther (Hermes Cortex)
license: MIT
metadata:
  hermes:
    tags: [deploy, verification, gateway, mcp, config, restart]
    related_skills: [hermes-gateway-operations, cortex-bus, change-checklist]
---

# Deploy ≠ Load Verification

## When to Use

- After changing `config.yaml` (MCP servers, plugins, enforcer) — is the change actually live?
- After renaming a service/package (e.g. `agent_bus` → `cortex_bus`) — do tool names match what skills/crons reference?
- Symptom: "tools still expose old names", "deployed but nothing changed", "restart needed"
- BEFORE claiming "everything renamed" — verify the config key AND the running process, not just the repo

## Core Principle

A file on disk is not a running process. The gateway (and any long-running
daemon) loads config/plugin/enforcer code at START and keeps it in memory.
**Deploy ≠ load.** Verification = compare when the process started vs when the
files changed, and inspect what the process ACTUALLY spawned.

## Verification Recipe

```bash
# 1. When did the process start vs when did the files change?
ps -eo pid,lstart,cmd | grep 'hermes_cli.main gateway' | grep -v grep
stat -c '%y %n' ~/.hermes/plugins/governance-enforcer/__init__.py ~/.hermes/config.yaml

# 2. What did the running process ACTUALLY spawn? (ground truth)
ps -eo pid,lstart,cmd | grep mcp_stdio_watchdog | grep -v grep

# 3. Bus/server daemon: exact module name in argv
ps -eo pid,lstart,cmd | grep uvicorn | grep -v grep
```

**Rule of thumb:** process start > file mtime → new code loaded. Start < mtime
→ old code still in memory; restart required.

**MCP children are ground truth:** each `mcp_stdio_watchdog` child carries the
exact script path the gateway spawned at startup. An old path in the child argv
(e.g. `agent-bus-mcp.py` while config now says `cortex-bus-mcp.py`) means the
gateway started before the config change — what config.yaml says on disk is
irrelevant until restart.

### systemd --user units (cortex_gateway, and any agent-hosted service)

The gateway family is not the only long-running process on a host. `cortex_gateway`
runs as its own `systemctl --user` unit, separate from the Hermes gateway, and a
deploy does NOT restart it — so new code sits on disk while the unit keeps answering
with the previous behaviour. Compare the unit's start time with the deploy:

```bash
systemctl --user show <unit> -p MainPID -p ExecMainStartTimestamp --value
systemctl --user is-active <unit>
date '+%F %T %Z'        # now, to compare against
```

Start time older than the deploy → the unit is running the old code and every
behavioural probe against the live unit will show the OLD behaviour. Report that
exactly: "deployed, not yet loaded", not "the change failed". A user reporting the
old behaviour right after a clean deploy is this, not a broken fix.

**Hand over the restart; do not hunt for a way to run it yourself.** The lifecycle
guard refuses a gateway restart from inside an agent session, and its stated reason
(SIGTERM reaching the child) may not even apply to the unit you want — the guard is
pattern-based and cannot tell. Give the operator the exact one-line command and say
what will change after it. What the guard does NOT block is proving a startup guard:
a throwaway probe unit can be run to show an `ExecStartPre` refusing or accepting a
config, which is how you verify that logic without touching the live service.

**A per-turn `command` backend answers from the code loaded at START**, so a change
to the gateway's own modules (a new slash command, a changed prompt template) is
inert until the unit cycles. Only a change to the *config* can be verified live —
and only if the module reads it per turn.

## MCP Config-Key → Tool-Namespace Coupling

- The `mcp_servers.<name>:` key in `config.yaml` determines the exposed tool
  namespace: key `agent-bus` → tools `mcp__agent_bus__*` (hyphen → underscore).
- Renaming the key (e.g. → `cortex-bus`) changes the tool namespace and breaks
  every skill/cron that references the old `mcp__<name>__*` tools — until the
  gateway restarts with the new key.
- A rename that sweeps packages/skills/crons but leaves the config key = tool
  names stay old while docs claim the new ones. **Search config keys with
  HYPHENS** (`grep -iE 'agent-bus|cortex-bus'`), never underscores — `agent_bus`
  matches the Python package, never the config key.

## Changing config.yaml

- `config.yaml` is **enforcer-blocked for direct agent patch** ("Agent cannot
  modify security-sensitive configuration"). Use `hermes config set <path>`
  / `hermes config unset <path>` (see `hermes config --help`), or have the
  user edit the file directly.
- Gateway restart is a lifecycle-guarded operator action on this fleet —
  prepare everything, verify on disk, then hand the restart to the host
  operator with the exact command. Don't loop-retry.

## Memory-Provider Tool Registration (advertised ≠ routed)

A memory provider can advertise tools in the system prompt that the executor
cannot route, because its schemas are collected in two passes on opposite sides of
`initialize()`. Full diagnosis, fix, and the RED→GREEN regression test:
`references/memory-provider-tool-registration.md`.

**Plugin modules are cached in `sys.modules`** — `load_memory_provider`
reuses the cached module (`_load_provider_from_dir` checks `sys.modules`
first). A deployed plugin file fix is NOT loaded until the gateway process
restarts, even though a fresh AIAgent is built per message. Log line
"registered (0 tools)" persisting after deploy = old module still in
memory; restart required (from a separate shell — in-process restart is
blocked by the lifecycle guard).

## Deploy ≠ IMPORTABLE: the source tree can stop importing while the runtime is green

The same file is loaded from TWO sites, and a bootstrap that resolves its own
dependencies by probing relative paths works in exactly one of them:

| Loaded as | Shared code sits |
|-----------|------------------|
| Deployed (`<deploy>/scripts/<file>.py`) | **beside** it |
| In-repo (`<repo>/<subdir>/<file>.py`) | **one level down** — `<repo>/ops/scripts/` |

**Why it survives for weeks:** nothing at runtime fails. The deployed copy resolves,
so the service is green — while the SOURCE TREE can no longer be imported at all.
Only the repo's own tests break, and they break in a shape that reads as unrelated:
pytest reports `INTERNALERROR> … SystemExit: 1` and `mainloop: caught unexpected
SystemExit!`, and OTHER files in the same run fail to COLLECT, because a module-level
`sys.exit()` fired during import.

- **Verify the source tree IMPORTS, not just that the service runs.** "It works" and
  "the repo can load it" are two different questions; ask the second one explicitly,
  with its own test that loads the file from the repo path.
- **Treat a `SystemExit` during test COLLECTION as a bootstrap bug**, not a test
  problem — the bootstrap could not find its resource in that layout.
- **Assert any shared bootstrap block is byte-identical across every copy** (hash it).
  Divergence is how one copy keeps a stale candidate list while the others are fixed.
- **Strip the deploy's header by LINE, not with a pattern that swallows the shebang.**
  The deploy INSERTS two comment lines (`# SOURCE: <repo path>`, `# Do NOT edit …`) plus a
  blank line AFTER the first line; it does not replace it. A strip anchored at the start of
  the file therefore eats the shebang too and reports a false `deployed != repo` on a
  correct deploy. Remove exactly those two lines (`^(# SOURCE:.*\n)(# Do NOT edit.*\n)\n?`,
  `re.M`) and let the shebang through.

## Deploy ≠ LOADED: make the new code PROVE it ran

`lstart > mtime` is necessary but NOT sufficient — a process can start after a
deploy and still never execute the changed path (a guard only reached on some
inputs, a branch the daemon did not take). The decisive evidence is a
**liveness witness**: a side effect ONLY the new revision can produce.

- Pick something the new code writes or emits that the old one could not — a new
  state file, a new log field, a new branch of output. Its existence with an mtime
  AFTER the deploy proves the running process executed the new code.
- Prefer a witness an ORDINARY call produces. If reaching it needs a special
  invocation, you have shown the code is importable, not that it is in play.
- State which claim you are making. "Deployed and loaded, proven by <witness> at
  <time>" is a different sentence from "deployed"; only the first is verified.

**The two halves of a plugin + MCP change reload differently — know which you
have:**

- An **MCP server** fix is loaded by restarting that server's *child* process.
  Kill it and the parent respawns it on the next call; no gateway restart is
  needed, and an in-session agent CAN do this. Confirm with
  `ps -eo pid,lstart,etime,args | grep <server>.py` before and after — the new
  PID, with a start time after the deploy, is the evidence.
  - **Check the child's PPID before calling the restart yours.** `ps -o pid,ppid,etime,args
    -p <child>`, then the parent's own argv. A child whose parent is the *session* is
    yours to cycle. A child whose parent is the GATEWAY is HOST-SHARED — every session
    on that host is served by the same process, so cycling it is a host-wide action that
    drops other agents' in-flight governance calls mid-cycle. Hand that one to the
    operator, and never describe a host-shared child's staleness as if it were only your
    own session's: "my session needs a reload" and "every session on this host is
    affected" call for different decisions.
  - **EXCEPTION — never restart the child that is serving your OWN active
    governance lock mid-cycle.** The lock persists in
    `~/.hermes-cortex/state/` and is read through that same MCP server, so
    killing it mid-cycle strands the lock and cuts the governance tooling you
    still need for `end_change` — a worse outcome than a push that is simply
    blocked. Close the cycle first, then restart, then push (the receipt gate
    below/next may still require a fresh `begin_change`).
  - **A change whose PRODUCER is not yet live can look like a broken feature.**
    New code that writes an artifact (a receipt, a token, a marker) on a
    later trigger is deployed but inert until the child reloads, so the trigger
    runs and nothing appears. Verify the DEPLOYED FILE contains the new symbol
    (`grep -c _write_review_receipt <deployed path>`) to prove the disk copy is
    current, and report "deployed, not yet loaded" rather than "the change
    failed". If the consumer of that artifact is fail-closed, this state blocks
    the fleet until the reload — so fly the reload as part of the deploy.
  - **A producer can also be LOADED and still inert.** Reloading fixes staleness,
    not a writer that resolves its subject from context it was never given: a
    helper called with no arguments returns empty, so the writer bails on every
    run, and a fresh child makes no difference. Distinguish the two before asking
    for another restart — the deployed file containing the symbol proves the first
    case is over; only driving the function directly (import the deployed module,
    call it with the same arguments the real path passes, watch what it writes)
    rules out the second. Prefer that direct call over another reload cycle when a
    write keeps not appearing after a restart.
  - **Extend the deploy's EXISTING deploy≠load detector instead of inventing one.**
    When the deploy already compares the running process's start time against a
    CHANGED FILE (a `_restart_pending`-style banner backed by a persisted
    hash+epoch state file), a daemon that is simply not covered is fixed by adding
    its source to that WATCHED SET — not by adding a second check, and never by
    adding a restart. Hash the set as ONE combined value so the persisted state
    format needs no migration; skip files that are absent so a host without that
    daemon behaves exactly as before; and keep a hash/temp-write failure as
    UNVERIFIABLE so the banner still fires rather than reading as clean. Then hand
    the restart over as usual. Start-up ordering matters here too: if the newly
    watched daemon is the one that produces an artifact a fail-closed gate
    consumes, the fleet is blocked from the deploy until the operator restarts.
- A **plugin/enforcer** fix needs the GATEWAY to reload. An in-session agent
  cannot restart it (lifecycle guard), so hand it over with the exact command and
  say plainly which half is loaded and which is still pending.
- Never let "it deployed" stand in for "it is in play". Reporting half a fix as
  live is the failure this section exists to prevent.

**Validate the chain against the DEPLOYED module copies, hop by hop** — import the
file that actually runs (`importlib.util.spec_from_file_location(<deploy path>)`)
and drive its functions, asserting each stage of the pipeline (input learned →
value injected → value consumed → bad value refused). A green unit test against
the repo copy says nothing about what the running process loaded, and a
successful deploy says nothing about which branch it takes.

**…but `spec_from_file_location` fails for a file that lives INSIDE a package.**
Loading a package member by path executes it while the package's `__init__` still
needs it, so the import chain re-enters around a half-initialised module and raises
a misleading error — `cannot import name <X> from <pkg>.<mod>` for a symbol that is
plainly defined in the file you just opened. That reads as a broken module when the
module is fine and the LOADER is wrong. Import the package normally instead
(`sys.path.insert(0, <pkg parent>); import <pkg>.<mod>`), or `importlib.import_module`.
Reserve path-loading for standalone scripts, which is what the deployed-copy case
above usually is.

## Deploy ≠ LAST STEP: a commit after the deploy re-stales the tree

The deploy-sync check compares **HEAD against the deployed commit**, so any commit
made *after* a deploy leaves HEAD ahead of it and the next check reports
`HEAD ahead of last deploy — N commit(s) not deployed`.

- **Order the work: change → commit → deploy → push.** The deploy is the LAST step
  before the push, not a mid-task refresh, and it is not idempotent with respect to
  your own edits: it snapshots HEAD, so committing again re-opens the gap it just
  closed.
- **Let the push gate's own dogfood do the deploy.** The pre-push path runs
  `pull → deploy → doctor → verify` before allowing a push, so the correct final
  sequence is commit, dogfood, push. A `Deploy sync` failure immediately before a
  push is usually nothing more than "you committed after deploying" — re-run the
  dogfood rather than debugging it.
- **Run the sequence as SEPARATE BOUNDED STEPS, never one long-lived call.** A single
  cell chaining the test runs, the full deploy and the push outlives a code
  interpreter's execution ceiling, is killed mid-flight, and takes its variables with
  it — so a commit it had not yet reached is silently un-landed and the outcome is
  ambiguous: the failure does not tell you whether the commit, the deploy or the push
  happened. Deploy work is slow and stateful; issue each phase as its own command with
  its own timeout, read the result, then continue.
  - **Name the ceiling and put long deploy work in `terminal`.** The interpreter's
    per-cell ceiling is a CONFIG VALUE, not a wall: Hermes
    `tools/code_execution_tool.py` defines `DEFAULT_TIMEOUT = 300` and resolves the
    live value from `code_execution.timeout` in `config.yaml`. A full
    pull → deploy → doctor → verify pass costs minutes on its own (several doctor
    passes), so tests + deploy + push in one cell crosses it — read the knob before
    blaming the payload. `terminal` is the right container for this work: a longer
    foreground allowance, and it backgrounds itself past that with a completion
    notification. A raised ceiling is read at tool discovery, so it may need a new
    session to take effect — and the same file holds a SEPARATE hard-coded 300s that
    is the deadline for a NESTED tool call made from inside a cell, which raising the
    config does not lift. After any killed cell, re-establish
  the real state (`git status`, `git log -1`) before assuming what took effect, and
  re-do only the phases that provably did not run.
- **Never quote a deploy-sync result as evidence without re-deploying first.** An
  artifact captured between a deploy and a later commit is one commit stale, so
  filing it as proof that "the deployed tree matches" contradicts your own claim,
  and a reviewer reading the artifact against the claim files it as fabrication —
  the artifact disproving its own headline. Either re-deploy and re-capture, or
  state plainly that the capture precedes the final commit and that the push-time
  dogfood closes the gap. Say which moment the capture is from; a doctor's exit 1
  is also a WARNING level, not necessarily a failure, so read the level too.
- **Expect the gap after every documentation commit.** Docs and skills are deploy
  targets, so a docs-only commit re-stales the tree exactly like a code change.
- **An evidence artifact can be committed by definition only after the run it
  records**, so it will always reflect the pre-commit revision it was taken at.
  Frame it as "captured at <revision>, before the commit that adds it", never as a
  claim about the tree at HEAD.

## Pitfalls

1. **Claiming "everything renamed" while the config key still has the old
   name.** Happened 2026-08-04: the migration summary said "one name" but
   `config.yaml` still had `mcp_servers.agent-bus:` — only the file-mutation
   verifier (refused patch) surfaced the overstatement. Always verify the
   config key + running children, not just the repo strings.
2. **Grepping config with underscore patterns.** `agent_bus` finds the Python
   package, not the config key `agent-bus`. Hyphens in config keys, underscores
   in code/package names.
3. **Trusting config.yaml on disk over the running process.** The running
   gateway may predate the edit; the child argv is the truth.
4. **Assuming a fresh gateway is automatically clean.** A gateway restarted
   AFTER the deploy is clean — verify with `lstart`, don't assume.

## Verification Checklist

- [ ] Gateway `lstart` > every changed file's mtime (or restart happened after deploy)
- [ ] The changed file IMPORTS from the repo tree, not only from the deployed path
- [ ] `mcp_stdio_watchdog` children show the NEW script paths
- [ ] Config key name matches the tool namespace skills reference (`mcp__<key>__*`)
- [ ] Bus/daemon process argv shows the new module name
- [ ] Any required restarts handed to the operator with exact commands

## Deploy ≠ Durable: manifests revert live edits

**A live change that contradicts a repo manifest gets silently REVERTED by the
next deploy.** The cron-model chain is the canonical example (2026-08-31):

- `hermes cron edit <id> --model X --provider Y` pins the LIVE job in
  `jobs.json` — but `cortex-update.sh` → `install-crons.sh` drift-edit calls
  `pin_cron_model`, which reads `ops/install/cron-manifest.yaml` and the
  manifest's model/provider WIN over the env default AND over the live pin.
  Symptom: repinned 21 crons, ran cortex-update, 14 were back to the old model.
- **Durable-change recipe:** patch the manifest FIRST, then re-apply the live
  pins, then run `cortex-update.sh` and RE-VERIFY pins survived
  (`python3 -c "import json; [print(j['name'], j.get('model'), j.get('provider'))
  for j in json.load(open('$HOME/.hermes/cron/jobs.json'))['jobs']
  if not j.get('no_agent')]"`). A pin that survives a deploy is real; one that
  doesn't means the manifest still disagrees.
- **Remove the writer, not just its auto-run** (2026-09-08 → 09-09): the two
  cortex scripts that WROTE operator-owned `config.yaml` model/fallback keys
  (`install-model-default.sh`, `install-fallback-providers.py`) were first
  de-registered from auto-run (d709d752), then removed entirely — source,
  register lines, deployed copies, env vars, docs. A config-writer must be
  deleted, not left "registered for manual use": a registered-but-inert writer
  is a live clobber footgun that only needs one re-invocation to strike.
- Verify end-to-end through the REAL path, not the picker:
  `hermes chat -q "Reply with exactly: OK" -m <model> --provider <provider>`
  — a fallback fires as `⚠️ Model fallback: ... unavailable (provider failure);
  using ...` in the output. See `references/cron-model-fallback-chain.md` for
  the full 2026-08-31 trace (chain rebuild, opencode free/zen landscape,
  propagation gap).

## Verify through the PRODUCT's own builders, not a hand-built harness

**Full recipe: `references/probe-and-harness-verification.md`.** A harness that
reimplements the product's invocation tests the harness, not the product, and its
failures look exactly like product bugs. In short: drive the code through its own
API (never rebuild argv/env by hand), assert on the isolation KEY not the visible
id, make every probe unique per run, run the acceptance script twice, place the
fixture where the code's contract expects it and outside `HOME`, and clone a real
artifact to build a fixture rather than inventing one from the fields you think
matter. When a probe fails, suspect the PROBE before the code.

Two false FAILs from one such script, with the product correct both times: a
hand-built argv omitted the env var that was the real isolation seam, and a fixed
probe id made run 2 resume run 1's leftovers. Both are in the reference above,
with the rules for avoiding them.


- The script built `[command, "--session-id", id, prompt]` directly instead of
  calling the backend's own `_argv`/`_child_env`. It therefore omitted
  `CORTEX_SESSION_KEY` — and that env var, not the argv, was the real isolation
  seam. Every session shared one checkpoint, so the new session "remembered" the
  old secret and the report read **"/new leaks memory"**. The product was fine.
- The script then used a FIXED probe id, so its second run resumed the sessions
  its first run had left behind — the same false failure, for a different reason.

## Deploy ≠ VERIFIED: warnings sourced from another system's record

Some verification checks read the state of a DIFFERENT system than the one you
just deployed, so re-running the local artifact clears nothing. The check that
fails will keep failing while the fix looks broken.

- **The Hermes doctor's `Cron status (<job>)` and `Script run evidence` checks read the
  SCHEDULER's recorded `last_status`/run history**, not the script's exit code. A
  `bash <script>` from a terminal therefore clears neither. Clear each with a
  scheduler fire — `cronjob action='run' job_id=<id>` — then re-run the doctor to
  confirm. The warnings clear independently, so one deploy can need several fires.
  Non-orchestrators have no `cronjob` tool: request the fire, do not work around it.
- **Look up the id read-only** when the `cronjob` tool is unavailable (cron
  sessions): `grep -n -B4 "<job-name>" ~/.hermes/cron/jobs.json`.
- **A watchdog script that prints nothing and exits 0 is a PASS.** `no_agent`
  watchdogs use the silent-PASS convention (PASS → empty stdout + exit 0;
  FAIL → report on stdout + exit 1). Read the script's header comment before
  calling an empty run a failure — the empty output is the designed signal.
- **A failure in one check can be a downstream symptom of a failure in another.**
  A golden-suite gate that reports `doctor_clean: doctor reports N failure(s) —
  gate blocked` is reporting the DOCTOR's failure, not its own. Fix the doctor,
  then re-fire the gate; do not debug the gate.
- **Read the deploy's own commit line, not its file count.** A run on an unchanged
  HEAD still re-checks every mapped file and can print a large `N file(s) updated`
  summary; `✓ Updated: <sha> → <sha>` is what actually moved.

## Coda: a lesson written only into the DEPLOYED skill copy is not landed

The deployed tree (`~/.hermes/skills/…`) and the repo source
(`skills/…/*/SKILL.md`) drift independently; the repo is the source of truth and
the only copy that reaches other hosts. A lesson appended to the deployed copy
alone is therefore invisible to the fleet AND is **clobbered by the next
`cortex-update.sh` deploy**, which copies the repo source over it.

- **Write the lesson into the REPO source**, then deploy. Verify by grepping the
  repo path, not `~/.hermes/skills/`.
- Tell them apart by size: a deployed copy materially LARGER than its repo source
  is carrying un-synced lessons (this exact drift was 16858 vs 8427 bytes,
  2026-10-03). Sync deployed → repo before editing, or the edit is a no-op.
- **The doctor detects the drift for you — run the check before closing any session that
  touched a skill.** `python3 ops/scripts/manage/cortex-doctor.py | grep -i 'Skill drift'`
  names each drifted path (`Deployed copy is newer than repo source (<path>). Commit the
  repo source before cortex-update overwrites it.`). Sync verbatim with
  `cp <deployed> <repo source>` — do not retype the lesson — confirm the md5s match,
  commit, push, and re-run until it reports `<N> skills in sync, 0 drifted`. Trust the
  check's content comparison, not mtime: a deploy in the same session rewrites the
  deployed copy and makes mtime alone ambiguous.

## References

- `references/rename-verification-example.md` — worked example: the `agent_bus` → `cortex_bus` fleet rename (2026-08-04)
- `references/cron-model-fallback-chain.md` — LLM cron model/fallback chain rebuild: manifest-vs-live pin reversion, env-driven fallback chain, opencode free/zen providers, fleet propagation gap (2026-08-31)
- `references/memory-provider-tool-registration.md` — provider advertises tools the executor cannot route: the two-pass registration timing, the unconditional-schemas fix, and the RED→GREEN regression test
