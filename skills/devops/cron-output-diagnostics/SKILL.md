---
name: cron-output-diagnostics
version: 1.0.0
category: devops
description: "Use when a cron delivery is flagged or looks wrong."
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [cron, diagnostics, watchdog, quality, silent, triage]
    related_skills: [cron-quality-gate, cron-format-standard, cron-job-management]
---

# Cron Output Diagnostics

Use when a cron delivery looks wrong: a quality-watchdog alert (🟠/🟡/🔴), a
suspiciously short or oddly-formatted response, or repeated identical cron
outputs. **Triage before touching anything** — most flags are either a one-off
model deviation or a watchdog false positive, not a broken job.

## Step 1 — Classify the response (md5-compare technique)

Pull the `## Response` section from recent output files
(`~/.hermes/cron/output/<job-id>/2026-*.md`) and compare byte-hashes:

- **All byte-identical across runs** (same md5) → pipeline/serialization
  artifact or the agent echoing injected script output. Check the runner and
  the pre-run script, NOT the model.
- **Exactly ONE run differs, rest identical** → one-off model deviation. The
  normal case for a healthy no-op delivered in a wrong wrapper.
- **Many differ, all garbage** → fallback-chain problem or prompt drift. Check
  `fallback_providers` in `~/.hermes/config.yaml` for known-bad models
  (e.g. `qwen2.5-coder:3b`) and pin provider/model explicitly.

## Step 2 — Recognize watchdog false positives

The quality watchdog (`agent-cron-quality-watchdog`, every 10 min) evaluates
only the LATEST output file per LLM-driven job. Known verdicts:

| Flag | Likely verdict |
|------|----------------|
| 🟠 short response (<100 chars) whose content is `["SILENT"]` / `[ SILENT ]` / `'[SILENT]'` | **FALSE POSITIVE** — JSON/whitespace-wrapped healthy no-op. The watchdog's `[SILENT]` exemption is a LITERAL match (`response == "[SILENT]"`), so wrapped variants fall through to the short-response garbage check. Still a real contract breach: the wrapped variant was DELIVERED to the user (suppression requires the exact bare token). |
| 🟠 identical alert repeating every 10 min | **ONE stale bad run, not N failures** — the watchdog has NO dedup; it re-flags the same latest output until the job's next run replaces it. Check the output file timestamp before reacting. |
| 🔴 `QUALITY_G_BLOCKED` | Agent self-blocked (model stall / gate failed) — real. |
| 🔴 known-bad fallback model | Real (garbage delivered with `last_status: ok` during provider outage). Fix: `hermes fallback remove`. |

## Step 3 — Remediate from the worker lane

The watchdog script lives at `ops/scripts/health/` — **orchestrator-only**
(shared repo; the pre-commit hook blocks `ops/scripts/` staging for workers).
Workers do NOT edit it. The compliant path:

1. **Harden the offending cron's LIVE prompt** via `cronjob action='update'`:
   require the bare `[SILENT]` literal — "never JSON-wrapped, quoted, or in a
   code block" — plus a quality-gate self-check item ("is [SILENT] the bare
   literal token?"). Note: install-script prompt edits do NOT propagate to
   existing jobs — the live update is the only lever.
2. **Escalate the class fix** with a ready-to-apply patch:
```bash
bash ~/.hermes-cortex/scripts/contact-orchestrator.sh \
  "📝 PROPOSAL: <what>" "<patch description incl. exact line numbers>" normal
```
   → lands in the shared `inbox_orchestrator` (verified working 2026-08-19).
3. **Verify**: re-read the stored prompt from `~/.hermes/cron/jobs.json`;
   the next scheduled tick replaces the stale output; run the doctor
   (`cortex-doctor.py --quiet`) and confirm no new warnings.

## Worked example

2026-08-19: `agent-inbox-workday` JSON-wrapped-SILENT false positive — full
evidence trail and the proposed watchdog normalization:
`references/silent-json-wrapper-case.md`.

## Pitfalls

- **Don't fire a manual `cronjob action='run'` to "test" the fix.** Manual
  runs are tool-restricted by design (no governance MCP tools; enforcer
  fail-closes writes) and can half-process real inbox messages. The natural
  tick is the real dogfood — verify from its output file afterward.
- **Don't edit the deployed watchdog copy** (`~/.hermes-cortex/scripts/`) —
  it is overwritten by `cortex-update.sh`, and the repo source is
  orchestrator-only. Never `--no-verify` around it.
- **A wrapped no-op is a TWO-layer failure**: (1) delivery suppression broke
  (user got noise), (2) watchdog false-flagged it. Fix both: source (prompt
  hardening — worker lane) and detection (watchdog normalization —
  orchestrator lane).
- **`deliver: "origin"` on cron jobs created from a script/CLI context
  delivers nowhere** — a silent watchdog can look healthy while being
  invisible. Confirm the alert destination when triaging.
