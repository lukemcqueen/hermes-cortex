#!/usr/bin/env python3
"""cortex-gateway functional parity matrix — executed, not asserted.

Answers Luke's "thoroughly test for parity between the two gateways" (2026-10-02). The
matrix and its verdict live in docs/design/cortex-gateway-parity.md; THIS file is the
evidence for it: golden Telegram updates driven through the target's real `parse()` and
`send()`, plus the outbound behaviors a cutover depends on.

Design note — the gaps are asserted as TODAY'S behavior on purpose. If someone implements
media, slash dispatch, reaction/callback handling or chunking, the corresponding case here
FAILS, which forces the matrix to be updated instead of letting it silently go stale. A
gap register that cannot notice an improvement is not a register.

Run: python3 -m pytest tests/test_cortex_gateway_parity_matrix.py -q
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


def _adapter(home_channel=None):
    """home_channel=None is intentional in one case: no chat AND no home channel
    must refuse rather than guess a destination."""
    a = T.TelegramAdapter(token="test-token", home_channel=home_channel)
    sent: list[dict] = []

    def _fake_api(method, params):
        sent.append({"method": method, "params": params})
        return {"ok": True}

    a._api = _fake_api          # capture outbound without touching Telegram
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
            print(f"  ignored  {name:<22} {'GAP: ' + c['gap'] if c['gap'] else '(no text)'}")
            if c["gap"]:
                _GAPS.append(f"{name}: {c['gap']}")
            continue
        assert env is not None, f"{name}: expected an envelope, got None"
        assert env["body"] == c["body"], f"{name}: body {env['body']!r} != {c['body']!r}"
        assert env["channel"] == "telegram"
        assert env["channel_user_id"] is not None
        assert env["thread_id"] == c["thread"], f"{name}: thread {env['thread_id']!r} != {c['thread']!r}"
        assert env["media"] == [], f"{name}: target never populates media"
        print(f"  envelope {name:<22} body={env['body'][:20]!r} thread={env['thread_id']}")
        if c["gap"]:
            _GAPS.append(f"{name}: {c['gap']}")
    assert len(_CASES) >= 10, "the golden set shrank — update the matrix deliberately"


def test_outbound_behaviors():
    """The outbound behaviors a cutover depends on, asserted against real send()."""
    print("outbound: send() behaviors")
    # 1. plain text
    a, sent = _adapter()
    assert a.send({"channel_user_id": 100001, "body": "hi"}) is True
    assert sent[-1]["method"] == "sendMessage" and sent[-1]["params"]["chat_id"] == 100001

    # 2. reply threading when the envelope carries it
    a, sent = _adapter()
    a.send({"channel_user_id": 100001, "body": "hi", "reply_to_msg_id": 99})
    assert sent[-1]["params"]["reply_to_message_id"] == 99

    # 3. proactive message with no chat → the home channel
    a, sent = _adapter(home_channel=100001)
    a.send({"body": "cron output"})
    assert sent[-1]["params"]["chat_id"] == 100001

    # 4. no chat and no home channel → refuse (never guess a destination)
    a, _ = _adapter(home_channel=None)
    try:
        a.send({"body": "nowhere"})
        raise AssertionError("send with no chat and no home channel should refuse")
    except ValueError:
        pass

    # 5. LONG MESSAGE: the target truncates at 4000 — an explicit, silent data loss.
    a, sent = _adapter()
    a.send({"channel_user_id": 100001, "body": "x" * 5000})
    sent_len = len(sent[-1]["params"]["text"])
    assert sent_len == 4000, f"truncation length changed to {sent_len} — update the matrix"
    _GAPS.append("outbound: long replies are truncated at 4000 chars (no chunking)")
    print(f"  long reply truncated to {sent_len} chars (GAP: no chunking)")


def test_gap_register_is_non_empty():
    """The register must still name real gaps — empty means the matrix is stale."""
    assert _GAPS, "no gaps recorded: either they were all fixed (update the matrix) or the fixtures lost their gap markers"
    print(f"gap register ({len(_GAPS)} entries):")
    for g in _GAPS:
        print(f"  - {g}")
