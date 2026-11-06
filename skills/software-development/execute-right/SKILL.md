---
name: execute-right
version: 0.1.0
category: software-development
description: >-
  Execution contract: real work, honest results, verified outputs, survey
  before creating, extend-don't-rebuild, and the TDD Iron Law (absorbed
  agent-contract + survey-before-action + prove-before-create +
  test-driven-development). Load before ANY file create/modify.
pinned: true
aliases:
  - agent-contract
  - survey-before-action
  - prove-before-create
  - test-driven-development
  - cortex-preflight
related_skills:
  - task-orient
  - verify-and-ship
  - shell-scripting
  - codebase-design
---

# Execute Right — Real Work, Real Evidence

The non-negotiable rules of doing the work. Route (`task-orient`) → execute
(this file) → verify (`verify-and-ship`).

## Execution rules (NON-NEGOTIABLE)

1. **Do real work** — use tools, never simulate outputs/reads/tests/edits.
2. **Inspect before acting** — read actual files, never guess.
3. **One change at a time** — never batch unrelated edits.
4. **Verify with real commands** — never claim success without evidence.
   A stated claim is a promise: show the output.
5. **Test FIRST (TDD Iron Law)** — no production code without a failing test
   first. A test written after the code passes immediately and proves nothing.
6. **Never ask "do you want tests?"** — testing is mandatory.
7. **Push only through a governed cycle** — begin_change → work →
   feedback_accept → end_change → deploy → push. Integrate a peer's push with
   `git merge`, never a rebase (the range's review receipt is tied to those
   commits).
8. **Follow repo conventions** over generic advice. **Keep context lean** —
   load only needed skills.
9. **Stop before destruction** — approval for data loss, security risk,
   privilege escalation. Once something is blocked, never rephrase or retry it
   toward the same outcome — switch to a non-destructive equivalent.
10. **Protect secrets + auth** — never expose, never weaken.
11. **Proactively fix pre-existing issues** — fix discovered bugs even if you
    didn't cause them; skip only destructive fixes needing approval.
12. **Never ask permission for obvious fixes** — fix first, report after.
    Once a SET of work is authorised, pick the order by what unblocks most,
    say it in one clause, start — don't hand the sequencing back.
13. **Cron fixes run through the scheduler** — `python3 script.py` does not
    update the cron scheduler's status; run the cron, confirm the doctor clears.
14. **No PII in the repo** — placeholders only; the PII gate also rejects what
    it can't distinguish from PII (epoch-style ids, surnames) — rewrite the
    VALUE, never delete the field.
15. **Test end-to-end before declaring done** — watch RED → GREEN for every
    change. A passing test file is not coverage until a runner actually runs
    it: grep the runner's own list for its path.
16. **Extension points before core patches** — plugin, config, hook, external
    provider, wrapper, in that order, before a local core patch (which is lost
    on every update). Never patch upstream; upstream fixes go as a PR.

## Survey before action (mandatory pre-flight)

Run BEFORE writing any file, adding a cron, creating a skill, or modifying a
resource. This runs after loading always-skills + classifying, but BEFORE
`begin_change` — you can't know what to lock before you know the domain.

**Phase 0a — load domain skills (operation × extension):**
Operation axis: cron → `cron-job-management`; shell/deploy script →
`shell-scripting`; nginx → `nginx-web-app-deployment`; docker →
`docker-management`; tests → `test-driven-development`; debugging →
`root-cause-debugging`; install packages → `package-security`; create skill →
`hermes-agent-skill-authoring` + `pii-scrubbing`; documentation →
`documentation-auditing` + `doc-freshness`; security change →
`linux-server-hardening`; CI/CD → `ci-cd-pipeline`; MCP server →
`mcp-server-building`; credentials → `secure-credential-handling`.
Extension axis: `.sh` → `shell-scripting`; `.py` module → `codebase-design`;
`.py` one-shot → `error-handling`; nginx → `nginx-web-app-deployment`; `.env`
→ `pii-scrubbing`; Makefile → `project-run-scripts`.
Discovery fallback (always): `skills_list(category=...)` for the domain +
load any `related_skills` a loaded skill names. A skill you never load can
never save you.

**1. Search for existing resources — 3+ different terms.** One search is not
a survey; if nothing matches term-1 you haven't proven the gap. Batch:
`search_files` over the repo + deployed trees, `skills_list()`, cron list.
**2. Examine & decide:** 100% overlap → use as-is; 80%+ → patch the existing
tool; 50–80% → refactor/extend; <50% → create new and document why in the
commit.
**3. Before deleting/renaming:** present the plan and wait for confirmation;
make old names discoverable (aliases/tags, "formerly known as" comment, both
names in the commit message); verify the target exists before patch/write.

**Prove-before-create — extend, don't rebuild.** The most expensive mistake is
creating a new file when an existing one could be extended: every new file is
debt that compounds. When a skill matches, load it and check its `references/`
dir — it may contain the ready-to-use solution. Wire the capability that
exists: add a CLI entrypoint, add the `--json` flag, add the register() call —
a flag costs 1/10th the debt of a parallel system. If you still create new,
document in the commit: terms searched, what was found and why it didn't fit,
minimum viable scope. **Name the file at the CLASS level**, never after a
session artifact (`circuit-breaker.py` right; `fix-registry-timeout.py`
wrong). Violation classification: fragmentation, review time, merge conflicts,
canonical-ambiguity — compounds with every file.

**Repo-specific pre-flight:**
1. git vs disk — a file may exist in git but not deployed (`git show HEAD:<path>`);
   deploy with cortex-update.sh.
2. Governance files (hooks, enforcer, skills): fix the REPO SOURCE in
   `~/steadfaste-fleet/` first, commit/push, then cortex-update.sh — a fix to
   the deployed copy is overwritten on next update.
3. Hermes boundary: in `~/steadfaste-fleet/` → ours; in `~/.hermes/` AND repo
   skills/ → edit repo copy + deploy; in `~/.hermes/` NOT in repo → Hermes
   default, don't touch; `~/.steadfaste-fleet/state/*` → live state, edit
   directly. `~/.hermes/config.yaml` is security-sensitive — change it with
   `hermes config set <dotted.key> <value>`, never a raw shell write.
4. Foreign working-tree check — git status; never stash/clean a peer's work.
5. Agent type — orchestrator (Moses/Esther): fleet/bus; server-agent: local
   maintenance; dev-agent: local reports.

## TDD — the Iron Law

**NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.** Write code before the
test? Delete it. Start over. If you didn't watch the test fail, you don't know
it tests the right thing.

RED → verify it fails for the RIGHT reason → GREEN (minimal code, cheating is
OK — refactor cleans it) → verify GREEN (specific test + full suite, no
regressions) → REFACTOR (green only, no behaviour added). One behavior per
test, one vertical tracer-bullet slice per cycle — never all tests then all
implementation. Exceptions (ask first): throwaway prototypes, generated code,
config files. "Just this once" is rationalization.

Test names are CLAIMS, not evidence: a name asserting a COMPARATIVE property
(worst/best/first/last) needs the discriminating pair in the fixture — run the
test against the PRE-FIX code and see the assertion FAIL, or the name overclaims.

In repos with gates: assert the RETURN CODE of a process-driven subject, not
only its output (a content-only assertion stays green across a crash; give
"could not run" its own distinct code). A test file must be INERT ON IMPORT
(no module-level work/`SystemExit` — it kills pytest collection for the whole
suite). A check that CANNOT RUN is a third outcome (code 3 = could not verify),
not a pass. A test whose verdict depends on WHO invoked it (ambient HOME/env)
must derive its paths from the repo under test instead. Save and restore every
env var a test mutates. A regression test drives the DETECTOR with controlled
inputs in BOTH directions — never a live ambient state (it flaps).

## Report format (MANDATORY)

```md
## Result        — what changed
## Files changed — path: purpose
## Verification  — command: result
## Unverified    — anything not tested
## Notes         — risks, follow-ups
```

Reporting order — **defects outrank ceremony**: lead with what is BROKEN or
unproven; process items go last. "Fixed" is a claim that requires a test
failing without it — otherwise write "code changed, unverified". When asked
what is left, answer with the INVENTORY (blocking state → known defects →
unverified → owed), never the wins. Plain words, no history. A direct question
gets the direct answer in the FIRST word. A BLOCKAGE IS WORK, NOT A STATUS:
fix the gating tooling, or report the ONE action that clears it.

## Stop when

Requirements unclear | verification can't run | destructive action (needs
approval) | dependency/tool missing | scope exceeds safe bounds.

## Anti-patterns

Guessing | multi-change | skip verify | mask failures | "should work" |
simulate outputs | code before understanding | test-after-code |
commit-without-red-green | core-patch-first | parallel systems | "I'll search
later".
