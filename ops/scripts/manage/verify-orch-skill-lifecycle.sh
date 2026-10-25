#!/usr/bin/env bash
# verify-orch-skill-lifecycle.sh — prove the 2026-10-26 no-op was justified.
#
# Exits non-zero when the claim behind the no-op stops holding:
#   "every skill named in the last-48h Learning Reports is already committed
#    AND already deployed (repo == deployed), so there is nothing to upgrade."
#
# Overridable so the check measures THIS run's file set, never a frozen list:
#   SKILLS="cortex-bus change-checklist" ./verify-orch-skill-lifecycle.sh
#
# Probes the probe: see test-verify-orch-skill-lifecycle.sh
set -uo pipefail

REPO="${REPO:-$HOME/hermes-cortex}"
DEPLOYED="${DEPLOYED:-$HOME/.hermes/skills}"
WINDOW_HOURS="${WINDOW_HOURS:-48}"
SKILLS="${SKILLS:-}"

fail=0
say() { printf '%s\n' "$*"; }

[ -d "$REPO" ] || { say "FAIL: repo not found: $REPO"; exit 2; }
[ -d "$DEPLOYED" ] || { say "FAIL: deployed skills tree not found: $DEPLOYED"; exit 2; }

# ---- 1. Skill drift: the doctor is the authority on repo<->deployed parity ----
DOCTOR="$REPO/ops/scripts/manage/cortex-doctor.py"
RECON="$REPO/ops/scripts/manage/reconcile-stranded-skills.py"
[ -f "$DOCTOR" ] || { say "FAIL: doctor not found at $DOCTOR"; exit 2; }
[ -f "$RECON" ]  || { say "FAIL: reconciler not found at $RECON"; exit 2; }

doc_out="$(cd "$REPO" && python3 "$DOCTOR" --quiet 2>&1)"
doc_rc=$?
lines=$(printf '%s\n' "$doc_out" | grep -c .)
# Run-evidence bar: the real doctor emits >=100 per-check lines, AND it must
# print an actual per-check verdict. A real run with ANY warning still exits 1,
# so rc alone cannot separate "ran" from "crashed" — require the verdict line.
if [ "$lines" -lt 100 ] || ! printf '%s\n' "$doc_out" | grep -qE '^[[:space:]]*[✅❌⚠️➖]'; then
  say "COULD NOT VERIFY: doctor produced $lines lines / no verdict (rc=$doc_rc) — not a real run"
  exit 2
fi
drift="$(printf '%s\n' "$doc_out" | grep -iE '^[[:space:]]*[✅❌⚠️].*Skill drift' | head -1)"
case "$drift" in
  *"✅ Skill drift"*) say "OK   doctor:${drift#*Skill drift}" ;;
  "")                 say "COULD NOT VERIFY: doctor printed no 'Skill drift' line"; exit 2 ;;
  *)                  say "FAIL doctor skill drift: $drift"; fail=1 ;;
esac

# ---- 2. Stranded content (deployed-only lessons) must be zero ----------------
rec_out="$(cd "$REPO" && python3 "$RECON" 2>&1)"
rec_rc=$?
stranded="$(printf '%s\n' "$rec_out" | grep -oE 'stranded: [0-9]+' | head -1 | grep -oE '[0-9]+$')"
if [ -z "$stranded" ]; then
  # exit codes are ambiguous here; require the named count, not rc
  say "COULD NOT VERIFY: reconciler printed no 'stranded: N' (rc=$rec_rc)"
  printf '%s\n' "$rec_out" | sed 's/^/    /'
  exit 2
fi
if [ "$stranded" -eq 0 ]; then say "OK   stranded: 0"; else say "FAIL stranded: $stranded"; fail=1; fi

# ---- 3. Each reported skill: committed recently AND deployed == repo ---------
if [ -z "$SKILLS" ]; then
  SKILLS="$(cd "$REPO" && python3 - <<'PY'
import json,glob,os,re,datetime
pat=re.compile(r'Generated:\s*([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.\-+]+)')
now=datetime.datetime.now(datetime.timezone.utc); names=set()
hours=float(os.environ.get("WINDOW_HOURS","48"))
for f in glob.glob(os.path.expanduser("~/.hermes-cortex/state/learning-reports/*.md")):
    raw=open(f,encoding='utf-8',errors='replace').read()
    try:
        j=raw.index('{'); text=json.loads(raw[j:]).get('text',raw)
    except Exception: text=raw
    text=text.replace('\\n','\n')
    m=pat.search(text)
    if not m: continue
    try: dt=datetime.datetime.fromisoformat(m.group(1).replace('Z','+00:00'))
    except Exception: continue
    if dt.tzinfo is None: dt=dt.replace(tzinfo=datetime.timezone.utc)
    if (now-dt).total_seconds()/3600>hours: continue
    for line in text.splitlines():
        s=line.strip()
        if s.startswith('[MOD]') or s.startswith('[NEW]'): names.add(s.split()[1].split('(')[0])
print(" ".join(sorted(names)))
PY
)"
fi
say "checking $(printf '%s\n' $SKILLS | wc -w) reported skill(s): window=${WINDOW_HOURS}h"
for n in $SKILLS; do
  rel="$(cd "$REPO" && find skills -maxdepth 2 -type d -name "$n" | head -1)"
  repo_f="$REPO/${rel:+$rel/}SKILL.md"; dep_f="$DEPLOYED/${rel#skills/}/SKILL.md"
  [ -n "$rel" ] || { say "  WARN $n: no repo source found (fleet-only skill)"; continue; }
  if [ ! -f "$repo_f" ]; then say "  FAIL $n: repo file missing ($repo_f)"; fail=1; continue; fi
  if [ ! -f "$dep_f" ];  then say "  FAIL $n: deployed file missing ($dep_f)"; fail=1; continue; fi
  a=$(md5sum "$repo_f" | cut -d' ' -f1); b=$(md5sum "$dep_f" | cut -d' ' -f1)
  if [ "$a" = "$b" ]; then say "  OK   $n (repo==deployed)"; else say "  FAIL $n: deployed != repo -> a deploy is outstanding"; fail=1; fi
done

if [ "$fail" -eq 0 ]; then say "PASS: no unapplied skill content in the window"; exit 0; fi
say "FAIL: unapplied content exists — the no-op is no longer justified"; exit 1
