"""Tests for auto_apply.py — safety bounds, apply logic, config patching."""
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAutoApplySafety:
    def test_safe_threshold_change(self, tmp_config):
        from auto_apply import check_safety
        config = {"thresholds": {"stop": 8.0}, "weights": {}, "auto_apply": {}}
        changes = {"thresholds": {"stop": 8.5}}
        result = check_safety(changes, config)
        assert "stop" in result["safe"].get("thresholds", {})

    def test_blocks_large_threshold_delta(self, tmp_config):
        from auto_apply import check_safety
        config = {"thresholds": {"stop": 8.0}, "weights": {}, "auto_apply": {}}
        changes = {"thresholds": {"stop": 9.5}}  # delta 1.5 > max 1.0
        result = check_safety(changes, config)
        assert "stop" not in result["safe"].get("thresholds", {})
        assert len(result["skipped"]) > 0

    def test_safe_weight_change(self, tmp_config):
        from auto_apply import check_safety
        config = {"weights": {"completeness": 0.40}, "thresholds": {}, "auto_apply": {}}
        changes = {"weights": {"completeness": 0.45}}  # delta 0.05 < max 0.10
        result = check_safety(changes, config)
        assert "completeness" in result["safe"].get("weights", {})

    def test_blocks_large_weight_delta(self, tmp_config):
        from auto_apply import check_safety
        config = {"weights": {"completeness": 0.40}, "thresholds": {}, "auto_apply": {}}
        changes = {"weights": {"completeness": 0.55}}  # delta 0.15 > max 0.10
        result = check_safety(changes, config)
        assert "completeness" not in result["safe"].get("weights", {})
        assert len(result["skipped"]) > 0

    def test_out_of_range_stop_threshold(self, tmp_config):
        from auto_apply import check_safety
        config = {"thresholds": {"stop": 8.0}, "weights": {}, "auto_apply": {}}
        changes = {"thresholds": {"stop": 15.0}}
        result = check_safety(changes, config)
        assert "stop" not in result["safe"].get("thresholds", {})

    def test_out_of_range_move_on(self, tmp_config):
        from auto_apply import check_safety
        config = {"thresholds": {"move_on": 3.0}, "weights": {}, "auto_apply": {}}
        changes = {"thresholds": {"move_on": 10.0}}
        result = check_safety(changes, config)
        assert "move_on" not in result["safe"].get("thresholds", {})

    def test_blocks_non_numeric_values(self, tmp_config):
        from auto_apply import check_safety
        config = {"thresholds": {"stop": 8.0}, "weights": {}, "auto_apply": {}}
        changes = {"thresholds": {"stop": "not-a-number"}}
        result = check_safety(changes, config)
        assert not result["safe"].get("thresholds")

    def test_empty_changes_returns_empty(self, tmp_config):
        from auto_apply import check_safety
        config = {"thresholds": {}, "weights": {}, "auto_apply": {}}
        changes = {"thresholds": {}, "weights": {}, "auto_apply": {}}
        result = check_safety(changes, config)
        assert not result["safe"]
        assert not result["skipped"]

    def test_apply_updates_config(self, tmp_config):
        from auto_apply import apply
        changes = {"thresholds": {"stop": 8.2}}
        result = apply(changes, note="Test apply", dry_run=False)
        assert result["applied"] is True

    def test_dry_run_does_not_apply(self, tmp_config):
        from auto_apply import apply
        changes = {"thresholds": {"stop": 8.2}}
        result = apply(changes, note="Dry run test", dry_run=True)
        assert result["applied"] is False
        assert result["dry_run"] is True

    def test_no_progress_limit_within_range(self, tmp_config):
        from auto_apply import check_safety
        config = {"thresholds": {}, "weights": {}, "auto_apply": {"no_progress_limit": 3}}
        changes = {"auto_apply": {"no_progress_limit": 2}}
        result = check_safety(changes, config)
        assert result["safe"].get("auto_apply", {}).get("no_progress_limit") == 2

    def test_no_progress_limit_out_of_range(self, tmp_config):
        from auto_apply import check_safety
        config = {"thresholds": {}, "weights": {}, "auto_apply": {"no_progress_limit": 3}}
        changes = {"auto_apply": {"no_progress_limit": 99}}
        result = check_safety(changes, config)
        assert "no_progress_limit" not in result["safe"].get("auto_apply", {})