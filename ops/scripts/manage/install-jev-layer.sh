#!/usr/bin/env bash
# Install or upgrade the Jev decision layer on THIS host.
#
# Jev takes the cheap decisions (which model a turn needs, which skill to load,
# which search results to open) so the expensive model does only the thinking.
# It is OPTIONAL per host — this script is the one way to put it on a host, and
# it is idempotent, so re-running it is the upgrade path.
#
#   install-jev-layer.sh --check          report what would change, change nothing
#   install-jev-layer.sh                  install / upgrade, then verify
#   install-jev-layer.sh --force-pools    also rewrite the routing pools (cost-ordered)
#   install-jev-layer.sh --commit <sha>   pin a different upstream revision
#
# What it does, in order:
#   1. clone or fetch the upstream repo (MIT) at the PINNED commit
#   2. run its installer with --check, print that, then run it for real
#   3. `jev doctor` — key present, endpoint reachable, pools loaded
#   4. write COST-ORDERED routing pools if none exist (or --force-pools)
#   5. print a VERDICT
#
# It never prints a credential, never uses sudo, and never touches the API key:
# `jev setup-key` is a separate, private step the person runs themselves.
#
# WHY THE POOLS ARE WRITTEN HERE RATHER THAN LEFT TO `jev models suggest --write`:
# that command bands by price and on the first host it was installed on it put a
# model at the head of medium/coding costing 6.5x what we already run — and first
# fit wins, so switching routing on as-shipped would have RAISED spend on every
# medium coding turn. Measured $/M blended at the time of writing: our default
# 0.56, qwen3.7-flash 0.05, kimi-k2.7-code 3.66. The doctor's `Jev decision layer`
# check now fails a pool that leads with a dearer model while routing is on, so
# this mistake cannot ship quietly twice.
set -u

UPSTREAM="${JEV_UPSTREAM:-https://github.com/kerpopule/hermes-jev-skills.git}"
PIN="${JEV_PIN:-2f490beb7f07628366186f2b17eed6c36cc46b94}"
CHECKOUT="${JEV_CHECKOUT:-$HOME/hermes-jev-skills}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
MODE="install"
FORCE_POOLS=0

while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE="check" ;;
    --force-pools) FORCE_POOLS=1 ;;
    --commit) shift; PIN="${1:-}" ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '%s\n' "$*"; }
die() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null 2>&1 || die "git is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required (the kit is stdlib-only, 3.9+)"
[ -n "$PIN" ] || die "empty --commit; refusing to install an unpinned revision"

say "== 1. checkout $PIN =="
if [ -d "$CHECKOUT/.git" ]; then
  git -C "$CHECKOUT" fetch --quiet origin || die "could not fetch from $UPSTREAM"
  git -C "$CHECKOUT" checkout --quiet "$PIN" || die "could not check out $PIN"
  say "  updated $CHECKOUT"
else
  git clone --quiet "$UPSTREAM" "$CHECKOUT" || die "could not clone $UPSTREAM"
  git -C "$CHECKOUT" checkout --quiet "$PIN" || die "could not check out $PIN"
  say "  cloned $CHECKOUT"
fi
ACTUAL="$(git -C "$CHECKOUT" rev-parse HEAD)"
[ "$ACTUAL" = "$PIN" ] || say "  NOTE: HEAD is $ACTUAL, not the pin $PIN"
say "  revision: $ACTUAL"

say "== 2. the upstream installer =="
if [ "$MODE" = "check" ]; then
  python3 "$CHECKOUT/install.py" --check --hermes-home "$HERMES_HOME" || die "installer --check failed"
  say "  (check mode: nothing was installed)"
else
  # The pre-flight result is PRINTED and its failure is fatal: a check that fails
  # and is ignored is a check that was never run, and the real install would then
  # fail later with a worse message (or half-install).
  PREFLIGHT="$(python3 "$CHECKOUT/install.py" --check --hermes-home "$HERMES_HOME" 2>&1)"
  PREFLIGHT_RC=$?
  [ -n "$PREFLIGHT" ] && printf '%s\n' "$PREFLIGHT"
  [ "$PREFLIGHT_RC" -eq 0 ] || die "the upstream installer's pre-flight check failed (rc=$PREFLIGHT_RC) — nothing was installed"
  python3 "$CHECKOUT/install.py" --hermes-home "$HERMES_HOME" || die "installer failed"
fi

DOCTOR_FAILED=0
say "== 3. jev doctor =="
JEV_BIN="$HERMES_HOME/bin/jev"
[ -x "$JEV_BIN" ] || JEV_BIN="$(command -v jev 2>/dev/null || true)"
if [ -z "$JEV_BIN" ]; then
  say "  SKIP: no \`jev\` command found — the gateway picks it up from \$HERMES_HOME/bin after a restart"
elif [ "$MODE" = "check" ]; then
  say "  (check mode: not running doctor)"
else
  if ! "$JEV_BIN" doctor; then
    say "  FAIL: \`jev doctor\` reported a problem — the layer is installed but NOT VERIFIED"
    DOCTOR_FAILED=1
  fi
fi

say "== 4. cost-ordered routing pools =="
POOLS="$HERMES_HOME/jev/routing.json"
if [ -f "$POOLS" ] && [ "$FORCE_POOLS" -eq 0 ]; then
  say "  pools already exist at $POOLS (use --force-pools to reorder them)"
elif [ "$MODE" = "check" ]; then
  say "  would write $POOLS with the cheap model first in every simple/medium pool"
else
  if [ -x "$JEV_BIN" ]; then
    if ! SEED_OUT="$("$JEV_BIN" models suggest --write 2>&1)"; then
      say "  WARN: \`jev models suggest --write\` failed; writing the cost-ordered draft directly. Its output:"
      printf '%s\n' "$SEED_OUT" | head -5
    fi
  else
    say "  WARN: no \`jev\` command yet; writing the cost-ordered draft directly"
  fi
  JEV_POOLS="$POOLS" python3 - <<'PY'
import json, os, pathlib

path = pathlib.Path(os.environ["JEV_POOLS"])
CHEAP = "openrouter:qwen/qwen3.7-flash"                 # cheapest capable flash we found
TRUSTED = "openrouter:deepseek/deepseek-v4.1-flash"     # the model the fleet already runs
try:
    data = json.loads(path.read_text())
except (OSError, json.JSONDecodeError):
    data = {"mode": "redacted-text", "exclude": ["*:free", "cloudflare-ai-gateway:*"], "tiers": {}}
tiers = data.setdefault("tiers", {})

def front(models, first):
    out = [first]
    for model in models or []:
        if "moonshotai/kimi" in model:   # dearer than what we run: never route there by accident
            continue
        if model not in out:
            out.append(model)
    return out

for tier, first in (("simple", CHEAP), ("medium", TRUSTED)):
    for spec, models in (tiers.get(tier) or {}).items():
        tiers[tier][spec] = front(models, first)
# `hard` is left alone: escalation there is deliberate spend, not a mistake.
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, indent=2) + "\n")
print(f"  wrote {path} — simple/* leads with {CHEAP}, medium/* with {TRUSTED}, hard/* untouched")
PY
fi

say
if [ "$MODE" = "check" ]; then
  say "VERDICT: check complete — nothing changed"
  exit 0
fi
if [ "$DOCTOR_FAILED" -ne 0 ]; then
  say "VERDICT: installed/upgraded at $ACTUAL, but NOT VERIFIED — \`jev doctor\` failed above"
  exit 1
fi
say "VERDICT: installed/upgraded at $ACTUAL, doctor verified"
say "NEXT: restart the gateway (the plugin loads at start), then in a session:"
say "  /jev            status"
say "  /jev routing shadow    decide and log, switch nothing  <- start here"
