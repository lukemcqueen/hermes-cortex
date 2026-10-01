# Agent Session Lifecycle — What a Working Session Looks Like

> **For a new agent (or a human) asking "what does a normal HC session actually do?"**
> Connecting to the fleet is [`agent-onboarding.md`](agent-onboarding.md). This is
> the *working* session: the gates you will hit, the exact calls, and the failure
> modes that have cost real time.
>
> Where a rule exists because something broke, the breakage is named.

---

## The shape of one unit of work

Governance wraps every change in a fixed order. There is no step to invent.

```
skill_view('task-start')        ← always first; it bundles everything below
  cache_search(query)           ← what did past cycles learn about this?
  begin_change(task_id, desc)   ← opens a cycle, writes a lock
  … load skills, do the work …
  adversarial-verify.py --file X --level A2|A4
  git commit                    ← the hook chain runs here
  git push                      ← the doctor + dogfood gate runs here
  feedback_accept(cycle_id, scores, note)
  end_change(task_id)           ← releases the lock
  verify the DEPLOYED path
```

One lock, one cycle, one logical change. **Do not stack several pieces of work
under one lock** — see the last gotcha, the most expensive lesson here.

---

## 1. Session start — the two gates

Write tools are blocked by two **independent** gates. Fixing one does not satisfy
the other; a second block after the first is expected, not a malfunction.

| Gate | Message | Fix |
|---|---|---|
| 1 — skills | `session skills not fully loaded (N/7)` | load the 7 always-skills, all in ONE turn |
| 2 — lock | `GOVERNANCE LOCK REQUIRED` | `begin_change(task_id=…, description=…)` |

The block message names its gate and the exact call. Read it and do that — do not
go source-diving into the enforcer to work out how governance works.

**Skill credit is per session** and survives a deploy as long as the skill file's
content did not change. After a **gateway restart**, load all 7 again in one turn.

### Read-only is not the same as lock-free

For `terminal`, `ls | grep foo` and `git status && git log --oneline` are read
primitives and run without a lock. Anything containing an interpreter, a
redirection, or a subshell — including `python3 -c "…"` and `python3 script.py`
inside a governed repo — is **write-class** and needs the lock. When you only need
to inspect, prefer `read_file` / `search_files`: those are never gated.

---

## 2. While you work

- Read before you write. `search_files` before creating anything — extend an
  existing script/doc/skill rather than adding a second implementation.
- `~/hermes-cortex/` is ours. `~/.hermes/` files that are not in the repo are
  Hermes-owned: don't touch them. `~/.hermes-cortex/state/*` and
  `~/.hermes/config.yaml` are live config.
- Identity is host-derived (`moses`/`esther`), never from `AGENT_ID`/`AGENT_TYPE`.
- Never print secrets. `$(cat <file>)` in a subshell only.

---

## 3. Pre-commit — the adversarial gate

```bash
python3 ops/scripts/quality/adversarial-verify.py --file <changed> --level A2 --gate
# A4 for plugins/, hooks/, mcp-servers/, ops/scripts/manage/, tests/,
# ops/scripts/quality/, cortex-update.sh, pre-commit-score
```

Critical/high findings **block**. Fix them with real handling; an inline
`# adversarial-ignore:` exists but suppressing a HIGH is the wrong instinct.

A **static scan returning 0 findings is not a pass** — it does not execute the
code. Also run the changed path with boundary inputs (empty, `None`, negative,
unicode, injection-shaped strings).

---

## 4. Commit — the hook chain

The hook is **global** (`core.hooksPath`), so it fires in every repo on the host:

syntax → docs audit → secret/PII scan → TDD gate (new production code needs a test
in the same commit) → **reflexion gate** → adversarial → score-cycle.

- `--no-verify` is **logged** by the sentinel and counts against a bypass budget.
- **Reflexion gate**: the commit must prove this session loaded `reflexion-check`.
  It asks HC's own session/memory store (`mycortex_mem.tool_events`), keyed by the
  governance lock's `session_id`. Hermes sessions record automatically (the enforcer
  plugin writes a row per `skill_view`); any other harness calls
  `cortex-context.py session_tool_event` with its `session_key`.
  Exit codes: `0` loaded, `1` not loaded, `3` store unreachable — **all non-zero
  refuse**. A gate that passes when it cannot verify is not a gate.

---

## 5. Push — the doctor and dogfood

The pre-push gate runs the doctor. If deployed state ≠ repo source (i.e. you changed
anything `cortex-update.sh` deploys), the push is **rejected** until you run:

```bash
bash ~/.hermes-cortex/scripts/cortex-dogfood.sh --force   # pull → deploy → doctor → verify
```

Then push, and verify the **deployed** copy afterwards — a committed file is not a
running service.

> One caveat that bites: `cortex-update.sh` purges governance locks at the end of
> its run, including yours. Be ready to re-acquire with `begin_change` and to score
> any PENDING cycles before `end_change`.

---

## 6. Close-out — scoring and the adversarial review

```
feedback_accept(cycle_id=…, completeness=…, quality=…, progress=…, note="…")
end_change(task_id=…)
```

A bare note is refused: pass scores, or an explicit `unscored_reason`. `end_change`
refuses while the cycle is unscored.

**Complex changes are reviewed before closing.** Complexity is measured from the
actual diff (≥50 lines or ≥3 files, or any always-review path), never self-reported.
The reviewer runs with a **different model** and its verdict is durable:

- **CLEAN** → the close proceeds.
- **FINDINGS** → the close is refused. Fix the findings, then call
  `rereview_change` with a **NEW** note (an unchanged note is refused: re-review
  exists to re-judge a *fixed* change, not to re-roll a verdict).

A verdict is stored **once per cycle**, pinned by a fingerprint of the material it
judged (note + diff). A CLEAN is reused while that material is unchanged; material
that moved after a review is judged again.

---

## 7. Gotchas that cost real time

| Symptom | Cause | Fix |
|---|---|---|
| `No active governance lock` from the CLI | the CLI is a **subprocess** with no harness session, so it cannot resolve your lock | pass `session_id` in the payload — the documented priority-0 override |
| A commit-message phrase vanished | **backticks in a shell-quoted message** — bash ran them as command substitution | single-quote the message, or avoid backticks |
| A command is blocked, mentioning a `.db` you never named | the lifecycle guard scans scripts your command references, and a binary DB cannot be scanned as a script | don't name the Hermes conversation DB in a command; edit with file tools instead |
| The reviewer calls your evidence "unverifiable self-report" | you pasted test output into your closing **note**; the reviewer sees the note and the diff and cannot re-run your terminal | put the proof **in the repo** as a runnable test; the note describes the change |
| A complex cycle will not close however much you fix | the lock's **description** no longer matches the diff window — work was stacked under one lock | one lock per logical change; if it already happened, the orchestrator must clear the cycle |

The last one is the most expensive: a cycle whose locked description no longer
matches its diff cannot converge, and a lock description must never be hand-edited.

---

## Quick reference

| Action | Call |
|---|---|
| Start work | `begin_change(task_id=…, description=…)` |
| What past cycles learned | `cache_search(query=…)` |
| List open cycles | `cycle_query(status="pending")` |
| Score + close | `feedback_accept(…scores…)` → `end_change(task_id=…)` |
| Re-judge a fixed change | `rereview_change(task_id=…, note=<NEW note + evidence>)` |
| Commit-hook gate | automatic (`core.hooksPath`) |
| Deploy + verify | `bash ~/.hermes-cortex/scripts/cortex-dogfood.sh --force` |
| Full health | `python3 ops/scripts/manage/cortex-doctor.py` |
