---
name: change-checklist
version: 2.3.0
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
- [ ] **Name the cycle for the diff it will CONTAIN, not the instruction that started it.** A task id that under-describes the work fails the close on scope drift no matter how good the evidence is: the reviewer sees the real range and refuses a cycle whose name does not cover it. An instructed next step ("pull latest and update", then a follow-on reconciliation the update itself demanded) belongs in its OWN correctly-named cycle — do not fold a derived deliverable into the parent's cycle. Check before begin_change: does `<task_id>` describe every path the range will touch? If not, split it. (Cost of getting this wrong: cycle 12012 was refused four times and held a 60-minute TTL wait; the identical work closed CLEAN on the first attempt under a correctly-named cycle.) Recovery for an already mis-framed cycle: retire it through the state machine (`advance_task_state` → `cancelled`, reason logged, no override) and open a correctly-named one — never `force`/override.
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
- [ ] Governance lock — after begin_change(), confirm with check_lock. **Pass the session context:** a bare `check_lock()` with no args cannot resolve the session and reads a FALSE "inactive" while your lock is live — the enforcer then blocks the very next write. Trust the lock FILE (`ls ~/.hermes-cortex/state/.governance-*.json`) over a no-arg reading, and when the two disagree, the file is right and your close is still permitted. (Observed 2026-10-10: a no-arg `check_lock` reported inactive, the operator-visible file was active, and the close then succeeded — the false reading had nearly cost a needless re-acquire and a second cycle.)
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
      entry it cannot actually run. **A duplicated definition is a silent disarm**: Python
      keeps the LAST `def main()`, so a file carrying two of them runs the second and leaves
      the first — and every check only it contained — dead, with the suite still green.
      Assert the definition is unique (or assert the property directly) so the duplicate
      cannot come back.
- [ ] **A captured check transcript must carry its EXIT CODE and its WARNING COUNT — a bare
      PASS line is a swallowed error.** A gate that prints `✅ PASSED` while emitting N warnings
      and an unresolved sub-check reads as a clean system to everyone downstream, including the
      close reviewer, which files it as exactly that. Capture `rc=$?` beside the command, record
      the warning count, and write the measured numbers into the evidence — including the ones
      that are NOT clean ("rc=0 with N warnings and unresolved X" beats a PASS line with the
      warnings omitted). A transcript with the counts absent is not evidence: the reader cannot
      tell a clean run from a skipping one, and a summary line claiming cleanliness the
      transcript contradicts is a fabrication finding.
- [ ] **Never commit a query's output without first seeing it return rows.** Proof of a
      disposition ("recorded as this issue", "promoted to a task") must be the store's ACTUAL
      row: run the query, confirm it returns the row, then commit that. Commit a traceback or an
      empty section and it proves nothing — and because the reviewer reads the DIFF, a later
      correction of that same passage can keep reading as the broken version. List the store's
      tables before writing the query (`SELECT name FROM sqlite_master WHERE type='table'`):
      store table names are not guessable, and a task store may not be a file DB on the host at
      all — capture what the tool itself returns instead.
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
- [ ] When a component cannot RUN because a dependency is missing, INSTALL it (age-gated via
      `ops/scripts/health/check-package-age.py <mgr> <pkg>`) rather than teaching every
      caller to route around it. A workaround fixes the one call site you were looking at
      and leaves the component broken for the next caller — and the missing dependency is
      usually why the failure looked unrelated in the first place. Pin and match a version
      already proven on this fleet.
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
      silently, which is how a mistyped revision becomes a green tick. The same bite hits a
      CONTENT digest: normalise trailing newlines and whitespace before hashing a file, or a
      byte-identical copy fails the comparison by one `\n` and looks like real drift.
- [ ] A regression test must exercise the DETECTOR, not a live ambient state. A test that
      asserts "the tree is clean" / "the deployed copy matches" / "the queue is empty"
      flaps the moment normal operation dirties it — a pipeline writing a lesson, a peer
      mid-deploy — and a gate that flaps on healthy systems teaches its readers to ignore
      it. Drive the detector with controlled inputs in both directions (one it must report,
      one it must not) and keep the live state out of the assertion.
- [ ] When a heuristic warning is noisy, tighten its TRIGGER — do not add an exemption list.
      A check that cannot tell the case it exists for from a deliberate long-standing state
      fires on every instance of the latter, and the reader learns to scroll past it. Scope
      the condition to the case itself (`git diff --cached --name-only --diff-filter=A` —
      only NEWLY ADDED files), which removes the noise and keeps the real case; an
      allow-list of known-good paths instead drifts out of date and the noise returns with
      the next legitimate tool.
- [ ] Test the warning BOTH ways before trusting it: the case it must report, and the case it
      must now stay silent on. A warning verified only in the reporting direction cannot show
      that the noise is gone; verify only in the silent direction and you may have deleted the
      check. (`shell-scripting` has the extraction pattern for driving one block of a large
      script this way; `tests/test_updater_robustness.py` is a worked exemplar.)
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
- [ ] Doctor clean — python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet
      (✅ Crons registered / Orch crons / Crons total). Record its EXIT CODE and warning count,
      not just the ✅ lines: a non-zero rc with warnings is NOT a clean doctor, and reporting it
      as one is the failure the close review catches.
- [ ] Governance scored — feedback_accept() before end_change().
- [ ] Cron-governance compat — if hooks/plugins/enforcer changed, verify the cycle works in a test cron session, then delete it.
- [ ] Deploy, THEN push — that order, with nothing committed in between. The pre-push path
      itself runs pull → deploy → doctor → verify, and the gate reads `Deploy sync`, so any
      commit made after a deploy leaves the deployed tree trailing HEAD and blocks the push.
      Run it as one step: `bash ~/.hermes-cortex/scripts/cortex-dogfood.sh --force` and then
      `git push origin main`. A close-time review receipt is bound to the
      RANGE, and the gate accepts it when the receipt's reviewed blobs COVER every blob that
      range changes — so a rebase that rewrites the tip of identical content no longer
      invalidates a review of that content (a tip-equality rule is exactly what a shared
      checkout breaks). A further COMMIT that adds unreviewed content still invalidates it:
      the deploy is the LAST step, not a mid-task refresh. The Deploy-sync check is scoped the
      same way — compare only the deploy-map files changed in the range, so a peer's unrelated
      commit cannot block your push, while an undeployed deploy-map file still FAILs and is named.
- [ ] Integrate a peer's work by MERGE, never `git pull --rebase`. A rebase rewrites the
      peer's unpushed commits and their authorship, and it refuses outright when another
      session holds unstaged files — which you must never stash. A merge needs neither and
      keeps every commit identity on the shared branch.
- [ ] **Scope every gate that runs on a shared checkout to CONTENT, not to the tip.** Two
      gates were tip-coupled and each blocked a push whose content was in fact fine: the
      review receipt (bound to tip+base) and the Deploy-sync check (keyed on the revision
      alone). Both now compare what the range CHANGES — receipt blobs, and the deploy-map
      files touched in the range — with ONE shared implementation of the rule
      (`review-receipt-check.py`) called by the hook, the verifier and the tests. Coverage,
      not equality: a range that GAINED an unreviewed file must still refuse, and a receipt
      with no blob list is only ever accepted by exact tip+base. A peer commit landing inside
      the pushed range is genuinely unreviewed and still refuses — correct, not a bug to widen
      away.
- [ ] **Never `git commit --amend` while a peer may be working in the tree.** `--amend`
      rewrites whatever HEAD is *now*, not "your" commit: a sibling commit that landed since
      you started becomes the target, folding THEIR files into YOUR message and stripping
      their authorship. Before amending, assert HEAD is the commit you created
      (`git log -1 --format='%h %s'`); if it is not, commit your paths as a NEW commit.
      Recovery if you already amended theirs: `git reflog` to find the peer's SHA,
      `git reset --soft <peer-sha>` to restore it verbatim (message and all files), then
      re-commit only your staged paths — never `reset --hard`, which discards their work.
- [ ] **A plain `git commit` commits the WHOLE index — a peer's already-STAGED files ride into
      your commit.** `git add <your paths>` does not unstage theirs, so the commit captures
      whatever is staged at that moment, under YOUR message and authorship. Commit by
      pathspec every time — `git commit -F <msgfile> -- <your paths...>` — and assert the set
      first with `git diff --cached --name-only`. Recovery if it already happened:
      `git reset --soft HEAD~1` (keeps every file and the message), then re-commit with the
      pathspec. Never `reset --hard`, and never unstage or discard a peer's paths to tidy up:
      their staged work is theirs to land.
- [ ] A close-review window is `base..HEAD`, so a **peer's commit landing mid-cycle shows up
      as scope drift in YOUR range**. Name the peer's SHA in the cycle note and leave their
      work untouched; reverting another session's commit to green your gate is the same
      violation as the amend above.
- [ ] Verify the landing rather than assuming it: `python3 ops/scripts/manage/verify-landed.py
      --repo . --base <previous tip>` asserts a CLEAN receipt for the tip, that every changed
      deploy-map file matches its deployed copy, and that `origin/<branch>` equals the tip.
      Exit 0 / 1 (a real mismatch, named) / 2 COULD NOT VERIFY — a partial check is not a pass.
- [ ] **Ship the automation and its evidence INSIDE the repo — a host-local script, a cron job, or a
      session transcript is not a deliverable.** Verification that lives only in the deploy dir, a
      state dir, or the operator's chat cannot be read or re-run by the next agent or the close
      reviewer, which correctly files it as an unverified claim and refuses the close. Put the
      reusable logic in a registered script (deploy-map entry + a hermetic case in a `tests/` runner
      that actually executes it), keep only the host-specific values in a thin `local-`-prefixed
      wrapper, and commit the measured transcripts (each command beside its real output, with exit
      code and warning count) under `docs/evidence/`. When the work is a watcher for a deferred
      landing, commit its contract too — the automation has to outlive the session that wrote it.
- [ ] Pushed — `git log --oneline -1 origin/main` shows your commit.
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
