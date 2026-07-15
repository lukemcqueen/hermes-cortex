---
name: change-checklist
version: 1.0.0
category: software-development
description: "Mandatory pre-ship verification before calling end_change(). Covers 5 phases: test, multi-OS, multi-role, docs, final verification. Every governance cycle must run this before closing."
pinned: true
---

# Change Checklist — Pre-Ship Verification

**Mandatory before every `end_change()` call.**

Load this skill BEFORE closing a governance cycle. Run through all 5 phases. Do not skip, batch, or defer.

## Phase 1: Test

- [ ] Did the change actually apply cleanly? (No errors in write_file/patch/terminal)
- [ ] If code: does it run without errors? (Run it, don't guess)
- [ ] If config: does the service still start? (Restart/reload and check)
- [ ] If cron: does the script exit 0 when run manually?

## Phase 2: Multi-OS Awareness

- [ ] Is this change Linux-only, macOS-only, or cross-platform?
- [ ] If cross-platform: did you test the relevant paths?
- [ ] If single-platform: is that documented or obvious from context?

## Phase 3: Multi-Role Awareness

- [ ] Does this change affect other agents? (configs, scripts, crons, docs they rely on)
- [ ] If yes: did you notify them via inbox or update shared docs?

## Phase 4: Documentation

- [ ] Are any docs that reference the changed system updated?
- [ ] Does the commit message explain what changed AND why (not just "fix bug")?
- [ ] If you added a new file: is there a `why-new` rationale?

## Phase 5: Final Verification

- [ ] Run the end-to-end path: deploy, health check, and smoke test
- [ ] Diff the actual output against expected output (not just "looks right")
- [ ] Verify no stale locks remain (`cortex-doctor.py` or `mcp_loop_governance__check_lock`)
- [ ] Are all cycles scored? No PENDING cycles should remain.

## When to Reject

If any Phase 1 check fails → fix first, re-run this checklist.
If Phase 4 is incomplete → fix the docs, don't skip the cycle.
If Phase 5 reveals issues → start a new cycle, don't patch the closure.

## Why This Exists

Without a pre-ship checklist, governance cycles get closed with half-verified work — tests skipped, docs stale, other agents unaware. The change-checklist is the quality gate that ensures every scored change is actually shippable.
