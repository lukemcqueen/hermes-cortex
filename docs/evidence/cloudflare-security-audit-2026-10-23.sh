#!/usr/bin/env bash
# Re-runnable evidence generator for the vendored Cloudflare security-audit skill.
#
# Writes the committed transcript itself (exec >"$OUT"), so `generated-by` is a
# fact about the file rather than a claim about who typed it. Read-only: it runs
# every tool in a non-mutating mode and repairs nothing it measures.
#
# Re-run:  bash docs/evidence/cloudflare-security-audit-2026-10-23.sh
# Exit 0 = every applicable check passed.
#
# NOTE ON REVISIONS: this file prints `captured-at`, the revision the working
# tree sat on when the run happened. It deliberately does NOT print a `tip:`
# line — writing this file changes the revision, so a committed copy is always
# one commit ahead of whatever it could have printed.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="${OUT:-$HERE/cloudflare-security-audit-2026-10-23.txt}"
SKILL="$REPO/skills/security/codebase-security-audit"
SKILL_NAME="codebase-security-audit"

exec >"$OUT" 2>&1

# One normaliser for every emitted line: no /home/<user> paths, no host name,
# no ANSI colour. Applied to our own printed lines too, not only command output.
norm() { sed -e "s|$HOME|~|g" -e "s|$(hostname)||g" -e 's/\x1b\[[0-9;]*m//g'; }
say()  { printf '%s\n' "$*" | norm; }
rule() { say "────────────────────────────────────────────────────────────"; }

fail=0
ok()   { say "OK    $1"; }
bad()  { say "FAIL  $1"; fail=1; }
skip() { say "SKIP  $1"; }

say "Cloudflare security-audit skill — vendored-skill evidence"
say "generated-by : docs/evidence/cloudflare-security-audit-2026-10-23.sh"
say "captured-at  : $(git -C "$REPO" rev-parse --short=8 HEAD 2>/dev/null || echo unknown) (working tree at run time)"
say "date         : $(date -Iseconds)"
say "host         : $(uname -s) $(uname -m)"
say "upstream     : github.com/cloudflare/security-audit-skill @ c1c8a8c1471069fb0e188eeaff69b8e8db6564a8 (MIT)"
rule

say "## 1. The vendored file set (20 files, upstream set pinned)"
if [ -d "$SKILL" ]; then
  n=$(find "$SKILL" -maxdepth 1 -type f | wc -l)
  if [ "$n" -eq 20 ]; then ok "20 files landed"; else bad "expected 20 files, found $n"; fi
  find "$SKILL" -maxdepth 1 -type f -printf '%f\n' | sort | while read -r f; do
    say "      $(printf '%-42s' "$f") $(stat -c%s "$SKILL/$f") B"
  done
else
  bad "skill directory missing: ${SKILL/#$HOME/~}"
fi
rule

say "## 2. Frontmatter parses and declares the renamed skill"
# Resolve an interpreter that can IMPORT yaml rather than trusting PATH: the
# bare python3 here is the Hermes tools python, which has no yaml (measured).
# python-with-module.sh exits 3 = no interpreter can import it, which is its own
# outcome ("cannot check"), never a negative result.
PROBE_DIR="$(mktemp -d)"
trap 'rm -rf "$PROBE_DIR"' EXIT
cat >"$PROBE_DIR/probe.py" <<'PY'
import sys, yaml
path, want = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
assert text.startswith("---"), "does not start with ---"
fm = yaml.safe_load(text.split("---", 2)[1])
assert isinstance(fm, dict), "frontmatter is not a mapping"
assert fm.get("name") == want, f"name is {fm.get('name')!r}, expected {want!r}"
d = fm.get("description")
assert isinstance(d, str) and d.strip(), "description missing or blank"
print(f"OK    name={fm['name']}  description={len(d)} chars  version={fm.get('version')}")
print(f"OK    upstream_commit={fm.get('upstream_commit')}  license={fm.get('license')}")
PY
out=$(bash "$REPO/ops/scripts/lib/python-with-module.sh" yaml "$PROBE_DIR/probe.py" "$SKILL/SKILL.md" "$SKILL_NAME" 2>&1); rc=$?
case "$rc" in
  0) printf '%s\n' "$out" | norm ;;
  3) skip "COULD NOT VERIFY — no interpreter on this host can import yaml" ;;
  *) bad "frontmatter check failed (rc=$rc)"; printf '%s\n' "$out" | norm | tail -10 ;;
esac

say "## 2b. The name does not collide with the server-hardening skill"
names=$(find "$REPO/skills" -name SKILL.md -exec sh -c 'grep -m1 "^name:" "$1"' _ {} \; | sed 's/^name: *//' | tr -d '"'"'"'')
c=$(printf '%s\n' "$names" | grep -c "^${SKILL_NAME}$")
if [ "$c" -eq 1 ]; then ok "'$SKILL_NAME' appears exactly once"; else bad "'$SKILL_NAME' appears $c times"; fi
if printf '%s\n' "$names" | grep -q "^security-audit$"; then
  ok "pre-existing devops 'security-audit' still present (no collision introduced)"
else
  bad "the pre-existing devops 'security-audit' skill is gone"
fi
rule

say "## 3. Shipped Node validators parse (node --check)"
if command -v node >/dev/null 2>&1; then
  say "      node $(node --version)"
  for f in "$SKILL"/*.cjs; do
    node --check "$f" >/dev/null 2>&1; rc=$?
    if [ "$rc" -eq 0 ]; then ok "node --check $(basename "$f")"; else bad "node --check $(basename "$f") rc=$rc"; fi
  done
else
  skip "no node on PATH — validators NOT checked on this host"
fi

say "## 4. Shipped validator suites pass (upstream suites, own verdict)"
if command -v node >/dev/null 2>&1; then
  for f in "$SKILL"/*.test.cjs; do
    out=$(node "$f" 2>&1); rc=$?
    fails=$(printf '%s\n' "$out" | grep -c '^# fail 0')
    if [ "$rc" -eq 0 ] && [ "$fails" -ge 1 ]; then
      ok "$(basename "$f") rc=0  '# fail 0' present"
    else
      bad "$(basename "$f") rc=$rc  '# fail 0' count=$fails"
    fi
  done
else
  skip "no node on PATH — validator suites NOT run on this host"
fi
rule

say "## 5. Repo gates"
for spec in \
  "tests/test_cloudflare_security_audit_skill.py" \
  "tests/test_skill_code_assets_parse.py tests/test_skills_loadable_check.py tests/test_skill_references_current.py"
do
  out=$(cd "$REPO" && bash tests/run-tests.sh $spec -q 2>&1); rc=$?
  last=$(printf '%s\n' "$out" | grep -E '^[0-9]+ (passed|failed)|passed|failed' | tail -1)
  if [ "$rc" -eq 0 ]; then ok "run-tests.sh $spec -> rc=0  [$last]"; else bad "run-tests.sh $spec -> rc=$rc  [$last]"; fi
done

out=$(cd "$REPO" && bash ops/scripts/manage/gen-skills-manifest.sh --check 2>&1); rc=$?
if [ "$rc" -eq 0 ]; then ok "gen-skills-manifest.sh --check -> rc=0 (manifest fresh)"; else bad "manifest NOT fresh rc=$rc: $out"; fi
rule

say "## 6. Secret-leak detector over the vendored skill"
out=$(bash "$REPO/ops/scripts/secret-leak-detector.sh" "$SKILL" 2>&1); rc=$?
if [ "$rc" -eq 0 ]; then ok "secret-leak-detector.sh -> rc=0"; else bad "secret-leak-detector.sh -> rc=$rc"; printf '%s\n' "$out" | tail -20; fi
rule

say "## 7. Captured runs — the guard was watched to FAIL, then to PASS"
# Both captures are committed byte-identical to the run's own stdout (md5 shown).
# They live under docs/evidence/ as .txt because *.log is gitignored — a capture
# written to an ignored path is not evidence, it is a file no reviewer can read.
for pair in "RED:the skill was not yet vendored" "GREEN:the skill was vendored"; do
  kind="${pair%%:*}"; why="${pair#*:}"
  f="$HERE/cloudflare-security-audit-2026-10-23.$kind.txt"
  if [ -f "$f" ]; then
    say "      $kind ($why)"
    say "        path : docs/evidence/cloudflare-security-audit-2026-10-23.$kind.txt"
    say "        md5  : $(md5sum "$f" | cut -d' ' -f1)"
    say "        lines: $(wc -l <"$f")"
    say "        produced by: bash tests/run-tests.sh tests/test_cloudflare_security_audit_skill.py -q"
    say "        verdict    : $(grep -E '^=+ .*(passed|failed)' "$f" | tail -1)"
  else
    bad "$kind capture missing"
  fi
done
rule

if [ "$fail" -eq 0 ]; then
  say "RESULT: ALL PASS"
else
  say "RESULT: FAILURES PRESENT (see FAIL lines above)"
fi
exit "$fail"
