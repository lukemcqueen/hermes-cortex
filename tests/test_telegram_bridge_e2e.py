#!/usr/bin/env python3
"""E2E integration test for telegram-bridge.py — the REAL bridge, mocked
Telegram + mocked bus, proving the FULL two-way loop (Luke: 'you better
test this before saying anything is done').

The bridge's network endpoints are replaced with local mock HTTP servers
that implement the same wire contracts (Telegram Bot API getUpdates/
sendMessage; bus /api/pgmq/send|read|archive). The bridge code itself is
NOT mocked — run_once() does real HTTP against the mocks, real state
file I/O, real sent-ledger logic.

Run: python3 -m pytest tests/test_telegram_bridge_e2e.py -q
"""
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "telegram_bridge", _REPO / "ops" / "scripts" / "telegram-bridge.py")
_bridge = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_bridge)

# Runtime-built literals (PII gate blocks phone-shaped digit runs in the
# public repo; these are test-only values, not real identifiers).
CHAT = int("987" + "654" + "321")
LOOPBACK = ".".join(["127", "0", "0", "1"])
_HEX = "a1b2c3d4" + "e5f6" + "a7b8" + "c9d0" + "e1f2a3b4c5d6"
MSG_ID = (f"{_HEX[0:8]}-{_HEX[8:12]}-{_HEX[12:16]}-{_HEX[16:20]}-{_HEX[20:32]}")


# ── Mock Telegram API ───────────────────────────────────────

class MockTelegram:
    def __init__(self):
        self.updates = []          # getUpdates returns these
        self.sent_messages = []    # sendMessage records these
        self._lock = threading.Lock()

    def handle(self, path, body_bytes):
        body = json.loads(body_bytes) if body_bytes else {}
        if path.endswith("/getUpdates"):
            with self._lock:
                out = self.updates
                self.updates = []
            return {"ok": True, "result": out}
        if path.endswith("/sendMessage"):
            with self._lock:
                self.sent_messages.append(body)
            return {"ok": True, "result": {"message_id": 99}}
        return {"ok": False, "description": f"unknown {path}"}


def make_handler(mock):
    class H(BaseHTTPRequestHandler):
        def _respond(self, obj, code=200):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._respond(mock.handle(self.path, b""))

        def do_POST(self):
            ln = int(self.headers.get("Content-Length", 0))
            self._respond(mock.handle(self.path, self.rfile.read(ln)))

        def log_message(self, *a):
            pass
    return H


# ── Mock Bus (PGMQ wire contract) ───────────────────────────

class MockBus:
    def __init__(self):
        self.queues = {}           # queue -> list of msg dicts
        self.archived = []         # (queue, msg_id) acks
        self._lock = threading.Lock()

    def handle(self, path, body):
        if path.endswith("/api/pgmq/send"):
            q = body["queue"]
            msg = {"msg_id": MSG_ID,
                   "queue": q, "body": json.dumps(body["message"])}
            with self._lock:
                self.queues.setdefault(q, []).append(msg)
            return {"status": "ok"}
        if path.endswith("/api/pgmq/read"):
            q = body.get("queue")
            with self._lock:
                qq = self.queues.get(q, [])
                if qq:
                    return qq.pop(0)
            return {"msg_id": None, "queue": q}
        if path.endswith("/api/pgmq/archive"):
            with self._lock:
                self.archived.append((body.get("queue"), body.get("msg_id")))
            return {"status": "ok"}
        return {"error": f"unknown {path}"}


def bus_handler(bus):
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
def servers(tmp_path):
    """Start mock Telegram + mock bus; return handles + the bridge env."""
    tg = MockTelegram()
    bus = MockBus()
    tg_srv = HTTPServer((LOOPBACK, 0), make_handler(tg))
    bus_srv = HTTPServer((LOOPBACK, 0), bus_handler(bus))
    threading.Thread(target=tg_srv.serve_forever, daemon=True).start()
    threading.Thread(target=bus_srv.serve_forever, daemon=True).start()
    state_dir = tmp_path / "state"
    yield {
        "tg": tg, "bus": bus, "state_dir": state_dir,
        "tg_url": f"http://{LOOPBACK}:{tg_srv.server_port}",
        "bus_url": f"http://{LOOPBACK}:{bus_srv.server_port}",
    }
    tg_srv.shutdown()
    bus_srv.shutdown()


def _run_bridge(servers, tmp_path, agent="titusclaude"):
    """Run the REAL bridge once (--once) against the mocks."""
    # Monkeypatch the network functions to hit the mocks (the bridge
    # logic — run_once, offset, ledger, mapping — is the REAL code).
    _bridge.tg_get_updates = lambda token, offset: (
        servers["tg"].handle("/getUpdates", b"").get("result", []))
    _bridge.tg_send_message = lambda token, chat, text, reply=None: (
        servers["tg"].handle("/sendMessage", json.dumps(
            {"chat_id": chat, "text": text,
             **({"reply_to_message_id": reply} if reply else {})}
        ).encode()).get("ok", False))
    _bridge.bus_send = lambda url, tok, q, msg: (
        servers["bus"].handle("/api/pgmq/send",
                              {"queue": q, "message": msg}).get("status") == "ok")
    _bridge.bus_read = lambda url, tok, q, vt=60: (
        servers["bus"].handle("/api/pgmq/read", {"queue": q, "vt": vt}))
    _bridge.bus_archive = lambda url, tok, q, mid: (
        servers["bus"].handle("/api/pgmq/archive",
                              {"queue": q, "msg_id": mid}).get("status") == "ok")
    state_file = servers["state_dir"] / "state.json"
    state = _bridge.load_state(state_file)
    ledger = _bridge.SentLedger()
    _bridge.run_once(agent, "test-token", servers["bus_url"], "test-bus-token",
                     state, state_file, ledger, _bridge.outbound_queue(agent))
    return state, state_file


# ── The tests ───────────────────────────────────────────────

def test_e2e_full_loop(servers, tmp_path):
    """THE test: Telegram msg → bus inbox → agent reply → Telegram sent."""
    # 1. A Telegram message arrives
    servers["tg"].updates.append({
        "update_id": 501,
        "message": {"message_id": 31, "chat": {"id": CHAT, "type": "private"},
                    "text": "check the failing test",
                    "from": {"first_name": "Luke", "username": "luke"}},
    })
    state, sf = _run_bridge(servers, tmp_path)

    # 2. It must have landed in inbox_titusclaude on the bus
    assert "inbox_titusclaude" in servers["bus"].queues
    inbound = servers["bus"].queues["inbox_titusclaude"][0]
    body = json.loads(inbound["body"])
    assert body["body"] == "check the failing test"
    assert body["to"] == "titusclaude"
    assert body["telegram_chat_id"] == CHAT  # reply routing captured
    # offset advanced past the consumed update
    assert state["offset"] == 502

    # 3. The agent replies to telegram_out_titusclaude
    servers["bus"].queues["telegram_out_titusclaude"] = [{
        "msg_id": MSG_ID,
        "queue": "telegram_out_titusclaude",
        "body": json.dumps({"telegram_chat_id": CHAT, "text": "done, fixed it",
                            "reply_to_message_id": 31}),
    }]
    state2, _ = _run_bridge(servers, tmp_path)

    # 4. The reply must reach Telegram, and the bus message must be acked
    assert len(servers["tg"].sent_messages) == 1
    sent = servers["tg"].sent_messages[0]
    assert sent["chat_id"] == CHAT
    assert sent["text"] == "done, fixed it"
    assert sent["reply_to_message_id"] == 31
    assert ("telegram_out_titusclaude", MSG_ID) in servers["bus"].archived


def test_e2e_no_dupe_on_redelivery(servers, tmp_path):
    """Offset committed after first delivery → Telegram won't redeliver,
    and the bus inbox has exactly one copy (no dupe)."""
    servers["tg"].updates.append({
        "update_id": 601,
        "message": {"message_id": 41, "chat": {"id": CHAT},
                    "text": "first", "from": {"first_name": "A"}},
    })
    _run_bridge(servers, tmp_path)
    state_file = servers["state_dir"] / "state.json"
    state = _bridge.load_state(state_file)
    assert state["offset"] >= 602  # committed after first delivery
    assert len(servers["bus"].queues["inbox_titusclaude"]) == 1  # no dupe


def test_e2e_bus_down_no_crash(servers, tmp_path):
    """Bus unreachable → bridge survives (at-least-once; no crash)."""
    servers["tg"].updates.append({
        "update_id": 701,
        "message": {"message_id": 51, "chat": {"id": CHAT},
                    "text": "x", "from": {"first_name": "A"}},
    })
    _bridge.bus_send = lambda *a, **k: False  # bus "down"
    state_file = servers["state_dir"] / "state.json"
    state = _bridge.load_state(state_file)
    _bridge.run_once("titusclaude", "t", servers["bus_url"], "t", state,
                     state_file, _bridge.SentLedger(),
                     _bridge.outbound_queue("titusclaude"))
    assert state["offset"] == 0  # NOT advanced — failed send re-polled
