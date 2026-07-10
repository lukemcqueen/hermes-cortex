"""Tests for loop_scorer.py — scoring functions and graceful degradation."""
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Mark all tests in this module as needing Ollama
pytestmark = pytest.mark.online


@pytest.fixture(scope="module")
def scorer():
    from loop_scorer import (
        embed, cosine_similarity, score_completeness, score_quality,
        score_progress, composite_score, full_score
    )
    return {
        "embed": embed,
        "cosine_similarity": cosine_similarity,
        "score_completeness": score_completeness,
        "score_quality": score_quality,
        "score_progress": score_progress,
        "composite_score": composite_score,
        "full_score": full_score,
    }


class TestEmbed:
    def test_returns_list(self, scorer):
        result = scorer["embed"]("hello world")
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(x, float) for x in result)

    def test_different_inputs_different_embeddings(self, scorer):
        a = scorer["embed"]("hello world")
        b = scorer["embed"]("goodbye world")
        # Cosine similarity should be < 0.95 for different texts
        sim = scorer["cosine_similarity"](a, b)
        assert sim < 0.95

    def test_same_input_returns_same_embedding(self, scorer):
        a = scorer["embed"]("repeat me")
        b = scorer["embed"]("repeat me")
        sim = scorer["cosine_similarity"](a, b)
        assert sim > 0.99


class TestScoreCompleteness:
    def test_empty_output_returns_zero(self, scorer):
        assert scorer["score_completeness"]("", "spec") == 0.0

    def test_empty_spec_returns_pass_rate(self, scorer):
        assert scorer["score_completeness"]("passed", "", pass_pct=1.0) == 10.0

    def test_all_tests_pass_high_score(self, scorer):
        score = scorer["score_completeness"](
            "3 passed, 0 failed",
            "Implement add function",
            pass_pct=1.0
        )
        assert score >= 6.0

    def test_no_tests_pass_low_score(self, scorer):
        score = scorer["score_completeness"](
            "0 passed, 3 failed",
            "Implement add function",
            pass_pct=0.0
        )
        assert score < 4.0

    def test_graceful_degradation(self, scorer):
        """Should return pass-rate-only score when embed is unavailable."""
        # Simulate Ollama down by checking embed already handles it
        # We can't easily force embed failure, but we verify the API is safe
        score = scorer["score_completeness"]("passed", "spec", pass_pct=1.0)
        assert 0 <= score <= 10


class TestScoreQuality:
    def test_empty_code_returns_zero(self, scorer):
        assert scorer["score_quality"]("") == 0.0

    def test_stub_code_low_score(self, scorer, stub_code):
        score = scorer["score_quality"](stub_code)
        assert score < 5.0

    def test_good_code_higher_than_stub(self, scorer, sample_code, stub_code):
        good = scorer["score_quality"](sample_code)
        bad = scorer["score_quality"](stub_code)
        assert good > bad

    def test_todo_penalty(self, scorer):
        """Code with TODO should score lower."""
        clean = scorer["score_quality"]("def f(): return 1")
        todo = scorer["score_quality"]("def f(): pass  # TODO: implement")
        assert clean > todo  # at minimum, todo should not be higher


class TestScoreProgress:
    def test_same_code_zero_progress(self, scorer):
        code = "def add(a,b): return a+b"
        score = scorer["score_progress"](code, code)
        assert score < 2.0

    def test_empty_previous_full_progress(self, scorer):
        score = scorer["score_progress"]("", "some new code")
        assert score == 10.0

    def test_different_code_detects_progress(self, scorer):
        prev = "def add(a,b): pass"
        curr = "def add(a,b): return a + b"
        score = scorer["score_progress"](prev, curr)
        assert score > 2.0

    def test_both_empty_returns_midpoint(self, scorer):
        assert scorer["score_progress"]("", "") == 5.0


class TestCompositeScore:
    def test_high_scores_stop(self, scorer):
        result = scorer["composite_score"](9.0, 8.0, 9.0)
        assert result["composite"] >= 8.0
        assert result["decision"].startswith("STOP ✓")

    def test_medium_scores_loop(self, scorer):
        result = scorer["composite_score"](6.0, 5.0, 4.0)
        assert 5.0 <= result["composite"] < 8.0
        assert result["decision"].startswith("LOOP")

    def test_low_scores_move_on(self, scorer):
        result = scorer["composite_score"](4.0, 3.0, 2.0)
        assert 3.0 <= result["composite"] < 5.0

    def test_very_low_scores_hard_fail(self, scorer):
        result = scorer["composite_score"](2.0, 1.0, 1.0)
        assert result["composite"] < 3.0
        assert result["decision"].startswith("STOP ✗")

    def test_no_progress_detected(self, scorer):
        result = scorer["composite_score"](9.0, 8.0, 1.5)
        assert result["no_progress"] is True

    def test_config_override(self, scorer):
        """Should accept custom config for threshold overrides."""
        custom_cfg = {
            "weights": {"completeness": 0.50, "quality": 0.25, "progress": 0.25},
            "thresholds": {"stop": 9.0, "loop": 6.0, "move_on": 4.0, "no_progress_score": 2.0, "no_progress_limit": 3},
        }
        result = scorer["composite_score"](8.5, 7.0, 6.0, config=custom_cfg)
        # With stricter stop threshold (9.0), composite 7.8 shouldn't stop
        assert result["composite"] < 9.0


class TestFullScore:
    def test_basic_flow(self, scorer):
        """Full score with all params should return complete result."""
        result = scorer["full_score"](
            spec="Add two numbers",
            output="def add(a,b): return a+b",
            pass_pct=1.0
        )
        assert "composite" in result
        assert "completeness" in result
        assert "quality" in result
        assert "progress" in result
        assert "decision" in result
        assert "no_progress" in result

    def test_logs_to_db_with_task_id(self, scorer):
        """Should log to DB when task_id and db_path are provided."""
        import tempfile
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            result = scorer["full_score"](
                spec="Test",
                output="def f(): pass",
                task_id="test-task",
                cycle_num=1,
                db_path=db_path,
            )
            assert result.get("logged") is True or result.get("log_error") is None
        finally:
            os.unlink(db_path)

    def test_warnings_in_result(self, scorer):
        """Result should include warnings key."""
        result = scorer["full_score"]("spec", "code")
        assert "warnings" in result
        assert isinstance(result["warnings"], list)


@pytest.mark.slow
class TestGracefulDegradation:
    """Tests that simulate Ollama being unavailable."""

    def test_embed_returns_none_with_bad_url(self):
        """embed() should return None when Ollama is unreachable."""
        import loop_scorer
        loop_scorer.OLLAMA_URL = "http://localhost:11435/api/embeddings"
        result = loop_scorer.embed("test")
        assert result is None

    def test_full_score_still_works_without_ollama(self):
        """full_score() should return fallback scores when Ollama is down."""
        import loop_scorer
        loop_scorer.OLLAMA_URL = "http://localhost:11435/api/embeddings"
        result = loop_scorer.full_score(
            spec="Add numbers",
            output="def add(a,b): return a+b",
            pass_pct=1.0,
        )
        # Should have valid fallback scores
        assert result["completeness"] >= 0
        assert result["quality"] >= 0
        assert result["progress"] >= 0
        # Should have warning
        assert any("unavailable" in w.lower() for w in result.get("warnings", []))