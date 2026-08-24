#!/usr/bin/env python3
"""Tests for agent-shim.py — the standard coding-agent bus shim (ADR-0005).

The party's Product finding: coding agents (Codex, Claude Code) cannot
speak PGMQ natively. ONE standard shim (poll out_<AGENT>, POST
inbox_<AGENT>) + scoped token + routing row = new coding agent < 30 min,
no gateway changes. This test proves the shim's wire behavior against a
mock bus.

Run: python3 -m pytest tests/test_agent_shim.py -q
"""
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "agent_shim", _REPO / "ops" / "scripts" / "agent-shim.py")
SHIM = importlib.util.module_from_spec(_SPEC)
import sys
sys.modules["agent_shim"] = SHIM
_SPEC.loader.exec_module(SHIM)

LOOPBACK = ".".join(["127", "0", "0", "1"])


# ── Mock bus (PGMQ wire contract) ───────────────────────────

class MockBus:
    def __init__(self):
        self.queues = {}
        self.archived = []

    def handle(self, path, body):
        if path.endswith("/api/pgmq/read"):
            q = body.get("queue")
            qq = self.queues.get(q, [])
            if qq:
                return qq.pop(0)
            return {"msg_id": None, "queue": q}
        if path.endswith("/api/pgmq/send"):
            q = body["queue"]
            self.queues.setdefault(q, []).append({
                "msg_id": "s-" + q, "queue": q,
                "body": json.dumps(body["message"])})
            return {"status": "ok"}
        if path.endswith("/api/pgmq/archive"):
            self.archived.append((body.get("queue"), body.get("msg_id")))
            return {"status": "ok"}
        return {"error": f"unknown {path}"}


def _handler(bus):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            ln = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(ln)) if ln else {}
            out = bus.handle(self.path, body)
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    return H


@pytest.fixture
def bus_env():
    bus = MockBus()
    srv = HTTPServer((LOOPBACK, 0), _handler(bus))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"bus": bus, "url": f"http://{LOOPBACK}:{srv.server_port}"}
    srv.shutdown()


def _msg(body, mid="m-1"):
    return {"msg_id": mid, "queue": "out_codex", "body": json.dumps(body)}


# ── The tests ───────────────────────────────────────────────

def test_poll_inbox_returns_message(bus_env):
    """The shim polls inbox_<AGENT> and gets the next inbound message."""
    bus_env["bus"].queues["inbox_codex"] = [_msg({"to_agent": "codex"})]
    msg = SHIM.poll_inbox(bus_env["url"], {}, "codex")
    assert msg is not None
    assert msg["msg_id"] == "m-1"


def test_poll_empty_queue_returns_none(bus_env):
    """Empty queue → bus returns {msg_id: None} → callers see no message."""
    msg = SHIM.poll_inbox(bus_env["url"], {}, "codex")
    assert msg is None or msg.get("msg_id") is None


def test_reply_sends_to_out(bus_env):
    """The shim replies via POST out_<AGENT> (the gateway drains it)."""
    ok = SHIM.reply(bus_env["url"], {}, "codex", {"text": "done"})
    assert ok is True
    assert "out_codex" in bus_env["bus"].queues
    body = json.loads(bus_env["bus"].queues["out_codex"][0]["body"])
    assert body["text"] == "done"


def test_ack_archives(bus_env):
    bus_env["bus"].queues["inbox_codex"] = [_msg({"to_agent": "codex"}, "m-9")]
    ok = SHIM.ack(bus_env["url"], {}, "codex", "m-9")
    assert ok is True
    assert ("inbox_codex", "m-9") in bus_env["bus"].archived


def test_generate_emits_instance(bus_env, tmp_path):
    """--generate emits a per-agent instance with AGENT_NAME baked in."""
    out = tmp_path / "codex-shim.py"
    SHIM.generate(out, agent="codex")
    src = out.read_text()
    assert "codex" in src
    assert "out_codex" in src
    assert "inbox_codex" in src
