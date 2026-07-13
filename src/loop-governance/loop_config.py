#!/Users/luke/.hermes/mcp-venv/bin/python3
"""
Loop Governance Config — runtime thresholds and weights for the scoring system.

Config lives at ~/.hermes-cortex/data/loop-governance-config.json and is read on every
score call (cheap — ~50µs file stat). This allows safe, auditable runtime tuning
without patching Python source files.

All config changes are logged to the config_history table for rollback.

Default values match the original hardcoded constants in loop-scorer.py.
"""

import copy
import json
import os

DEFAULT_CONFIG_PATH = os.path.expanduser(
    "~/.hermes-cortex/state/loop-governance-config.json"
)

DEFAULTS = {
    "version": 1,
    "weights": {
        "completeness": 0.40,
        "quality": 0.30,
        "progress": 0.30,
    },
    "thresholds": {
        "stop": 8.0,           # composite ≥ stop → STOP ✓
        "loop": 5.0,           # composite ≥ loop → LOOP 🔄 (below stop, above move_on)
        "move_on": 3.0,        # composite ≥ move_on → MOVE ON → (below loop)
        "no_progress_score": 2.0,   # progress < this → no-progress
        "no_progress_limit": 3,      # consecutive no-progress before HARD FAIL
    },
    "auto_apply": {
        "min_confidence": 0.7,       # skip patches below this confidence
        "max_threshold_delta": 1.0,  # max single-threshold change
        "max_weight_delta": 0.10,    # max single-weight change
        "requires_review": True,      # always require human review (safety default)
    },
}


def _ensure_config():
    """Create config file with defaults if it doesn't exist."""
    if not os.path.exists(DEFAULT_CONFIG_PATH):
        os.makedirs(os.path.dirname(DEFAULT_CONFIG_PATH), exist_ok=True)
        with open(DEFAULT_CONFIG_PATH, "w") as f:
            json.dump(DEFAULTS, f, indent=2)
        return DEFAULTS
    return None


def get_config(path: str = None) -> dict:
    """Load the current config, merging with defaults for missing keys."""
    path = path or DEFAULT_CONFIG_PATH
    _ensure_config()

    cfg = copy.deepcopy(DEFAULTS)
    try:
        with open(path) as f:
            loaded = json.load(f)
            # Deep merge: update nested dicts recursively
            for section in ["weights", "thresholds", "auto_apply"]:
                if section in loaded and isinstance(loaded[section], dict):
                    cfg[section].update(loaded[section])
            # Top-level keys
            for key in loaded:
                if key not in ("weights", "thresholds", "auto_apply"):
                    cfg[key] = loaded[key]
    except (FileNotFoundError, json.JSONDecodeError):
        pass  # fall through to defaults

    return cfg


def update_config(changes: dict, path: str = None) -> dict:
    """Apply a changeset to the config file. Expects structure like:
    {
        "weights": {"completeness": 0.45},
        "thresholds": {"stop": 8.5},
    }
    Returns the full new config dict.
    """
    path = path or DEFAULT_CONFIG_PATH
    _ensure_config()
    cfg = get_config(path)

    for section in ("weights", "thresholds", "auto_apply"):
        if section in changes and isinstance(changes[section], dict):
            for key, value in changes[section].items():
                if key in cfg[section]:
                    cfg[section][key] = value

    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)

    return cfg


def get_diff(previous: dict, current: dict) -> str:
    """Return a human-readable diff between two config dicts."""
    lines = []
    for section in ("weights", "thresholds", "auto_apply"):
        if section not in previous or section not in current:
            continue
        for key in current[section]:
            old = previous[section].get(key)
            new = current[section].get(key)
            if old != new:
                lines.append(f"  {section}.{key}: {old} → {new}")
    return "\n".join(lines)


if __name__ == "__main__":
    # CLI: show current config
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--show":
        print(json.dumps(get_config(), indent=2))
    elif len(sys.argv) > 2 and sys.argv[1] == "--set":
        key = sys.argv[2]
        if "." in key:
            section, subkey = key.split(".", 1)
            value = float(sys.argv[3]) if "." in sys.argv[3] or sys.argv[3].isdigit() else sys.argv[3]
            update_config({section: {subkey: value}})
            print(f"Updated {key} = {value}")
        else:
            print("Usage: loop-config --set weights.completeness 0.45")
    else:
        cfg = get_config()
        print("═" * 45)
        print("  Loop Governance Config")
        print("═" * 45)
        print(f"\n  Weights:")
        for k, v in cfg["weights"].items():
            print(f"    {k}: {v:.0%}")
        print(f"\n  Thresholds:")
        for k, v in cfg["thresholds"].items():
            print(f"    {k}: {v}")
        print(f"\n  Auto-apply:")
        for k, v in cfg["auto_apply"].items():
            print(f"    {k}: {v}")
        print(f"\n  File: {DEFAULT_CONFIG_PATH}")
        print()