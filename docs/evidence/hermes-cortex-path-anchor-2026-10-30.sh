#!/usr/bin/env bash
# Evidence generator: every command below is run for real and its output is written
# verbatim (after the one normaliser) to the committed transcript beside this file.
#
#   re-run:  bash docs/evidence/hermes-cortex-path-anchor-2026-10-30.sh
#   output:  docs/evidence/hermes-cortex-path-anchor-2026-10-30.txt
#
# The generator WRITES the committed file itself (via an atomic rename), so
# `generated-by` is a fact about the file rather than a claim about who typed it.
#
# BASELINE is pinned to the LITERAL pre-change revision. It is deliberately not
# `origin/main` or `HEAD~1`: origin/main IS the fix once this range is pushed, so a
# ref-based baseline starts comparing the change with ITSELF and prints success forever.
# c161e75c is the tip this range was built on. The run asserts the extracted copy really
# is pre-change (the phrase the fix INTRODUCED must be absent from it) before it claims
# anything about the comparison.
#
# PORTABILITY: no GNU-only flags and no bash-4 syntax — this file is committed and may be
# run on macOS. Hash via sha256sum OR shasum; ANSI strip via a literal ESC (BSD sed has no
# \x1b); counting via `git grep` (no --include/--exclude-dir); no `timeout`.
#
# MISSING DEPLOY: this host's cortex deploy is required for the adversarial gate and the
# doc audit. Where it is absent the run says so and records rc=3 (could-not-verify) — it
# never lets a missing tool masquerade as a pass, and never tracebacks.
#
# CONCURRENCY: the transcript is written to a unique temp path and moved into place with a
# single atomic rename, so a reader never sees a half-written file. Two SIMULTANEOUS runs
# are still last-writer-wins on the committed path — this is a single-writer tool by
# convention; there is no lock.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FINAL="$REPO/docs/evidence/hermes-cortex-path-anchor-2026-10-30.txt"
OUT="$FINAL.tmp.$$"
BASE_REV=c161e75c                      # pre-change tip; see BASELINE note above
FIX_MARKER='the deployed runtime copy, and the one the governance enforcer enforces'
TESTFILE=tests/test_agents_md_home_path_convention.py
DEPLOY="${HOME}/.hermes-cortex/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/path-anchor-evidence.XXXXXX")"
ESC=$(printf '\033')

rule() { printf '%s\n' "--------------------------------------------------------------"; }
# ONE normaliser, applied to EVERY emitted line (command output included, via a pipe):
# no $HOME paths, no hostname, no ANSI escapes.
norm() {
  sed -e "s#${HOME}#~#g" \
      -e "s#$(hostname -s 2>/dev/null || echo __no_host__)#<host>#g" \
      -e "s/${ESC}\[[0-9;]*m//g"
}
say() { printf '%s\n' "$*"; }          # already-normalised text (uses ~ and <host> by hand)
hash_of() {                            # portable: GNU coreutils OR macOS shasum
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -c1-16
  else shasum -a 256 "$1" | cut -c1-16; fi
}
# bare refs on a revision (tracked tree; excludes archived history and this artifact)
count_refs() {                         # $1 = rev
  git -C "$REPO" grep -c -E '(^|[^/])\.hermes-cortex' "$1" -- AGENTS.md docs skills \
    ':!docs/older' ':!docs/evidence' 2>/dev/null | awk -F: '{t+=$NF} END {print t+0}'
}

exec >"$OUT" 2>&1

say "Evidence — anchoring .hermes-cortex references to ~/ (infra dir vs repo-local overlay)"
rule
say "generated-by:  bash docs/evidence/hermes-cortex-path-anchor-2026-10-30.sh"
say "captured-at:   $(git -C "$REPO" rev-parse --short=8 HEAD) (the revision the working tree sat on)"
say "baseline:      $BASE_REV (pre-change tip, pinned in the generator's own default)"
say "redaction:     ONE normaliser, applied to every COMMAND-OUTPUT line; literal lines are"
say "               written path-free by hand (no interpolated \$HOME path, no hostname)."
say "note:          the committed copy is one commit AHEAD of the revision above by construction"
say "               (writing this file changes the revision). Re-run the generator to reproduce."
say "rule under test: every '.hermes-cortex' that MEANS the runtime infra dir is home-anchored."
say "  ~/.hermes-cortex/  = runtime infra dir (deployed; scripts/ state/ sessions/ memory/"
say "                       hooks/ and the skills.yaml the enforcer reads)"
say "  ./.hermes-cortex/  = repo-local overlay inside a CONSUMER project (seed-project.sh)"
rule

# ---- 1. BEFORE: the pinned pre-change revision, asserted to be pre-change ---------
say "1. BEFORE — test against the pinned pre-change revision"
say "   extracting AGENTS.md@$BASE_REV into a scratch tree (path redacted)"
mkdir -p "$WORK/base/tests"
git -C "$REPO" show "$BASE_REV:AGENTS.md" > "$WORK/base/AGENTS.md"
cp "$REPO/$TESTFILE" "$WORK/base/tests/"
say "   extracted sha=$(hash_of "$WORK/base/AGENTS.md")  revision=$(git -C "$REPO" rev-parse "$BASE_REV")"
if grep -qF "$FIX_MARKER" "$WORK/base/AGENTS.md"; then
  say "   ASSERT FAILED — the extraction carries the phrase the fix INTRODUCED."
  say "   comparison NOT RUN, nothing claimed (a baseline that already passes is a tautology)."
  before_rc=3
else
  say "   assert: the extraction does NOT carry the phrase the fix introduced -> pre-change copy confirmed"
  say "   bare '.hermes-cortex' occurrences in AGENTS.md@$BASE_REV: $(grep -c -E '(^|[^/])\.hermes-cortex' "$WORK/base/AGENTS.md")"
  ( cd "$WORK/base" && bash "$REPO/tests/run-tests.sh" "$TESTFILE" -q ) 2>&1 | norm
  before_rc=${PIPESTATUS[0]}
  say "   BEFORE rc=$before_rc   (1 = the rule was violated on the pre-change copy, i.e. the test can fail)"
fi
say ""

# ---- 2. AFTER: the live working tree (deployed copy synced) ----------------------
say "2. AFTER — same test file, same runner, against the live checkout"
( cd "$REPO" && bash tests/run-tests.sh "$TESTFILE" -q ) 2>&1 | norm
after_rc=${PIPESTATUS[0]}
say "   AFTER rc=$after_rc   (0 = repo copy and deployed ~/.hermes/AGENTS.md both home-anchored)"
say ""

# ---- 3. Moving counts across the doc surface -------------------------------------
say "3. Moving counts — bare '.hermes-cortex' refs on the tracked tree"
say "   (excludes docs/older = archived history, and docs/evidence = this artifact)"
say "   AGENTS.md (the always-loaded doc):  $(git -C "$REPO" grep -c -E '(^|[^/])\.hermes-cortex' "$BASE_REV" -- AGENTS.md 2>/dev/null | awk -F: '{print $NF}')  ->  $(git -C "$REPO" grep -c -E '(^|[^/])\.hermes-cortex' HEAD -- AGENTS.md 2>/dev/null | awk -F: '{print $NF}')"
say "   docs/ + skills/ (all files):        $(count_refs "$BASE_REV")  ->  $(count_refs HEAD)"
say "   RESIDUAL IS NOT ZERO, and is mostly INTENTIONAL. Bare refs that mean the"
say "   RUNTIME dir were fixed; the remainder are dominated by pages whose SUBJECT is"
say "   the repo-local overlay itself (seed-project-bootstrapping.md,"
say "   project-cortex-directory.md, the seed sections of hermes-cortex/SKILL.md),"
say "   by pages documenting the shadowing HAZARD (docs/review-receipt-gate.md), and"
say "   by the guard-file mirror in governance-compliance-reporting (repo-relative by"
say "   design, since the guard matches staged paths). A raw count cannot separate an"
say "   intentional overlay reference from a missed runtime one, so it is reported as"
say "   a count, not as a pass."
say ""

# ---- 4. Adversarial gate on the new test file -----------------------------------
say "4. Adversarial gate (A4 — tests/ level) on the new test file"
if [ -f "$DEPLOY/adversarial-verify.py" ]; then
  python3 "$DEPLOY/adversarial-verify.py" --file "$TESTFILE" --level A4 --gate 2>&1 | norm
  adv_rc=${PIPESTATUS[0]}
  say "   A4 rc=$adv_rc"
else
  say "   could-not-verify: no deployed copy at \$HOME/.hermes-cortex/scripts/adversarial-verify.py"
  say "   (run bash ~/hermes-cortex/ops/scripts/cortex-update.sh) — NOT a pass."
  adv_rc=3
fi
say ""

# ---- 5. Doc audit (the same tool the pre-commit hook runs) ----------------------
say "5. agents-doc-audit.py --repo (AGENTS.md mandatory sections, hook mode)"
if [ -f "$DEPLOY/agents-doc-audit.py" ]; then
  python3 "$DEPLOY/agents-doc-audit.py" --repo "$REPO" --json 2>&1 | norm
  doc_rc=${PIPESTATUS[0]}
  say "   doc-audit rc=$doc_rc"
else
  say "   could-not-verify: no deployed copy at \$HOME/.hermes-cortex/scripts/agents-doc-audit.py"
  doc_rc=3
fi
say ""

# ---- 6. Deployed == repo ---------------------------------------------------------
say "6. Deployed copy check — the file agents actually load"
if [ -f "$HOME/.hermes/AGENTS.md" ]; then
  diff -q "$HOME/.hermes/AGENTS.md" "$REPO/AGENTS.md" >/dev/null 2>&1
  diff_rc=$?
  say "   diff ~/.hermes/AGENTS.md ~/hermes-cortex/AGENTS.md rc=$diff_rc  (0 = identical)"
  say "   deployed size: $(wc -c < "$HOME/.hermes/AGENTS.md" | tr -d ' ') bytes  (AGENTS.md WARN >15K, FAIL >20K)"
else
  say "   could-not-verify: no deployed ~/.hermes/AGENTS.md on this host"
  diff_rc=3
fi
say ""

rule
say "SUMMARY (each number is the exit code / count printed above, measured in this run)"
say "  1. BEFORE (pinned $BASE_REV)            rc=${before_rc:-not-run}"
say "  2. AFTER  (live checkout)              rc=$after_rc"
say "  3. AGENTS.md bare refs                 (see section 3; residual disclosed, not scored as pass)"
say "  4. A4 adversarial gate                 rc=$adv_rc   (3 = could not verify)"
say "  5. agents-doc-audit --repo             rc=$doc_rc   (3 = could not verify)"
say "  6. deployed == repo AGENTS.md          rc=$diff_rc  (3 = could not verify)"
rule
exec 1>&- 2>&-
rm -rf "$WORK" 2>/dev/null
mv -f "$OUT" "$FINAL"
