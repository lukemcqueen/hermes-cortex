# Backlog run — top-task selection record (2026-10-17, orch-bus-worker)

**Purpose.** The close review of cycle 12714 filed `ADV-12714-1` (scope-drift,
medium): a backlog pass must action a **task row** and document *why that row*.
This file is that documentation for the 2026-10-17 pass, committed so the
selection can be judged rather than asserted. Every block below is one command
and its real output.

Run: governance session `cron_1954deb5ad76_20261017_142142`, cycle **12769**.

## 1. Queue census (verbatim)

```
$ docker exec -i mycortex-postgres psql -U mycortex_reader_esther -d mycortex -t -A -F '|' \
    -c "SELECT status, count(*) FROM tasks.tasks WHERE status IN
        ('pending','in_progress','paused','waiting','blocked') GROUP BY status ORDER BY status;"
blocked|2
in_progress|1
paused|18
pending|25
waiting|2

$ ... -c "SELECT priority, count(*) FROM tasks.tasks WHERE status='pending'
          GROUP BY priority ORDER BY priority DESC;"
3|1
2|17
1|7
```

This is the orchestrator's own store only. Fleet rows minted on other hosts are
**not visible here**, so this is not a fleet-wide claim.

## 2. The top row by (priority desc, created_at) has no unblocked slice

Top row = `c579ef95`, priority 3, **kind=story** — a container. Its slices,
verbatim:

```
$ cd ~/hermes-cortex && python3 ops/scripts/manage/task-db.py list --parent c579ef95
511ad057  waiting  3  [cost/3] Continuous cost monitoring        depends on [cost/1]
5e875477  pending  2  [cost/1] Baseline fleet cost               no live spend source
40cb307d  waiting  2  [cost/2] Reduce top cost drivers           depends on [cost/1]
66914fe1  pending  2  [queue/1] Return the 18 session-TTL rows   escalated to Luke
2fc4d871  blocked  1  [queue/3] Populate depends_on              blocked on 8369bc52
```

- **[cost/1]** cannot run as written: the cost-report script and cron were
  retired 2026-10-06 (`docs/evidence/cost-removal-2026-10-06.md`). Producing
  `docs/cost-baseline-2026-09.md` would mean inventing spend numbers — SOUL
  Principle 2. Established by cycle 12714 and re-checked here; unchanged.
- **[queue/1]** was worked to its unattended limit by cycle 12714: all 18 paused
  rows are `source=inbox`, `priority=0`, content ≤130 chars, and the slice's own
  plan forbids unattended cancellation of the junk batch. It now needs a **Luke
  decision**, so re-running it would be a no-op.

So the highest-priority *row* is a story whose every slice is waiting, blocked,
or escalated.

## 3. The next block (KAESA) is blocked on client input, not on me

Priority 2 is ordered by `created_at`; the oldest rows are the KAESA fleet
slices (2026-08-23) — `ca282975` (pre-order landing page), `1e8737fc` (case
study), `82310c5e`/`c711e28d`/… (90-day content sprint). Their story's own first
slice is still pending and is the gate:

```
1d09760f  pending  1  Slice 1 of 6 - KAESA discovery audit: inventory current
                      channels and stack … run stakeholder interview on goals,
                      voice, constraints …
```

A stakeholder interview and a client's live IG/TikTok/YouTube/mailing-list
accounts are not unattended cron actions; dispatching the build slices blind
would be a fleet broadcast with no verified owner. Left pending, reported.

## 4. What was actioned, and why it qualifies

**`f97dcffe` — "Detector gap: stranded-skill detection covers SKILL.md only —
extend `check-skill-drift-parity.py` to SUPPORT files under repo-owned skill
dirs."** It is the first row in the sort order that is a real task row, is
orchestrator-local (a repo change, not a dispatch), and can be finished and
verified unattended. It also unblocks `3cc049e8` (broken skill references, same
class) and decides the 131 files by content, as the row asked.

The premise was verified first, not assumed — the measurement the row cites
(131 files / 386 repo-owned skill dirs) reproduces exactly:

```
$ python3 <probe: deployed file, no repo counterpart, ancestor carries a repo SKILL.md>
repo-owned skill dirs: 386
deployed-only files under repo-owned skill dirs: 131

$ python3 <probe: does the path exist in repo history?>
orphans: 131
path once existed in repo history (deleted residue): 6
path never in repo history (deployed-only): 125
```

The six `dropped-from-repo` paths are the class `3cc049e8` describes:

```
devops/llm-cost-optimization/references/fleet-cost-data-sources.md
devops/llm-cost-optimization/references/interactive-session-cost-state-db.md
devops/llm-cost-optimization/references/session-telemetry-reporting.md
devops/codebase-portability/references/gbrain-wrapper-crossplatform.md
devops/sensor-false-positive-remediation/references/gbrain-health-false-positive.md
software-development/role-gating-and-public-moderation/references/rgm-fastapi-example.md
```

The 125 `never-committed` files are dangling routes: the repo's own `SKILL.md`
links to them, e.g.

```
$ grep -n "references/b2b-paid-playbook.md" skills/ads/SKILL.md
50:| B2B strategy, funnel stages, budget splits, kill rules, lead quality, breakeven math | [b2b-paid-playbook.md](references/b2b-paid-playbook.md) | Demand lifecycle, leading/lagging signals, kill rules, offline conversion loop, U/B/F lead scoring, scaling quadrant |
$ ls skills/ads/
SKILL.md
$ ls ~/.hermes/skills/ads/references/ | head -3
abm-playbook.md
ad-copy-templates.md
audience-targeting.md
```

### The change

`survey()` now distinguishes two classes instead of filing both as "Hermes
default": a deployed file with **no repo counterpart** is OURS when an ancestor
directory carries a repo `SKILL.md` (`_repo_owned_skill_dir`), and is reported as
`dropped-from-repo` (the path is in repo history) or `never-committed`
(`_path_in_history`). The verdict FAILs on either class, so the condition is a
gate, not prose (SOUL P6). Recovery is deliberately **not** part of this cycle —
the doctor's own hint is that recovery is its own governed change.

### Verification (verbatim)

```
$ python3 ops/scripts/manage/check-skill-drift-parity.py
| Measure | Value |
|---|---|
| Stranded in place (path in repo, content only deployed) | 6 |
| Absent from the repo (deployed under a repo-owned skill) | 131 |
|   ↳ path dropped from repo history | 6 |
|   ↳ path never committed | 125 |
| Files in sync | 835 |
| Skipped (Hermes defaults, or repo ahead) | 498 |
**Verdict: FAIL**
```

`Skipped` fell 629 → 498, exactly the 131 reclassified — the change moved files
between classes and invented none.

```
$ bash tests/run-tests.sh tests/test_skill_drift_parity.py tests/test_capture_evidence_readonly.py -q
tests/test_skill_drift_parity.py .                                       [ 12%]
tests/test_capture_evidence_readonly.py .......                          [100%]
============================== 8 passed in 10.02s ==============================
run-tests.sh: interpreter=$HOME/.hermes-cortex/venv/bin/python3 rc=0  (home path redacted per repo PII policy)
```

The parity test now exercises the new class in **both** directions — a support
file under a repo-owned skill dir is reported, a file under a skill the repo does
not own stays skipped — so the class cannot swallow Hermes defaults.

```
$ bash ops/scripts/manage/run-skill-parity-verify.sh
**Verdict: PASS**
rc=0
```

The repo's own A4 adversarial gate passes on both the checker and its test.

## 5. Left open (reported, not silently dropped)

- `c579ef95` / `5e875477` [cost/1] — no live spend source; blocked as §2.
- `66914fe1` [queue/1] — needs a Luke decision on the 18 paused rows (§2).
- `2fc4d871` [queue/3] — blocked on `8369bc52` (no `depends_on` update surface).
- The **125 dangling routes** and the **6 dropped-from-repo** files are now
  measured but not recovered: recovery is its own governed change
  (`reconcile-stranded-skills.py`, report first).
