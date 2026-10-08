---
name: change-checklist
version: 2.2.0
category: software-development
description: "Mandatory pre-ship verification before calling end_change(). Covers survey, test, adversarial verify, multi-OS, multi-role, docs, final verification, and reflexion. Every governance cycle must run this before closing."
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [governance, testing, documentation, multi-os, multi-role, quality]
    related_skills: [loop-governance, change-test-loop, two-hard-rules, cron-job-management, survey-before-action, agent-contract]
---

# Change Checklist — Pre-Ship Validation

The easy path (one file, one test) is never the complete path. Ask: what else does this touch? Did the SYMPTOM resolve? Did I check sibling locations? Did I run the doctor? Did I push so the fleet benefits?

Load this before end_change() on any script, deploy-config, cron, shared-doc, or updater change.

## Writing Quality (prompts, docs, skills)

1. **Concrete examples, never abstract placeholders** — show real-looking values (`43 cycles scored`, `$0.006/run`, `2026-07-15 10:01 KST`), not templates (`[N] cycles`, `<cost>`, `<datetime>`). LLMs mimic concrete structure faithfully; they interpret placeholders loosely.
2. **Be concise — every sentence must earn its place.** After writing, review: "Would the agent do anything differently if I deleted this?" If no, delete it.

## Phase 0: Survey the Change Surface (BEFORE begin_change)

- [ ] Pushback Check (3 questions, BEFORE begin_change) — Is this idea wrong (harm, data loss, wrong scope, better mechanism)? Is there a clearly better alternative? If you raised an objection, do NOT begin_change until the user acknowledges (override is final). Silence is not consent (SOUL P5).
- [ ] Foreign working-tree check — git status; another session's in-flight edits block the pre-push dogfood gate. Coordinate — never stash/clean/commit a peer's files (SOUL P9).
- [ ] search_files() for the old name/term across the whole repo.
- [ ] Live cron prompts — grep ~/.hermes/cron/jobs.json for the old term; source edits don't rewrite existing jobs — update each hit via cronjob action='update'.
- [ ] Cron manifest — install-crons.sh AND install-orch-crons.sh: uninstall arrays, create_cron blocks, guards.
- [ ] Updater — cortex-update.sh register() calls.
- [ ] Doctor — cortex-doctor.py parse_expected_crons() / parse_orch_crons() read the uninstall arrays.
- [ ] Deployed path — verify ~/.hermes-cortex/scripts/<script> exists at runtime, not just the repo.
- [ ] Category — orchestrator-only (orch-* in install-orch-crons.sh) vs all-agents (agent-* in install-crons.sh). Update the fleet-reference.md cron table.
- [ ] Install array sync — create_cron block name must match the uninstall array entry EXACTLY. Run python3 ~/hermes-cortex/ops/scripts/manage/fix-cron-duplicates.py (zero issues = in sync).
- [ ] Old cron cleanup — crons don't self-destruct; confirm the old name was removed.
- [ ] Governance lock — after begin_change(), confirm with check_lock.
- [ ] PII scan — bash ~/hermes-cortex/ops/scripts/secret-leak-detector.sh before pushing.

## Phase 1: Test the Change (no simulated output)

- [ ] Scripts — run with real inputs, verify real output. ⚠️ DOGFOOD (enforced): the deployed copy must run its real scheduler invocation — cortex-update.sh then cronjob action='run' job_id=<id>. Manual python3 script.py does NOT update the scheduler's last_status (the doctor reads scheduler status). Run the full command, not an imported function.
- [ ] Config — diff generated vs deployed; only intended changes.
- [ ] Syntax — .sh bash -n; .py py_compile; .yaml yaml.safe_load (hook catches staged files; verify unstaged too).
- [ ] nginx — sudo nginx -t.

## Phase 1.5: Adversarial Verification (MANDATORY — no bypass)

Enforced at 3 layers: pre-commit hook (static gate), enforcer (blocks commit until adversarial-verifier loaded), and this checklist.
- [ ] Static gate on every changed script: python3 ~/.hermes-cortex/scripts/adversarial-verify.py --file <file> --level A2 --gate. A4 for plugins/, hooks/, mcp-servers/, ops/scripts/manage/, cortex_doctor/, quality/, tests/, and enforcement scripts. Critical/high → block. No --no-verify.
- [ ] "0 findings" is NOT a pass — execute the changed path with boundary inputs (-1, 0, None, empty, inf/nan, non-ASCII); attack the premise (list implicit assumptions, violate each with a 30s test); verify deployed == loaded (restart/daemon check for guards/hooks/enforcers).
- [ ] A green check is not evidence until you have seen the assertion RUN. A test
      file with no executable entry point (a pytest-style file with no
      `if __name__ == "__main__":` when pytest is absent) imports, runs NOTHING,
      and exits 0 — so any harness that records `rc=0` scores it PASS. Prove a test
      executed by its OUTPUT, not its exit code, and make the harness REJECT any
      entry it cannot actually run.
- [ ] A test whose verdict depends on WHO invoked it is not a test. A test that
      SPAWNS a process to exercise a component (a server, a CLI, a hook) must
      resolve an interpreter that can actually RUN that component — read it from the
      component's own registration/config — never `sys.executable`, because the
      harness's interpreter usually lacks the component's dependencies: the child
      dies before initialising and the assertion blames the component for the
      harness's choice. Fall back through known-good candidates and FAIL LOUDLY
      when none can run it. Do not hand-roll that candidate list — the fleet ships it as
      `bash ops/scripts/lib/python-with-module.sh <module> <script> [args]` (exit 3 = no
      interpreter can import the module), and the same capability test applies to any
      script that picks its own interpreter (`shell-scripting`).
- [ ] A check that CANNOT RUN is a third outcome — not a pass, not a negative
      result. Give it its own exit code (`3 = could not verify`) and its own message,
      and make every caller dispatch on the code: a gate shaped
      `if ! <check>; then <report the bad thing>; fi` reports a crash AS the bad
      thing, so a host that cannot run the tool is told its artifact is stale.
      Report "cannot check" as exactly that.
- [ ] Test the could-not-verify branch by CONSTRUCTING the failure, never by waiting
      for a host that has it: run the tool with a neutered environment (non-existent
      PATH, HOME and interpreter) and assert the distinct outcome and message. A
      branch exercised only on healthy hosts is untested.
- [ ] A checker that re-implements a GATE's rule must mirror it COMPLETELY — the same
      scope and the same validator — and must never demand an input the gate does not
      require. A check that refuses a case the gate allows is a false alarm, and an alarm
      that fires on a clean run teaches its reader to ignore it; a check that validates a
      WEAKER property than the gate (a verdict string instead of a range binding) passes
      work the gate would refuse. Re-use the gate's own validator rather than writing a
      second copy of the rule — a second, looser implementation is how binding stops
      binding. Before citing the check, run it on a case each way: one the gate allows and
      one it refuses, and assert the distinct outcome AND message for each.
      **Canonicalise what you compare before comparing it**: a short revision never equals
      a full one, so normalise both sides the way the gate does (`git rev-parse`). And when
      an input CANNOT be resolved, return the could-not-verify code rather than an empty
      result — an empty range or empty result reads as "nothing to check" and passes
      silently, which is how a mistyped revision becomes a green tick.
- [ ] A regression test must exercise the DETECTOR, not a live ambient state. A test that
      asserts "the tree is clean" / "the deployed copy matches" / "the queue is empty"
      flaps the moment normal operation dirties it — a pipeline writing a lesson, a peer
      mid-deploy — and a gate that flaps on healthy systems teaches its readers to ignore
      it. Drive the detector with controlled inputs in both directions (one it must report,
      one it must not) and keep the live state out of the assertion.
- [ ] Evidence must be self-consistent: a summary line may never name a file,
      path or count that the artifact it accompanies does not show. A stat built
      from a wider set than the diff beside it is a contradiction a reviewer will
      (correctly) read as fabrication — cite the range you actually show.
- [ ] Maker/checker split — use a different model for verifier vs implementer where quality is critical.
- [ ] Record evidence — finding IDs, boundary inputs, assumptions violated, exit codes. Report "checked X, Y, Z" never "verified clean".

## Phase 2: Multi-OS Compatibility

- [ ] Hardcoded paths → use ${NGINX_DIR}, $HOME/Path.home(), guard /opt/homebrew/ with IS_MAC.
- [ ] OS binaries → systemctl→IS_LINUX; launchctl/brew→IS_MAC; apt/yum/dnf→IS_LINUX.

## Phase 3: Multi-Role Compatibility

- [ ] Process name — pgrep -f cortex-bus misses cortex_bus; check ps aux for the real argv.
- [ ] Hook/enforcer changes — test in a throwaway project repo (git init /tmp/hook-test, set core.hooksPath), since hooks fire in every repo on the host. Confirm fail-closed still blocks.
- [ ] Role matrix — Titus (macOS, no systemd/nginx, many project repos) / Joseph (Linux full stack) / Esther (Linux + orch crons) / Kustos (stricter perms, handle PermissionError). Verify none are broken.
- [ ] Non-orchestrators — no cronjob tool (request via inbox); new crons registered in the install scripts. Message audit: would a non-orchestrator read an output line and try to install an orchestrator-only service? Gate or rephrase.

## Phase 4: Documentation

- [ ] New script → register in cortex-update.sh; cron → add to install script.
- [ ] New skill → SKILL.md + docs/skills-manifest-reference.md if auto-loaded.
- [ ] Path restructure → fix live refs, update ~/.hermes/config.yaml, add compat symlinks, update repo-organization.
- [ ] Agent workflow change → update AGENTS.md / SOUL.md. Doc audit: grep -rn "<feature>" AGENTS.md docs/agent-onboarding.md — zero matches = undocumented.

## Phase 5: Final Verification

- [ ] No dangling leftovers — DECIDE, do not defer. A leftover (uncommitted files, an
      unregistered tool, a stale artifact, an unresolved finding) ends either LANDED or
      with a stated decision backed by a measurement — how many instances already share
      the state, what the alternative costs, what the tool reports. "It is not mine" is a
      description of ownership, an input to the decision, never a resting state: an
      unexamined leftover is exactly what the user has to come back for. Never land a
      peer's IN-FLIGHT edits to satisfy this — decide about them, or report them by path.
      An uncommitted `skills/` (or docs) edit is NOT automatically a leftover to discard:
      content authored on the DEPLOYED copy and never copied back is a STRANDED lesson,
      invisible to the fleet because the deploy's guardrail refuses to overwrite it. Decide
      the direction by CONTENT, never by mtime or `git checkout --`: run
      `python3 ops/scripts/manage/check-skill-drift-parity.py`, then diff repo against the
      deployed copy with the deploy header stripped, and take the deployed side only where
      it is a superset (pure additions, no deletions of repo content).
- [ ] Symptom proof — the specific error/alert/blocker is gone (not just code compiles + doctor passes). Show evidence in the cycle note.
- [ ] Stale expected-list cleanup — removed crons also removed from uninstall arrays (doctor reads them as expected list).
- [ ] Stale bus/state cleanup — delete test bus messages and stale state-file entries before end_change().
- [ ] Doctor clean — python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet (✅ Crons registered / Orch crons / Crons total).
- [ ] Governance scored — feedback_accept() before end_change().
- [ ] Cron-governance compat — if hooks/plugins/enforcer changed, verify the cycle works in a test cron session, then delete it.
- [ ] Pushed — git pull --rebase then git push origin main; verify git log --oneline -1 origin/main shows the commit.
- [ ] Deployed — bash ops/scripts/cortex-update.sh after push (not before).
- [ ] Cron delivery audit — deliver goes somewhere visible (origin/local deliver nowhere from scripts).
- [ ] Timeout audit — deadline ≈ 3× expected worst-case completion.

## Phase 6: Reflexion

Run reflexion-check (7 questions). Score HIGH/MEDIUM/LOW/ZERO. MEDIUM → disclose; LOW/ZERO → fix before delivering. Ask: "What is the most likely thing I got wrong?" (Mandatory for multi-file/service/config changes; 10s mental pass for trivial ones.)

## Anti-Patterns
"I tested it manually" · "agents won't see that message" · "the rest is trivial" · "other OS can wait" · "docs later" · "the hook didn't catch it" · "I'll write a migration script" (the commit IS the migration) · "long sleep" (poll short intervals) · "worked from my repo terminal" (test from the deployed path — Path("") from an unset env var is the classic cron crash).

## Path Patterns by OS

| Purpose | Linux | macOS (arm64) | macOS (x86_64) |
|---------|-------|---------------|----------------|
| nginx config dir | /etc/nginx | /opt/homebrew/etc/nginx | /usr/local/etc/nginx |
| nginx sites dir | sites-available/ | servers/ | servers/ |
| htpasswd file | .hermes-htpasswd | .htpasswd | .htpasswd |
| nginx log dir | /var/log/nginx | /opt/homebrew/var/log/nginx | /usr/local/var/log/nginx |
| Service manager | systemctl --user | launchctl | launchctl |
| Package manager | apt/yum/dnf | brew | brew |
