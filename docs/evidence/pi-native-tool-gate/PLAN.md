# PLAN — gate pi's native write tools on the shared governance lock

Cycle: 12598 · task_id: `pi-native-tool-gate` · author: esther · 2026-10-14
Status: PLAN, pre-build. This file is *material for review*, not a claim of work done.

## 1. The reported defect (titus) and what validation actually shows

Titus reported: "loop governance thinks it controls the filesystem, but it only
controls the Hermes MCP path; pi enters through a side door."

**VERIFIED CORRECT (the layer mismatch is real).**

- The Hermes enforcement layer is a *Hermes plugin*:
  `~/.hermes/plugins/governance-enforcer/__init__.py`, which registers a
  `pre_tool_call` hook and blocks write-classified tool calls. It is reached only
  for tool calls made through the Hermes agent loop. Pi does not run Hermes.
- The pi extension that IS installed —
  `ops/install/harnesses/pi/extensions/cortex-context.ts` — registers exactly
  four hooks and NO gate:

  ```
  pi.on("before_agent_start", ...)      # restore + inject
  pi.on("turn_end", ...)                # checkpoint trigger
  pi.on("session_before_compact", ...)  # checkpoint before compaction
  pi.on("tool_result", ...)             # records ONLY toolName === "skill_view"
  ```

  There is no `tool_call` handler, so nothing intercepts pi's native
  `read` / `bash` / `edit` / `write`. Confirmed by reading the file end to end
  (257 lines).
- `loop-gov-mcp.py` cannot close this: it is a *tool surface*. It can hand the
  agent `begin_change`, but it never sees the host's native `edit`/`write`.
  Registering it over MCP (which `install-pi-mcp.sh` does) gives pi the ritual,
  not the gate.
- Pi 1.2.0 *does* provide the interception point Titus assumed was missing —
  `tool_call` handlers, and the type contract says they "Can block"
  (`ToolCallEvent`, `ToolCallEventResult.block`, `ExtensionHandler` in
  `dist/core/extensions/types.d.ts`). So the gap is closable at the harness
  layer; it was simply never wired.

**TITUS IS WRONG on one specific point — correction needed.**

He states: *"There is no 'Level 3' fallback in the pre-commit hook that actually
checks for a governance lock — the hook assumes MCP already handled it."*

A Level 3 lock check **does exist**: in `ops/scripts/pre-commit-score`, the
`# ── Level 3: Governance lock check` block scans
`~/.hermes-cortex/state/.governance-*.json`, matches on the `repo_slug` field
inside each lock, and exits 1 when no lock covers the repo. The header he quotes
is followed, a few hundred lines later, by the code he says is absent.

**But his conclusion survives, for a different reason — the check is repo-scoped:**

```bash
# the Level 3 refusal condition, verbatim
if [[ "$SANCTIONED_PIPELINE" != "1" && "$IS_CORTEX_REPO" -eq 1 && "$LOCK_FOUND" -ne 1 ]]; then
```

`IS_CORTEX_REPO` is set only when `$REPO_ROOT == ${HOME}/hermes-cortex`, a
deliberate operator decision recorded in the same file ("Repo scope guard") so
that manual human commits in client repos are not blocked.

Net effect, measured against the code:

| Where pi works | write tools gated? | commit gated by a lock? |
|---|---|---|
| `~/hermes-cortex` | NO | YES (Level 3) |
| any project repo (the normal titus case) | NO | NO |

So the honest statement is: *pi's writes are ungated everywhere, and pi's commits
are ungated in every repo except `~/hermes-cortex`* — which is the opposite of
where pi is normally used.

## 2. Design decision — where the verdict comes from (operator steer)

The operator said this session: *"mcp servers should route via hermes-cortex
and/or steadfaste."*

Agreed, and it is already the fleet's rule (one implementation, thin per-harness
adapters). So:

- The pi gate is a **thin adapter**. It makes NO governance decision.
- The verdict comes from the **existing shared implementation**:
  `ops/scripts/loop-gov.py`, whose own contract is "one implementation, generic
  by construction" — it loads `loop-gov-mcp.py` and calls the server's own
  handlers, with gateable exit codes:

  ```
  0 = ran / allowed     1 = governance REFUSED     2 = usage error     3 = governance unavailable
  ```

- No TypeScript re-implementation of lock parsing, staleness, or repo matching
  in the extension. Anything the gate needs to *decide*, it asks for.

### Open question the reviewer should rule on

`loop-gov.py check_lock '{}'` returns the session-scoped answer PLUS the full
live set:

```json
{"active": false, "lock": null, "live_lock_count": 2,
 "locks": [{"repo_path": "...", "repo_slug": "...", "task_id": "...", "...": "..."}]}
```

(`_check_lock` and `_live_locks` in `mcp-servers/loop-gov-mcp.py`; `_live_locks`
applies the server's own staleness predicate.)

Two options for "does a lock cover THIS session's repo":

- **(a) filter in the extension** — match each entry's `repo_path` against the
  session repo. Zero new server surface, but puts a *coverage rule* in a second
  place.
- **(b) add one repo-scoped predicate to the shared implementation** so the
  extension consumes a verdict and nothing decides "covered" twice.

I lean (b) on the fleet's own rule ("a second, looser copy is how binding stops
binding"), and I want the reviewer's ruling before writing either.

## 3. Proposed change surface

1. `ops/install/harnesses/pi/extensions/cortex-governance.ts` — NEW. Registers
   only a `tool_call` handler. Blocks `write`/`edit` when no lock covers the
   session repo; blocks `bash` when the command is write-classified (reusing the
   enforcer's conservative metachar rule: `;` `|` `&` `>` `<` backtick, `$()`,
   newline, interpreter forms). Read-only tools (`read`, `grep`, `find`, `ls`)
   always pass.
2. `ops/install/harnesses/registry.yaml` — declare the new artifact and its
   capability verify steps (the registry is the single source; the harness README
   is GENERATED from it).
3. `ops/scripts/install/install-pi-integration.sh` — wire the second extension at
   user scope (it currently writes `extensions: [cortex-context.ts]`).
4. `ops/install/harnesses/pi/verify-governance-extension.mjs` — NEW guard that
   EXECUTES the extension (loads it with pi's own jiti loader, hands it a stub
   `pi`, fires synthetic `tool_call` events, asserts the returned decision) and
   checks BOTH directions: unlocked write ⇒ blocked; locked write ⇒ allowed.
   Modelled on the existing `verify-extension.mjs`, the working precedent for
   "execute, don't grep".
5. Tests + docs: a `tests/` case that actually executes the guard, plus the pi
   skill, the generated harness README, and a runbook entry.

## 4. Failure semantics (explicit, because this can brick a host)

- **Exit 1 (refused)** ⇒ block the tool call; the message names the remedy
  (`loop-gov.py begin_change`) and does NOT echo lock contents.
- **Exit 3 (governance unavailable)** ⇒ the dangerous one. Unconditionally
  fail-closed would let a broken venv on titus stop *all* file writes. The fleet
  rule is: a gate that cannot verify must REFUSE, but say what that costs, and
  give the operator an explicit, documented, auditable override rather than a
  silent one.
- **Host with no cortex tree at all** ⇒ the gate cannot exist; the extension must
  be inert (not installed), and `cortex-update.sh` / the doctor must report that
  as WARN, never silently PASS. A fleet-wide gap needs a CHECK, not just a doc.

## 5. What I am explicitly NOT doing

- Not touching `pre-commit-score`'s repo scope. Widening Level 3 to every repo
  would re-break manual human commits in client repos — the exact regression the
  scope guard was added for. If the reviewer sees a way to gate pi's commits in
  project repos without that, it is a separate cycle.
- Not patching Hermes core (the fleet is migrating off Hermes).
- Not writing a second lock parser in TypeScript.

## 6. Evidence gathered (commands run this cycle)

- `ops/scripts/pre-commit-score`: read the Level 3 block, the repo scope guard,
  and the `IS_CORTEX_REPO` assignment.
- `ops/install/harnesses/pi/extensions/cortex-context.ts`: read end to end
  (257 lines, four hooks, zero registered tools).
- `ops/install/harnesses/registry.yaml`: read the pi entry (capabilities
  `context` / `skills` / `governance`; governance declares mcp plus a cli
  fallback).
- `~/.pi/agent/install/current-version` = `1.2.0`; `releases/` holds `1.1.0`,
  `1.2.0`.
- `dist/core/extensions/types.d.ts`: read `ToolCallEvent`,
  `ToolCallEventResult.block`, `ExtensionHandler`.
- `ops/scripts/loop-gov.py`: read end to end — exit-code contract, repo stamping
  (`_stamp_repo_into_payload`), refusal markers (`is_refusal`).
- `mcp-servers/loop-gov-mcp.py`: read `_live_locks`, `_check_lock`, `_derive_slug`,
  `_derive_repo_path`.
- Not yet exercised: no code written, nothing deployed, no test run.

## 7. Open questions for the reviewer

1. Section 2: (a) filter in the extension, or (b) add the repo-scoped predicate to
   the shared implementation?
2. Section 4: is a documented operator override acceptable for exit 3, or must it
   be unconditionally fail-closed?
3. Is scoping this to pi only correct, or should the same `tool_call` gate ship
   for steadfaste's harness in the same cycle?
