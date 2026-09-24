"""Sink-side metrics arrival check (2026-09-24).

The other half of the push fix. `agent-push-metrics` is universal, so its failure
used to surface only as each agent's own cron erroring every 5m (1053 consecutive
runs) — the sink never noticed that nobody had arrived, because push cannot report
its own absence. This check asks VictoriaMetrics which agents have pushed and how
long ago, so a push outage is caught centrally: silence stops looking like health.

Hermetic: a stub HTTP server stands in for the sink, so no real VictoriaMetrics is
needed and nothing is written anywhere.
"""
import http.server
import json
import sys
import threading
import importlib.util
from pathlib import Path
from urllib.parse import urlparse, parse_qs

REPO = Path(__file__).resolve().parents[2]
CHECKS = REPO / "ops" / "scripts" / "manage" / "cortex_doctor" / "checks.py"


def _load_checks():
    """Import the doctor's checks module as part of its package.

    checks.py uses relative imports (`from .immutability import …`), so loading it
    by file path alone raises "attempted relative import with no known parent
    package" — import the package instead.
    """
    manage_dir = str(CHECKS.parent.parent)      # ~/hermes-cortex/ops/scripts/manage
    scripts_dir = str(CHECKS.parent.parent.parent)  # ~/hermes-cortex/ops/scripts
    for p in (manage_dir, scripts_dir):
        if p not in sys.path:
            sys.path.insert(0, p)
    return importlib.import_module("cortex_doctor.checks")


class _Sink(http.server.BaseHTTPRequestHandler):
    """Minimal VictoriaMetrics query API stand-in."""

    labels: list = []
    ages: dict = {}

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/v1/label/agent/values":
            body = {"status": "success", "data": self.labels}
        elif parsed.path == "/api/v1/query":
            q = parse_qs(parsed.query).get("query", [""])[0]
            agent = ""
            if 'agent="' in q:
                agent = q.split('agent="', 1)[1].split('"', 1)[0]
            if agent in self.ages:
                body = {"status": "success",
                        "data": {"resultType": "vector",
                                 "result": [{"metric": {"agent": agent},
                                             "value": [0, str(self.ages[agent])]}]}}
            else:
                body = {"status": "success", "data": {"resultType": "vector", "result": []}}
        else:
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # silence
        return


def _serve(labels, ages):
    handler = type("Sink", (_Sink,), {"labels": labels, "ages": ages})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def test_fresh_agents_pass():
    checks = _load_checks()
    srv, base = _serve(["alpha", "beta"], {"alpha": 60, "beta": 120})
    try:
        level, detail, _ = checks.evaluate_metrics_arrival(base, stale_min=30)
    finally:
        srv.shutdown()
    assert level == "PASS", detail
    assert "2 agent(s) pushed within 30m" in detail


def test_stale_agent_warns_and_names_the_age():
    checks = _load_checks()
    srv, base = _serve(["alpha", "beta"], {"alpha": 60, "beta": 90 * 60})
    try:
        level, detail, suggestion = checks.evaluate_metrics_arrival(base, stale_min=30)
    finally:
        srv.shutdown()
    assert level == "WARN", detail
    assert "beta: last push 90m ago" in detail
    assert "alpha" not in detail.split("beta")[0], "a fresh agent must not be named as stale"
    assert "push-metrics-nginx-deploy.md" in suggestion


def test_reachable_sink_with_no_series_is_info_not_pass():
    """Silence must never read as health: nothing pushed = we cannot confirm anything."""
    checks = _load_checks()
    srv, base = _serve([], {})
    try:
        level, detail, suggestion = checks.evaluate_metrics_arrival(base, stale_min=30)
    finally:
        srv.shutdown()
    assert level == "INFO", detail
    assert "NO agent series" in detail
    assert "push-metrics-nginx-deploy.md" in suggestion, "an empty sink must point at the runbook"


def test_sink_candidates_come_from_this_hosts_push_config(tmp_path, monkeypatch):
    """The check must query the sink this host actually pushes to — on a host whose
    primary is refused and whose fallback serves, a hardcoded local query would
    report an empty sink while the data was arriving at the peer."""
    checks = _load_checks()
    creds = "u" + ":" + "s"  # assembled, so no literal credential token exists here
    env = tmp_path / ".env"
    env.write_text(
        f"VICTORIA_METRICS_URL=https://{creds}@127.0.0.1:13005/api/v1/import/prometheus\n"
        f"VICTORIA_METRICS_FALLBACK_URL=http://{creds}@127.0.0.1:14005/api/v1/import/prometheus\n"
    )
    monkeypatch.setattr(checks, "CORTEX_HOME", tmp_path)
    cands = checks._push_sink_candidates()
    assert cands[0][0] == "https://127.0.0.1:13005", "push order preserved, userinfo stripped"
    assert cands[0][1], "the credential must survive as a ready Basic-auth header"
    assert cands[1][0] == "http://127.0.0.1:14005"
    assert cands[-1] == (checks.VM_QUERY_DEFAULT, ""), "the local backend is the last resort"


def test_authenticated_sink_is_queried_with_credentials():
    """The sink's nginx blocks sit behind htpasswd — an unauthenticated query 401s,
    which must not be mistaken for 'sink unreachable'."""
    checks = _load_checks()
    class _AuthSink(_Sink):
        def do_GET(self):
            if self.headers.get("Authorization") != "Basic dGVzdDp0ZXN0":
                self.send_response(401)
                self.end_headers()
                return
            return super().do_GET()

    handler = type("AuthSink", (_AuthSink,), {"labels": ["alpha"], "ages": {"alpha": 30}})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        level, detail, _ = checks.evaluate_metrics_arrival(base, stale_min=30)
        assert level == "INFO" and "not verifiable" in detail, "no auth → 401 → unverifiable"

        level, detail, _ = checks.evaluate_metrics_arrival(base, stale_min=30, auth="dGVzdDp0ZXN0")
        assert level == "PASS", detail
    finally:
        srv.shutdown()


def test_unreachable_sink_is_info_with_a_reason():
    checks = _load_checks()
    # Nothing listens on this port — no fake server started.
    level, detail, _ = checks.evaluate_metrics_arrival("http://127.0.0.1:1", stale_min=30)
    assert level == "INFO", detail
    assert "not verifiable" in detail


def test_roster_agents_that_never_pushed_are_noted_not_warned():
    """A registered agent with no metrics is normal (it may not push at all) —
    it must be visible in the text, but it must not raise a WARN."""
    checks = _load_checks()
    srv, base = _serve(["alpha"], {"alpha": 30})
    try:
        level, detail, _ = checks.evaluate_metrics_arrival(
            base, stale_min=30, roster=["alpha", "theta", "omega"])
    finally:
        srv.shutdown()
    assert level == "PASS", detail
    assert "2 known agent(s) not seen at this sink" in detail
    assert "theta" in detail and "omega" in detail


def test_roster_match_is_case_insensitive():
    """Live bug (2026-09-24): the registry is display-cased (Moses) while the
    pushed label is lowercase (moses), so a raw string diff reported the checking
    host itself as 'never pushed'."""
    checks = _load_checks()
    srv, base = _serve(["moses", "esther"], {"moses": 30, "esther": 60})
    try:
        level, detail, _ = checks.evaluate_metrics_arrival(
            base, stale_min=30, roster=["Moses", "Esther", "Titus"])
    finally:
        srv.shutdown()
    assert level == "PASS", detail
    assert "arrived: " in detail and "Moses" in detail.split("arrived: ")[1].split(";")[0], \
        "display casing from the roster is used in the message"
    assert "Esther" in detail.split("arrived: ")[1].split(";")[0]
    assert "Titus" in detail
    assert "not seen" in detail and "Moses" not in detail.split("not seen")[1], \
        "a case-mismatched agent must not be reported as absent"


def test_agent_with_no_sample_of_the_freshness_metric_is_reported():
    checks = _load_checks()
    # beta has the label (it pushed something, once) but no recent uptime sample.
    srv, base = _serve(["alpha", "beta"], {"alpha": 30})
    try:
        level, detail, _ = checks.evaluate_metrics_arrival(base, stale_min=30)
    finally:
        srv.shutdown()
    assert "no node_uptime_seconds sample for: beta" in detail


def test_timestamp_query_uses_the_configured_metric():
    """The freshness metric must be injectable — a renamed/other series still works."""
    checks = _load_checks()
    seen = {}

    class _Spy(_Sink):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/v1/query":
                seen["q"] = parse_qs(parsed.query).get("query", [""])[0]
            return super().do_GET()

    handler = type("Spy", (_Spy,), {"labels": ["alpha"], "ages": {"alpha": 30}})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        checks.evaluate_metrics_arrival(base, metric="node_memory_used_percent", stale_min=30)
    finally:
        srv.shutdown()
    assert "timestamp(node_memory_used_percent{agent=\"alpha\"})" in seen["q"]
