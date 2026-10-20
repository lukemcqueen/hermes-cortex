#!/usr/bin/env bash
# Re-verify the MCP-SDK version-skew guard, against a PINNED baseline and two fabricated SDKs.
#
# WHAT THIS PROVES, and why each case is needed:
#   gisu (2026-10-20) — an interpreter whose `mcp` imports perfectly but predates the 2.0
#   constructor API kills `mcp-servers/loop-gov-mcp.py` AT IMPORT, and because
#   `ops/scripts/loop-gov.py` loads that file with exec_module, the CLI adapter dies with it
#   ("governance is unavailable", exit 3) on every write gate. The same skew made
#   `fix-cortex-venv.py --check` — the check cortex-update.sh gates its repair on — print
#   "ok: imports all N declared requirements" and repair nothing.
#
#   The fabrication is deliberate: both SDK generations are built here, so the guard is
#   proven WITHOUT depending on which version this host happens to have installed. The
#   baseline is the RANGE BASE (git merge-base origin/main HEAD), never HEAD~1 — a relative
#   base starts containing the fix the moment this change commits.
#
#   bash docs/evidence/verify-mcp-sdk-guard.sh
# Exits 0 only if every claim below holds; 3 when it cannot run at all (no interpreter).
set -uo pipefail

REPO="${REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$REPO" || exit 2

FAILS=0
# ONE normaliser for every emitted line (Rule 16): this transcript is committed to a PUBLIC
# repo, so the home path and the checkout path are replaced at the GENERATOR — never patched
# by hand in the committed copy, which would soon disagree with the command printed above it.
norm() { sed -e "s|${WORK}|<work>|g" -e "s|${HOME}|~|g" -e "s|${REPO}|<repo>|g"; }
say() { printf '%s\n' "$*" | norm; }
ok() { say "  ok    $1"; }
bad() { say "  FAIL  $1"; FAILS=$((FAILS + 1)); }
# Raw captured output of a command under test, indented so it cannot be confused with a result.
raw() { printf '%s\n' "$*" | norm | sed 's/^/  | /'; }

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for cand in "$HOME/.hermes-cortex/venv/bin/python3" python3; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys' >/dev/null 2>&1; then
      PY="$cand"; break
    fi
  done
fi
[ -n "$PY" ] || { say "COULD NOT VERIFY — no usable python3 on this host"; exit 3; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/mcp-sdk-guard-XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT
say "MCP-SDK version-skew guard — re-runnable verification"
say "====================================================="
say "interpreter        : $PY ($("$PY" -c 'import sys; print(sys.version.split()[0])'))"
BASE="$(git merge-base origin/main HEAD)"
say "range base         : $BASE ($(git rev-parse --short "$BASE"))"
say "tip (this tree)    : $(git rev-parse --short HEAD)"
say "command            : bash docs/evidence/verify-mcp-sdk-guard.sh"
say "generated          : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
say ""


# ── The baseline: extracted, then ASSERTED to be the pre-change revision ──────────────
mkdir -p "$WORK/base"
git show "$BASE:mcp-servers/loop-gov-mcp.py" > "$WORK/base/loop-gov-mcp.prefix.py"
git show "$BASE:ops/scripts/manage/fix-cortex-venv.py" > "$WORK/base/fix-cortex-venv.prefix.py"

say "== baseline extraction =="
say "  pre-fix server : $WORK/base/loop-gov-mcp.prefix.py ($(wc -l < "$WORK/base/loop-gov-mcp.prefix.py") lines)"
say "  pre-fix fixer  : $WORK/base/fix-cortex-venv.prefix.py ($(wc -l < "$WORK/base/fix-cortex-venv.prefix.py") lines)"
# A baseline that is not the pre-change revision measures nothing: the guard this change ADDS
# must be ABSENT from it, and the extracted copy must still carry the ImportError-only guard.
if grep -q 'except ImportError:  # pragma: no cover' "$WORK/base/loop-gov-mcp.prefix.py"; then
  ok "the extracted baseline carries the OLD ImportError-only guard"
else
  bad "the extracted baseline does not look pre-change — it has no ImportError-only guard"
fi
if grep -q 'sdk-capability-probe' "$WORK/base/loop-gov-mcp.prefix.py"; then
  bad "the extracted baseline ALREADY contains the capability probe (baseline is not pre-change)"
else
  ok "the extracted baseline does NOT contain the capability probe"
fi
say ""

# ── Two fabricated SDKs, so neither direction depends on this host's version ──────────
build_sdk() {  # build_sdk <dir> <old|new>
  "$PY" - "$1" "$2" <<'PYEOF'
import pathlib, sys
root, gen = pathlib.Path(sys.argv[1]), sys.argv[2]
(root / "mcp" / "server").mkdir(parents=True, exist_ok=True)
(root / "mcp" / "types").mkdir(parents=True, exist_ok=True)
(root / "mcp" / "__init__.py").write_text(f'FAKE_SDK_GENERATION = "{gen}"\n')
(root / "mcp" / "types" / "__init__.py").write_text(
    "class Tool:\n"
    "    def __init__(self, name='', description='', inputSchema=None, **kw):\n"
    "        self.name, self.description = name, description\n"
    "        self.input_schema = inputSchema or {}\n"
    "    def model_dump(self):\n"
    "        return {'name': self.name, 'description': self.description}\n"
    "class TextContent:\n"
    "    def __init__(self, type='text', text=''):\n"
    "        self.type, self.text = type, text\n"
    "    def model_dump(self):\n"
    "        return {'type': self.type, 'text': self.text}\n"
    "class CallToolResult:\n"
    "    def __init__(self, content=None, is_error=False):\n"
    "        self.content, self.is_error = content or [], is_error\n"
    "    def model_dump(self):\n"
    "        return {'content': [c.model_dump() for c in self.content], 'isError': self.is_error}\n"
    "class ListToolsResult:\n"
    "    def __init__(self, tools=None):\n"
    "        self.tools = tools or []\n")
if gen == "new":
    # The 2.0 constructor API: mcp/server/lowlevel/server.py:15-20 in the fleet venv.
    ctor = ("class Server:\n"
            "    def __init__(self, name, *, on_list_tools=None, on_call_tool=None, **kw):\n"
            "        self.name = name\n")
else:
    ctor = ("class Server:\n"   # the decorator-era signature: these kwargs do not exist
            "    def __init__(self, name):\n"
            "        self.name = name\n")
(root / "mcp" / "server" / "__init__.py").write_text(ctor)
(root / "mcp" / "server" / "stdio.py").write_text(
    "class _Ctx:\n"
    "    async def __aenter__(self):\n"
    "        return (None, None)\n"
    "    async def __aexit__(self, *a):\n"
    "        return False\n"
    "def stdio_server():\n"
    "    return _Ctx()\n")
PYEOF
}

build_sdk "$WORK/sdk-old" old
build_sdk "$WORK/sdk-new" new
say "== fabricated SDKs (both generations, built here) =="
say "  old: $WORK/sdk-old  (Server(name) — rejects the 2.0 handler kwargs)"
say "  new: $WORK/sdk-new  (Server(name, on_list_tools=..., on_call_tool=...))"
say ""

# The loader probe: import a server module under a chosen SDK and report what it did.
LOAD_PROBE="$WORK/load-server.py"
cat > "$LOAD_PROBE" <<'PYEOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("gov_under_test", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print("SDK_FILE=%s" % getattr(sys.modules["mcp"], "__file__", "?"))
print("FAKE_GEN=%s" % getattr(sys.modules["mcp"], "FAKE_SDK_GENERATION", "?"))
print("MCP_AVAILABLE=%s" % mod.MCP_AVAILABLE)
result = mod._check_lock({})
print("HANDLER_OK=%s" % ("active" in result.model_dump()["content"][0]["text"]))
PYEOF

# The pre-fix server under the old SDK is the gisu failure. `env -u PYTHONPATH` is NOT used
# here on purpose: the fabricated SDK is injected VIA PYTHONPATH so it shadows site-packages.
say "== case 1: PRE-FIX server + OLD SDK (the gisu failure, reproduced) =="
out="$(PYTHONPATH="$WORK/sdk-old" "$PY" "$LOAD_PROBE" "$WORK/base/loop-gov-mcp.prefix.py" 2>&1)"; rc=$?
raw "$out"
say "  rc=$rc"
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "unexpected keyword argument 'on_list_tools'"; then
  ok "the pre-change module dies at import with exactly the reported TypeError"
else
  bad "the baseline did not reproduce the reported failure (rc=$rc)"
fi
if printf '%s' "$out" | grep -q "MCP_AVAILABLE="; then
  bad "the baseline produced output — it did not die at import, so case 2 proves nothing"
else
  ok "no output at all before the crash — the CLI adapter would exit 3"
fi
say ""

say "== case 2: THIS TREE's server + OLD SDK (guard engaged, CLI still drivable) =="
out="$(PYTHONPATH="$WORK/sdk-old" "$PY" "$LOAD_PROBE" "mcp-servers/loop-gov-mcp.py" 2>&1)"; rc=$?
raw "$out"
say "  rc=$rc"
if [ "$rc" -eq 0 ]; then ok "the module imports cleanly"; else bad "the module still dies at import (rc=$rc)"; fi
printf '%s' "$out" | grep -q "MCP_AVAILABLE=False" || bad "MCP_AVAILABLE was not False under an unusable SDK"
printf '%s' "$out" | grep -q "MCP_AVAILABLE=False" && ok "MCP_AVAILABLE=False (stdio serving declined)"
printf '%s' "$out" | grep -q "HANDLER_OK=True" || bad "the handlers are not drivable under an unusable SDK"
printf '%s' "$out" | grep -q "HANDLER_OK=True" && ok "the handlers still work — the CLI adapter is usable"
printf '%s' "$out" | grep -q "cannot serve this module" || bad "no warning naming the cause"
printf '%s' "$out" | grep -q "cannot serve this module" && ok "a warning names the cause on stderr"
printf '%s' "$out" | grep -q "needs the mcp 2.0 constructor API" || bad "the warning does not name the required API"
say ""

say "== case 3: THIS TREE's server + NEW SDK (the guard must NOT fire) =="
out="$(PYTHONPATH="$WORK/sdk-new" "$PY" "$LOAD_PROBE" "mcp-servers/loop-gov-mcp.py" 2>&1)"; rc=$?
raw "$out"
say "  rc=$rc"
printf '%s' "$out" | grep -q "MCP_AVAILABLE=True" || bad "a usable SDK was degraded away"
printf '%s' "$out" | grep -q "MCP_AVAILABLE=True" && ok "the SDK is used, not degraded"
printf '%s' "$out" | grep -q "cannot serve this module" && bad "the warning fired on a usable SDK"
printf '%s' "$out" | grep -q "cannot serve this module" || ok "no warning on a usable SDK"
say ""

# ── The venv checker: an importable-but-unusable module must be a GAP ────────────────
# The fixer strips PYTHONPATH from the target's environment on purpose, so the fabricated SDK
# is injected by an interpreter WRAPPER — which is what a real venv's site-packages supplies.
make_stub_venv() {  # make_stub_venv <venv-dir> <sdk-dir>
  mkdir -p "$1/bin"
  printf '#!/bin/sh\nPYTHONPATH="%s" exec "%s" "$@"\n' "$2" "$PY" > "$1/bin/python3"
  chmod +x "$1/bin/python3"
}
printf 'mcp>=2.0\n' > "$WORK/reqs.txt"
make_stub_venv "$WORK/venv-old" "$WORK/sdk-old"
make_stub_venv "$WORK/venv-new" "$WORK/sdk-new"

say "== case 4: PRE-FIX fixer --check against an importable-but-too-old mcp (the gap) =="
out="$("$PY" "$WORK/base/fix-cortex-venv.prefix.py" --check --venv "$WORK/venv-old" --requirements "$WORK/reqs.txt" 2>&1)"; rc=$?
raw "$out"
say "  rc=$rc"
if [ "$rc" -eq 0 ]; then ok "the OLD check reported a broken venv as healthy (this is the defect)"; else bad "the baseline check already flagged it (rc=$rc) — then this fix fixes nothing"; fi
printf '%s' "$out" | grep -q "imports all 1 declared requirements" && ok "it claimed 'imports all … declared requirements'"
say ""

say "== case 5: THIS TREE's fixer --check, same venv (must be a GAP, rc=3) =="
out="$("$PY" "ops/scripts/manage/fix-cortex-venv.py" --check --venv "$WORK/venv-old" --requirements "$WORK/reqs.txt" 2>&1)"; rc=$?
raw "$out"
say "  rc=$rc"
[ "$rc" -eq 3 ] && ok "rc=3 — cortex-update.sh's repair gate now sees it" || bad "expected rc=3, got rc=$rc"
printf '%s' "$out" | grep -q "incompatible" && ok "reported as INCOMPATIBLE, not as missing" || bad "the report does not name the real fault"
printf '%s' "$out" | grep -q "on_list_tools" && ok "the report names the API the SDK lacks" || bad "the report does not name the API"
say ""

say "== case 6: THIS TREE's fixer --check against a usable mcp (must pass, rc=0) =="
out="$("$PY" "ops/scripts/manage/fix-cortex-venv.py" --check --venv "$WORK/venv-new" --requirements "$WORK/reqs.txt" 2>&1)"; rc=$?
raw "$out"
say "  rc=$rc"
[ "$rc" -eq 0 ] && ok "rc=0 — no false repairee, so a deploy does not reinstall a healthy venv" || bad "expected rc=0, got rc=$rc"
say ""

# ── The real host: what THIS interpreter's SDK is, and that the CLI runs either way ──
say "== case 7: this host's interpreters and the deployed CLI =="
for cand in "$HOME/.hermes-cortex/venv/bin/python3" "$(command -v python3)"; do
  [ -n "$cand" ] || continue
  ver="$(env -u PYTHONPATH -u PYTHONHOME "$cand" -c \
        "import importlib.metadata as m; from mcp.server import Server; import inspect; \
print(m.version('mcp'), '| on_list_tools accepted:', 'on_list_tools' in inspect.signature(Server.__init__).parameters)" 2>&1)"
  say "  $cand -> $ver"
done
if [ -f "$HOME/.hermes-cortex/scripts/loop-gov.py" ]; then
  for cand in python3 "$HOME/.hermes-cortex/venv/bin/python3"; do
    out="$(env -u PYTHONPATH -u PYTHONHOME "$cand" "$HOME/.hermes-cortex/scripts/loop-gov.py" --list 2>&1)"; rc=$?
    tools="$(printf '%s' "$out" | grep -c 'begin_change\|end_change')"
    say "  loop-gov.py --list under '$cand': rc=$rc, begin/end_change lines=$tools"
    if [ "$rc" -eq 0 ] && [ "$tools" -ge 2 ]; then
      ok "the deployed CLI answers under $cand"
    else
      bad "the deployed CLI failed under $cand (rc=$rc)"
    fi
    printf '%s' "$out" | grep -q "cannot serve this module" \
      && say "        (this interpreter's mcp is behind — the warning above is the signal)"
  done
else
  say "  SKIP — no deployed loop-gov.py on this host"
fi

say ""
say "====================================================="
say "exit code          : $([ "$FAILS" -eq 0 ] && printf 0 || printf 1)"
if [ "$FAILS" -eq 0 ]; then
  say "RESULT: ALL CLAIMS HOLD"
  exit 0
fi
say "RESULT: $FAILS CLAIM(S) FAILED"
exit 1
