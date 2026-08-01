"""Shared fixtures for loop-governance tests."""
import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="function")
def tmp_db():
    """Create a temporary LoopDB for testing (auto-cleaned)."""
    from loop_db import LoopDB
    db = LoopDB(":memory:")  # in-memory SQLite, auto-cleanup
    yield db
    db.close()


@pytest.fixture(scope="function")
def tmp_config():
    """Create a temporary config file with defaults."""
    import tempfile
    cfg = {
        "version": 1,
        "weights": {"completeness": 0.40, "quality": 0.30, "progress": 0.30},
        "thresholds": {"stop": 8.0, "loop": 5.0, "move_on": 3.0, "no_progress_score": 2.0, "no_progress_limit": 3},
        "auto_apply": {"min_confidence": 0.7, "max_threshold_delta": 1.0, "max_weight_delta": 0.10, "requires_review": True},
    }
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w") as f:
        json.dump(cfg, f)
    yield path
    os.unlink(path)


@pytest.fixture(scope="function")
def seeded_db(tmp_db):
    """Pre-fill LoopDB with sample cycles including user feedback."""
    rows = [
        ("feature-a", 1, 6.5, 5.0, 7.0, 6.0, 0, "LOOP 🔄", None, ""),
        ("feature-a", 2, 8.5, 7.0, 8.0, 8.0, 0, "STOP ✓", 0, "Good stop"),
        ("feature-b", 1, 7.0, 6.0, 9.0, 7.2, 0, "STOP ✓", 1, "Premature stop"),
        ("feature-b", 2, 9.0, 8.0, 9.0, 8.7, 0, "STOP ✓", 0, "Good stop"),
        ("feature-c", 1, 2.0, 2.0, 1.0, 1.5, 1, "STOP ✗", None, ""),
    ]
    for row in rows:
        tmp_db.conn.execute("""INSERT INTO loop_cycles
            (task_id, cycle_num, completeness, quality, progress, composite,
             no_progress, decision, user_overrode, outcome_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", row)
    tmp_db.conn.commit()
    return tmp_db


@pytest.fixture(scope="function")
def sample_code():
    return """
def add(a, b):
    \"\"\"Add two numbers and return the result.\"\"\"
    if not isinstance(a, (int, float)):
        raise TypeError("a must be numeric")
    if not isinstance(b, (int, float)):
        raise TypeError("b must be numeric")
    return a + b
"""


@pytest.fixture(scope="function")
def stub_code():
    return """
def add(a, b):
    pass  # TODO: implement
"""