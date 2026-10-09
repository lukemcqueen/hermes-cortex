# land-nonhermes-lock-fix — landing evidence

RESULT: dogfood 1/1 PASS (rc=0) · doctor rc=1 WARNING 447 pass / 12 warn / 0 fail / 7 info · Deploy sync PASS

Ran at revision 2b3a1001. Committed at HEAD = merge 91278a67 + this evidence commit.
Generated 2026-10-10T06:37:03+09:00 KST on host esther.

## Assertions

1. The two previously-blocked paths are clean in the working tree.
2. `git merge origin/main` completed with no conflicts (strategy ort, two auto-merges).
3. Deployed commit matches HEAD (doctor: Deploy sync PASS).
4. The audited range contains origin/main tip `9b375e7a`'s own 47 files, integrated by the merge.

## 1. Blocked paths clean

```
$ git status --porcelain -- docs/DOCS-INDEX.md ops/install/deploy/nginx/blocked_ips.add
(no output = both paths clean; the owner landed their work)
```

## 2. Merge

```
$ git merge origin/main -m "merge: integrate origin/main before landing the non-Hermes lock-repo fix"
Merge made by the 'ort' strategy.
Auto-merging docs/DOCS-INDEX.md
Auto-merging ops/install/deploy/nginx/blocked_ips.add
47 files changed, 7344 insertions(+)

$ git show --stat --oneline 91278a67 | head -2
91278a67 merge: integrate origin/main before landing the non-Hermes lock-repo fix


$ git log --oneline -1 9b375e7a   # origin/main tip before the merge
9b375e7a auto: block 34 suspect IPs [pipeline]
```

## 3. Range content

Close window `d0752f34..HEAD`. Two sources:

- `9b375e7a` (origin/main, pre-existing on the remote) — the 47 files the merge integrated:
  auto-remediation evidence, bus-healthcheck transcripts, DOCS-INDEX.md, blocked_ips.add,
  tools/auto-remediation-scan.sh. Not authored here, not edited here.
- this session — merge commit `91278a67` (no file content of its own) and this evidence commit.

```
$ git diff --name-only d0752f34 9b375e7a | wc -l
47
$ git log --format="%h %an %s" 91278a67..HEAD
```

## 4. Dogfood

```
✅  DOGFOOD PASSED — deployed state verified clean.
DOGFOOD_RC=0
$ echo $?   # cortex-dogfood.sh
0   (exits 0 only on the PASSED branch, line 180)
```

## 5. Doctor

```
16:  ✅ Deploy sync — deployed commit matches HEAD
492:  ⚠️  Overall: WARNING  (447 pass · 12 warn · 0 fail · 7 info)
513:DOCTOR_RC=1
```

rc=1 is the doctor's WARNING exit; **0 checks FAILED**. All 12 warnings, enumerated
verbatim from the transcript at lines 13, 22, 122, 449-465:

| # | Warning | Disposition |
|---|---|---|
| 1 | `Repo clean — 14 uncommitted change(s)` | 14 files are OTHER sessions' in-flight work in this shared checkout (`ops/services/mycortex-mem/store.py`, `plugins/mycortex-mem/__init__.py`, `tests/test_*`, `docs/evidence/briefings/*`, `docs/evidence/skill-drift-parity.txt`). Not touched, not stashed, not committed here. |
| 2 | `AGENTS.md efficiency (proj)` | dev-repo AGENTS.md under `/home/esther/proj` — different tree. |
| 3 | `Stale deploy: scripts/review-sweep-check.py` | deployed-only file not in the register map; pre-existing, unrelated to this landing. |
| 4-11 | `Skill drift: devops/{cortex-deployment-sync, cron-job-management, fleet-commands, governance-closeout, governance-lock-lifecycle, mycortex, psql-automation}` + `software-development/change-checklist` | deployed skill copies are NEWER than the repo source — content authored on the deployed tree by earlier sessions; pre-existing before this cycle. |
| 12 | `Skill drift — 8 drifted, 379 in sync, 126 Hermes defaults skipped` | summary line for the 8 rows above. |

None of the 12 was introduced by this landing: this landing changes only
`docs/evidence/land-nonhermes-lock-fix-*` and three `docs/DOCS-INDEX.md` rows, so no
doctor check that reads code, skills, deploy-map or crons can be affected by it. The
doctor's own `Deploy sync` check — the one this landing is about — is `✅`.

## 6. Full transcripts

- `docs/evidence/land-nonhermes-lock-fix-dogfood-2026-10-10.txt` (1384 lines)
- `docs/evidence/land-nonhermes-lock-fix-doctor-2026-10-10.txt` (513 lines)
