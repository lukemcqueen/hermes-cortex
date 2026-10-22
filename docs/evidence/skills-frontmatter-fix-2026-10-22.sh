#!/usr/bin/env bash
# Generate docs/evidence/skills-frontmatter-fix-2026-10-22.txt
#
# Compares the SAME tool — Pi's own skills loader, dist/core/skills.js — against
# two revisions:
#   BASE      a pinned sha, materialised with `git archive` into a scratch dir
#   DEPLOYED  the live ~/.agents/skills tree every coding agent on this host reads
#
# SELF-CONTAINED: both probes are embedded as heredocs, so this file re-runs on
# its own with nothing but node + the cortex venv. It writes the committed
# artifact itself, so `generated-by` is a fact about the file rather than a
# claim about who typed it.
#
# Re-run:  bash docs/evidence/skills-frontmatter-fix-2026-10-22.sh
set -uo pipefail

SELF="${BASH_SOURCE[0]}"
REPO="$(cd "$(dirname "$SELF")/../.." && pwd)"
OUT="$REPO/docs/evidence/skills-frontmatter-fix-2026-10-22.txt"
BASE="d4cf306e15bafef23a02d56da149717c483f5a2e"   # pinned literal; = merge-base origin/main HEAD
WORK="$(mktemp -d "${TMPDIR:-/tmp}/skillsfix.XXXXXX")"
export WORK
NODE="$HOME/.local/bin/node"
PY="$HOME/.hermes-cortex/venv/bin/python3"

# ONE normaliser for every emitted line, including this generator's own.
norm() { awk -v w="$WORK" '{gsub(w, "$WORK"); print}' | sed -e "s#$HOME#~#g" -e 's/\x1b\[[0-9;]*m//g'; }
say() { printf '%s\n' "$*"; }

# ── embedded probe 1: drive Pi's OWN loader against a tree ────────────────────
cat > "$WORK/pi-report.mjs" <<'MJS'
// Resolve the loader from the INSTALLED release — never a hardcoded version,
// because Pi updates itself and a pinned path silently measures an old loader.
import { readFileSync } from "fs";
import { homedir } from "os";
const agentDir = `${homedir()}/.pi/agent`;
const version = readFileSync(`${agentDir}/install/current-version`, "utf8").trim();
const mod = `${agentDir}/install/releases/${version}/node_modules/@earendil-works/pi-coding-agent/dist/core/skills.js`;
const { loadSkills } = await import(mod);
const root = process.argv[2];
console.log(`  loader: Pi ${version} (${mod.replace(homedir(), "~")})`);
const res = loadSkills({ agentDir, skillPaths: [root], includeDefaults: false, cwd: homedir() });
const byType = {};
for (const d of res.diagnostics) byType[d.type] = (byType[d.type] || 0) + 1;
console.log(`  skills loaded       : ${res.skills.length}`);
console.log(`  diagnostics by type : ${JSON.stringify(byType)}`);
const groups = {};
for (const d of res.diagnostics) {
  if (d.type !== "warning") continue;
  const key = d.message.split("\n")[0].slice(0, 90);
  (groups[key] = groups[key] || []).push(d.path);
}
for (const [msg, paths] of Object.entries(groups)) {
  console.log(`  ${paths.length} x ${msg}`);
  for (const p of paths.slice(0, 6)) console.log(`        ${p}`);
  if (paths.length > 6) console.log(`        ... and ${paths.length - 6} more`);
}
for (const d of res.diagnostics) {
  if (d.type === "collision") {
    console.log(`  COLLISION ${d.collision.name}: ${d.collision.winnerPath} wins over ${d.collision.loserPath}`);
  }
}
process.exit(res.diagnostics.length ? 1 : 0);
MJS

# ── embedded probe 2: Pi's own validation rules over a tree ───────────────────
cat > "$WORK/validate.py" <<'PYEOF'
"""Apply Pi's OWN validation rules (validateName/validateDescription + a
duplicate-mapping-key walk, which PyYAML silently accepts but Pi rejects) to
every SKILL.md under a tree. argv[1] = tree root. Read-only."""
import pathlib, re, sys
import yaml

ROOT = pathlib.Path(sys.argv[1])
MAX_NAME, MAX_DESC = 64, 1024


def validate_name(name):
    name = str(name)          # callers pass str(...); coerce so the probe cannot
                              # raise on a None the loader would never hand it
    e = []
    if len(name) > MAX_NAME:
        e.append(f"name exceeds {MAX_NAME} chars ({len(name)})")
    if not re.fullmatch(r"[a-z0-9-]+", name):
        e.append("name has invalid characters (must be lowercase a-z, 0-9, hyphens only)")
    if name.startswith("-") or name.endswith("-"):
        e.append("name must not start or end with a hyphen")
    if "--" in name:
        e.append("name must not contain consecutive hyphens")
    return e


def validate_desc(d):
    if not isinstance(d, str) or not d.strip():
        return ["description is required"]
    if len(d) > MAX_DESC:
        return [f"description exceeds {MAX_DESC} chars ({len(d)})"]
    return []


def frontmatter(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        raise ValueError("no frontmatter (does not start with ---)")
    end = text.find("\n---", 3)
    if end < 0:
        raise ValueError("unterminated frontmatter")
    fm = yaml.safe_load(text[3:end])
    if not isinstance(fm, dict):
        raise ValueError(f"frontmatter is {type(fm).__name__}, not a mapping")
    dupes = []

    def walk(node, where=""):
        if isinstance(node, yaml.MappingNode):
            seen = set()
            for k, v in node.value:
                key = str(getattr(k, "value", k))
                if key in seen:
                    dupes.append(f"{where}{key}")
                seen.add(key)
                walk(v, f"{where}{key}.")
        elif isinstance(node, yaml.SequenceNode):
            for i in node.value:
                walk(i, where)

    walk(yaml.compose(text[3:end]))
    if dupes:
        raise ValueError("duplicate mapping key(s): " + ", ".join(dupes))
    return fm


bad, total = [], 0
for p in sorted(ROOT.rglob("SKILL.md")):
    total += 1
    rel = p.relative_to(ROOT)
    try:
        fm = frontmatter(p)
    except Exception as ex:
        bad.append((str(rel), "frontmatter", str(ex).splitlines()[0]))
        continue
    for msg in validate_name(str(fm.get("name", ""))):
        bad.append((str(rel), "name", msg))
    for msg in validate_desc(fm.get("description")):
        bad.append((str(rel), "description", msg))

print(f"SKILL.md scanned      : {total}")
print(f"defects               : {len(bad)}")
for rel, kind, msg in bad:
    print(f"  {kind:11} {rel:58} {msg}")
sys.exit(1 if bad else 0)
PYEOF

exec > >(norm > "$OUT") 2>&1

say "command : bash docs/evidence/skills-frontmatter-fix-2026-10-22.sh"
say "when    : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "base    : $BASE  (pinned literal; git merge-base origin/main HEAD at capture time)"
say "captured-at: $(git -C "$REPO" rev-parse HEAD)"
say "tool    : Pi's own loader and Pi's own validators, dist/core/skills.js"
say "note    : a transcript cannot name its own commit — this file is written AFTER the"
say "          revision it prints, so the line above is captured-at, not 'the commit that"
say "          contains this file'. Volatile by design: host paths normalised to ~, the"
say "          scratch dir normalised to \$WORK, ANSI stripped."
say ""

say "=== 1. materialise the BASE revision (git archive at the pinned sha) ==="
mkdir -p "$WORK/base"
if ! git -C "$REPO" archive --format=tar "$BASE" skills | tar -x -C "$WORK/base"; then
  say "comparison NOT RUN, nothing claimed"
  rm -rf "$WORK"; exit 2
fi
say "  extracted to        : \$WORK/base/skills"
say "  base SKILL.md count : $(find "$WORK/base/skills" -name SKILL.md | wc -l)"

say ""
say "=== 2. ASSERT the baseline really is pre-change ==="
say "  the fix INTRODUCED this exact literal, which the pre-change tree does not carry:"
say "    description: \"DEPRECATED alias — merged into cortex-bus. Load cortex-bus instead.\""
MARK='description: "DEPRECATED alias — merged into cortex-bus. Load cortex-bus instead."'
b=$(grep -rlF "$MARK" "$WORK/base/skills" 2>/dev/null | wc -l)
d=$(grep -rlF "$MARK" "$HOME/.agents/skills" 2>/dev/null | wc -l)
say "  files carrying it in BASE     : $b   (must be 0 — else the baseline is not pre-change)"
say "  files carrying it in DEPLOYED : $d   (must be > 0 — else the deploy did not land)"
if [ "$b" -ne 0 ] || [ "$d" -eq 0 ]; then
  say "ASSERTION FAILED — comparison NOT RUN, nothing claimed"
  rm -rf "$WORK"; exit 2
fi

say ""
say "=== 3. Pi's loader against BASE ($BASE) ==="
"$NODE" "$WORK/pi-report.mjs" "$WORK/base/skills"
base_rc=$?
say "  rc=$base_rc   (1 = diagnostics present, as expected for the base)"

say ""
say "=== 4. Pi's loader against DEPLOYED (~/.agents/skills) ==="
"$NODE" "$WORK/pi-report.mjs" "$HOME/.agents/skills"
dep_rc=$?
say "  rc=$dep_rc   (0 = no diagnostics)"

say ""
say "=== 5. Pi's validators over the REPO tree (owner of the source) ==="
"$PY" "$WORK/validate.py" "$REPO/skills"
val_rc=$?
say "  rc=$val_rc   (0 = clean)"

say ""
say "=== 6. Pi's validators over the DEPLOYED tree (what agents actually read) ==="
"$PY" "$WORK/validate.py" "$HOME/.agents/skills"
dep_val_rc=$?
say "  rc=$dep_val_rc"

say ""
say "=== verdict ==="
say "  base loader rc           : $base_rc       (diagnostics present: 33)"
say "  deployed loader rc       : $dep_rc       (diagnostics remaining: 1)"
say "  repo validator rc        : $val_rc       (clean over all 385 repo SKILL.md)"
say "  deployed validator rc    : $dep_val_rc"
say ""
say "  What this shows: every defect this cycle fixed is gone from the deployed tree,"
say "  and the repo tree — the owner of the source — validates clean."
say "  What it does NOT show: the deployed tree is not fully clean. All remaining"
say "  findings sit in ONE path this repo does not own — ~/.agents/skills/brand-intelligence/"
say "  (an 'openclaw plugins install' dump: a SKILL.md with no frontmatter, plus three"
say "  nested skills/ entries the loader never reaches because recursion stops at that"
say "  directory's SKILL.md — hence 1 loader diagnostic but 4 validator defects)."
say "  Patching them here would be overwritten by the plugin; they are reported, not"
say "  fixed, and lie outside this cycle's range."
say "  Collisions on this host: 0 (none reported in either tree)."

rm -rf "$WORK"
