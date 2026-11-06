#!/usr/bin/env python3
"""Evidence capture for docs/plans/cortex-to-fleet-rename-plan.md (READ-ONLY).

Emits every number the plan quotes, with the command that produced it.
Run from the repo root:  python3 docs/evidence/cortex-to-fleet-scope-2026-11-06.py
"""
import re, subprocess, collections, os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
os.chdir(REPO)

EXCLUDE_DIRS = ("docs/older/", "docs/evidence/", "tests/artifacts/", "docs/reviews/")

# The documents that DESCRIBE this change mention the very tokens being counted, so
# including them makes every figure grow each time the plan is edited — a count that
# changes under the reader's feet. They are excluded from the token counts and from
# the path inventory; the exclusion is printed so a "0 residuals" claim cannot read
# as coverage of everything.
SELF_EXCLUDES = (
    "docs/rename-cortex-to-fleet.md",
    "docs/plans/cortex-to-fleet-rename-plan.md",
    "docs/evidence/cortex-to-fleet-scope-2026-11-06.py",
    "docs/evidence/cortex-to-fleet-scope-2026-11-06.txt",
    "docs/evidence/cortex-to-fleet-worktree-2026-11-06.sh",
    "docs/evidence/cortex-to-fleet-worktree-2026-11-06.txt",
    "tests/test_cortex_to_fleet_scope_evidence.py",
)

# The four hermes-cortex* skills are MEASURED in the family totals but DEFERRED from
# this sweep (operator decision Q4). Excluding them from the sweep-scope column keeps
# the table aligned with the boundary: hermes-cortex* stays byte-identical.
DEFERRED_DIRS = (
    "skills/autonomous-ai-agents/hermes-cortex/",
    "skills/autonomous-ai-agents/hermes-cortex-setup/",
    "skills/devops/hermes-cortex-maintenance/",
    "skills/devops/hermes-cortex-repo-deploy/",
)


def excluded(f: str) -> bool:
    """True for records + self-documents + Q4-deferred skill dirs (sweep-scope column)."""
    return f.startswith(EXCLUDE_DIRS) or f in SELF_EXCLUDES or f.startswith(DEFERRED_DIRS)

FAMILIES = [
    ("cortex- (hyphen)",       re.compile(r"cortex-")),
    ("cortex_ (underscore)",   re.compile(r"cortex_")),
    ("CORTEX_ (env/const)",    re.compile(r"CORTEX_")),
    ("Cortex (titlecase)",     re.compile(r"(?<![a-zA-Z])Cortex")),
    (r"\bcortex\b (bare)",     re.compile(r"(?<![a-zA-Z])cortex(?![a-zA-Z_-])")),
]


def sh(*args) -> str:
    return subprocess.run(args, capture_output=True, text=True, check=False).stdout


def tracked() -> list:
    return [f for f in sh("git", "ls-files").splitlines() if f]


def main() -> int:
    files = tracked()
    print("=" * 72)
    print(f"REPO={REPO}")
    print(f"cmd: git ls-files | wc -l   ->  tracked files = {len(files)}")
    print("=" * 72)

    print("\n## 1. Token families (tracked text files, .pyc skipped)")
    print(f"{'family':26s} {'total':>8s} {'files':>7s} {'in-scope':>9s}")
    for label, rx in FAMILIES:
        hits = collections.Counter()
        for f in files:
            p = REPO / f
            if p.suffix == ".pyc" or not p.is_file():
                continue
            if f in SELF_EXCLUDES:
                # the change-describing docs (incl. this script's own .txt dump)
                # are regenerated every run — counting them makes `total` drift
                continue
            try:
                txt = p.read_text(errors="replace")
            except Exception:
                continue
            n = len(rx.findall(txt))
            if n:
                hits[f] = n
        total = sum(hits.values())
        inscope = sum(v for k, v in hits.items() if not excluded(k))
        print(f"{label:26s} {total:8d} {len(hits):7d} {inscope:9d}")

    print("\n## 2. In-scope carriers, top 5 by hit count")
    rx = re.compile(r"cortex-|cortex_|CORTEX_|(?<![a-zA-Z])Cortex|(?<![a-zA-Z])cortex(?![a-zA-Z_-])")
    hits = collections.Counter()
    for f in files:
        p = REPO / f
        if p.suffix == ".pyc" or not p.is_file():
            continue
        hits[f] = len(rx.findall(p.read_text(errors="replace")))
    inscope_hits = {k: v for k, v in hits.items() if not excluded(k)}
    for f, n in collections.Counter(inscope_hits).most_common(5):
        print(f"  {n:5d}  {f}")

    print("\n## 3. Tracked paths containing 'cortex' (excluding mycortex)")
    named = [f for f in files if "cortex" in f.lower() and "mycortex" not in f.lower()]
    records = [f for f in named if excluded(f)]
    print(f"  total = {len(named)}   excluded = {len(records)}   in-scope = {len(named) - len(records)}")
    print("  excluded (records + self-documents + Q4-deferred skills):")
    for d in EXCLUDE_DIRS:
        print(f"    dir  {d}")
    for d in SELF_EXCLUDES:
        print(f"    self {d}")
    for d in DEFERRED_DIRS:
        print(f"    q4   {d}")

    print("\n## 4. register() map — exact count in cortex-update.sh")
    upd = REPO / "ops/scripts/cortex-update.sh"
    txt = upd.read_text(errors="replace")
    n_calls = len(re.findall(r"(?m)^\s*register\s+\"", txt))
    n_orch = len(re.findall(r"(?m)^\s*register_orch\s+\"", txt))
    n_token = len(re.findall(r"register", txt))
    n_deploy_home = len(re.findall(
        r"(?m)^(?:register|register_orch)\s+\"[^\"]+\"\s+\"\$\{CORTEX_DEPLOY_HOME\}/", txt))
    print(f"  cmd: grep -cE '^[[:space:]]*register[[:space:]]+\"' ops/scripts/cortex-update.sh")
    print(f"  leading-anchored register \"<...>\" calls    = {n_calls}")
    print(f"  leading-anchored register_orch \"<...>\" calls = {n_orch}")
    print(f"  MAP TOTAL (register + register_orch)         = {n_calls + n_orch}")
    print(f"  of which ${'{CORTEX_DEPLOY_HOME}/'} shape (test-visible) = {n_deploy_home}")
    print(f"  all occurrences of the token 'register'      = {n_token}")
    print(f"  (plan history: the TOKEN count was once mistaken for the MAP count; corrected)")

    print("\n## 5. CORTEX_* env var names — distinct count + top carriers")
    names = collections.Counter()
    for f in files:
        p = REPO / f
        if p.suffix == ".pyc" or not p.is_file() or excluded(f):
            continue
        try:
            for m in re.findall(r"CORTEX_[A-Z0-9_]+", p.read_text(errors="replace")):
                names[m] += 1
        except Exception:
            continue
    distinct = {k for k in names if not k.endswith("_")}
    print(f"  distinct CORTEX_* names = {len(distinct)}")
    print(f"  total occurrences       = {sum(names.values())}")
    for k, v in names.most_common(8):
        print(f"    {v:5d}  {k}")

    print("\n## 6. mycortex post-condition (must be unchanged by the sweep)")
    my = sh("git", "grep", "-c", "mycortex")
    n_files = len([l for l in my.splitlines() if l.strip()])
    print(f"  files containing 'mycortex' = {n_files}")

    print("\n## 7. CORTEX_ delta — family counter vs identifier-token counter")
    print("  The two counts quoted in the plan are NOT the same measurement. Both come")
    print("  from THIS run; a replacement driven by the family counter rewrites prose")
    print("  wildcards too, and a residue grep driven by the identifier counter misses them.")
    fam = ident = 0
    delta_next = collections.Counter()
    sites = []
    for f in files:
        p = REPO / f
        if p.suffix == ".pyc" or not p.is_file():
            continue
        try:
            txt = p.read_text(errors="replace")
        except Exception:
            continue
        if not excluded(f):
            fam += len(re.findall(r"CORTEX_", txt))
            ident += len(re.findall(r"CORTEX_[A-Z0-9_]+", txt))
        for m in re.finditer(r"CORTEX_", txt):
            nxt = txt[m.end():m.end() + 1]
            if not re.match(r"[A-Z0-9_]", nxt or ""):
                delta_next[nxt] += 1
                sites.append((f, txt.count("\n", 0, m.start()) + 1))
    print(f"  family  r'CORTEX_'            = {fam}")
    print(f"  ident   r'CORTEX_[A-Z0-9_]+'  = {ident}")
    print(f"  delta                         = {fam - ident}")
    print("  both counters EXCLUDE the files listed in §3, so the pair is stable across")
    print("  edits to this plan (it mentions CORTEX_* itself and would otherwise inflate")
    print("  its own numbers on every rewrite).")
    print("  char following each trailing occurrence (all files, incl. excluded):")
    for ch, n in delta_next.most_common():
        print(f"    {n:4d}  {ch!r}")
    print(f"  sites (file:line) — first 6 of {len(sites)}:")
    for f, ln in sites[:6]:
        print(f"    {f}:{ln}")
    print("  NOTE: a replacement driven by the FAMILY counter rewrites prose wildcard")
    print("  mentions too; a residue grep driven by the IDENTIFIER counter will not see")
    print("  them. Use the family counter for the sweep and the identifier counter for")
    print("  the env-var inventory, and never mix the two in one claim.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
