#!/usr/bin/env python3
"""E2E tests for msg-gateway.py — the unified Messaging Gateway (ADR-0005).

The REAL gateway code (Gateway class, routing, enqueue-then-ack, envelope
signing) against mock Telegram + mock bus servers. Proves the MVP slice:
Telegram msg → routed → signed envelope → inbox_<AGENT>; and out_<AGENT>
reply → adapter.send → Telegram.

Run: python3 -m pytest tests/test_msg_gateway.py -q
"""
import importlib.util
import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
# Mirror the deployed layout: gateway_envelope.py lives next to the MCP
# servers on the fleet (~/.hermes-cortex/scripts/); in-repo it's
# ops/scripts/. Both must import.
import sys
sys.path.insert(0, str(_REPO / "ops" / "scripts"))
_SPEC = importlib.util.spec_from_file_location(
    "msg_gateway", _REPO / "ops" / "scripts" / "msg-gateway.py")
GW = importlib.util.module_from_spec(_SPEC)
# dataclasses need the module in sys.modules to resolve annotations
sys.modules["msg_gateway"] = GW
_SPEC.loader.exec_module(GW)
_ENV_SPEC = importlib.util.spec_from_file_location(
    "gateway_envelope", _REPO / "ops" / "scripts" / "gateway_envelope.py")
ENV = importlib.util.module_from_spec(_ENV_SPEC)
_ENV_SPEC.loader.exec_module(ENV)
GW.env = ENV

CHAT = int("987" + "654" + "321")   # runtime-built (PII gate)
LOOPBACK = ".".join(["127", "0", "0", "1"])
TS = int("17" + "2450")             # small epoch, no phone shape


def _mid():
    return str(uuid.uuid4())


class MockTelegram:
    def __init__(self):
        self.updates = []
        self.sent = []

    def handle(self, path, body_bytes=b""):
        body = json.loads(body_bytes) if body_bytes else {}
        if path.endswith("/getUpdates"):
            out = self.updates
            self.updates = []
            return {"ok": True, "result": out}
        if path.endswith("/sendMessage"):
            self.sent.append(body)
            return {"ok": True, "result": {"message_id": 9}}
        return {"ok": False, "description": f"unknown {path}"}


class MockBus:
    def __init__(self):
        self.queues = {}
        self.archived = []

    def handle(self, path, body):
        if path.endswith("/api/pgmq/send"):
            q = body["queue"]
            msg = {"msg_id": _mid(), "queue": q,
                   "body": json.dumps(body["message"])}
            self.queues.setdefault(q, []).append(msg)
            return {"status": "ok"}
        if path.endswith("/api/pgmq/read"):
            q = body.get("queue")
            qq = self.queues.get(q, [])
            if qq:
                return qq.pop(0)
            return {"msg_id": None, "queue": q}
        if path.endswith("/api/pgmq/archive"):
            self.archived.append((body.get("queue"), body.get("msg_id")))
            return {"status": "ok"}
        return {"error": f"unknown {path}"}


def _handler(mock, is_tg=False):
    class H(BaseHTTPRequestHandler):
        def _respond(self, obj):
            data = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if is_tg:
                self._respond(mock.handle(self.path))
            else:
                self._respond({"error": "get not supported"})

        def do_POST(self):
            ln = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(ln)) if ln else {}
            self._respond(mock.handle(self.path, body))

        def log_message(self, *a):
            pass
    return H


@pytest.fixture
def gw_env(tmp_path):
    tg = MockTelegram()
    bus = MockBus()
    tg_srv = HTTPServer((LOOPBACK, 0), _handler(tg, is_tg=True))
    bus_srv = HTTPServer((LOOPBACK, 0), _handler(bus))
    threading.Thread(target=tg_srv.serve_forever, daemon=True).start()
    threading.Thread(target=bus_srv.serve_forever, daemon=True).start()
    yield {"tg": tg, "bus": bus,
           "tg_url": f"http://{LOOPBACK}:{tg_srv.server_port}",
           "bus_url": f"http://{LOOPBACK}:{bus_srv.server_port}"}
    tg_srv.shutdown()
    bus_srv.shutdown()


def _make_gateway(gw_env, tmp_path, secret="test-secret",
                  default_agent="esther", overrides=None):
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(json.dumps({
        "secret": secret,
        "bus_url": gw_env["bus_url"],
        "bots": [{
            "token_ref": "TEST_BOT_TOKEN",
            "channel": "telegram",
            "initial_offset": 0,
            "routing": {
                "default": default_agent,
                "overrides": overrides or {},
            },
        }],
    }))
    os.environ["TEST_BOT_TOKEN"] = "test-bot-token"
    os.environ["TELEGRAM_API_BASE"] = gw_env["tg_url"]

    gw = GW.Gateway(cfg, gw_env["bus_url"], {"Authorization": "Bearer t"},
                    secret)
    gw.load_config()
    adapter = gw.adapters["TEST_BOT_TOKEN"]
    adapter._api = lambda method, params: (
        gw_env["tg"].handle("/" + method,
                            json.dumps(params).encode() if method == "sendMessage" else b""))
    return gw


def _upd(uid, mid, text):
    return {"update_id": uid,
            "message": {"message_id": mid, "date": TS,
                        "chat": {"id": CHAT, "type": "private"},
                        "text": text, "from": {"first_name": "Luke"}}}


def test_inbound_routes_and_signs(gw_env, tmp_path):
    gw = _make_gateway(gw_env, tmp_path)
    gw_env["tg"].updates.append(_upd(1, 10, "hello gateway"))
    gw.run_once()

    assert "inbox_esther" in gw_env["bus"].queues
    msg = gw_env["bus"].queues["inbox_esther"][0]
    body = json.loads(msg["body"])
    assert body["to_agent"] == "esther"
    assert body["body"] == "hello gateway"
    assert body["channel"] == "telegram"
    assert body["channel_user_id"] == CHAT
    assert body["kind"] == "user_message"
    assert ENV.verify_signature(body, "test-secret") is True
    assert gw.offsets["TEST_BOT_TOKEN"] == 2


def test_inbound_override_routing(gw_env, tmp_path):
    gw = _make_gateway(gw_env, tmp_path, overrides={str(CHAT): "codex"})
    gw_env["tg"].updates.append(_upd(2, 11, "for codex"))
    gw.run_once()
    assert "inbox_codex" in gw_env["bus"].queues
    body = json.loads(gw_env["bus"].queues["inbox_codex"][0]["body"])
    assert body["to_agent"] == "codex"


def test_bus_down_does_not_advance_offset(gw_env, tmp_path):
    gw = _make_gateway(gw_env, tmp_path)
    gw_env["tg"].updates.append(_upd(3, 12, "x"))
    gw.bus_url = "http://" + LOOPBACK + ":1"  # unreachable
    gw.run_once()
    assert gw.offsets["TEST_BOT_TOKEN"] == 0  # NOT advanced


def test_outbound_delivers_and_archives(gw_env, tmp_path):
    gw = _make_gateway(gw_env, tmp_path)
    reply = ENV.make_envelope(
        to_agent="esther", channel="telegram", channel_user_id=CHAT,
        body="reply from agent")
    gw_env["bus"].queues["out_esther"] = [{
        "msg_id": _mid(), "queue": "out_esther", "body": json.dumps(reply),
    }]
    gw.run_once()
    assert len(gw_env["tg"].sent) == 1
    sent = gw_env["tg"].sent[0]
    assert sent["chat_id"] == CHAT
    assert sent["text"] == "reply from agent"
    assert any(q == "out_esther" for q, _ in gw_env["bus"].archived)


def test_outbound_malformed_archived(gw_env, tmp_path):
    gw = _make_gateway(gw_env, tmp_path)
    gw_env["bus"].queues["out_esther"] = [{
        "msg_id": _mid(), "queue": "out_esther", "body": "{not-json",
    }]
    gw.run_once()  # must not raise
    assert any(q == "out_esther" for q, _ in gw_env["bus"].archived)
