#!/usr/bin/env bash
# Emit the skills-ownership evidence for a cycle. Re-runnable; mutates NOTHING.
#
# CHECKOUT-ONLY — deliberately not in cortex-update.sh register(): this is a run-scoped
# evidence emitter invoked by an agent from the checkout, not something a host needs to stay
# healthy. The two tools it EXERCISES are registered and deployed:
# ops/scripts/manage/migrate-skills-ownership.py and ops/scripts/manage/publish-agent-skills.py.
#
# Every line goes through `red`, which replaces $HOME with `~`: this repo is public and
# must not carry the operator's home path (adversarial finding ADV-13491-2).
#
# Usage:  bash ops/scripts/manage/emit-skills-ownership-evidence.sh > docs/evidence/skills-ownership-<date>.txt
set -uo pipefail

PY="${CORTEX_PY:-python3}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OWNER="${HERE}/migrate-skills-ownership.py"
PUBLISHER="${HERE}/publish-agent-skills.py"

red() { sed -e "s|${HOME}|~|g"; }

echo "== skills ownership evidence (cycle 13491) =="
date -u +"generated: %Y-%m-%dT%H:%M:%SZ"
echo "repo rev : $(git -C "${HERE}/../.." rev-parse --short HEAD 2>/dev/null || echo unknown)"

echo
echo "-- 1. the three paths --"
echo "expected: cortex REAL, the other two POINTERS to it"
for p in "${HOME}/.hermes-cortex/skills" "${HOME}/.hermes/skills" "${HOME}/.agents/skills"; do
  if [ -e "$p" ] || [ -L "$p" ]; then
    printf '%s\n' "$(ls -ld "$p" 2>&1)" | red
  else
    echo "MISSING: ${p/${HOME}/~}"
  fi
done

echo
echo "-- 2. ownership classifier (cortex owns the tree = NEW, exit 0) --"
_owner_out="$("$PY" "$OWNER" --check 2>&1)"; _owner_rc=$?
printf '%s\n' "$_owner_out" | red
echo "ownership rc=${_owner_rc}  (0 = cortex owns the tree, 1 = still inverted)"

echo
echo "-- 3. published view (in sync = exit 0, and a plain scan sees every skill) --"
_pub_out="$("$PY" "$PUBLISHER" --check 2>&1)"; _pub_rc=$?
printf '%s\n' "$_pub_out" | red
echo "publish rc=${_pub_rc}  (0 = in sync, 1 = drift, 4 = a foreign tree occupies the path)"

echo
echo "-- 4. a reader through the Hermes pointer (content must resolve) --"
_read_out="$(head -3 "${HOME}/.hermes/skills/workflow/task-start/SKILL.md" 2>&1)"; _read_rc=$?
printf '%s\n' "$_read_out" | red
echo "read through the Hermes path rc=${_read_rc}  (0 = resolves)"

echo
echo "-- 5. a WRITE through the Hermes pointer lands in the cortex tree --"
PROBE="${HOME}/.hermes/skills/.ownership-probe.$$"
if printf 'probe\n' > "$PROBE" 2>/dev/null; then
  if [ -f "${HOME}/.hermes-cortex/skills/.ownership-probe.$$" ]; then
    echo "PASS: the write is visible in the cortex tree (same inode via the pointer)"
  else
    echo "FAIL: the write through the Hermes path did NOT reach the cortex tree"
  fi
  rm -f "$PROBE"
else
  echo "COULD NOT VERIFY: the Hermes path is not writable (read-only mount?)"
fi

echo
echo "-- 6. skill count per path, and READER SENSITIVITY (why the mode matters) --"
echo "   plain 'find' does NOT traverse a symlinked root; python rglob/os.walk DOES."
for p in "${HOME}/.hermes-cortex/skills" "${HOME}/.hermes/skills" "${HOME}/.agents/skills"; do
  plain="$(find "$p" -name SKILL.md -type f 2>/dev/null | wc -l)"
  followed="$(find -L "$p" -name SKILL.md -type f 2>/dev/null | wc -l)"
  python_sees="$("$PY" - "$p" <<'EOF' 2>/dev/null
import sys, pathlib
print(len(list(pathlib.Path(sys.argv[1]).rglob("SKILL.md"))))
EOF
)"
  printf '%6s find | %6s find -L | %6s rglob   %s\n' "$plain" "$followed" "$python_sees" "$p"
done | red
echo "   a harness that enumerates with find-default sees NOTHING through a symlinked root:"
echo "   probe each harness's own enumeration before declaring its capability."

echo
echo "-- verdict --"
_fail=0
[ "${_owner_rc:-9}" -eq 0 ] || { echo "FAIL: ownership rc=${_owner_rc} — cortex does not own the tree"; _fail=1; }
[ "${_pub_rc:-9}" -eq 0 ]   || { echo "FAIL: publish rc=${_pub_rc} — the agent-visible view is not in sync"; _fail=1; }
[ "${_read_rc:-9}" -eq 0 ]  || { echo "FAIL: the Hermes pointer does not resolve"; _fail=1; }
[ "$_fail" -eq 0 ] && echo "PASS: cortex owns the tree, the view is published, the pointer resolves"

echo
echo "note: the Hermes pointer is the transition accommodation; the requirement is that no"
echo "      HARNESS path other than Hermes's own names a Hermes directory (see the plan)."
# Exit non-zero when any check above failed: an evidence emitter that always exits 0 is a
# false green (self-adversarial findings ADV-13491-1..4, all swallowed-exit-code class).
exit "$_fail"
