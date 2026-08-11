"""L0 unit tests for lib/telegram_notify.py (design task-lifecycle-v2.md §8).

Covers (R-5/R-6/R-9/R-15/R-20/M-3): env chat_id (never hardcoded), extended
scrub gate (abs paths, ~/, user@host, bare hostnames, IPv4/IPv6), HTML
escaping, flock coalescing <=1 msg/2s (fake clock), 429 Retry-After backoff
with bounded retries + failure counter, persisted state, file logging (not
stdout), quiet-hours defer/digest flush, per-status mute registry, and the
notify message format helpers.

Hermetic: no network (urllib monkeypatched), no real ~/.hermes state
(TELEGRAM_NOTIFY_STATE_DIR + TELEGRAM_NOTIFY_ENV_FILE point at tmp dirs).
"""
from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
NOTIFY_PATH = REPO / "ops" / "scripts" / "lib" / "telegram_notify.py"


def _load():
    spec = importlib.util.spec_from_file_location("telegram_notify", NOTIFY_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {NOTIFY_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tn = _load()


# ── Fixtures: hermetic env ─────────────────────────────────

def _write_env(tmp_path: Path, token: str = "123456:TESTTOKEN", chat: str = "111222333") -> Path:
    env = tmp_path / "env"
    env.write_text(f"TELEGRAM_BOT_TOKEN={token}\nTELEGRAM_HOME_CHANNEL={chat}\n")
    return env


def _setup(tmp_path, monkeypatch, chat: str = "111222333", quiet: str = "", mute: str = ""):
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)
    env_file = _write_env(tmp_path, chat=chat)
    monkeypatch.setenv("TELEGRAM_NOTIFY_STATE_DIR", str(state_dir))
    monkeypatch.setenv("TELEGRAM_NOTIFY_ENV_FILE", str(env_file))
    monkeypatch.setenv("TASKS_NOTIFY_QUIET", quiet)
    monkeypatch.setenv("TASKS_NOTIFY_MUTE", mute)
    return state_dir, env_file


# ── Scrub gate (R-6 / NF-031 extension) ─────────────────────

def test_scrub_strips_absolute_paths():
    out = tn.scrub_text("see /home/user/hermes-cortex/ops/x.py for details")
    assert "/home/" not in out
    assert "hermes-cortex" not in out


def test_scrub_strips_tilde_paths():
    out = tn.scrub_text("config at ~/.hermes/config.yaml is fine")
    assert "~/" not in out
    assert ".hermes" not in out


def test_scrub_strips_user_host():
    out = tn.scrub_text("deploy as luke@server42 now")
    assert "luke@server42" not in out


def test_scrub_strips_bare_hostname():
    out = tn.scrub_text("check the output on titus-2 before pushing")
    assert "titus-2" not in out


def test_scrub_strips_ipv4():
    out = tn.scrub_text("dial 192.168.1.50:8903 for the bus")
    assert "192.168.1.50" not in out


def test_scrub_strips_ipv6():
    out = tn.scrub_text("connect to 2001:db8::ff00:42:8329 directly")
    assert "2001:db8::ff00:42:8329" not in out


def test_scrub_preserves_plain_words():
    out = tn.scrub_text("slice S2 completed on esther")
    assert out == "slice S2 completed on esther"


# ── Message format (F-031 / §8) ─────────────────────────────

def test_format_story_message():
    msg = tn.format_task_message("esther", "story", "Task Lifecycle v2", "in_progress", "abc-123")
    assert msg == "[esther] Task Lifecycle v2: 🚧 in_progress (abc-123)"


def test_format_slice_message_has_parent():
    msg = tn.format_task_message("esther", "slice", "S2 notify lib", "pending", "abc-124", parent_title="Task Lifecycle v2")
    assert msg == "[esther] Task Lifecycle v2 → S2 notify lib: ⏳ pending (abc-124)"


def test_format_slice_message_scrubs_title():
    msg = tn.format_task_message("esther", "slice", "fix /home/user/x", "pending", "abc-125", parent_title="story")
    assert "/home/" not in msg


def test_format_all_statuses_have_icons():
    expected = {
        "pending": "⏳",
        "in_progress": "🚧",
        "paused": "⏸️",
        "completed": "✅",
        "cancelled": "❌",
    }
    for status, icon in expected.items():
        msg = tn.format_task_message("esther", "story", "Status", status, "abc-126")
        assert msg == f"[esther] Status: {icon} {status} (abc-126)", msg


def test_format_unknown_status_no_icon():
    msg = tn.format_task_message("esther", "story", "Status", "blocked", "abc-127")
    assert msg == "[esther] Status: blocked (abc-127)"


def test_format_overdue_marker_appended():
    msg = tn.format_task_message("esther", "story", "Status", "in_progress", "abc-128", overdue=True)
    assert msg == "[esther] Status: 🚧 in_progress · ⏰ overdue (abc-128)"


def test_format_overdue_marker_slice():
    msg = tn.format_task_message("esther", "slice", "S2", "pending", "abc-129",
                                 parent_title="Story", overdue=True)
    assert msg == "[esther] Story → S2: ⏳ pending · ⏰ overdue (abc-129)"


def test_format_not_overdue_default():
    msg = tn.format_task_message("esther", "story", "Status", "in_progress", "abc-130")
    assert "⏰" not in msg


# ── Send path: success + escaping ───────────────────────────

def test_notify_sends_escaped_html(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    sent = {}

    def fake_send(token, chat_id, text):
        sent["token"] = token
        sent["chat"] = chat_id
        sent["text"] = text
        return 200

    with patch.object(tn, "_send_once", side_effect=fake_send):
        ok = tn.notify("a <b> & c", subject="hi")
    assert ok is True
    assert sent["text"] == "hi\na &lt;b&gt; &amp; c"


def test_notify_uses_env_chat_id_not_hardcoded(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, chat="999888777")
    sent = {}

    def fake_send(token, chat_id, text):
        sent["chat"] = chat_id
        return 200

    with patch.object(tn, "_send_once", side_effect=fake_send):
        tn.notify("hello")
    assert sent["chat"] == "999888777"


def test_notify_missing_token_is_silent_skip(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("TELEGRAM_NOTIFY_ENV_FILE", str(tmp_path / "empty"))
    (tmp_path / "empty").write_text("OTHER=1\n")
    with patch.object(tn, "_send_once") as mock:
        ok = tn.notify("hello")
    assert ok is False
    mock.assert_not_called()


# ── Coalescing: host-level flock + last-send (R-5) ──────────

def test_coalescing_drops_second_message_within_2s(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    calls = []
    fake_clock = {"t": 1_000_000.0}

    def fake_now():
        return fake_clock["t"]

    def fake_send(token, chat_id, text):
        calls.append(text)
        return 200

    with patch.object(tn, "_now", side_effect=fake_now), \
         patch.object(tn, "_send_once", side_effect=fake_send):
        tn.notify("first")
        fake_clock["t"] += 1.0  # 1s later — inside 2s window
        ok2 = tn.notify("second")
    assert ok2 is False
    assert len(calls) == 1


def test_coalescing_allows_after_2s(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    calls = []
    fake_clock = {"t": 1_000_000.0}

    def fake_now():
        return fake_clock["t"]

    def fake_send(token, chat_id, text):
        calls.append(text)
        return 200

    with patch.object(tn, "_now", side_effect=fake_now), \
         patch.object(tn, "_send_once", side_effect=fake_send):
        tn.notify("first")
        fake_clock["t"] += 3.0  # 3s later — outside window
        ok2 = tn.notify("second")
    assert ok2 is True
    assert len(calls) == 2


# ── 429 Retry-After backoff (R-5) ───────────────────────────

def test_429_retries_then_succeeds(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    attempts = []
    fake_clock = {"t": 1_000_000.0}
    sleeps = []

    def fake_now():
        return fake_clock["t"]

    def fake_sleep(s):
        fake_clock["t"] += s
        sleeps.append(s)

    def flaky_send(token, chat_id, text):
        attempts.append(1)
        if len(attempts) == 1:
            raise tn._RateLimited(retry_after=2)
        return 200

    with patch.object(tn, "_now", side_effect=fake_now), \
         patch.object(tn, "_sleep", side_effect=fake_sleep), \
         patch.object(tn, "_send_once", side_effect=flaky_send):
        ok = tn.notify("hello")
    assert ok is True
    assert len(attempts) == 2
    assert sleeps == [2]  # honored Retry-After


def test_429_drops_after_bounded_retries_and_counts(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    attempts = []
    fake_clock = {"t": 1_000_000.0}

    def fake_now():
        return fake_clock["t"]

    def always_429(token, chat_id, text):
        attempts.append(1)
        raise tn._RateLimited(retry_after=1)

    with patch.object(tn, "_now", side_effect=fake_now), \
         patch.object(tn, "_sleep", side_effect=lambda s: None), \
         patch.object(tn, "_send_once", side_effect=always_429):
        ok = tn.notify("hello")
    assert ok is False
    # 1 initial + 2 bounded retries = 3 attempts, then drop
    assert len(attempts) == 3


def test_failure_counter_persisted(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    def always_fail(token, chat_id, text):
        raise OSError("network down")

    with patch.object(tn, "_send_once", side_effect=always_fail):
        tn.notify("hello")
    state_file = tmp_path / "state" / "telegram-notify.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert state["failures"] == 1
    assert "network down" in state.get("last_error", "")


# ── Quiet hours (R-20) ──────────────────────────────────────

def _quiet_ts(hh_mm: str) -> float:
    """Epoch for today at HH:MM (fake clock for quiet-hours tests)."""
    from datetime import datetime
    hh, mm = (int(x) for x in hh_mm.split(":"))
    return datetime(2026, 8, 8, hh, mm, 0).timestamp()


def test_quiet_hours_defers_message(tmp_path, monkeypatch):
    state_dir, _ = _setup(tmp_path, monkeypatch, quiet="22:00-07:00")
    fake_clock = {"t": _quiet_ts("23:30")}  # in window

    def fake_now():
        return fake_clock["t"]

    with patch.object(tn, "_now", side_effect=fake_now), \
         patch.object(tn, "_send_once") as mock:
        ok = tn.notify("night message")
    assert ok is True  # accepted, deferred
    mock.assert_not_called()
    state = json.loads((state_dir / "telegram-notify.json").read_text())
    assert state.get("deferred_count") == 1


def test_quiet_hours_digest_flush_after_window(tmp_path, monkeypatch):
    state_dir, _ = _setup(tmp_path, monkeypatch, quiet="22:00-07:00")
    fake_clock = {"t": _quiet_ts("23:30")}  # in window
    sent = []

    def fake_now():
        return fake_clock["t"]

    def fake_send(token, chat_id, text):
        sent.append(text)
        return 200

    with patch.object(tn, "_now", side_effect=fake_now), \
         patch.object(tn, "_send_once", side_effect=fake_send):
        tn.notify("night one")
        tn.notify("night two")
        assert len(sent) == 0  # both deferred
        fake_clock["t"] = _quiet_ts("08:00")  # out of window
        tn.notify("morning")
    assert len(sent) == 2  # digest flush + the morning message
    assert "night one" in sent[0] and "night two" in sent[0]


# ── Mute registry (R-20) ────────────────────────────────────

def test_muted_status_suppressed(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, mute="in_progress,paused")
    with patch.object(tn, "_send_once") as mock:
        ok = tn.notify("[esther] S2: in_progress (x)", status="in_progress")
    assert ok is True  # intentionally suppressed
    mock.assert_not_called()


def test_unmuted_status_sends(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, mute="in_progress,paused")
    with patch.object(tn, "_send_once", return_value=200) as mock:
        ok = tn.notify("[esther] S2: completed (x)", status="completed")
    assert ok is True
    mock.assert_called_once()


# ── Health surface (for doctor S7) ──────────────────────────

def test_health_reports_state(tmp_path, monkeypatch):
    state_dir, _ = _setup(tmp_path, monkeypatch)
    (state_dir / "telegram-notify.json").write_text(json.dumps(
        {"failures": 3, "last_error": "boom", "sent": 10, "coalesced": 4}
    ))
    h = tn.telegram_notify_health()
    assert h["failures"] == 3
    assert h["last_error"] == "boom"
    assert h["sent"] == 10
