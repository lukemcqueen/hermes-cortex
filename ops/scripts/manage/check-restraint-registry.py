#!/usr/bin/env python3
"""Validate the guardrail registry (Story M1 — failure-propensity register).

Every correction class in docs/guardrail-registry.json must carry a
non-empty `restraint` (the named enforcement artifact that would have
caught the failure) and a valid ISO `noticed` timestamp. Once a propensity
is documented this way, deploying without its restraint is the culpable act,
and the registry proves notice.

Usage:
    python3 ops/scripts/manage/check-restraint-registry.py
    python3 ops/scripts/manage/check-restraint-registry.py --registry <path>

Exit codes: 0 = well-formed · 1 = validation error(s) · 2 = cannot load.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_REGISTRY = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "docs"
    / "guardrail-registry.json"
)

VALID_LAYERS = {"model", "harness", "ops", "institutional"}
VALID_TIERS = {"enforced", "encouraged", "detected"}
MODEL_ARTIFACT_PREFIXES = ("SOUL.md:", "AGENTS.md:", "skill:")


def _is_valid_iso(value) -> bool:
    """Accept an ISO date (YYYY-MM-DD) or a full ISO-8601 datetime."""
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v:
        return False
    try:
        datetime.fromisoformat(v)
        return True
    except ValueError:
        return False


def validate_registry(data) -> list:
    """Return a list of error strings; empty == well-formed."""
    errors: list = []
    if not isinstance(data, dict):
        return ["registry root is not an object"]
    classes = data.get("classes")
    if not isinstance(classes, dict):
        return ["'classes' is not an object"]

    for name, cls in classes.items():
        if not isinstance(cls, dict):
            errors.append(f"{name}: class entry is not an object")
            continue
        restraint = cls.get("restraint")
        if not restraint or not str(restraint).strip():
            errors.append(f"{name}: empty 'restraint'")
        noticed = cls.get("noticed")
        if not _is_valid_iso(noticed):
            errors.append(f"{name}: invalid or missing 'noticed' ({noticed!r})")

        layer = cls.get("layer")
        if layer not in VALID_LAYERS:
            errors.append(f"{name}: missing or invalid 'layer' ({layer!r})")
        tier = cls.get("tier")
        if tier not in VALID_TIERS:
            errors.append(f"{name}: missing or invalid 'tier' ({tier!r})")

        # Placement rule (M2.1): a class whose artifacts are all model-layer
        # (SOUL.md/AGENTS.md/skill) is encouraged, never enforced — a
        # requirement enforced only in the model is not enforced, it is
        # encouraged. Reject an 'enforced' tag on such a class.
        if tier == "enforced":
            artifacts = cls.get("artifacts", [])
            if artifacts and all(
                isinstance(a, str) and a.startswith(MODEL_ARTIFACT_PREFIXES)
                for a in artifacts
            ):
                errors.append(
                    f"{name}: tier 'enforced' but all artifacts are model-layer "
                    "(SOUL.md/AGENTS.md/skill) — a model-layer artifact can never be enforced"
                )

    gaps = data.get("known_gaps", [])
    if not isinstance(gaps, list):
        errors.append("'known_gaps' is not a list")
    else:
        for i, gap in enumerate(gaps):
            if not isinstance(gap, dict):
                errors.append(f"known_gaps[{i}]: gap entry is not an object")
                continue
            gclass = gap.get("class")
            if not gclass or not str(gclass).strip():
                errors.append(f"known_gaps[{i}]: empty 'class'")
            restraint = gap.get("restraint")
            if not restraint or not str(restraint).strip():
                errors.append(f"known_gaps[{i}]: empty 'restraint'")
            noticed = gap.get("noticed")
            if not _is_valid_iso(noticed):
                errors.append(f"known_gaps[{i}]: invalid or missing 'noticed' ({noticed!r})")
    return errors


def load_registry(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--registry", default=str(DEFAULT_REGISTRY),
        help="path to guardrail-registry.json",
    )
    args = ap.parse_args(argv)

    try:
        data = load_registry(args.registry)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot load registry: {e}", file=sys.stderr)
        return 2

    errors = validate_registry(data)
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print("OK: every class has a non-empty restraint and a valid noticed timestamp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
