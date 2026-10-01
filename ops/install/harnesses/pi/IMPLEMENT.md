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
   Missing ⇒ your hook is not firing. Check stderr for `CORTEX_*` lines.

**d. Session-start injection:** start a SECOND session. The checkpoint must appear
without being asked, and Pi logs `CORTEX_RESUME <key> facts=N` on stderr.

**e. Fail-open:** stop the store, call a tool, confirm Pi continues with
`memory unavailable …` and does not error out. Restart the store.

---

## 4. Read stderr — it is the difference between "no memory" and "broken"

| Marker | Meaning |
|---|---|
| `CORTEX_RESUME <key> facts=N` | hook fired. **`facts=0` means the checkpoint was EMPTY** — content was not captured, not "nothing happened". |
| `CORTEX_RESUME none` | no checkpoint found for this identity — check `CORTEX_SESSION_*` before assuming the store is empty. |
| `CORTEX_CHECKPOINT_EMPTY turn=… keys=…` | the turn carried nothing recognisable. The `keys=` list is the event's real shape. |
| `CORTEX_FAIL <tool>: …` | the CLI failed to run — usually a python path or CLI path problem. |

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
P=$(npm root -g)/@earendil-works/pi-coding-agent
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
default, and `--skill <path>` (repeatable) adds a file or directory. Confirm your
own install:

```bash
P=$(npm root -g)/@earendil-works/pi-coding-agent
grep -rl "skills" "$P"/dist/core/ | head        # discovery implementation
ls ~/.pi/agent/                                  # your config dir (may not exist)
```

Two rules, learned from Hermes:

- **Point it at a CURATED set, not the whole fleet library.** Hermes autoloads
  skill *names + descriptions* and loads bodies on demand (progressive
  disclosure). If Pi loads whole skill bodies, wiring 400 skills into the context
  window is a self-inflicted wound. Ship the handful that matter for the repo you
  are in.
- **Discovery is not enforcement.** A skill autoloaded is a *suggestion*; nothing
  checks that it was followed. Do not confuse the two — see below.

```bash
pi -e extensions/cortex-context.ts --skill <curated-skills-dir> --tools …
```

---

## 9. Governance

**The good news, verified on this host: the commit-time pipeline already covers
you, whatever harness you are.** `core.hooksPath` is global, so a `git commit`
made from inside a Pi session in ANY repo runs the same gates as Hermes:
change-validate, an orchestrator self-test (host-derived, not env-spoofable), an
adversarial scan, and `score-cycle` — which records a governance cycle and scores
it. A foreign-repo commit from a Pi-style session was observed passing all four
and succeeding. **You do not need to do anything to be governed at commit time.**

**The gap: the interactive ritual.** Hermes agents call
`cache_search → begin_change → work → cycle_query → feedback_accept → end_change`
through the **loop-governance MCP server**. **Pi has no MCP client**, so those
calls are unavailable to you. Do not pretend otherwise, and do not hand-write a
lock file under `~/.hermes-cortex/state/` — a fabricated lock is a governance
violation and is audited.

The correct shape (same pattern as everything else here — **one implementation,
a per-host adapter**):

```
   loop-governance MCP server  ──┬── Hermes, Claude Code, Codex  (MCP)
   (the one implementation)      │
                                 └── a `loop-gov` CLI  ⤷ Pi extension  (no MCP client)
```

That CLI adapter **does not exist yet** — it is the next build, the exact
counterpart of `cortex-context` for governance. Until it lands:

1. **Commit-time governance applies anyway** (above) — rely on it, do not skip it.
2. If you need the ritual, **ask the orchestrator** to run
   `begin_change`/`end_change` for your task id, and say plainly in your report
   that you could not call them yourself.

---

## 10. Report back

Tell the orchestrator, in this order:

1. Which layer you wired (CLI + extension) and the **exact** `pi` command.
2. `cortex-context mem_context '{}'` output (or the failure message).
3. The checkpoint you proved, quoted from `session_restore` — not a claim that
   it works.
4. Any `CORTEX_*` stderr line that is not what you expected.

A wiring you have not exercised is not a wiring. Quote the tool output.
