#!/usr/bin/env python3
"""cortex-gateway functional parity matrix — executed, not asserted.

Answers Luke's "thoroughly test for parity between the two gateways" and then
"build feature parity, and once we are confident, then cut over" (2026-10-02).

Parity is built in SLICES and this file is the progress bar: every entry in the gap
register is asserted as TODAY'S behavior, so implementing it FAILS the test and forces
the matrix (docs/design/cortex-gateway-parity.md) to be updated. A gap register that
cannot notice an improvement is not a register.

Slice 1 (transport) closed: media inbound + caption, reply linkage, edited/reaction/
callback forwarding, outbound chunking (no truncation), media outbound, formatting with
a plain-text fallback, retry/backoff, polling-conflict classification, and failing closed
when TELEGRAM_API_BASE is unset.
Still open (daemon slice): slash-command dispatch (/stop), inline keyboards, DM-topic
anchors, busy/interrupt queueing, typing indicators.

Run: python3 -m pytest tests/test_cortex_gateway_parity_matrix.py -q -s
"""
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

from cortex_gateway import transport as T  # noqa: E402

_FIXTURES = json.loads((_REPO / "tests" / "fixtures" / "telegram-golden-updates.json").read_text())
_CASES = _FIXTURES["cases"]
_GAPS: list[str] = []


def _adapter(home_channel=None, results=None):
    """Capture outbound calls instead of touching Telegram.

    `results` lets a case script a sequence of API answers (e.g. reject-then-accept).
    """
    a = T.TelegramAdapter(token="test-token", home_channel=home_channel)
    sent: list[dict] = []
    answers = list(results or [])

    def _fake_api(method, params):
        # COPY the params: send() mutates the dict it passes (it pops parse_mode for
        # the plain-text retry), so recording by reference rewrites history and made
        # "the retry dropped the formatting" pass for the wrong reason.
        sent.append({"method": method, "params": dict(params)})
        return answers.pop(0) if answers else {"ok": True}

    a._api = _fake_api
    return a, sent


def test_inbound_parity_matrix():
    """Each golden update → the target's actual envelope (or None), per the matrix."""
    print("inbound: golden Telegram updates → cortex-gateway parse()")
    for c in _CASES:
        a, _ = _adapter()
        env = a.parse(c["update"])
        name = c["name"]
        if c["expect"] is None:
            assert env is None, f"{name}: expected the target to IGNORE this update, got {env}"
            print(f"  ignored   {name:<22} (no text, no media)")
            continue
        assert env is not None, f"{name}: expected an envelope, got None"
        assert env["body"] == c["body"], f"{name}: body {env['body']!r} != {c['body']!r}"
        assert env["channel"] == "telegram"
        assert isinstance(env["channel_user_id"], int)
        assert env["thread_id"] == c["thread"], f"{name}: thread {env['thread_id']!r} != {c['thread']!r}"
        assert len(env["media"]) == c["media"], f"{name}: media {len(env['media'])} != {c['media']}"
        assert env["reply_to_msg_id"] == c["reply_to"], \
            f"{name}: reply_to {env['reply_to_msg_id']!r} != {c['reply_to']!r}"
        assert env["tg_kind"] == c["tg_kind"], f"{name}: tg_kind {env['tg_kind']!r} != {c['tg_kind']!r}"
        print(f"  envelope  {name:<22} body={env['body'][:18]!r} media={len(env['media'])} "
              f"reply={env['reply_to_msg_id']} kind={env['tg_kind']}")
        if c["gap"]:
            _GAPS.append(f"{name}: {c['gap']}")
    assert len(_CASES) >= 11, "the golden set shrank — update the matrix deliberately"


def test_outbound_behaviors(monkeypatch):
    """Outbound behaviors a cutover depends on, asserted against the real send()."""
    print("outbound: send() behaviors")
    # 1. plain text
    a, sent = _adapter()
    assert a.send({"channel_user_id": 100001, "body": "hi"}) is True
    assert sent[-1]["method"] == "sendMessage" and sent[-1]["params"]["chat_id"] == 100001

    # 2. reply threading
    a, sent = _adapter()
    a.send({"channel_user_id": 100001, "body": "hi", "reply_to_msg_id": 99})
    assert sent[-1]["params"]["reply_to_message_id"] == 99

    # 3. thread id passes through
    a, sent = _adapter()
    a.send({"channel_user_id": 100001, "body": "hi", "thread_id": 42})
    assert sent[-1]["params"]["message_thread_id"] == 42

    # 4. proactive message with no chat → the home channel
    a, sent = _adapter(home_channel=100001)
    a.send({"body": "cron output"})
    assert sent[-1]["params"]["chat_id"] == 100001

    # 5. no chat and no home channel → refuse (never guess a destination)
    a, _ = _adapter(home_channel=None)
    try:
        a.send({"body": "nowhere"})
        raise AssertionError("send with no chat and no home channel should refuse")
    except ValueError:
        pass

    # 6. CHUNKING: a long reply is split, never truncated — slice 1 closed this gap.
    a, sent = _adapter()
    body = "line\n" * 2000                     # 10k chars
    assert a.send({"channel_user_id": 100001, "body": body}) is True
    texts = [s["params"]["text"] for s in sent]
    assert len(texts) > 1, "a 10k body must be chunked, not sent whole"
    assert all(len(t) <= T.TG_MAX_CHARS for t in texts), "every chunk must fit Telegram's limit"
    assert "".join(texts) == body, "chunking must not lose or reorder characters"
    print(f"  chunked {len(body)} chars into {len(texts)} messages, all characters preserved")

    # 7. MEDIA OUTBOUND: attachments are sent (photo → sendPhoto), not dropped.
    a, sent = _adapter()
    a.send({"channel_user_id": 100001, "body": "see attached",
            "media": [{"kind": "photo", "file_id": "abc", "caption": "cap"}]})
    assert [s["method"] for s in sent] == ["sendPhoto", "sendMessage"], sent
    assert sent[0]["params"]["photo"] == "abc" and sent[0]["params"]["caption"] == "cap"

    # 8. FORMATTING with a fallback: parse_mode is sent, and a rejection retries plain
    #    (formatting must never cost a message).
    a, sent = _adapter(results=[{"ok": False, "description": "can't parse entities"},
                                {"ok": True}])
    ok = a.send({"channel_user_id": 100001, "body": "*bold*", "parse_mode": "MarkdownV2"})
    assert ok is True
    assert sent[0]["params"].get("parse_mode") == "MarkdownV2"
    assert "parse_mode" not in sent[1]["params"], "the retry must drop the formatting"

    # 9. env-driven formatting, and an invalid mode is ignored (never guessed on)
    monkeypatch.setenv("TELEGRAM_PARSE_MODE", "HTML")
    a, sent = _adapter()
    a.send({"channel_user_id": 100001, "body": "<b>x</b>"})
    assert sent[0]["params"].get("parse_mode") == "HTML"
    monkeypatch.setenv("TELEGRAM_PARSE_MODE", "NotAMode")
    a, sent = _adapter()
    a.send({"channel_user_id": 100001, "body": "plain"})
    assert "parse_mode" not in sent[0]["params"]


def test_fail_closed_without_api_base(monkeypatch):
    """TELEGRAM_API_BASE missing must be a loud error, not a broken URL.

    The old code defaulted it to "" and built '/bot<token>/method' — an invalid URL that
    fails at send time, per call, forever. msg-gateway.py refuses to start; so do we now.
    """
    monkeypatch.delenv("TELEGRAM_API_BASE", raising=False)
    try:
        T.api_base()
        raise AssertionError("api_base() must refuse when TELEGRAM_API_BASE is unset")
    except RuntimeError as e:
        assert "TELEGRAM_API_BASE" in str(e)
    monkeypatch.setenv("TELEGRAM_API_BASE", "https://api.example.invalid")
    assert T.api_base() == "https://api.example.invalid"


def test_polling_conflict_is_classified():
    """A second poller must surface as PollingConflict, not a generic error or a loop."""
    a, _ = _adapter()
    a._api = lambda method, params, attempts=4: {
        "ok": False, "description": "Conflict: terminated by other getUpdates request"}
    try:
        a.get_updates()
        raise AssertionError("a conflict must raise")
    except T.PollingConflict as e:
        assert "Conflict" in str(e)


def test_gap_register_shrank_and_still_names_what_is_left():
    """The register is the progress bar: transport gaps closed, daemon gaps left."""
    assert _GAPS, "no gaps recorded — if they were all fixed, update the matrix"
    assert all("DAEMON SLICE" in g or "anchors" in g or "inline-keyboard" in g
               or "bindings" in g or "button" in g for g in _GAPS), \
        f"a transport-level gap is still registered after slice 1: {_GAPS}"
    print(f"gap register ({len(_GAPS)} entries — daemon slice):")
    for g in _GAPS:
        print(f"  - {g}")
