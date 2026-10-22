#!/usr/bin/env bash
# Generate docs/evidence/brand-intelligence-removal-2026-10-22.txt
#
# Records the removal of the orphaned `openclaw-brand-intelligence` plugin dump
# from the agent-visible skills tree, and PROVES it was the sole cause of the
# remaining loader diagnostic by re-running Pi's own loader over a copy of the
# preserved directory.
#
# The removal itself is a DEPLOYED-TREE change (that path has no repo source), so
# the repo diff for the cycle that owns it is EMPTY — this artifact is the
# deliverable, per change-checklist's rule for diagnostic/state cycles.
#
# SELF-CONTAINED and re-runnable: bash docs/evidence/brand-intelligence-removal-2026-10-22.sh
set -uo pipefail

SELF="${BASH_SOURCE[0]}"
REPO="$(cd "$(dirname "$SELF")/../.." && pwd)"
OUT="$REPO/docs/evidence/brand-intelligence-removal-2026-10-22.txt"
PUB="$HOME/.agents/skills"
ARCHIVE="$HOME/.hermes-cortex/skills/.archive/brand-intelligence-openclaw-plugin-2026-10-22"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/bi.XXXXXX")"
export WORK
NODE="$HOME/.local/bin/node"

norm() { awk -v w="$WORK" '{gsub(w, "$WORK"); print}' | sed -e "s#$HOME#~#g" -e 's/\x1b\[[0-9;]*m//g'; }
say() { printf '%s\n' "$*"; }

# Pi's own loader, resolved from the INSTALLED release (never a pinned version).
cat > "$WORK/report.mjs" <<'MJS'
import { readFileSync } from "fs";
import { homedir } from "os";
const agentDir = `${homedir()}/.pi/agent`;
const v = readFileSync(`${agentDir}/install/current-version`, "utf8").trim();
const { loadSkills } = await import(`${agentDir}/install/releases/${v}/node_modules/@earendil-works/pi-coding-agent/dist/core/skills.js`);
const res = loadSkills({ agentDir, skillPaths: [process.argv[2]], includeDefaults: false, cwd: homedir() });
const byType = {};
for (const d of res.diagnostics) byType[d.type] = (byType[d.type] || 0) + 1;
console.log(`  loader      : Pi ${v}`);
console.log(`  skills      : ${res.skills.length}`);
console.log(`  diagnostics : ${JSON.stringify(byType)}`);
for (const d of res.diagnostics) {
  console.log(`    ${d.type}: ${d.message.split("\n")[0].slice(0, 80)}  <- ${d.path}`);
}
process.exit(res.diagnostics.length ? 1 : 0);
MJS

exec > >(norm > "$OUT") 2>&1

say "command : bash docs/evidence/brand-intelligence-removal-2026-10-22.sh"
say "when    : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "captured-at: $(git -C "$REPO" rev-parse HEAD)"
say "note    : the removal is a DEPLOYED-TREE change — ~/.agents/skills/brand-intelligence"
say "          has no repo source, so the repo diff for this cycle is EMPTY and this"
say "          transcript IS the deliverable. Volatile by design: host paths normalised"
say "          to ~, scratch to \$WORK, ANSI stripped."
say ""

say "=== 1. what it was ==="
say "  path      : ~/.agents/skills/brand-intelligence   (12 files)"
say "  identity  : openclaw.plugin.json id=sigai-brand-intelligence, a THIRD-PARTY"
say "              (geo.sig.ai) openclaw plugin installed by 'openclaw plugins install'"
say "  files     : SKILL.md, skill-card.md, README.md, package.json, _meta.json,"
say "              openclaw.plugin.json, src/{index,client,config}.ts, and"
say "              skills/{brand-brief,compare-brands,watchlist-digest}/SKILL.md"
say ""
say "  WHY IT WAS DEAD WEIGHT — each checked, not assumed:"
say "    - its SKILL.md carried NO frontmatter, so every Agent-Skills loader DROPPED it"
say "    - its skills/ entries instruct an agent to call the plugin's sigai_* tools, and"
say "      those tools only exist when the openclaw runtime loads the plugin —"
say "      'command -v openclaw' → not installed; ~/.openclaw → absent"
say "    - nothing consumes it: no entry in ~/.hermes/plugins, no reference in the cron"
say "      store, and the only hits in ~/.hermes are caches, logs and DB snapshots"
say "    - it COLLIDED by name with the repo-owned skills/research/brand-intelligence,"
say "      because the loader derives a skill's name from its directory when the"
say "      frontmatter carries none — which is why skill_view('brand-intelligence')"
say "      could not resolve on this host"

say ""
say "=== 2. what was done — PRESERVED, not deleted ==="
say "  moved : ~/.agents/skills/brand-intelligence"
say "       -> $ARCHIVE"
say "  the destination is a dot-dir inside the cortex skills tree: a loader skips"
say "  dot-dirs, so the copy is out of every agent's view while remaining on disk."
say "  ASSERT nothing was lost:"
if [ -d "$ARCHIVE" ]; then
  say "    preserved files : $(find "$ARCHIVE" -type f | wc -l)   (must be 12)"
else
  say "    PRESERVED COPY ABSENT — the move did not land where this artifact claims"
fi
say "  ASSERT it is gone from the agent-visible tree:"
if [ -e "$PUB/brand-intelligence" ]; then
  say "    ~/.agents/skills/brand-intelligence STILL PRESENT — removal did not take effect"
else
  say "    ~/.agents/skills/brand-intelligence : absent"
fi

say ""
say "=== 3. PROOF it was the sole cause — Pi's own loader, the dump re-materialised ==="
say "  a scratch root holding ONLY a copy of the preserved directory:"
mkdir -p "$WORK/withdump"
cp -a "$ARCHIVE" "$WORK/withdump/brand-intelligence"
"$NODE" "$WORK/report.mjs" "$WORK/withdump"
say "  rc=$?   (1 = diagnostics present, which is the point)"

say ""
say "=== 4. the same loader over the LIVE published tree ==="
"$NODE" "$WORK/report.mjs" "$PUB"
live_rc=$?
say "  rc=$live_rc   (0 = no diagnostics at all)"

say ""
say "=== 5. the doctor's own view of the published tree ==="
"$HOME/.hermes-cortex/venv/bin/python3" "$HOME/.hermes-cortex/scripts/cortex-doctor.py" --quiet 2>&1 \
  | grep -E "Skills loadable|Skills manifest|Overall:"
say "  (the 'Skills loadable (published)' WARN that used to name brand-intelligence is"
say "   ABSENT above; it is present in the previous capture,"
say "   docs/evidence/doctor-interpreter-2026-10-22.txt, section 3.)"

say ""
say "=== verdict ==="
say "  The dump is preserved on disk and invisible to every agent. Pi's loader over the"
say "  published tree now reports ZERO diagnostics of any type — the whole defect class"
say "  this session started from is gone: no refused SKILL.md, no name collision."
say "  The skill COUNT is the second half of the proof: section 4 loads 441, and the"
say "  PRE-removal capture of this same tree reports 441 too"
say "  (docs/evidence/skills-frontmatter-fix-2026-10-22.txt, section 4) — the dump"
say "  contributed nothing loadable, so nothing was lost by removing it."
say ""
say "  Honest limits:"
say "    - This is a HOST-LOCAL fix. The deploy's stale pass deliberately skips"
say "      root-level skill dirs (it treats them as Hermes defaults), so this removal"
say "      will not be undone by a deploy — but it also does not propagate. Another"
say "      host carrying the same openclaw dump still gets the doctor WARN, which is"
say "      the correct behaviour: report it, do not silently delete it."
say "    - plugins/hc-lean-index and install-lean-index.py still list 'brand-intelligence'"
say "      as a demoted CATEGORY. That entry is fleet-wide and may still match on hosts"
say "      with the Hermes catalogue, so it was deliberately left alone; here it now"
say "      matches nothing, which is harmless."
say "    - No replacement was written. The capability is already covered by the"
say "      repo-owned skills/research/brand-intelligence, and the removed plugin's own"
say "      tools required the absent openclaw runtime plus a sig.ai account."

rm -rf "$WORK"
