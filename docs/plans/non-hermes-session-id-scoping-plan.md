PLAN MATERIAL — cycle 13855, task fix-non-hermes-session-id-scoping
base revision: 391abff5fc63b98e28e63f27bfb0bff27b70bc78

## 1. THE DEFECT (measured, re-runnable)
Evidence: docs/evidence/shared-session-id-non-hermes-2026-10-27/transcript.txt (generator run.sh beside it).
Case A: two separate processes in ONE repo with no injected id both resolved sess_108f05ce7587 and wrote ONE lock file .governance-sess_108f05ce7587.json.
Case F: with the holder's heartbeat past TTL the peer's begin_change purged that lock, resolved the holder's PENDING cycle to MOVE_ON as '[orphan-reaper] abandoned', rewrote the SAME lock path, and the holder's end_change then answered "Lock belongs to task 'task-d', not 'task-c'".
Case C: either process can score and end the other's cycle (no owner check).
Case D/E: an explicit per-call session_id yields a separate lock; without repo_path the lock records an empty repo_path.

## 2. CURRENT CODE (extracted verbatim from the file under change)
def get_session_id(args: dict | None = None) -> str:
    """Return a persistent session ID, creating one on first call.

    Resolution order:
    0. Per-call session_id injected into the tool call args by the
       governance-enforcer plugin (Hermes gateway). The ONLY reliable signal
       for Hermes: the MCP server is one shared process for all Hermes
       sessions, and the shared marker files below are clobbered by concurrent
       sessions.
    1. Non-Hermes caller (no per-call id): a PROCESS-scoped id, generated once
       per MCP server process. Claude Code spawns one stdio child per
       session/project, so this is a correct session discriminator. We do NOT
       fall back to the host-global ~/.hermes/session.id cache or the Hermes
       marker files — those are shared by every session and caused
       begin/end to collide across concurrent Claude+Hermes sessions
       (2026-09-29).

    The old Priority 1-3 marker-file fallbacks were REPLACED by the
    process-scoped id. Rationale: the markers only ever hold the last Hermes
    session id, so a non-Hermes caller adopting them stole another session's
    identity instead of getting its own. A per-process id cannot collide.
    """
    # Priority 0: per-call session ID injected by the enforcer plugin
    sid = _injected_session_id(args)
    if sid:
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(sid)
        return sid

    # Priority 1: process-scoped id for non-Hermes callers — stable per MCP
    # child (per Claude session), disjoint across concurrent sessions, and
    # never adopts another session's Hermes id. PERSISTED per project
    # (repo slug of cwd, same resolution the git hooks use) so the id
    # survives an MCP-child restart mid-session (adversarial finding
    # ADV-2872-2: an in-memory-only id orphans the lock when Claude Code
    # restarts the server between begin_change and end_change). Same-project
    # sharing is correct governance semantics — begin_change already
    # serializes a repo to one active change; cross-PROJECT ids stay disjoint,
    # which is the collision class this fix removes.
    global _PROCESS_SESSION_ID
    if not _PROCESS_SESSION_ID:
        slug = _derive_slug()
        persist = GOVERNANCE_STATE_DIR / f".session-{slug}.id"
        try:
            if persist.exists():
                cached = persist.read_text().strip()
                if cached:
                    _PROCESS_SESSION_ID = cached
            if not _PROCESS_SESSION_ID:
                _PROCESS_SESSION_ID = f"sess_{uuid.uuid4().hex[:12]}"
                GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
                persist.write_text(_PROCESS_SESSION_ID)
        except OSError:
            # Persist failure must not break the session — fall back to the
            # in-memory id (restart orphan risk returns, but the lock system
            # still works for the common no-restart path).
            if not _PROCESS_SESSION_ID:
                _PROCESS_SESSION_ID = f"sess_{uuid.uuid4().hex[:12]}"
    return _PROCESS_SESSION_ID


def _injected_session_id(args: dict | None) -> str:
    """The per-call session id the ENFORCER injected, or "" when absent.

    Its presence is ALSO the "this caller is Hermes" signal: the enforcer injects
    on every mcp__loop_governance__* call (see ``get_session_id`` Priority 0), so
    a caller without it is a non-Hermes harness or the CLI.
    """
    if not isinstance(args, dict):
        return ""
    sid = args.get("session_id", "")
    return sid.strip() if isinstance(sid, str) else ""


## 3. THE CHANGE (precise)

In `mcp-servers/loop-gov-mcp.py`, `get_session_id(args)`, between the existing
Priority 0 (per-call `session_id` injected by the Hermes enforcer) and the
existing Priority 1 (the per-REPO persisted file `state/.session-<slug>.id`),
insert one step: **when no per-call id is injected, take the session id from the
CALLER'S OWN ENVIRONMENT**, because one MCP child process serves one session —
the same premise the module already relies on for its process-scoped fallback.

Precedence, each value stripped and ignored when empty:
  1. `CORTEX_SESSION_KEY`   — the fleet's documented per-session key
  2. `PI_SESSION_ID`        — Pi's own documented "Current session ID"

The derived id is namespaced so it can never be mistaken for a Hermes session id
and so an operator reading `ls .governance-*.json` can see where it came from:

    sess_<source>_<sanitised value>      e.g. sess_pi_session_id_01a17c0b-82ee-72f1-be80-f25d7f225015
                                              sess_session_key_hc-pi-12345

Sanitisation: keep `[A-Za-z0-9._-]`, replace every other character with `_`,
collapse repeats, and cap the whole id at 120 characters (truncate the value, not
the prefix). The result therefore contains no `/`, no `\`, no whitespace and no
NUL — the same constraint the enforcer's `_assert_safe_session_id` enforces on
ids used in marker file names, and it cannot start with `cron_`/`bg_` (which
`_session_type()` reads as a scheduler session), because it always starts with
`sess_`.

When an env id is used, the per-repo persisted file is NOT written and NOT read:
the env value is already stable across an MCP-child restart, which is the only
reason that file exists.

## 4. THE ENV NAMES ARE SURVEYED, NOT INVENTED

- `CORTEX_SESSION_KEY` — already the fleet's per-session identity. Documented in
  `docs/runbooks/context-integration.md` ("One session = one identity.
  Precedence is args -> CORTEX_SESSION_* env -> git"), consumed by
  `ops/services/mycortex-mem/context_tools.py` and
  `ops/scripts/session-autocheckpoint.py`, and pinned per chat by the
  cortex-gateway `command` backend for Pi:
  `ops/scripts/cortex_gateway/agents.py` ("Declaring
  env: {\"CORTEX_SESSION_KEY\": \"{session_id}\"} makes each chat its own"),
  `ops/scripts/gateway-pi.example.yaml`.
- `PI_SESSION_ID` — Pi's own variable, documented in the installed package at
  `~/.pi/agent/install/releases/1.4.0/node_modules/@earendil-works/pi-coding-agent/docs/environment-variables.md`:
  "PI_SESSION_ID | Current session ID". It is the variable the reporting agent
  (Titus) quoted for his own session, and it is the only per-session identity a
  bare interactive `pi` exposes.

No new configuration name is introduced.

## 5. WHAT THIS DOES NOT CHANGE

- Hermes callers: unchanged. The enforcer injects `session_id` on every call and
  Priority 0 still returns it verbatim (this session's own lock carries the
  Hermes session id, and it must keep doing so).
- A caller with no env id: unchanged. It still gets the per-repo persisted id,
  which is what keeps the CLI and a bare harness restart-stable.
- `_derive_slug` / repo identity: untouched. Note the known consequence, already
  measured in case E: a caller that supplies an id per call and no `repo_path`
  gets a lock with an empty `repo_path` (the unclosable-lock class). That is a
  separate defect and is NOT fixed here; the env path is unaffected because
  `_derive_slug`'s Priority 0c is skipped only when an id is INJECTED PER CALL,
  which the env path is not.

## 6. REJECTED OPTIONS

- **Per-process random id instead of the per-repo file.** Reintroduces the
  defect the persistence was added for (adversarial finding ADV-2872-2: an
  in-memory-only id orphans the lock when the harness restarts the MCP child
  between begin_change and end_change). Rejected.
- **Delete the per-repo persisted fallback entirely.** Would break the CLI and
  any harness with no session identity at all, and the failure mode is an
  orphaned lock, not a shared one. Rejected as a wider change than the defect.
- **Make the installer inject a per-session key into ~/.pi/agent/mcp.json.** The
  block is static configuration written once; it cannot know a Pi session id at
  write time. The installer already documents that Pi MERGES the block over its
  own environment, so `PI_SESSION_ID` (set by Pi on its own process) reaches the
  MCP child without any change. Therefore no installer change is proposed; this
  is an inference from that documented merge plus the gateway's own pinning test
  (`tests/test_gateway_new_session.py`), and it is listed under UNVERIFIED below
  rather than claimed.
- **Have each harness adapter pass `session_id` per call.** Requires per-harness
  code in every adapter, and the CLI path has no adapter; the resolver is the
  single seam every harness already goes through.

## 7. TESTS (TDD: written first, RED observed, then GREEN)

New file `tests/test_harness_session_id_env.py`, driving the module's own
`get_session_id` with the environment controlled per subprocess:

1. two DIFFERENT `CORTEX_SESSION_KEY` values in ONE repo -> DISJOINT ids, and two
   lock files coexist (the defect's headline case).
2. `PI_SESSION_ID` alone -> used; id is stable across two processes with the same
   value (survives an MCP-child restart).
3. `CORTEX_SESSION_KEY` wins when both are set.
4. a per-call injected `session_id` still wins over both env values.
5. an env value of "" / whitespace -> ignored, falls through to the per-repo id.
6. sanitisation: a value containing `/`, `\`, whitespace, a newline and a `..`
   segment yields a single filename component with none of those characters, and
   the resulting lock path stays inside the state dir.
7. no env value -> the existing per-repo behaviour is unchanged (regression
   guard: `tests/test_non_hermes_session_id.py` must stay green).
8. the env path does NOT write the per-repo `state/.session-<slug>.id` file.

Existing suites that must stay green: `tests/test_non_hermes_session_id.py`,
`tests/test_non_hermes_repo_identity.py`, `tests/test_governance_lock_lifecycle_claims.py`.

## 8. UNVERIFIED (stated, not claimed)

- That `PI_SESSION_ID` reaches the MCP child on a Pi host. The evidence is the
  installer's own comment that Pi merges the env block over its own environment;
  it has not been exercised on a Pi host from here. The change is still correct
  if it does not: the env is read from the MCP child's own environment, so
  nothing is claimed about who sets it.
- That Claude Code exposes a comparable variable. No such name was found in this
  repo, so none is honoured; a Claude Code session therefore keeps the per-repo
  fallback and its documented workaround (pass `session_id` per call).
