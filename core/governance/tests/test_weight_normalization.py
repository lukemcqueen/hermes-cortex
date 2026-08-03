"""Regression tests for weight normalization + weight-set integrity.

Covers two fixed bugs (2026-08-03):
1. loop_evaluator.get_weight_recommendations() produced non-normalized weight
   patches (e.g. 0.46+0.36+0.36 = 1.18) because each dimension was adjusted
   independently. composite_score requires weights to sum to 1.0.
2. auto_apply.check_safety() accepted any weight set within per-weight bounds,
   so a malformed evaluator patch could corrupt the runtime config at high
   confidence. The merged proposed set must now sum to ~1.0.
"""
import os
import sys
import pytest

GOV_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GOV_DIR)

from auto_apply import check_safety  # noqa: E402
from loop_evaluator import LoopEvaluator  # noqa: E402

BASE_CONFIG = {
    "weights": {"completeness": 0.40, "quality": 0.30, "progress": 0.30},
    "auto_apply": {"max_weight_delta": 0.10},
}


class TestWeightRecommendationsNormalize:
    def test_recommended_weights_sum_to_one(self):
        """The full recommended set must sum to 1.0 (composite_score contract)."""
        ev = LoopEvaluator()
        try:
            recs = ev.get_weight_recommendations()
            if not recs:
                pytest.skip("no weight recommendations from live DB")
            total = sum(r["recommended_weight"] for r in recs)
            assert abs(total - 1.0) < 0.01, f"weights sum to {total:.3f}, not 1.0"
        finally:
            ev.close()

    def test_single_dimension_rec_normalizes_with_current(self):
        """A lone recommendation must not push the set past 1.0."""
        # Simulate: only completeness recommended at 0.50 while others stay 0.30
        proposed = {"completeness": 0.50}
        current = {"completeness": 0.40, "quality": 0.30, "progress": 0.30}
        full = {d: proposed.get(d, current[d]) for d in current}
        total = sum(full.values())
        assert abs(total - 1.0) > 1e-9  # raw set is 1.10 — needs normalization
        full = {d: round(w / total, 4) for d, w in full.items()}
        assert abs(sum(full.values()) - 1.0) < 0.01


class TestAutoApplyWeightSetIntegrity:
    def test_malformed_weight_set_rejected(self):
        """Patch summing to 1.18 must be rejected wholesale."""
        bad = {"weights": {"completeness": 0.46, "quality": 0.36, "progress": 0.36}}
        res = check_safety(bad, BASE_CONFIG)
        assert res["safe"].get("weights", {}) == {}
        assert any("sums to" in s for s in res["skipped"])

    def test_valid_weight_set_accepted(self):
        """Patch summing to 1.0 passes."""
        good = {"weights": {"completeness": 0.42, "quality": 0.29, "progress": 0.29}}
        res = check_safety(good, BASE_CONFIG)
        assert res["safe"]["weights"] == good["weights"]
        assert res["skipped"] == []

    def test_partial_set_validated_against_merged_config(self):
        """A patch touching only one weight is validated against the full set."""
        one = {"weights": {"completeness": 0.50}}
        res = check_safety(one, BASE_CONFIG)
        # merged = 0.50 + 0.30 + 0.30 = 1.10 → rejected
        assert res["safe"].get("weights", {}) == {}
        assert any("sums to" in s for s in res["skipped"])
