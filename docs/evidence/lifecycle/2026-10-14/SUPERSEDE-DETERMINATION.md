# Drift-sync supersede determination — orch-skill-lifecycle 2026-10-14

Satisfies ADV-12498-001, ADV-12498-002, ADV-12498-004, ADV-12498-005, ADV-12498-007.

## Method (re-runnable)

`bash ops/scripts/quality/classify-drift-supersede.sh` re-derives the verdict for
every REVIEW-flagged file. It normalises whitespace, compares WORD SETS between
the pre-sync repo side (`git show HEAD~1:<path>`) and the deployed copy, and
reports words present in repo-but-not-deployed. It exits 1 if any file loses
words, so it functions as a gate.

Output: `drift-supersede-classification.txt` (same directory).

**Probe probity:** the first version of this script was BROKEN (`sort` on
`uniq -c` output is not lexical, so `comm` reported ~650 false losses on every
file). It was caught because the numbers were implausible, then fixed to
`sort -u` with a plain `comm`. A green run after a probe fix is only meaningful
if the probe was shown failing first — the broken run is preserved in this
directory's git history as that demonstration.

## Finding: the classifier's REVERT-RISK verdict is a FALSE POSITIVE class

The classifier flags 6 files. Each was inspected line-by-line. **All 6 are
in-place rewrites of existing passages, not content loss.** The classifier
cannot distinguish "rewritten" from "deleted" because it compares word sets,
and a rewrite replaces old words with new ones. Its value is as a SCREEN
(narrowing 10 files to 6), not an oracle — the per-file determination below is
the actual evidence.

- utf8: approve-gate-debugging — lost 0 words — SUPERSEDE, clean superset.
- software-development/agent-contract — lost 0 — SUPERSEDE, items 10 and 16 extended in place.
- software-development/change-checklist — lost 0 — SUPERSEDE, clean superset.
- software-development/hermetic-python-testing — lost 0 — SUPERSEDE, clean superset.
- software-development/prove-before-create — lost "Concept" — REWORD: deployed reads "Capability exists in one codebase but not another". Same lesson, one word corrected in place.
- devops/maintenance-scan — lost "prior" — REWRITE: repo said "uncommitted changes from prior work"; deployed says "establish WHAT is uncommitted before assigning it an owner" plus a full new paragraph on test-run byproducts. Old wording deliberately replaced by stronger guidance.
- devops/governance-closeout — lost TRANSPORT/model/faster/routes/substitutes/faithfully/auditable/written/opt — REWRITE: the "let a tier change the TRANSPORT, never the model" passage was deliberately replaced by the corrected stance (the depth tier IS a deliberate model decision, named as a DEPTH decision) plus a new "Verify the WIRING, not the constant" lesson. This CORRECTS the repo's older, now-wrong guidance.
- devops/governance-lock-lifecycle — lost bare/check_lock/Called/When/disk/inactive/arg — REWRITE: repo's "A bare check_lock() is not a status check" replaced by the fuller "Read the lock's FULL picture; active alone is only YOUR lock", which preserves the false-negative lesson and adds locks/live_lock_count/repo_path detail.
- devops/loop-governance — lost a path token and "size." — REWORD: a path in a backtick list reflowed across a line break; no lesson lost.
- devops/mcp-health-monitoring — lost Config/uses/LIVE/Parse/key/probes — REWORD: repo's "Config key is not the canonical name ... Parse the LIVE config for probes" reflowed into the deployed paragraph covering the same conclusion with the cortex-bus args-path detail.

**Conclusion: 0 of the 10 REVIEW-flagged files suffered a real loss.** The sync
was correct. This conclusion rests on the per-file inspection above, which is
why the classifier alone was not sufficient evidence — a point the reviewer was
right to insist on.

## Doctor after-sync

`doctor-after.txt` — full transcript. Result: `OK Overall: HEALTHY
(460 pass, 0 warn, 0 fail, 3 info)` and `OK Skill drift`, versus
`WARN Overall: WARNING (458 pass, 25 warn, 0 fail)` with 23 drift warns before.

## Secret leak check

`secret-leak.txt` — empty output, rc 0 (clean). Combined with the enforcer's
own PII gate at commit time.

## Evidence files excluded from the commit (ADV-12498-007)

Four files were dirty in the working tree and were NOT committed; they are
test-run/tool byproducts per the maintenance-scan lesson, restored with
`git checkout -- docs/evidence/`:

- docs/evidence/briefings/cycle-evidence-2026-10-10.md
- docs/evidence/briefings/test-results-2026-10-10.txt
- docs/evidence/gateway-suite-results.txt
- docs/evidence/skill-drift-parity.txt

The sync commit contains 23 files, all under `skills/` — verified with
`git status --short | grep -c '^ M skills/'` returning 23 and no non-skills entries.

## Phase 1 collection record (ADV-12498-003)

- Staging dir `~/.hermes-cortex/state/learning-reports/`: 1085 files total;
  60 modified within 48h; 11 unique by md5 (the dual-orchestrator staging race
  writes the same body under several agent names, so 10 of the 60 were exact
  duplicate bodies).
- Agents reporting: esther, moses, joseph, gisu, kustos, titus.
- Ledger: `python3 ops/scripts/manage/learning-ledger.py list --status pending`
  printed "No learnings found." (0 pending; nothing to set-status.)
- Session compliance scan: `session_search` for
  `correction|"never ask"|"fix permanently"|"CODIFY THIS"` returned only prior
  runs of this same pipeline (cron sessions), i.e. no unguarded user
  corrections in the window.
