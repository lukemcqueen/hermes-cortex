# Fleet Update Protocol — Agent Bus Message Schema

Defines the bus message format for Moses to orchestrate fleet-wide updates
via the Agent Bus (PGMQ). Agents receive requests, execute work, report results.

## Message Flow

```
Moses → Agent:  UPDATE_REQUEST  (cortex-update + doctor)
Agent → Moses:  UPDATE_RESULT   (success/fail + doctor JSON + git SHA)
Moses → Agent:  FIX_REQUEST    (targeted fix instruction)
Agent → Moses:  FIX_RESULT    (fix applied? + evidence)
Moses → Telegram: Fleet status report (aggregated)
```

## Common Headers

Every message in this protocol uses these base fields:

| Field | Type | Description |
|-------|------|-------------|
| `from` | string | Sender agent name |
| `to` | string | Target agent queue (inbox_<agent>) |
| `topic` | string | Always `"fleet-update"` |
| `subject` | string | Message type: `UPDATE_REQUEST`, `UPDATE_RESULT`, `FIX_REQUEST`, `FIX_RESULT` |
| `correlation_id` | string | UUID — ties request/response pairs for idempotency |
| `priority` | string | `"normal"` or `"high"` |

The `body` field is **structured JSON** (not free text) so agents can
parse it programmatically.

---

## UPDATE_REQUEST (Moses → Agent)

Sent when Moses pushes new code to main and the fleet should update.

When an agent receives `UPDATE_REQUEST`, it:
1. **`git pull origin main`** — pulls the latest code (so agents stuck on an old SHA get up to date)
2. **`cortex-update.sh --force-all`** — deploys all registered files to disk
3. **Runs doctor** (if `run_doctor: true`) — verifies all services are healthy
4. **Sends `UPDATE_RESULT`** — reports success/fail, git SHA before/after, and doctor output

> ⚠️ Agents that cannot `git pull` (auth failure, network down) report the failure in `UPDATE_RESULT` WITHOUT applying the update.

```json
{
 "from": "moses",
 "to": "inbox_gisu",
 "topic": "fleet-update",
 "subject": "UPDATE_REQUEST",
 "correlation_id": "uuid-v4",
 "priority": "normal",
 "body": {
  "target_sha": "d2bb495",
  "target_version": "2.0.0",
  "branch": "main",
  "mode": "force-all",
  "run_doctor": true,
  "deadline_minutes": 30,
  "summary": "feat(doctor): add structured JSON output"
 }
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `target_sha` | string | Git SHA to update to |
| `target_version` | string | Expected VERSION after update |
| `branch` | string | Branch to pull |
| `mode` | `"force-all"` or `"delta"` | cortex-update mode |
| `run_doctor` | bool | Whether to run doctor after update |
| `deadline_minutes` | int | Max minutes before Moses considers agent unresponsive |
| `summary` | string | Human-readable summary of the change |
| `target_agents` | string[] | **Optional** — only process on named agents (e.g. `["gisu", "titus"]`). All agents process when absent. |
| `target_labels` | map[string,string] | **Optional** — only process on agents whose labels match ALL specified key-value pairs (e.g. `{"group": "canary"}`). All agents process when absent. |

> **Label targeting:** Labels are set via `hermes cortex agent label set <name> <key>=<value>`.
> When both `target_agents` and `target_labels` are present, an agent matching EITHER criteria processes the request.
> Agents without matching labels silently skip the update (no response sent).

---

## UPDATE_RESULT (Agent → Moses)

Sent by each agent after processing UPDATE_REQUEST.

```json
{
 "from": "gisu",
 "to": "inbox_moses",
 "topic": "fleet-update",
 "subject": "UPDATE_RESULT",
 "correlation_id": "<same uuid from request>",
 "priority": "normal",
 "body": {
  "success": true,
  "git_sha_before": "4ef429e",
  "git_sha_after": "d2bb495",
  "version": "2.0.0",
  "update_output": "✓ 8 file(s) updated\n✓ All 4 cortex services managed by systemd (active)",
  "doctor": {
   "healthy": true,
   "pass": 39,
   "warn": 0,
   "fail": 0,
   "checks": [{"name": "Repo branch", "status": "PASS", "detail": "on 'main'"}]
  },
  "errors": [],
  "duration_seconds": 45.2
 }
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | bool | Did the full update succeed? |
| `git_sha_before` | string | SHA before update |
| `git_sha_after` | string | SHA after update |
| `version` | string | VERSION file content |
| `update_output` | string | Raw cortex-update.sh output |
| `doctor` | object | Full doctor --json output (if run_doctor was true) |
| `errors` | string[] | Any errors encountered |
| `duration_seconds` | float | Wall-clock time for the update |

---

## FIX_REQUEST (Moses → Agent)

Sent when UPDATE_RESULT contains issues Moses can identify and fix.

```json
{
 "from": "moses",
 "to": "inbox_kustos",
 "topic": "fleet-update",
 "subject": "FIX_REQUEST",
 "correlation_id": "uuid-v4",
 "priority": "high",
 "body": {
  "issue": "AGENTS.md needs sync",
  "fix": "cp ~/hermes-cortex/AGENTS.md ~/.hermes/AGENTS.md",
  "verify": "python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --json",
  "deadline_minutes": 10
 }
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `issue` | string | What's wrong |
| `fix` | string | Shell command to apply fix |
| `verify` | string | Shell command to verify fix worked |
| `deadline_minutes` | int | Max minutes to respond |

---

## FIX_RESULT (Agent → Moses)

Sent after agent executes a fix.

```json
{
 "from": "kustos",
 "to": "inbox_moses",
 "topic": "fleet-update",
 "subject": "FIX_RESULT",
 "correlation_id": "<same uuid from request>",
 "priority": "normal",
 "body": {
  "success": true,
  "fix_output": "COPY OK",
  "verify_output": "{\"summary\": {\"pass\": 39, \"warn\": 0, ...}}",
  "doctor_healthy": true,
  "duration_seconds": 2.1,
  "errors": []
 }
}
```

---

## Response Guarantee

Every message sent to an agent **always gets a response**, regardless of whether the handler succeeded:

| Outcome | Response | `success` Field |
|---------|----------|-----------------|
| Handler completed | `{subject}_RESULT` with handler output | `true` |
| Handler crashed (exception) | `{subject}_RESULT` with error detail | `false` |
| Unknown subject | `{subject}_RESULT` with `"Unknown subject"` error | `false` |

This means the sender (Moses or another agent) never hangs waiting for a response
that will never come — every message eventually produces a result.

## Idempotency

Every `UPDATE_REQUEST` and `FIX_REQUEST` has a unique `correlation_id`.
Agents **must** track processed IDs and skip duplicates. The Moses side
generates a new ID for each request round. If an agent receives the same
`correlation_id` twice, it should respond with its previous `UPDATE_RESULT`
without re-executing.

## Delivery Guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| At-least-once delivery | PGMQ auto-retry on read + vt timeout |
| At-most-once execution | correlation_id dedup on agent side |
| Response deadline | deadline_minutes field + Moses timeout handler |
| Confirmation tracking | Existing bus-message-tracker polls for unconfirmed messages |

## Agent Taxonomy

Fleet agents use three types in the registry `role` field:

| Type | bus_mode | Runs orchestrator crons? | Receives bus work? | Example |
|------|----------|--------------------------|--------------------|---------|
| **orchestrator** | `both` | Yes | Yes | Moses, Esther |
| **server-agent** | `poll` | No | Yes (polls inbox) | Joseph, Kustos, Gisu |
|| **dev-agent** | `poll` | No | Yes (polls inbox) | Titus |

- **orchestrators** use `orch-bus-*` scripts and `cronjob` MCP tool to manage fleet
- **server-agents** run `install.sh` (full stack) and poll inbox for work
- **dev-agents** use the `install-crons.sh` `agent-message-handler` cron to process UPDATE_REQUEST via `agent-message-handler.py`

## Timeouts

Moses waits `deadline_minutes` for each agent. If an agent doesn't respond:
1. Wait deadline, retry once
2. If still no response, mark agent as `unreachable` in the fleet report
3. Include in Telegram summary

---

## ROLLBACK_REQUEST (Moses → Agent)

Sent to revert an agent to a previous known-good SHA when an update fails.

```json
{
 "from": "moses",
 "to": "inbox_gisu",
 "topic": "fleet-update",
 "subject": "ROLLBACK_REQUEST",
 "correlation_id": "uuid-v4",
 "priority": "high",
 "body": {
  "target_sha": "4ef429e",
  "reason": "Doctor failed after update: 2 warn, 1 fail",
  "dispatch_id": "fleet-update-abc123-gisu",
  "run_doctor": true,
  "deadline_minutes": 10
 }
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `target_sha` | string | Git SHA to revert to |
| `reason` | string | Why rollback is needed |
| `dispatch_id` | string | Original dispatch ID for traceability |
| `run_doctor` | bool | Whether to run doctor after rollback |
| `deadline_minutes` | int | Max minutes before Moses considers agent unresponsive |

## ROLLBACK_RESULT (Agent → Moses)

Sent after agent reverts and verifies.

```json
{
 "from": "gisu",
 "to": "inbox_moses",
 "topic": "fleet-update",
 "subject": "ROLLBACK_RESULT",
 "correlation_id": "<same uuid from request>",
 "priority": "normal",
 "body": {
  "success": true,
  "sha_before": "d2bb495",
  "sha_after": "4ef429e",
  "reverted": true,
  "doctor": {"healthy": true, "pass": 39, "warn": 0, "fail": 0},
  "duration_seconds": 7.3,
  "errors": []
 }
}
```

---

## Git Auth Verification

Before dispatching an update, Moses verifies each agent can pull from the remote.
The `bus-git-auth-check.py` script SSHes into each server-agent and runs
`git ls-remote origin HEAD` to confirm credentials work.

For dev-agents (push-only, Titus), auth is verified on the agent side as part
of `agent-message-handler.py` — if `git pull` fails, the handler reports
the failure in UPDATE_RESULT WITHOUT applying the update.

### Server-Agent Git Auth Check

Sent as a lightweight bus message (no update, just verification):

```json
{
 "from": "moses",
 "to": "inbox_gisu",
 "topic": "fleet-update",
 "subject": "GIT_AUTH_CHECK",
 "correlation_id": "uuid-v4",
 "priority": "normal",
 "body": {
  "remote": "origin",
  "expected_url": "https://github.com/fleet-operator/hermes-cortex.git"
 }
}
```

The agent responds with `GIT_AUTH_RESULT` containing `{authenticated: true/false, remote_url: "...", error: "..."}`.

## See Also

- `agent-registry.json` — agent capability manifests (bus_mode, has_git, etc.)
- `cortex-doctor.py --json` — structured doctor output consumed by this protocol
- `bus-message-tracker.py` — existing confirmation tracking infrastructure
