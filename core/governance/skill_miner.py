#!/usr/bin/env python3.12
# skill_miner.py — Parse Hermes skills and generate checksums for loop governance scoring
import json, os, sys, hashlib
from pathlib import Path

# ── Silent watchdog: only produce output on actual changes ──
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Compute skill digests for loop governance scoring")
    parser.add_argument("action", nargs="?", default="collect", help="collect|score")
    parser.add_argument("--output", default="/tmp/skills-manifest.json", help="Output file path")
    args = parser.parse_args()

    if args.action == "collect":
        data = collect_skill_info()
        with open(args.output, "w") as f:
            json.dump(data, f, indent=2)
        # Silent unless there's a notable number of files
        if len(data) > 500:
            print(f"skill-miner: collected {len(data)} skill files to {args.output}")

    elif args.action == "score":
        # Read existing manifest if present
        manifest_path = Path(args.output)
        if manifest_path.exists():
            with open(manifest_path) as f:
                old = json.load(f)
        else:
            old = []

        current = collect_skill_info()
        old_map = {(e["relpath"], e["hash"]): e for e in old}
        new_map = {(e["relpath"], e["hash"]): e for e in current}
        added = [e for k, e in new_map.items() if k not in old_map]
        removed = [e for k, e in old_map.items() if k not in new_map]
        unchanged = [e for k, e in new_map.items() if k in old_map]
        result = {
            "timestamp": hashlib.sha256(str(json.dumps(current, sort_keys=True)).encode()).hexdigest(),
            "added": added,
            "removed": removed,
            "unchanged_count": len(unchanged),
            "total": len(current),
        }
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)

        # Silent unless there are actual changes
        if added or removed:
            print(f"skill-miner: {len(current)} skills ({len(added)} added, {len(removed)} removed)")
            if added:
                print(f"  Added: {', '.join(a['relpath'] for a in added[:5])}{'…' if len(added) > 5 else ''}")
            if removed:
                print(f"  Removed: {', '.join(r['relpath'] for r in removed[:5])}{'…' if len(removed) > 5 else ''}")
    else:
        print(f"Unknown action: {args.action}")
        sys.exit(1)

def collect_skill_info(skill_root=Path.home() / ".hermes" / "skills"):
    """Walk skill_root, return list of {path, relpath, size, hash, type}"""
    result = []
    if not skill_root.exists():
        return result
    for path in skill_root.rglob("*"):
        if path.is_file():
            rel = path.relative_to(skill_root)
            size = path.stat().st_size
            with open(path, "rb") as f:
                sha256 = hashlib.sha256(f.read()).hexdigest()
            typ = "skill" if path.name.upper() == "SKILL.MD" else "asset"
            result.append({
                "path": str(path),
                "relpath": str(rel),
                "size": size,
                "hash": sha256,
                "type": typ,
            })
    return result

if __name__ == "__main__":
    main()
