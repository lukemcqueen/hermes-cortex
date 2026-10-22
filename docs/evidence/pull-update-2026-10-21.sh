#!/usr/bin/env bash
# Capture for cycle 7077 — "pull latest hc and update cortex": the merge, the sanctioned
# cortex-update deploy, and the doctor triage that followed (Titus, 2026-10-21).
#
# READ-ONLY: it runs checks and writes ONLY its own transcript.
# Re-run:  bash docs/evidence/pull-update-2026-10-21.sh
#
# Every claim the close note makes about a RUN is re-derivable from a block below: each command
# is printed immediately above its own output, and each block records the command's OWN rc.
#
# SELF-INFLICTED WARN, disclosed rather than re-captured away: the doctor block below runs
# BEFORE this transcript and the regenerated skill-drift capture are committed, so its
# "Repo clean" line counts the very files this commit adds. That warn is the artifact, not a
# host fault, and it clears at the next doctor run after the commit.
#
# macOS + Linux, bash 3.2 safe (no GNU-only flags, no bash-4 syntax, no associative arrays).
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 2
OUT="${1:-docs/evidence/pull-update-2026-10-21.txt}"
PY="${CORTEX_PYTHON:-$HOME/.hermes-cortex/venv/bin/python3}"
exec >"$OUT" 2>&1
TMP="$(mktemp -d "${TMPDIR:-/tmp}/pull-update.XXXXXX")" || exit 2

WORST=0
say() { printf '%s\n' "$@"; }
rule() { printf '\n===== %s =====\n' "$1"; }
norm() { sed -e "s#${HOME}#~#g"; }

say "generated-by: docs/evidence/pull-update-2026-10-21.sh   (this file IS that script's stdout)"
say "host-date:    $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "cycle:        7077 · task cortex-pull-deploy-20261021 · agent titus"
say "scope:        git pull (merge) -> post-merge auto-deploy -> doctor -> triage to 0 fail"
say "revisions:    resolved below, never restated here"

rule "1. revision state after the merge, and the two commits it brought in"
say "\$ git rev-parse HEAD / origin/main / merge-base"
HEAD="$(git rev-parse HEAD)"
ORIGIN="$(git rev-parse origin/main)"
BASE="$(git merge-base origin/main HEAD)"
say "HEAD        $HEAD"
say "origin/main $ORIGIN"
say "merge-base  $BASE"
say "ahead:  $(git rev-list --count origin/main..HEAD)   behind: $(git rev-list --count HEAD..origin/main)"
say ""
say "The merge brought in exactly these two origin commits; the check ASSERTS they are ancestors"
say "of HEAD, so a transcript that no longer describes this merge reports a non-zero rc instead:"
for sha in c1333161 3b03c92c; do
  git merge-base --is-ancestor "$sha" HEAD
  arc=$?
  say "  ancestor? $sha -> rc=$arc   ($(git log -1 --format=%s "$sha"))"
  [ "$arc" -eq 0 ] || WORST=1
done

rule "2. the deploy the merge triggered (post-merge hook ran the sanctioned cortex-update)"
say "The merge IS the deploy in this repo: post-merge fires cortex-update.sh. Its verdict is"
say "re-read here through the doctor's own checks, not from the hook transcript."
say ""
say "\$ $PY ops/scripts/manage/cortex-doctor.py --quiet"
"$PY" ops/scripts/manage/cortex-doctor.py --quiet >"$TMP/doctor.txt" 2>&1
drc=$?
say "rc=$drc   (0 = clean, 1 = warnings only, 2 = failures)"
grep -E "Overall|Deploy sync|Repo sync|Governance plugin|Plugin content|Crons total|Cron manifest drift|Immutable: |Checksum: cortex-update\.sh|PENDING cycles" "$TMP/doctor.txt" | norm
[ "$drc" -le 1 ] || WORST=1
say ""
say "The verdict line above is the doctor's own; the counts are read from it, not restated here."

rule "3. the triage decisions (one record per check nobody had decided about)"
say "Written with cortex_doctor.dispositions.record — the same implementation the doctor CLI"
say "calls — and RE-READ here from the store the doctor reads:"
say ""
say "\$ $PY ops/scripts/manage/cortex-doctor.py --dispositions"
"$PY" ops/scripts/manage/cortex-doctor.py --dispositions >"$TMP/disp.txt" 2>&1
lrc=$?
say "rc=$lrc"
grep -v "^ *$" "$TMP/disp.txt" | norm

rule "4. the fixes this cycle applied, each re-checked in its non-mutating mode"
say "4a. Pi integration was NOT registered; install-pi-integration.sh registered it (idempotent,"
say "    backs up settings.json). Re-checked with its own read-only flag:"
bash "$HOME/.hermes-cortex/scripts/install-pi-integration.sh" --check >"$TMP/pi.txt" 2>&1
prc=$?
norm <"$TMP/pi.txt"
say "rc=$prc   (0 = all registered)"
[ "$prc" -eq 0 ] || WORST=1
say ""
say "4b. Skills manifest: template warned although the two files were already identical — the"
say "    check compares mtime. The prescribed cp refreshed it; identity is asserted here:"
diff "$HOME/hermes-cortex/skills.yaml" "$HOME/.hermes-cortex/skills.yaml" >"$TMP/skillsdiff.txt" 2>&1
src=$?
if [ "$src" -eq 0 ]; then
  say "  repo template == deployed manifest (byte-identical, 0 differing lines)"
else
  say "  DIFFERENT — the cp did not produce identity:"
  norm <"$TMP/skillsdiff.txt"
  WORST=1
fi
say ""
say "4c. Task-id hygiene: normalize-precommit-task-ids.py repaired 99 of 100 malformed rows"
say "    (1 refused, no guess). Durable record = its own manifest, listed here:"
MAN="$HOME/.hermes-cortex/state/task-id-normalization-manifest.txt"
if [ -f "$MAN" ]; then
  say "  manifest: ~/.hermes-cortex/state/task-id-normalization-manifest.txt"
  say "  repaired rows recorded there: $(grep -c '^row ' "$MAN")"
  say "  ledger + backup + timestamp, from the manifest's own header:"
  grep -E '^# (ledger|backup|when)' "$MAN" | norm | sed -e 's#^#    #'
else
  say "  MANIFEST MISSING — cannot verify the repair ran"
  WORST=1
fi
say ""
say "4d. Stale skills: orphaned — the deployed-only skill was renamed to the local- name that"
say "    the deploy and docs/cortex-doctor-reconciliation.md both prescribe (content preserved;"
say "    the doctor's orphan scan skips local-*):"
for d in "$HOME/.hermes/skills/research/local-job-board-research" "$HOME/.hermes/skills/research/job-board-research"; do
  if [ -d "$d" ]; then say "  present: ${d#$HOME/}"; else say "  absent:  ${d#$HOME/}"; fi
done

rule "5. the one item this cycle could NOT land, re-checked read-only"
say "skills/ is an orchestrator-only path (docs/orchestrator-only-paths.txt), so a"
say "non-orchestrator cannot commit the recovery. Two probes follow. Both are READ-ONLY, and the"
say "block asserts that by checksumming the generated capture before and after."
say ""
ART="$PWD/docs/evidence/skill-drift-parity.txt"
sum_before="$(cksum "$ART" 2>/dev/null)"
say "\$ $PY ops/scripts/manage/check-skill-drift-parity.py --check"
"$PY" ops/scripts/manage/check-skill-drift-parity.py --check >"$TMP/parity.txt" 2>&1
prc2=$?
say "rc=$prc2"
norm <"$TMP/parity.txt"
say ""
say "The counts the generated capture records, re-derived from the LIVE tree by the detector's"
say "own build(). The module writes only inside main() (its tail is guarded by"
say "if __name__ == __main__), so importing it derives the report without touching any file:"
say ""
say "\$ $PY - <<PY   # import the detector, call build(), print the report it would write"
"$PY" - <<'PY' >"$TMP/derived.txt" 2>&1
import importlib.util
spec = importlib.util.spec_from_file_location(
    "parity", "ops/scripts/manage/check-skill-drift-parity.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
text, ok = mod.build()
print(text)
print("build() ok flag: %s   (the detector exits 0 when ok is true, 1 otherwise)" % ok)
PY
brc=$?
say "rc=$brc"
norm <"$TMP/derived.txt"
sum_after="$(cksum "$ART" 2>/dev/null)"
say ""
say "capture checksum before this block: $sum_before"
say "capture checksum after  this block: $sum_after"
if [ "$sum_before" = "$sum_after" ]; then
  say "ASSERTED: the block did not write the generated capture (checksums equal)."
else
  say "ASSERT FAILED: the capture changed — this block is not read-only."
  WORST=1
fi
[ "$brc" -eq 0 ] || WORST=1
say ""
say "The generated capture itself is LEFT AT ITS COMMITTED REVISION in this cycle: its regenerated"
say "form was a disputed blob (a generated summary can carry no re-runnable proof of itself), so"
say "the live derivation above is the evidence and the next orchestrator-side reconcile regenerates"
say "the capture when the stranded skill lands."
say ""
say "The reconciler reports that single stranded file as a pure superset (+1, -0), and the"
say "recovery was filed to inbox_orchestrator as a PROPOSAL (bus message"
say "da8d20a1-ee4a-4a8e-ad2c-03e033649287) because the target path is orchestrator-only."
say "The two dispositions recorded for 'Skill drift' and 'Skill drift: devops/docker-management'"
say "name that blocker, so the deferral is a decision with a reason rather than silence."

rule "end of transcript"
say "worst rc across the asserted blocks: $WORST   (0 = every assertion held)"
rm -rf "$TMP"
exit "$WORST"
