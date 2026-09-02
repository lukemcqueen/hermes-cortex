"""Rate limiter tests. Loads by file path — never mutates sys.path (see
test_bus_validate.py header for why that matters)."""
import importlib.util
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
RATELIMIT_PATH = os.path.join(TESTS_DIR, "..", "core", "cortex_bus", "ratelimit.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.normpath(path))
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ratelimit = _load("cortex_bus_ratelimit_under_test", RATELIMIT_PATH)
RateLimiter = ratelimit.RateLimiter


def test_allows_within_window():
    rl = RateLimiter(max_per_window=3, window_seconds=60)
    assert rl.allow("agent-a")
    assert rl.allow("agent-a")
    assert rl.allow("agent-a")
    assert not rl.allow("agent-a")  # 4th exceeds the window


def test_independent_per_agent():
    rl = RateLimiter(max_per_window=1, window_seconds=60)
    assert rl.allow("agent-a")
    assert rl.allow("agent-b")  # different agent, own quota


def test_window_slides():
    rl = RateLimiter(max_per_window=2, window_seconds=60)
    assert rl.allow("agent-a")
    assert rl.allow("agent-a")
    assert not rl.allow("agent-a")
    # Simulate time passing: events expire, quota frees up.
    rl._events["agent-a"] = [rl._events["agent-a"][1] - 61]
    assert rl.allow("agent-a")
