# For the Pi agent: implement cortex memory + session

**Audience: a Pi agent (or any coding agent) asked to give itself memory and
session continuity.** Self-contained — follow it top to bottom. Hand-written;
the generated `README.md` beside it is derived from `registry.yaml`.

Runbooks: [`docs/runbooks/context-integration.md`](../../../docs/runbooks/context-integration.md) ·
Design: [`docs/design/agent-interop.md`](../../../docs/design/agent-interop.md)

---

## 0. What you get, and what you do not

**You get** — one store, two families, shared with every other host:

| Family | Tools | Answers |
|---|---|---|
| memory | `mem_profile`, `mem_search`, `mem_context`, `mem_conclude` | *what do I know?* |
| session | `session_checkpoint`, `session_restore`, `session_list`, `session_search`, `session_note`, `session_close` | *where am I?* |

**You do NOT get** (deliberate, not an oversight):

- **`mem_reasoning`** — needs a host LLM, so it lives in the Hermes adapter.
  It is excluded from the shared contract on purpose.
- **Embedding-backed search** — deferred.

**Do not reimplement any tool.** There is ONE implementation
(`ops/services/mycortex-mem/context_tools.py`). You add a *way in*, not semantics.
A second implementation of the same tool name is the defect this whole layer
exists to remove: it makes one of the two a phantom that fails silently.

---

## 1. Understand the split before you touch anything

| Concern | Owner |
|---|---|
| the store + search | the shared surface (CLI / MCP) |
| **WHEN a checkpoint is written** | **you — the harness** |

MCP is tool-call shaped with no lifecycle. The session that most needs a
checkpoint is the one that just got **killed**, and it can never call a tool.
So the trigger is a lifecycle hook, never a prompt instruction. "Remember to
save" is not a mechanism.

---

## 2. Install

```bash
cd <pi-project>
mkdir -p extensions
cp ~/hermes-cortex/ops/install/harnesses/pi/extensions/cortex-context.ts extensions/
```

Launch with the extension and an explicit tool allowlist:

```bash
pi -e extensions/cortex-context.ts \
   --tools read,bash,edit,write,mem_context,mem_search,mem_profile,mem_conclude,session_checkpoint,session_restore,session_search,session_note,session_close
```

Session identity (usually derived from git; pin it when it is not):

```bash
export CORTEX_SESSION_HARNESS=pi
export CORTEX_SESSION_REPO=<repo>
export CORTEX_SESSION_BRANCH=<branch>
```

**Precedence is `args → env → git`, identical in every layer** — which is why a
checkpoint written here can be restored by Hermes, and vice versa.

### macOS

`python3` may not be on your PATH (Homebrew is `/opt/homebrew/bin` on Apple
Silicon, `/usr/local/bin` on Intel; a GUI-launched Pi sees a narrower PATH):

```bash
export CORTEX_CONTEXT_PYTHON=/opt/homebrew/bin/python3
```

The store has a darwin path (direct `psql` + 0600 `PGPASSFILE`) — it never shells
through `sg docker`, which does not exist on macOS.

---

## 3. Verify — do not report a wiring you have not exercised

**a. The store answers at all** (before blaming your code):

```bash
cortex-context mem_context '{}'      # JSON with "card": [...]
```

`memory unavailable — … not an error` means the store is unreachable: fix that
first (`MYCORTEX_MEM_PASSWORD` in `~/hermes-cortex/.env`; is Postgres up?). Do not
debug the harness while the store is down.

**b. Read path, from inside Pi:** call `mem_context`; your peer card must return.

**c. Write path, THROUGH the harness** — the part that proves the trigger:

1. End a turn with a distinctive marker (a decision like `proof-<timestamp>`).
2. From a shell:
   ```bash
   cortex-context session_restore '{}' | grep proof-
   ```
   Missing ⇒ your hook is not firing. The extension's routine markers go to the
   cortex log (`~/.hermes-cortex/logs/pi-context.log`), not the visible stream — see §4.

**d. Session-start injection:** start a SECOND session. The checkpoint must appear
without being asked, and `CORTEX_RESUME <key> facts=N` is appended to
`~/.hermes-cortex/logs/pi-context.log` (set `CORTEX_CONTEXT_DEBUG=1` to also see it on
stderr).

**e. Fail-open:** stop the store, call a tool, confirm Pi continues with
`memory unavailable …` and does not error out. Restart the store.

---

## 4. Read the log — it is the difference between "no memory" and "broken"

Routine markers go to `~/.hermes-cortex/logs/pi-context.log` (rotates to
`pi-context.log.1` at `CORTEX_CONTEXT_LOG_MAX_BYTES`, default 1 MiB). **Only failures
are printed on stderr** — in Pi stderr *is* the prompt area, so a routine line there
scribbles over what the user is typing. `CORTEX_CONTEXT_DEBUG=1` echoes the routine
markers to stderr too, for when you are diagnosing live.

| Marker | Where | Meaning |
|---|---|---|
| `CORTEX_RESUME <key> facts=N` | log | hook fired. **`facts=0` means the checkpoint was EMPTY** — content was not captured, not "nothing happened". |
| `CORTEX_RESUME none` | log | no checkpoint found for this identity — check `CORTEX_SESSION_*` before assuming the store is empty. |
| `CORTEX_CHECKPOINT_EMPTY turn=… keys=…` | log | the turn carried nothing recognisable. The `keys=` list is the event's real shape. |
| `CORTEX_TOOL_EVENT <name> recorded` | log | the tool call was attributed to the session. |
| `CORTEX_FAIL <tool>: …` | **stderr** | the CLI failed to run — usually a python path or CLI path problem. |
| `CORTEX_TOOL_EVENT <name> FAILED` | **stderr** | attribution failed for that call. |

**Never let these be silent.** An empty checkpoint that *looks* like continuity is
worse than no checkpoint.

---

## 5. The hook API — verify it, never infer it

The first version of this extension failed **twice, silently**, by assuming:

| Assumption | Reality (Pi 0.87.1) |
|---|---|
| handler is `(ctx)` | it is **`(event, ctx)`** — the FIRST parameter is the EVENT. `ctx.completed?.()` read off it returned `undefined`, and optional chaining hid it: **every checkpoint was written empty**. |
| inject via `ctx.addSystemPrompt()` | there is **no such method** — injection is the handler's **RETURN VALUE** (`{ systemPrompt }` / `{ message }`). Calling a missing method did nothing while a stderr marker made it *look* like it worked. |

Check your own installed version:

```bash
V=$(cat ~/.pi/agent/install/current-version)
P="$HOME/.pi/agent/install/releases/$V/node_modules/@earendil-works/pi-coding-agent"
grep -n -A6  "type ExtensionHandler"   "$P"/dist/core/extensions/types.d.ts
grep -n -A10 "interface TurnEndEvent"  "$P"/dist/core/extensions/types.d.ts
grep -n -A12 "interface BeforeAgentStartEvent" "$P"/dist/core/extensions/types.d.ts
```

`turn_end` carries `turnIndex`, `message`, `toolResults`, `entries`, `outcome` —
build the checkpoint from `toolResults` + `message`.

---

## 6. Known failure to check before you file a bug

If your memory tools fail with **`definition.execute is not a function`**, that is
a **host-side tool registration** problem, not the store and not your extension —
a real agent hit exactly this and correctly refused to fabricate an answer. The
store is fine; the host's tool wiring is not. Report it to the orchestrator with
that exact string. Do **not** work around it by querying Postgres directly: that
bypasses the access layer, and it is how "the backend is the working path" became
a wrong conclusion once already.

---

## 8. Skills autoload

Pi discovers skills itself — `--no-skills` *disables* discovery, so it is ON by
default, and `--skill <path>` (repeatable) adds a file or directory. At startup
Pi advertises each skill's **name + description** and loads the body on demand.

**Register it once, at user scope — do not re-copy flags per repo:**

```bash
bash ~/hermes-cortex/ops/scripts/install/install-pi-integration.sh
# → ~/.pi/agent/settings.json: "skills": ["~/.pi/agent/cortex-skills"]
# → that dir holds ONE symlink per skill in the manifest's `always:` section
bash ~/hermes-cortex/ops/scripts/install/install-pi-integration.sh --check
```

Project scope (one repo, explicit flags) is the other half of the same pattern:

```bash
pi -e extensions/cortex-context.ts --skill <curated-skills-dir> --tools …
```

Two rules, learned from Hermes:

- **Point it at a CURATED set, not the whole fleet library.** Hermes autoloads
  skill *names + descriptions* and loads bodies on demand (progressive
  disclosure). If Pi loads whole skill bodies, wiring 400 skills into the context
  window is a self-inflicted wound. The curated set is DERIVED from the skills
  manifest's `always:` section — one definition, shared with Hermes — never
  hand-typed here.
- **Discovery is not enforcement.** A skill autoloaded is a *suggestion*; nothing
  checks that it was followed. Do not confuse the two — see below.

---

## 9. Governance

**Registered the same way as everything else here — one implementation, a thin
per-harness way in.**

- **Pi ≥ 0.99 (MCP client):** the four governance servers register at user scope
  in `~/.pi/agent/mcp.json`:

  ```bash
  bash ~/hermes-cortex/ops/scripts/install/install-pi-mcp.sh
  pi mcp list          # loop-governance, tasks, executor, agent-bus
  ```

  That is the SAME server set Claude Code gets from
  `install-claude-governance.sh` — not a Pi-specific governance implementation.

- **Older Pi, or no MCP client:** the **commit-time pipeline already covers you**,
  verified on this host. `core.hooksPath` is global, so a `git commit` made from
  inside a Pi session in ANY repo runs the same gates as Hermes: change-validate,
  an orchestrator self-test (host-derived, not env-spoofable), an adversarial
  scan, and `score-cycle` — which records a governance cycle and scores it. **You
  do not need to do anything to be governed at commit time.**

  The interactive ritual (`cache_search → begin_change → work → cycle_query →
  feedback_accept → end_change`) reaches a no-MCP harness through the generic CLI,
  which is an adapter over the same server module (never a second implementation):

  ```bash
  loop-gov begin_change '{"task_id":"my-task","description":"what and why"}'
  loop-gov --tools-json        # machine-readable manifest for any harness
  ```

Never hand-write a lock file under `~/.hermes-cortex/state/` — a fabricated lock
is a governance violation and is audited. If governance is unreachable, say so in
your report; do not pretend otherwise.

**The enforcement-hook half** (lifecycle triggers + gate evidence) is the
extension registered in §8's installer: the pre-commit reflexion gate asks HC's
store "did this session load skill X?", and without the `tool_result` writer a Pi
commit is refused no matter how well the agent behaved.

---

## 10. Report back

Tell the orchestrator, in this order:

1. Which layer you wired (CLI + extension) and the **exact** `pi` command.
2. `cortex-context mem_context '{}'` output (or the failure message).
3. The checkpoint you proved, quoted from `session_restore` — not a claim that
   it works.
4. Any `CORTEX_*` stderr line that is not what you expected.

A wiring you have not exercised is not a wiring. Quote the tool output.
