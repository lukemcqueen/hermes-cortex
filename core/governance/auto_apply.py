#!/usr/bin/env python3
"""
Auto-Apply Config Patches — closes the loop between evaluation and meta-learning.

Reads the evaluator's config patch, checks safety bounds, applies low-risk
changes to the runtime config, and logs everything to config_history.

Safety rules (from loop_config.json):
  - min_confidence: skip patches below this (default: 0.7)
  - max_threshold_delta: max per-threshold change per apply (default: 1.0)
  - max_weight_delta: max per-weight change per apply (default: 0.10)

Usage:
    python3 auto_apply.py                    # full apply attempt + report
    python3 auto_apply.py --dry-run           # preview without applying
    python3 auto_apply.py --force             # bypass min_confidence check
    python3 auto_apply.py --json              # JSON output (for crons)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from loop_db import LoopDB
from loop_config import get_config, update_config, get_diff
from loop_evaluator import LoopEvaluator

DEFAULT_DB_PATH = os.path.expanduser("~/.hermes-cortex/state/loop-governance.db")


def check_safety(changes: dict, config: dict) -> dict:
    """Validate each proposed change against safety bounds.

    Returns {'safe': {appliable changes}, 'skipped': {reasons}}.
    """
    safe = {"thresholds": {}, "weights": {}, "auto_apply": {}}
    skipped = []
    bounds = config.get("auto_apply", {})
    max_td = bounds.get("max_threshold_delta", 1.0)
    max_wd = bounds.get("max_weight_delta", 0.10)

    # Check threshold changes
    for key, value in changes.get("thresholds", {}).items():
        if not isinstance(value, (int, float)):
            skipped.append(f"thresholds.{key}: non-numeric value ({value})")
            continue
        current = config.get("thresholds", {}).get(key)
        if current is not None:
            delta = abs(value - current)
            if delta > max_td:
                skipped.append(
                    f"thresholds.{key}: delta {delta:.2f} > max {max_td} "
                    f"(current={current}, proposed={value})"
                )
                continue
        # Additional hard bounds
        if key == "stop" and (value < 5.0 or value > 10.0):
            skipped.append(f"thresholds.stop: {value} outside safe range [5.0, 10.0]")
            continue
        if key == "move_on" and (value < 1.0 or value > 5.0):
            skipped.append(f"thresholds.move_on: {value} outside safe range [1.0, 5.0]")
            continue
        if key == "no_progress_limit" and not (1 <= value <= 5):
            skipped.append(f"thresholds.no_progress_limit: {value} outside safe range [1, 5]")
            continue
        safe["thresholds"][key] = value

    # Check weight changes
    for key, value in changes.get("weights", {}).items():
        if not isinstance(value, (int, float)):
            skipped.append(f"weights.{key}: non-numeric value ({value})")
            continue
        if value < 0.05 or value > 0.80:
            skipped.append(f"weights.{key}: {value} outside safe range [0.05, 0.80]")
            continue
        current = config.get("weights", {}).get(key)
        if current is not None:
            delta = abs(value - current)
            if delta > max_wd:
                skipped.append(
                    f"weights.{key}: delta {delta:.3f} > max {max_wd} "
                    f"(current={current}, proposed={value})"
                )
                continue
        safe["weights"][key] = value

    # Check auto_apply changes
    for key, value in changes.get("auto_apply", {}).items():
        if key == "no_progress_limit" and isinstance(value, int) and 1 <= value <= 5:
            safe["auto_apply"][key] = value
        elif key == "min_confidence" and isinstance(value, float) and 0.5 <= value <= 0.95:
            safe["auto_apply"][key] = value
        elif key == "requires_review" and isinstance(value, bool):
            safe["auto_apply"][key] = value
        else:
            skipped.append(f"auto_apply.{key}: unexpected or out-of-range")

    # Remove empty sections
    safe = {k: v for k, v in safe.items() if v}

    return {"safe": safe, "skipped": skipped}


def apply(changes: dict, note: str = "", dry_run: bool = False) -> dict:
    """Apply a config patch with safety checks. Returns result dict."""
    db = LoopDB()

    try:
        config = get_config()
        safety = check_safety(changes, config)

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "patch": changes,
            "safe": safety["safe"],
            "skipped": safety["skipped"],
            "applied": False,
            "requires_review_override": False,
            "confidence": changes.get("_confidence", 0),
            "diff_before": "",
            "diff_after": "",
            "dry_run": dry_run,
        }

        if not safety["safe"]:
            result["reason"] = "No safe changes to apply"
            return result

        if dry_run:
            result["reason"] = "Dry run — no changes written"
            result["diff_before"] = json.dumps(config, indent=2)
            return result

        # Apply safe changes
        old_config = get_config()
        new_config = update_config(safety["safe"])
        diff = get_diff(old_config, new_config)

        # Log to config_history
        db.record_config_change(
            config_json=json.dumps(new_config, indent=2),
            diff=diff,
        )

        result["applied"] = True
        result["diff_before"] = json.dumps(old_config, indent=2)
        result["diff_after"] = json.dumps(new_config, indent=2)
        result["reason"] = f"Applied {len(safety['safe'])} change(s)"
        result["note"] = note

        return result

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Auto-apply low-risk config patches to the loop governance system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Preview which changes would be applied")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Bypass min_confidence and requires_review checks")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON (for cron consumption)")
    parser.add_argument("--db", default=DEFAULT_DB_PATH,
                        help=f"Database path (default: {DEFAULT_DB_PATH})")
    args = parser.parse_args()

    # 1. Run the evaluator to generate a patch
    ev = LoopEvaluator(args.db)
    patch = ev.generate_config_patch()
    ev.close()

    patch_changes = patch.get("changes", {})
    patch_confidence = patch.get("confidence", 0)
    requires_review = patch.get("requires_review", True)

    # 2. Check confidence threshold
    config = get_config()
    min_conf = config.get("auto_apply", {}).get("min_confidence", 0.7)

    if not args.force and (patch_confidence < min_conf or requires_review):
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "patch": patch_changes,
            "safe": {},
            "skipped": [],
            "applied": False,
            "confidence": patch_confidence,
            "min_confidence": min_conf,
            "requires_review": requires_review,
            "reason": (
                f"Confidence {patch_confidence} below threshold {min_conf}"
                if patch_confidence < min_conf
                else f"Patch requires review (confidence={patch_confidence}, evidence_count unknown)"
            ),
            "dry_run": args.dry_run,
        }
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"⏭  Auto-apply skipped — {result['reason']}")
            print(f"   Patch confidence: {patch_confidence} (threshold: {min_conf})")
            print(f"   Requires review: {requires_review}")
            print(f"   Changes proposed: {patch_changes}")
        return

    # 3. Inject confidence into changes for the apply function
    patch_changes["_confidence"] = patch_confidence

    # 4. Apply with safety checks
    note = f"Auto-apply (confidence={patch_confidence})"
    result = apply(patch_changes, note=note, dry_run=args.dry_run)
    result["confidence"] = patch_confidence
    result["min_confidence"] = min_conf
    result["requires_review"] = requires_review

    # 5. Output
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print("═" * 55)
        print(f"  Config Auto-Apply  |  {result['timestamp'][:19]} UTC")
        print("═" * 55)
        print()

        if result["dry_run"]:
            print(f"  🔍 DRY RUN — no changes written")
        elif result["applied"]:
            print(f"  ✅ Applied {len(result['safe'])} change(s)")
        else:
            print(f"  ⏭  Nothing applied")

        print()

        if result["safe"]:
            print("  Changes to apply:")
            for section, items in result["safe"].items():
                for key, value in items.items():
                    current = config.get(section, {}).get(key, "?")
                    print(f"    {section}.{key}: {current} → {value}")
            print()

        if result["skipped"]:
            print("  Skipped (unsafe):")
            for s in result["skipped"]:
                print(f"    ⚠  {s}")
            print()

        if not result["safe"] and not result["skipped"]:
            print("  No changes proposed by the evaluator.")
            print()

        print(f"  Patch confidence: {patch_confidence} (threshold: {min_conf})")
        print(f"  Requires review: {requires_review}")
        print(f"  Rationale: {patch.get('rationale', 'N/A')[:100]}")
        print()


if __name__ == "__main__":
    main()