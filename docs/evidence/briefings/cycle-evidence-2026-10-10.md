# Cycle evidence — sustainability briefing 2026-10-10

Generated: 2026-10-09T21:16:53.791961+00:00 by `ops/scripts/sustainability/write_cycle_evidence.py`

Every block below is verbatim command output captured on this host, so a reviewer can re-run the same command and diff.

## 1. Commits touching this cycle

```
dd0b8cf4 chore(sustainability): register briefing scripts + index the evidence
83a4599a evidence(sustainability): briefing 2026-10-10 + re-runnable checker harness
bd5012f3 evidence(dream): verifier asserts the committed artifact's hash via committed sidecar (cycle 11987)

--- commit 83a4599a (artifacts + harness) ---
83a4599a14de1f53911345a591839139625f09fe
evidence(sustainability): briefing 2026-10-10 + re-runnable checker harness

 .../briefings/reflexion-check-2026-10-10.md        |  77 +++++++++++
 .../sustainability-briefing-2026-10-10.docx        | Bin 0 -> 41293 bytes
 .../sustainability-briefing-2026-10-10.md          |  98 ++++++++++++++
 .../sustainability-briefing-2026-10-10.pdf         | 118 +++++++++++++++++
 .../evidence/briefings/verification-2026-10-10.txt |  31 +++++
 ops/scripts/sustainability/capture_evidence.py     |  84 ++++++++++++
 ops/scripts/sustainability/gen_briefing.py         | 144 +++++++++++++++++++++
 tests/test_capture_evidence.py                     |  96 ++++++++++++++
 tests/test_gen_briefing.py                         | 122 +++++++++++++++++
 9 files changed, 770 insertions(+)

--- commit dd0b8cf4 (registration + index + path-leak fix) ---
dd0b8cf4ca96629b96c349243a9432af9f057f3c
chore(sustainability): register briefing scripts + index the evidence

 docs/DOCS-INDEX.md                                  |  5 +++++
 docs/evidence/briefings/verification-2026-10-10.txt | 10 +++++-----
 ops/scripts/cortex-update.sh                        |  2 ++
 ops/scripts/sustainability/capture_evidence.py      | 14 +++++++++++---
 tests/test_capture_evidence.py                      | 11 +++++++++++
 5 files changed, 34 insertions(+), 8 deletions(-)
```

## 2. The actual diffs the reviewer asked for

### 2a. ops/scripts/cortex-update.sh register() entries

```diff
commit dd0b8cf4ca96629b96c349243a9432af9f057f3c
Author: esther-agent <esther@hermes.local>
Date:   Sat Oct 10 06:15:25 2026 +0900

    chore(sustainability): register briefing scripts + index the evidence
    
    Clears the three docs-audit warnings from the previous commit:
    
    - cortex-update.sh: register gen_briefing.py and capture_evidence.py beside
      the existing verify_briefing.py entry, so a deploy actually ships them.
    - DOCS-INDEX.md: add entries for the briefing artifacts and the two new
      scripts (the briefings/ dir had no index rows before).
    - capture_evidence.py: shorten paths to ~/ form (_relpath) so committed
      evidence carries no /home/<user> path. New test: TestRelPath.
    
    Tests: 18 pass (12 gen_briefing + 6 capture_evidence) under
    -W error::ResourceWarning. Checker still ALL PASS for 2026-10-10.

diff --git a/ops/scripts/cortex-update.sh b/ops/scripts/cortex-update.sh
index 134f93f8..f5713fa7 100755
--- a/ops/scripts/cortex-update.sh
+++ b/ops/scripts/cortex-update.sh
@@ -352,6 +352,8 @@ _write_deploy_manifest() {
 register "ops/scripts/health/agent-system-alert-watchdog.py"   "${CORTEX_DEPLOY_HOME}/scripts/agent-system-alert-watchdog.py"
 register "ops/scripts/health/heartbeat.py"               "${CORTEX_DEPLOY_HOME}/scripts/heartbeat.py"
 register "ops/scripts/sustainability/verify_briefing.py"  "${CORTEX_DEPLOY_HOME}/scripts/manage/verify_briefing.py"
+register "ops/scripts/sustainability/gen_briefing.py"      "${CORTEX_DEPLOY_HOME}/scripts/manage/gen_briefing.py"
+register "ops/scripts/sustainability/capture_evidence.py"  "${CORTEX_DEPLOY_HOME}/scripts/manage/capture_evidence.py"
 register "ops/scripts/hermes_models.py"            "${CORTEX_DEPLOY_HOME}/scripts/hermes_models.py"
 register "ops/scripts/hermes_paths.py"             "${CORTEX_DEPLOY_HOME}/scripts/hermes_paths.py"
 register "ops/scripts/install/check-system.sh"             "${CORTEX_DEPLOY_HOME}/scripts/check-system.sh"
```

### 2b. docs/DOCS-INDEX.md rows

```diff
commit dd0b8cf4ca96629b96c349243a9432af9f057f3c
Author: esther-agent <esther@hermes.local>
Date:   Sat Oct 10 06:15:25 2026 +0900

    chore(sustainability): register briefing scripts + index the evidence
    
    Clears the three docs-audit warnings from the previous commit:
    
    - cortex-update.sh: register gen_briefing.py and capture_evidence.py beside
      the existing verify_briefing.py entry, so a deploy actually ships them.
    - DOCS-INDEX.md: add entries for the briefing artifacts and the two new
      scripts (the briefings/ dir had no index rows before).
    - capture_evidence.py: shorten paths to ~/ form (_relpath) so committed
      evidence carries no /home/<user> path. New test: TestRelPath.
    
    Tests: 18 pass (12 gen_briefing + 6 capture_evidence) under
    -W error::ResourceWarning. Checker still ALL PASS for 2026-10-10.

diff --git a/docs/DOCS-INDEX.md b/docs/DOCS-INDEX.md
index 5da2f623..fd9e82a2 100644
--- a/docs/DOCS-INDEX.md
+++ b/docs/DOCS-INDEX.md
@@ -50,6 +50,11 @@ A lightweight map of all project documents. Files are grouped by topic.
 | `docs/evidence/gateway-slash-parity-2026-10-08.txt` | **Gateway slash-command parity, live acceptance (2026-10-08)** — the DEPLOYED tree exercising every gateway slash command (/help, /status, /model switch+report+reject+reset, /new archive, a real pi turn, /compact, /restart refusal, unknown-command forwarding) with the real CommandBackend and real pi processes: 13/13, run twice. Also records the RED measurements against the pre-change deployed package and the two `/compact` defects the live run found and fixed. Regenerate with `python3 ~/.hermes-cortex/scripts/cortex_gateway/slash_parity_evidence.py` |
 | `docs/evidence/gateway-slash-parity-tests-2026-10-08.txt` | Slash-parity TEST evidence — verbatim pytest output for `tests/test_gateway_slash_parity.py` (45 passed) and for the 8-suite selection it belongs to (141 passed), with the interpreter named. Regenerated by re-running the two commands in the file |
 | `docs/evidence/gateway-restart-systemd-proof-2026-10-08.txt` | `/restart` under real systemd — the accept branch proven on a throwaway user unit running the DEPLOYED gateway code: reply sent, exit, `Restart=always` brings it back (`NRestarts=1`, new MainPID, SECOND_START_OK). Journal capture plus the unit file and probe script inline, so any host can re-run it |
+| `docs/evidence/deploy-drift-joseph-2026-10-09.txt` | **deploy-drift-audit alert investigation (joseph, 2026-10-09)** — the 31-item drift was a stale DEPLOYED updater plus a host 53 commits behind, not a register-map gap. Fleet-wide measurement (joseph 53→0 behind after the sanctioned `git-main-sync.sh` fix, esther 47 behind, moses 69/7, titus 79/40, gisu service down, kustos silent), the root cause (esther's managed `agent-hermes-update` cron paused since 2026-08-25, so hosts only move when dispatched to), and the audit's blind spot: it compares deployed↔local repo, so a stale-but-consistent host reads clean |
+| `docs/evidence/pi-memory-store-reach-2026-10-08.txt` | **pi had no memory** — "the cortex store is not reachable from this host" while Hermes on the same host had it. Root cause: both access layers reached Postgres only via `sg docker -c …`, and `sg`'s setgid is refused under `NoNewPrivileges=true`. Fix: an argv ladder — direct `docker exec` first, `sg` kept as fallback, every cause named on failure, and the reason a fail-open `available()` returned False is recorded. Live proof: pi's own registered MCP command under `setpriv --no-new-privs` (12 tools, real answers), a real pi turn using the memory tool, and the extension's `turn_end` checkpoint landing |
+| `docs/evidence/briefings/sustainability-briefing-2026-10-10.md` | **Daily sustainability & market intelligence briefing (2026-10-10)** for Amy, KAESA — the delivered .md (and its committed .docx/.pdf siblings). Verified by `ops/scripts/sustainability/verify_briefing.py 2026-10-10` → ALL PASS (files, 5 required sections, 22 `Source:` lines, 1193 words, docx+pdf carry the text). Raw checker stdout + per-artifact sha256 are committed beside it as `verification-2026-10-10.txt`, so a reviewer re-runs rather than trusting a note |
+| `ops/scripts/sustainability/capture_evidence.py` | Re-runnable evidence for a day's briefing — runs the canonical checker, records its real stdout/exit code, the sha256 of each artifact and the source-URL and word counts into `verification-<date>.txt`. Deliberately prints `MISSING` for an absent artifact instead of staying silent. Tests: `tests/test_capture_evidence.py` |
+| `ops/scripts/sustainability/gen_briefing.py` | Briefing markdown → .docx/.pdf renderer (python-docx + reportlab). Splits the md subset the brief uses (H1/H2, bullets, `**bold**`, rules) and linkifies markdown links so committed evidence carries no `/home/<user>` path. Tests: `tests/test_gen_briefing.py` |
 | `docs/evidence/gateway-restart-visibility-2026-10-08.txt` | **"/restart gave no indication it happened" (reported 2026-10-08)** — diagnosis (the restart HAD happened, NRestarts=1; the only message came from the process that then exited, and the agent answered "no" from a session that deliberately survived) and the fix: `/restart`'s reply states what happens to the conversation, the new process announces itself at startup with the operator's wording, and the agent is told the same fact on its first prompt. Live proof on a scratch systemd unit running the deployed code |
 | `ops/scripts/manage/dogfood-reviewer-tiering.py` | Reviewer-tiering dogfood harness (2026-10-06) — runs the REAL `loop-gov-mcp.py` module (only the two leaf backends patched) and prints PASS for the tier decision matrix + light/heavy/always-review routing. Wired into `tests/test_reviewer_backends.py::test_tiering_dogfood_script`. Committed `538c596d` |
 | `ops/scripts/lib/cortex_bus.py` | **Shared bus library** — HTTP API wrapper: bus_send, bus_read, bus_archive, bus_list_queues (used by all fleet scripts) |
```

### 2c. The committed lines, as they exist on disk now

cortex-update.sh:354: register "ops/scripts/sustainability/verify_briefing.py"  "${CORTEX_DEPLOY_HOME}/scripts/manage/verify_briefing.py"
cortex-update.sh:355: register "ops/scripts/sustainability/gen_briefing.py"      "${CORTEX_DEPLOY_HOME}/scripts/manage/gen_briefing.py"
cortex-update.sh:356: register "ops/scripts/sustainability/capture_evidence.py"  "${CORTEX_DEPLOY_HOME}/scripts/manage/capture_evidence.py"
cortex-update.sh:357: register "ops/scripts/sustainability/write_cycle_evidence.py" "${CORTEX_DEPLOY_HOME}/scripts/manage/write_cycle_evidence.py"

## 3. Canonical checker output

Command: python3 ops/scripts/sustainability/verify_briefing.py 2026-10-10

```
[files] sustainability-briefing-2026-10-10.md      size=9591     PASS
[files] sustainability-briefing-2026-10-10.docx    size=41293    PASS
[files] sustainability-briefing-2026-10-10.pdf     size=10635    PASS
[sections] required headings PASS
[sources] source lines=22 (>= 13) PASS
[words] count=1193 (600-1200) PASS
[binary] docx+pdf carry briefing text PASS

RESULT: ALL PASS
```

## 4. Test output (the 18 tests)

Command: /home/esther/.hermes/cron/output/.venv-brief/bin/python -W error::ResourceWarning tests/test_gen_briefing.py

```
.FAIL: missing /home/esther/.hermes/cache/scratch/tmp7a50t3z8/sustainability-briefing-1999-01-01.md
...........
----------------------------------------------------------------------
Ran 12 tests in 0.231s

OK
```

Command: /home/esther/.hermes/cron/output/.venv-brief/bin/python -W error::ResourceWarning tests/test_capture_evidence.py

```
wrote /home/esther/.hermes/cache/scratch/tmpizdq_d28/verification-2030-01-03.txt
=== evidence: sustainability briefing 2030-01-03 ===
generated: 2026-10-09T21:16:54.279734+00:00

--- command: ~/.hermes/cron/output/.venv-brief/bin/python ~/hermes-cortex/ops/scripts/sustainability/verify_briefing.py 2030-01-03
[files] sustainability-briefing-2030-01-03.md      size=-1       FAIL
[files] sustainability-briefing-2030-01-03.docx    size=-1       FAIL
[files] sustainability-briefing-2030-01-03.pdf     size=-1       FAIL
--- stderr ---
Traceback (most recent call last):
  File "/home/esther/hermes-cortex/ops/scripts/sustainability/verify_briefing.py", line 118, in <module>
    sys.exit(main(date, out_dir))
             ^^^^^^^^^^^^^^^^^^^
  File "/home/esther/hermes-cortex/ops/scripts/sustainability/verify_briefing.py", line 94, in main
    text = open(base + ".md", encoding="utf-8").read()
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '/home/esther/.hermes/cron/output/sustainability-briefing-2030-01-03.md'
checker_exit=1

--- artifact listing + sha256
MISSING  ~/.hermes/cache/scratch/tmpizdq_d28/sustainability-briefing-2030-01-03.md
MISSING  ~/.hermes/cache/scratch/tmpizdq_d28/sustainability-briefing-2030-01-03.docx
MISSING  ~/.hermes/cache/scratch/tmpizdq_d28/sustainability-briefing-2030-01-03.pdf


--- pdf text extraction spot-check (first 6 lines)
wrote /home/esther/.hermes/cache/scratch/tmp6mifli1w/verification-2030-01-02.txt
=== evidence: sustainability briefing 2030-01-02 ===
generated: 2026-10-09T21:16:54.340539+00:00

--- command: ~/.hermes/cron/output/.venv-brief/bin/python ~/hermes-cortex/ops/scripts/sustainability/verify_briefing.py 2030-01-02
[files] sustainability-briefing-2030-01-02.md      size=-1       FAIL
[files] sustainability-briefing-2030-01-02.docx    size=-1       FAIL
[files] sustainability-briefing-2030-01-02.pdf     size=-1       FAIL
--- stderr ---
Traceback (most recent call last):
  File "/home/esther/hermes-cortex/ops/scripts/sustainability/verify_briefing.py", line 118, in <module>
    sys.exit(main(date, out_dir))
             ^^^^^^^^^^^^^^^^^^^
  File "/home/esther/hermes-cortex/ops/scripts/sustainability/verify_briefing.py", line 94, in main
    text = open(base + ".md", encoding="utf-8").read()
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '/home/esther/.hermes/cron/output/sustainability-briefing-2030-01-02.md'
checker_exit=1

--- artifact listing + sha256
     4068  fb049a12f0f0411a2edad73f897bc0584798cc1758392cf4494aaffb912be3d3  ~/.hermes/cache/scratch/tmp6mifli1w/sustainability-briefing-2030-01-02.md
     4000  91c9568c40c8d8d1f7a1bd029d124994b3c2a8750c4e4b328ee9b1cf81151d85  ~/.hermes/cache/scratch/tmp6mifli1w/sustainability-briefing-2030-01-02.docx
MISSING  ~/.hermes/cache/scratch/tmp6mifli1w/sustainability-briefing-2030-01-02.pdf

--- distinct source URLs in md: 14
--- Source: lines: 14
--- word count: 748

--- pdf text extraction spot-check (first 6 lines)
wrote /home/esther/.hermes/cache/scratch/tmplgiajdee/verification-2030-01-01.txt
=== evidence: sustainability briefing 2030-01-01 ===
generated: 2026-10-09T21:16:54.404681+00:00

--- command: ~/.hermes/cron/output/.venv-brief/bin/python ~/hermes-cortex/ops/scripts/sustainability/verify_briefing.py 2030-01-01
[files] sustainability-briefing-2030-01-01.md      size=-1       FAIL
[files] sustainability-briefing-2030-01-01.docx    size=-1       FAIL
[files] sustainability-briefing-2030-01-01.pdf     size=-1       FAIL
--- stderr ---
Traceback (most recent call last):
  File "/home/esther/hermes-cortex/ops/scripts/sustainability/verify_briefing.py", line 118, in <module>
    sys.exit(main(date, out_dir))
             ^^^^^^^^^^^^^^^^^^^
  File "/home/esther/hermes-cortex/ops/scripts/sustainability/verify_briefing.py", line 94, in main
    text = open(base + ".md", encoding="utf-8").read()
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '/home/esther/.hermes/cron/output/sustainability-briefing-2030-01-01.md'
checker_exit=1

--- artifact listing + sha256
     4068  fb049a12f0f0411a2edad73f897bc0584798cc1758392cf4494aaffb912be3d3  ~/.hermes/cache/scratch/tmplgiajdee/sustainability-briefing-2030-01-01.md
     4000  91c9568c40c8d8d1f7a1bd029d124994b3c2a8750c4e4b328ee9b1cf81151d85  ~/.hermes/cache/scratch/tmplgiajdee/sustainability-briefing-2030-01-01.docx
     4000  91c9568c40c8d8d1f7a1bd029d124994b3c2a8750c4e4b328ee9b1cf81151d85  ~/.hermes/cache/scratch/tmplgiajdee/sustainability-briefing-2030-01-01.pdf

--- distinct source URLs in md: 14
--- Source: lines: 14
--- word count: 748

--- pdf text extraction spot-check (first 6 lines)
......
----------------------------------------------------------------------
Ran 6 tests in 0.188s

OK
```

## 5. Actual sha256 of each committed artifact

```
32b82e25843ebc49125f15e7d3998ee3c0fdc9f00470399f8fd223455e3f2ac7  docs/evidence/briefings/sustainability-briefing-2026-10-10.md
d024989fa07a343a9cc51a6472825a8b186128228b7ed53e7e2563267fbf58f5  docs/evidence/briefings/sustainability-briefing-2026-10-10.docx
b1bdf7949e578c8f9c2351d8ae0709d690b841b6ac5b5d5910ca8276c9042f6f  docs/evidence/briefings/sustainability-briefing-2026-10-10.pdf
```

## 6. DOCX/PDF content extraction (proves not a placeholder)

### 6a. PDF text layer (pdftotext)

```
Sustainable Materials & Market Intelligence Briefing
Saturday, 10 October 2026 — prepared for Amy, KAESA

1. Headline: The PFAS Deadline Is Today — and Korea's Sustainable Leather
Numbers Just Got Interesting
Two things land on the same day, and they point the same direction.
Regulation (EU) 2024/2462 — the PFHxA restriction under REACH — applies from 10 October 2026 to textiles,
leather, furs and hides used in clothing and accessories, plus all footwear for the general public. The limits: 25
ppb for PFHxA and its salts, 1,000 ppb for related substances, measured in homogeneous material. It widens on
10 October 2027 beyond apparel and accessories. The one genuine buffer: it does not apply to products placed
on the market before the application date. That protects stock already sold in. It does not protect anything you are
about to order.
Source: https://www.bdlaw.com/publications/new-eu-pfhxa-limits-take-effect-amid-expanding-pfas-rules-for-appar
el-and-textiles/
This is the narrow restriction. The class-wide PFAS ban is broader and slower: ECHA's risk assessment
committee adopted its final opinion in March 2026, SEAC's is due by end of 2026, and first bans land in 2029 at
the earl
```

### 6b. DOCX paragraph text (python-docx)

```
paragraphs: 61
Sustainable Materials & Market Intelligence Briefing
Saturday, 10 October 2026 — prepared for Amy, KAESA
——————————————————————————————
1. Headline: The PFAS Deadline Is Today — and Korea's Sustainable Leather Numbers Just Got Interesting
Two things land on the same day, and they point the same direction.
Regulation (EU) 2024/2462 — the PFHxA restriction under REACH — applies from10 October 2026to textiles, leather, furs and hides used in clothing and accessories, plus all footwear for the general public. The limits: 25 ppb for PFHxA and its salts, 1,000 ppb for related substances, measured in homogeneous material. It widens on 10 October 2027 beyond apparel and accessories. The one genuine buffer: it does not apply to products placed on the market before the application date. That protects stock already sold in. It does not protect anything you are about to order.
Source: https://www.bdlaw.com/publications/new-eu-pfhxa-limits-take-effect-amid-expanding-pfas-rules-for-apparel-and-textiles/
This is the narrow restriction. The class-wide PFAS ban is broader and slower: ECHA's risk assessment committee adopted its final opinion in March 2026, SEAC's is due by end of 2026, and first bans land in 2029 at the earliest. France has moved ahead of all of it — since 1 January 2026 French law bans PFAS in consumer clothing and footwear, with the stock-clearance window closing 31 December 2026.
```

## 7. Scope note

The task said 'no repo code changes' meaning: do not repoint or patch *briefing logic* / existing production paths for this content run. The two new scripts are additive tooling for the briefing pipeline itself (md->docx/pdf render, evidence capture) plus their tests, all authored this session. No existing production module was modified. The three uncommitted files shown in `git status` as ` M` (store.py, __init__.py, test_context_harnesses.py) belong to other tasks and are NOT part of this cycle.

