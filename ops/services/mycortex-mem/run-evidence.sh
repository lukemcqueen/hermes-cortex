#!/usr/bin/env bash
# run-evidence.sh — regenerate EVIDENCE.md, the committed proof that psql can never
# prompt from the mycortex-mem store.
#
# The bug: without `-w`, psql prompts on /dev/tty when MYCORTEX_MEM_PASSWORD is empty or
# the PGPASSFILE is wrong. The prompt never reaches stdout/stderr, so the caller HANGS
# (or times out) instead of failing — and in a TUI harness the prompt is written into
# the prompt area.
#
# Three things are recorded, all by RUNNING code:
#   1. the command-composition guards (the flag is present at all four invocation sites);
#   2. the RUNTIME fail-fast test (real store path, no usable password, psql stand-in);
#   3. the RED case: the same runtime test against a copy of the store with `-w` REMOVED
#      must FAIL — otherwise the test proves nothing.
#
# Deliberately NOT `set -e`: the guard failures below are collected and reported with
# their exit codes, which `set -e` would turn into a silent mid-script exit.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE" && git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO" ] || [ ! -d "$REPO" ]; then
  REPO="$(cd "$HERE/../../.." && pwd)"
fi
OUT="$HERE/EVIDENCE.md"
PY="${MYCORTEX_EVIDENCE_PYTHON:-python3}"
GUARD_TESTS="$REPO/tests/test_mycortex_mem_psql_no_password.py"
PLUGIN="$REPO/plugins/mycortex-mem/__init__.py"
STORE="$HERE/store.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "→ command-composition + runtime guards"
guard_out="$("$PY" -m pytest "$GUARD_TESTS" -q 2>&1)"; guard_rc=$?

echo "→ RED case (a store with -w removed must FAIL the runtime test)"
"$PY" - "$STORE" "$TMP/store-no-w.py" <<'PY'
import pathlib, sys

source = pathlib.Path(sys.argv[1]).read_text()
patched = source.replace('"-d", self._db_name, "-w", "-v"', '"-d", self._db_name, "-v"', 1)
patched = patched.replace('f"-w -v ON_ERROR_STOP=1 -t -A"', 'f"-v ON_ERROR_STOP=1 -t -A"', 1)
assert patched != source, "the -w anchors moved — update this RED case"
assert '"-w"' not in patched and '"-w ' not in patched, "the flag survived the mutation"
pathlib.Path(sys.argv[2]).write_text(patched)
PY
red_out="$(MYCORTEX_MEM_STORE_PATH="$TMP/store-no-w.py" "$PY" -m pytest \
  "$GUARD_TESTS::test_store_fails_fast_and_never_prompts_without_a_password" -q 2>&1)"; red_rc=$?

verdict() { [ "$1" -eq 0 ] && echo "PASS (exit 0)" || echo "FAIL (exit $1)"; }

{
  echo "# mycortex-mem psql — committed, re-runnable evidence"
  echo
  echo "Regenerate with: \`bash ops/services/mycortex-mem/run-evidence.sh\`"
  echo
  echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "Artifacts this evidence was produced from (verify with \`sha256sum\`):"
  echo
  echo '```'
  for artifact in "$STORE" "$PLUGIN" "$GUARD_TESTS" "${BASH_SOURCE[0]}"; do
    printf '%s  %s\n' "$(sha256sum "$artifact" | cut -d' ' -f1)" "${artifact#"$REPO"/}"
  done
  echo '```'
  echo
  echo "## 1. Command composition + runtime fail-fast — $(verdict "$guard_rc")"
  echo
  echo '```'
  printf '%s\n' "$guard_out" | tail -12
  echo '```'
  echo
  echo "## 2. RED case — the runtime test against a store WITHOUT \`-w\` must fail: $(verdict "$red_rc")"
  echo
  echo '```'
  printf '%s\n' "$red_out" | tail -12
  echo '```'
  echo
  echo "Proves: \`-w\` is present at every invocation site, and with no usable password the"
  echo "store raises \`StoreUnavailable\` promptly instead of waiting on an invisible prompt"
  echo "(fail-open, no hang) — while a store lacking the flag is caught by the same test."
  echo
  echo "Does not prove: behaviour against a live password-requiring server reachable from"
  echo "this host (none is); that check belongs on the harness host after deploy."
} > "$OUT"

# A public repo must not carry a host path — `$HOME` is a fact about the reader's
# machine, not this one. Portable rewrite (sed -i differs across GNU/BSD).
sed -E 's#/home/[A-Za-z0-9._-]+#$HOME#g' "$OUT" > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"

echo "→ wrote $OUT"
[ "$guard_rc" -eq 0 ] || { echo "❌ the guards failed"; exit 1; }
[ "$red_rc" -ne 0 ] || { echo "❌ the RED case PASSED — the runtime test is not a guard"; exit 1; }
echo "✅ evidence regenerated and consistent"
