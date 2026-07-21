---
name: cron-job-management
description: Create, name, list, and maintain Hermes cron jobs — no_agent watchdog scripts, naming conventions, and the user's preferred listing format.
---

## When to use

When creating new cron jobs, renaming existing ones, listing all crons for display, or designing self-contained maintenance automation.

## Naming convention — definitive

Every cron name starts with a **group prefix** that determines install scope, doctor validation, and update workflow:

| Prefix | Scope | Who installs | Doctor validation |
|--------|-------|-------------|-------------------|
| `orch-` | Orchestrator-only (Moses, Esther). Bus infra, fleet watchdogs, health reports to Luke. | `install-orch-crons.sh` (in `ops/scripts/install/`) | `parse_orch_crons()` reads uninstall array from `install-orch-crons.sh` |
| `agent-` | All agents with Hermes Agent. Remediation, monitoring, memory, knowledge, governance, scoring. | `install-crons.sh` (in `ops/scripts/`) | `parse_expected_crons()` reads uninstall array from `install-crons.sh` |
| `local-` | This server only. Personal briefings, machine-specific maintenance. NOT in repo install scripts. | Created manually via `cronjob action='create' name='local-<name>'` | Skipped by doctor (not in any uninstall array) |

**Combining:** `local-agent-*` when a cron is both concept-level AND this-server-only. The `local-` prefix always comes first.

**Rules:**
- **Every cron in the repo MUST have a prefix** (`orch-` or `agent-`). Bare names like `system-alert-watchdog` or `remediation-sensor` are forbidden — they break doctor validation and create ambiguity about install scope. See the "Critical: uninstall array = doctor truth source" section below.
- Names are descriptive and human-readable — no abbreviations or cryptic codes.
- When renaming: `cronjob action='update' job_id=<id> name=<new-name>` — but read the full rename workflow below first.
- **Do not batch-rename more than 3-4 crons without confirming with the user first.** Large batch renames (10+) are disruptive — the user may undo them entirely. Prefer step-by-step or ask.
## Naming convention — definitive

Every cron name starts with a **group prefix** that determines install scope, doctor validation, and update workflow:

| Prefix | Scope | Who installs | Doctor validation |
|--------|-------|-------------|-------------------|
| `orch-` | Orchestrator-only (Moses, Esther). Bus infra, fleet watchdogs, health reports to Luke. | `install-orch-crons.sh` (in `ops/scripts/install/`) | `parse_orch_crons()` reads uninstall array from `install-orch-crons.sh` |
| `agent-` | All agents with Hermes Agent. Remediation, monitoring, memory, knowledge, governance, scoring. | `install-crons.sh` (in `ops/scripts/`) | `parse_expected_crons()` reads uninstall array from `install-crons.sh` |
| `local-` | This server only. Personal briefings, machine-specific maintenance. NOT in repo install scripts. | Created manually via `cronjob action='create' name='local-<name>'` | Skipped by doctor (not in any uninstall array) |

### Combining and nesting

- `local-agent-*` — a cron that is both machine-specific AND concept-level. The `local-` prefix always comes first.
- `orch-bus-*` — bus infrastructure crons (a sub-domain of orchestrator-only). All bus crons are orchestrator-only implicitly.
- No bare names allowed. Every cron in the repo MUST have a valid prefix.

### Critical rules

#### 1. No bare names (enforced by doctor)

Crons without a prefix (`orch-`, `agent-`, or `local-`) are **forbidden** in the repo. Examples of names that MUST be fixed if they exist:

| Bare name | Correct name |
|-----------|-------------|
| `bus-audit-watchdog` | `orch-bus-audit-watchdog` |
| `remediation-sensor` | `agent-remediation-sensor` |
| `system-alert-watchdog` | `agent-system-alert-watchdog` |
| `service-recovery` | `agent-service-recovery` |
| `memory-to-brain-sync` | `agent-memory-to-brain-sync` |
| `hermes-update` | `agent-hermes-update` |
| `hermes-cortex-sync` | `agent-hermes-cortex-sync` |

Prefix-less names break doctor validation because the doctor reads the uninstall arrays — and `parse_expected_crons()`/`parse_orch_crons()` only finds names in those arrays. A bare name that IS in the create section but ISN'T in the uninstall array silently passes doctor (no extra cron check) but causes drift.

#### 2. Uninstall array = doctor truth source (enforced by architecture)

`cortex-doctor.py` reads expected cron names from the **uninstall arrays** in `install-crons.sh` and `install-orch-crons.sh`. The doctor does NOT read the create sections. This means:

```
install-crons.sh                  cortex-doctor.py
┌──────────────┐                 ┌──────────────────┐
│ create_cron   │                 │                  │
│   "agent-fx"  │  ──(ignored)──►│  parse_expected  │
│               │                 │                  │
│ for job in    │                 │  reads this      │
│   "agent-fx"  │  ──(source)───►│  → expected list │
│   "agent-mem" │                 │                  │
│ ...; do       │                 └──────────────────┘
└──────────────┘
```

**Every cron in a `create_cron` block MUST be in the corresponding uninstall array, with the exact same name.** If they drift:
- Cron in create but NOT in uninstall → doctor doesn't check it → if it fails, nobody notices
- Cron in uninstall but NOT in create → doctor says "missing!" → false FAIL
- Same name in create and uninstall → doctor validates correctly ✓

After any rename cycle, run `python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet` to verify arrays are in sync.

#### 3. Create section is the install target; uninstall array is the doctor target

When adding a new cron:
1. Add `create_cron` block to the correct install script
2. Add the EXACT SAME name to the uninstall array in the SAME file
3. Register the script path in `cortex-update.sh`
4. Run doctor to verify

When renaming a cron, update BOTH arrays in the SAME commit. If you only update the create block, the old name stays in the uninstall array (doctor expects it) and no new cron is created with the new name (doctor misses it). This is the root cause of the July 2026 bus-rename bug.

## Cron rename workflow

When renaming a cron (e.g. `fleet-status-watchdog` → `orch-fleet-watchdog`):

1. **Survey first**: `search_files()` for the old name across the entire repo
2. **Remove old cron**: `cronjob action='remove' job_id=<id>`
3. **Rename/relocate script**: move from old path to new path in repo (e.g. `ops/scripts/inbox/` → `ops/scripts/agent/`)
4. **Update installer** — **critical: two-way sync required:**
   - Remove old name from `install-crons.sh` or `install-orch-crons.sh` uninstall array
   - Add new name to the uninstall array (doctor reads this for expected crons — see "Critical: uninstall array = doctor truth source" above)
   - Add `create_cron` block for new name with EXACTLY matching name string
   - Verify: the same name appears in BOTH the create_cron call AND the uninstall array
5. **Register in cortex-update.sh**: add `register()` call for new path
6. **Deploy**: copy script to `~/.hermes-cortex/scripts/` — verify it exists (`ls -la`)
7. **Create new cron**: `cronjob action='create' name=<new-name> ...`
8. **Test**: `python3 ~/.hermes-cortex/scripts/<script>` — verify exit code 0
9. **Verify install script syntax**: `bash -n ~/hermes-cortex/ops/scripts/install-crons.sh` and `bash -n ~/hermes-cortex/ops/scripts/install/install-orch-crons.sh` — must pass with zero errors. The `fix-cron-duplicates.py --fix` script now auto-verifies and reverts on failure, but always double-check after manual edits.
10. **Run doctor**: `python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet` — verify no failures
11. **Commit & Push**

## Canonical cron installer (crons.json + install-crons.py) — LEGACY, not in active use

The older template + installer pattern is preserved for reference but the active installers are `install-crons.sh` and `install-orch-crons.sh`.

Legacy template at `core/governance/crons.json` (if it still exists) is NOT the active pattern.

For self-contained pull + install / check + alert jobs that should be silent on success:

1. Write a script to `~/.hermes/scripts/<name>`:
   - Shebang: `#!/usr/bin/env bash` or `#!/usr/bin/env python3`
   - `set -euo pipefail` (bash) or proper error handling (Python)
   - Capture command output and exit code
   - On failure: echo error details, exit 1
   - On clean success (up to date or updated OK): exit 0 with NO stdout
2. `chmod +x ~/.hermes/scripts/<name>` + syntax check (`bash -n` or `python3 -m py_compile`)
3. Schedule with `cronjob`:
   - `no_agent=True`
   - `script=<name>` (resolves relative to `~/.hermes/scripts/`)
   - `deliver` set to where errors should reach the user (e.g. Telegram)
   - Empty stdout + exit 0 → silent, nothing delivered
   - Any stdout or non-zero exit → delivered as error alert

## Advanced: State-transition watchdogs — for dashboards that report multiple
dynamic values (agent status, workflows, pending messages), simple exit-code
silence isn't enough because every tick produces different output even when
nothing changed. Instead, track a compact JSON state signature and only fire
when the signature changes. See `references/state-transition-watchdog.md`.

## Advanced: Tiered schedule pattern — when a cron needs different polling
cadences at different times of day, split into multiple time-bounded jobs
instead of a single compromise schedule. See `references/tiered-schedule-pattern.md`.

**Real examples on this server:**
- `~/.hermes/scripts/hermes-update` — `hermes update --yes`, silent on success
- `~/.hermes/scripts/hermes-cortex-sync` — `git pull` on hermes-cortex, runs install-crons.py + setup.sh if changes detected

## Cron listing format for this user

When asked to list all crons, output in this compact format:

```
name    schedule    type
```

Where `type` is one of:
- `no_agent` — watchdog script, zero LLM tokens
- `LLM` — agent-driven, uses tokens

Group blocks by frequency:

```
 HIGH-FREQUENCY
  name    */5 * * * *    no_agent
  name    */10 * * * *   LLM

 DAILY
  name    0 7 * * *      LLM

 INFREQUENT
  name    0 6 * * 1      no_agent
```

Do not use tables, borders, or rich formatting. Just the raw columns.

## Cron delivery modes — critical lesson

**Never change the engine when the complaint is about delivery.**

If a cron's output is going to the wrong place or producing too much noise:
- **Delivery configuration** (`deliver` parameter, [SILENT] output protocol) — fix this
- **Mode** (`no_agent` ↔ LLM-driven) — this is about whether the task needs AI reasoning, not about delivery

See `references/cron-delivery-pipeline.md` for the full diagnostic checklist and [SILENT] protocol rules.

## Cross-profile cron management

**See also:** load the `cron-format-standard` skill — required output format for all LLM-driven cron jobs.

When explicitly directed to add a cron to another Hermes profile (e.g. Esther):

1. The profile's alias can run `hermes cron create` in that profile's context: `esther cron create --name "name" --deliver "target" "schedule" "prompt"`
2. If the CLI command errors (version incompatibility, schema differences), use a targeted patch on the profile's `cron/jobs.json` file instead — but ONLY when the user explicitly directs you
3. Always verify the profile already has the cron before duplicating it
4. After creating/updating in the target profile, **remove the duplicate from your own profile** if one existed

**CRITICAL:** Never touch another profile's cron files without explicit user direction. When you do, use `cross_profile=True` on write_file/patch and use surgical patches, not full-file overwrites.

## Pitfalls

- **Manual test ≠ scheduler test.** Running `python3 ~/.hermes-cortex/scripts/<script>` tests the script logic but does NOT update the cron scheduler's `last_status`. The doctor reads the scheduler's recorded status, not the script exit code. After fixing a cron, ALWAYS run `cronjob action='run' job_id=<id>` to refresh the scheduler's status, then run the doctor to confirm it clears. The user will see what the doctor shows — never claim a cron is "fixed" until the doctor confirms it.
- **Never guess job IDs.** Always `cronjob action='list'` first before update/remove.
- **no_agent scripts must handle silent-on-success correctly.** If the command prints "Already up to date." on stdout, the script must detect and suppress it — otherwise a "success" delivers noise to the user every tick.
- **no_agent scripts that import from project modules need PYTHONPATH.** Cron jobs run in a bare environment — no PYTHONPATH, no project venv. If a no_agent Python script imports from a project module (e.g. `agent_bus` under `~/hermes-cortex/core/agent_bus/`), it must handle both at the script level:
  1. **Shebang** to the project's venv python: `#!/home/moses/.hermes/hermes-agent/venv/bin/python3`
  2. **sys.path** before any project imports: `sys.path.insert(0, "/home/moses/hermes-cortex/core")`
  3. **Test** outside cron first: `/home/moses/.hermes/hermes-agent/venv/bin/python3 script.py`
  Without both, the cron silently fails with `ModuleNotFoundError` on every tick.
- **Delivery matters for cron jobs.** `deliver='local'` logs only. `deliver='origin'` delivers to the creating session (which may not exist at cron time). For unattended crons that should notify on error, set deliver to a live channel (e.g. `telegram:chat_id`).
- **Respect Esther's crons.** The Esther profile at `~/.hermes/profiles/esther/` has its own cron namespace. Never create, rename, or remove crons there unless explicitly directed.
- **shellcheck scripts.** Run `bash -n` after writing any bash script. A syntax error in a no_agent script means it silently fails forever.
- **Prefer crons.json over ad-hoc creation.** For anything permanent, use the template + installer pattern. Manual `hermes cron create` is for testing only.
- **Orchestrator-only crons.** If a cron should only run on the orchestrator (Moses), set `orchestrator_only: true` in crons.json. The installer will skip it on non-orchestrator machines.
- **Ask before bulk operations.** Renaming 10+ crons at once without confirmation will likely get undone. Batch at most 3-4 in a turn, or step through each group with user sign-off between batches. The user may reject the whole convention after seeing it applied — confirm early.
- **Undo is cheaper to prevent than to revert.** A batch of 22 renames takes 3-4 turns to undo because the cronjob tool has no rollback. Check with the user before applying a convention change to the entire cron table.
- **Doctor truth source = uninstall array.** `cortex-doctor.py` reads expected cron names from the uninstall arrays in `install-crons.sh` and `install-orch-crons.sh`. If a cron name in the `create_cron` block doesn't match the uninstall array — or is missing from it entirely — the doctor reports false failures. Every rename MUST update BOTH the create block and the uninstall array. Run `cortex-doctor.py --quiet` after any rename to verify sync. See the "Critical: uninstall array = doctor truth source" section under Naming Convention above for the function-level detail.
- **Cron execution paths have different inodes from the repo source path.** The cron execution paths (`~/.hermes-cortex/scripts/` and `~/.hermes/scripts/`) are hardlinked to each other but are **separate inodes** from the repo source (`hermes-cortex/ops/scripts/inbox/`). Fixing a script in the repo does **not** deploy to the cron paths — you must also `cp` the fixed file to `~/.hermes-cortex/scripts/` and `~/.hermes/scripts/`. Verify all inodes match (or the file content is identical) after deploying. This applies to every cron fix — always check what path the cron actually executes from before claiming the fix is live.
- **Python f-string single-quote nesting bug.** When an f-string uses single quotes as the delimiter AND contains a curly-brace expression with a string literal inside (e.g. `f'│ Stalled: {", ".join(x)}'`), the inner single quotes in `', '` will break the outer string. Use double quotes for the outer delimiter and single quotes inside: `f"│ Stalled: {', '.join(x)}"`, or vice versa. Always `python3 -m py_compile script.py` to catch these syntax errors before deploying.
