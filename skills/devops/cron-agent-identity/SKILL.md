---
name: cron-agent-identity
version: 1.0.0
category: devops
description: "Diagnose which agent/profile a Hermes cron session runs as."
license: MIT
platforms: [linux, darwin]
---

# Cron Agent Identity — What Profile/Name Does a Cron Run As?

## When to Use

- A cron run self-identifies as the **wrong agent or profile** (e.g. wrote to
  `~/brain/<wrongname>/`, created the wrong `mycortex_reader_<name>` DB role,
  sent messages from the wrong identity).
- You need to know which env vars a cron agent will see at runtime.
- You're debugging why `HERMES_PROFILE` / `AGENT_NAME` differ between a cron
  session and the host's config files.

## Core Facts (verified 2026-08-06 on macOS host, Hermes core)

1. **Cron agents do NOT load MEMORY.md or USER.md.** `cron/scheduler.py`
   constructs cron AIAgents with `skip_memory=True` (`agent/agent_init.py`).
   A wrong profile name in a cron run therefore did NOT come from USER.md's
   `Name:` field — don't waste a cycle on that theory. It came from the
   **cron session's environment**.
2. **Subprocess env = sanitized snapshot of the gateway process's runtime
   `os.environ`.** `tools/environments/local.py` `build_subprocess_env()`
   snapshots `os.environ`, scrubs secrets, and bridges gateway session
   ContextVars (`gateway/session_context.py` `_VAR_MAP` — only
   `HERMES_SESSION_*` / `HERMES_CRON_*` vars; AGENT_NAME is NOT in the map).
   So "why did the cron env contain X" = "where did the gateway's runtime
   `os.environ` get mutated" — not a per-job setting.
3. **`ps eww` on the gateway shows only the exec-time env.** A runtime
   `os.environ` mutation is invisible there. Don't conclude "gateway env has
   no AGENT_NAME" from `ps` alone — that only proves it wasn't there at boot.
4. **Profile resolution chain (mycortex CLI + install-profile-reader-role.sh):
   `HERMES_PROFILE` → `AGENT_NAME` → hostname.** The first non-empty env var
   wins. Host-level identity: `os-config.sh` `ensure_agent_identity()` uses
   AGENT_NAME env → `~/.hermes-cortex/agent.env` → hostname (**orchestrator
   hosts only**; non-orch hosts must provision agent.env). One inconsistent
   script (`install.sh` learning-sender) hardcodes `AGENT_NAME="${HOSTNAME%%.*}"`
   — hostname default, not design intent.

## Diagnostic Path

1. **Get the cron session id.** Cron session ids look like
   `cron_<jobid>_<timestamp>` (e.g. `cron_a28f8be0bc4e_20260806_112445`).
2. **Read the cron session's own tool output** — this is the authoritative
   evidence. Use `session_search(query='<distinct phrase from the run>',
   sort='newest')`, then `session_search(session_id=..., around_message_id=...)`
   to scroll to the first terminal call. The agent often echoes env vars
   (`echo "AGENT_NAME=$AGENT_NAME"`); that tool result is ground truth.
3. **Confirm which process ran the job** — `~/.hermes/cron/executions.db`
   `executions` table has `job_id`, `pid`, `started_at`. In-process ticker ⇒
   pid == gateway pid.
4. **Trace the mutation source** — grep Hermes core for writes to the env
   var (`os.environ[...] =`), check `build_subprocess_env()` + `_VAR_MAP`,
   then look outside the core: shell rc files, launchd plist env, `.env`
   loading, wrapper scripts. Hermes core has NO AGENT_NAME writer (verified
   2026-08-06 by repo-wide grep) — so a wrong AGENT_NAME came from outside
   the core's own code.
5. **Verify against the live server** — for DB-role symptoms, list actual
   roles (`SELECT rolname FROM pg_roles`) and DBs (`pg_database`); the cron
   agent may have created a role under its wrong identity (e.g.
   `mycortex_reader_joseph` while the host is titus).

## Pitfalls

- **Don't blame USER.md.** `skip_memory=True` means cron agents never see it.
- **Don't trust `ps eww` for runtime env.** Exec-time only.
- **The cron agent can create artifacts under its wrong identity** (DB roles,
   `~/brain/<wrong>/` dirs, INDEX files). After fixing the env/identity, clean
   those up deliberately — they're test artifacts, not knowledge.
- **A cron's `jobs.json` record carries no env block** for these vars —
   `workdir`, `enabled_toolsets`, `skills`, `prompt` are the only knobs. The
   env comes from the process, not the job.
- **Fix at the source, not by editing the prompt.** Don't patch the cron
   prompt to hardcode the right profile name (a per-host hack that breaks the
   fleet); find where the env is wrong and fix the process/identity layer.

## Related

- `mycortex` (user-owned) — dream layer, multi-tenancy, reader roles
- `cron-job-management` (user-owned) — cron naming, delivery, toolsets
- `config-drift-diagnostics` (user-owned) — stale connection-config names

  the first wrong-identity dream run (cron session id, executions.db pid,
  gateway env, core-grep proof) + the mycortex.conf gbrain-name finding.
