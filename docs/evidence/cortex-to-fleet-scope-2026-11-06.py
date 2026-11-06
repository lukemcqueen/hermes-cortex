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
            try:
                txt = p.read_text(errors="replace")
            except Exception:
                continue
            n = len(rx.findall(txt))
            if n:
                hits[f] = n
        total = sum(hits.values())
        inscope = sum(v for k, v in hits.items() if not k.startswith(EXCLUDE_DIRS))
        print(f"{label:26s} {total:8d} {len(hits):7d} {inscope:9d}")

    print("\n## 2. In-scope carriers, top 5 by hit count")
    rx = re.compile(r"cortex-|cortex_|CORTEX_|(?<![a-zA-Z])Cortex|(?<![a-zA-Z])cortex(?![a-zA-Z_-])")
    hits = collections.Counter()
    for f in files:
        p = REPO / f
        if p.suffix == ".pyc" or not p.is_file():
            continue
        hits[f] = len(rx.findall(p.read_text(errors="replace")))
    inscope_hits = {k: v for k, v in hits.items() if not k.startswith(EXCLUDE_DIRS)}
    for f, n in collections.Counter(inscope_hits).most_common(5):
        print(f"  {n:5d}  {f}")

    print("\n## 3. Tracked paths containing 'cortex' (excluding mycortex)")
    named = [f for f in files if "cortex" in f.lower() and "mycortex" not in f.lower()]
    records = [f for f in named if f.startswith(EXCLUDE_DIRS)]
    print(f"  total = {len(named)}   records(excluded) = {len(records)}   live = {len(named) - len(records)}")

    print("\n## 4. register() map — exact count in cortex-update.sh")
    upd = REPO / "ops/scripts/cortex-update.sh"
    txt = upd.read_text(errors="replace")
    n_calls = len(re.findall(r"(?m)^\s*register\s+\"", txt))
    n_token = len(re.findall(r"register", txt))
    print(f"  cmd: grep -cE '^[[:space:]]*register[[:space:]]+\"' ops/scripts/cortex-update.sh")
    print(f"  leading-anchored register \"<...>\" calls = {n_calls}")
    print(f"  all occurrences of the token 'register' = {n_token}")
    print(f"  (the plan cited the TOKEN count as if it were the MAP count — corrected)")

    print("\n## 5. CORTEX_* env var names — distinct count + top carriers")
    names = collections.Counter()
    for f in files:
        p = REPO / f
        if p.suffix == ".pyc" or not p.is_file():
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
