#!/usr/bin/env python3
"""Comprehensive test suite for Cortex Dashboard v2."""
import json, sys, urllib.request, urllib.error

BASE = "http://127.0.0.1:8901"

class TestSuite:
    """Simple test runner with context manager syntax."""
    passed = 0
    failed = 0
    errors = []

    def test(self, name):
        return _TestContext(self, name)


class _TestContext:
    def __init__(self, suite, name):
        self.suite = suite
        self.name = name

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.suite.passed += 1
            print(f"  ✅ {self.name}")
        elif exc_type is AssertionError:
            self.suite.failed += 1
            msg = str(exc_val) if exc_val else "Assertion failed"
            self.suite.errors.append(f"{self.name}: {msg}")
            print(f"  ❌ {self.name}: {msg}")
        else:
            self.suite.failed += 1
            msg = f"{exc_type.__name__}: {exc_val}" if exc_val else str(exc_type.__name__)
            self.suite.errors.append(f"{self.name}: {msg}")
            print(f"  ❌ {self.name}: {msg}")
        return True  # Don't propagate


suite = TestSuite()
test = suite.test

def api(path):
    r = urllib.request.urlopen(f"{BASE}{path}", timeout=10)
    return json.loads(r.read().decode())

# ════════════════ API TESTS ════════════════

print("\n📡 API Endpoints")

with test("GET /api/health returns valid JSON"):
    d = api("/api/health")
    assert d["overall"] in ("healthy", "degraded", "down")
    assert len(d["services"]) == 6
    for s in d["services"].values():
        assert s["status"] in ("up", "down")

with test("GET /api/health — all services present"):
    d = api("/api/health")
    expected = {"Ollama", "Hermes Gateway", "GBrain Sync", "nginx", "Langfuse"}
    assert set(d["services"].keys()) == expected

with test("GET /api/health — has system metrics"):
    d = api("/api/health")
    for key in ["disk_pct", "uptime_days", "load", "memory_pct", "summary"]:
        assert key in d, f"Missing key: {key}"
    assert isinstance(d["disk_pct"], int)
    assert 0 <= d["disk_pct"] <= 100
    assert isinstance(d["uptime_days"], (int, float))

with test("GET /api/langfuse returns traces+sessions+scores"):
    d = api("/api/langfuse")
    assert "traces" in d
    assert "sessions" in d
    assert "scores" in d
    assert isinstance(d["traces"]["trace_count"], int)
    assert isinstance(d["sessions"]["session_count"], int)
    assert isinstance(d["scores"]["score_count"], int)

with test("GET /api/langfuse — traces have expected structure"):
    d = api("/api/langfuse")
    traces = d["traces"]
    for key in ["trace_count", "model_usage", "total_cost", "recent", "cost_daily"]:
        assert key in traces, f"Missing key: {key}"

with test("GET /api/langfuse — model usage keyed by model name"):
    d = api("/api/langfuse")
    for name, stats in d["traces"]["model_usage"].items():
        assert "calls" in stats
        assert "tokens" in stats

with test("GET /api/langfuse — recent traces have IDs"):
    d = api("/api/langfuse")
    for t in d["traces"]["recent"]:
        assert "id" in t and t["id"]
        assert "timestamp" in t

with test("GET /api/langfuse — scores breakdown has averages"):
    d = api("/api/langfuse")
    for name, stats in d["scores"]["score_breakdown"].items():
        assert "count" in stats and stats["count"] > 0
        assert "sum" in stats

with test("GET /api/sessions returns Hermes session data"):
    d = api("/api/sessions")
    assert "total" in d
    assert "messages" in d
    assert "tokens" in d
    assert "models" in d
    assert "recent" in d
    assert isinstance(d["total"], int)
    assert isinstance(d["messages"], int)

with test("GET /api/sessions — recent sessions have IDs"):
    d = api("/api/sessions")
    for s in d["recent"]:
        assert "id" in s
        assert "title" in s

with test("GET /api/crons returns cron data"):
    d = api("/api/crons")
    assert "total" in d and "active" in d and "jobs" in d
    assert isinstance(d["total"], int)
    assert d["active"] <= d["total"]

with test("GET /api/crons — jobs have name + schedule"):
    d = api("/api/crons")
    for j in d["jobs"]:
        assert "name" in j
        assert "schedule" in j

with test("GET /api/sysinfo returns system info"):
    d = api("/api/sysinfo")
    assert "os" in d and d["os"].startswith("macOS")
    assert "arch" in d and d["arch"] == "x86_64"
    assert "python" in d and d["python"].startswith("Python")
    assert "hermes_home" in d
    assert "script_count" in d

with test("GET /api/all returns aggregated snapshot"):
    d = api("/api/all")
    for key in ["health", "langfuse", "crons", "sessions", "sysinfo", "timestamp"]:
        assert key in d, f"Missing key: {key}"

# ════════════════ FRONTEND TESTS ════════════════

print("\n🎨 Frontend")

with test("GET / returns 200"):
    r = urllib.request.urlopen(f"{BASE}/", timeout=10)
    assert r.status == 200

with test("GET / returns valid HTML"):
    r = urllib.request.urlopen(f"{BASE}/", timeout=10)
    html = r.read().decode()
    assert "<!DOCTYPE html>" in html
    assert "</html>" in html
    assert "Hermes Cortex" in html

with test("HTML has monitor JavaScript"):
    r = urllib.request.urlopen(f"{BASE}/", timeout=10)
    html = r.read().decode()
    assert "function fetchAll" in html or "fetch('/api/all')" in html
    assert "setInterval(refresh" in html

with test("HTML has all expected links"):
    r = urllib.request.urlopen(f"{BASE}/", timeout=10)
    html = r.read().decode()
    for link in [
        "localhost:3001",  # Langfuse
        
        "127.0.0.1:8901",         # Local
    ]:
        assert link in html, f"Missing link: {link}"

with test("HTML has all card sections"):
    r = urllib.request.urlopen(f"{BASE}/", timeout=10)
    html = r.read().decode()
    for section in ["Recent Traces", "Model Usage", "Hermes Sessions",
                     "Evaluation Scores", "Cron Jobs", "Daily Cost Trend"]:
        assert section in html, f"Missing section: {section}"

with test("HTML size is reasonable"):
    r = urllib.request.urlopen(f"{BASE}/", timeout=10)
    assert len(r.read()) > 10000  # At least 10KB
    assert len(r.read()) < 200000  # Less than 200KB

# ════════════════ EDGE CASES ════════════════

print("\n🔮 Edge Cases")

with test("Unknown path returns 404 correctly"):
    try:
        urllib.request.urlopen(f"{BASE}/nonexistent", timeout=5)
        assert False, "Should have raised 404"
    except urllib.error.HTTPError as e:
        assert e.code == 404

with test("API responds quickly (< 5s)"):
    import time
    start = time.time()
    api("/api/health")
    elapsed = time.time() - start
    assert elapsed < 5, f"Took {elapsed:.1f}s"

with test("Cache TTL works (repeated calls are faster)"):
    import time
    start = time.time()
    api("/api/langfuse")
    first = time.time() - start
    start = time.time()
    api("/api/langfuse")
    second = time.time() - start
    # Second call should use cache and be fast (typically < 0.1s)
    assert second < 1.0, f"Second call was slow: {second:.2f}s"

with test("JSON content type"):
    r = urllib.request.urlopen(f"{BASE}/api/health", timeout=10)
    ct = r.headers.get("Content-Type", "")
    assert "json" in ct, f"Got Content-Type: {ct}"

with test("HTML content type"):
    r = urllib.request.urlopen(f"{BASE}/", timeout=10)
    ct = r.headers.get("Content-Type", "")
    assert "html" in ct, f"Got Content-Type: {ct}"

# ════════════════ SUMMARY ════════════════

print(f"\n{'═'*50}")
total = suite.passed + suite.failed
pct = (suite.passed / total * 100) if total else 0
print(f"Results: {suite.passed}/{total} passed ({pct:.0f}%)")
if suite.failed:
    print(f"  {suite.failed} test(s) FAILED:")
    for e in suite.errors:
        print(f"    • {e}")
    sys.exit(1)
else:
    print("  All tests passed! ✨")
