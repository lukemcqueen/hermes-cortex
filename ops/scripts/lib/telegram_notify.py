#!/usr/bin/env python3
"""lib/telegram_notify.py — Shared Telegram notification module.

Single copy of the Bot API send path for Hermes Cortex (design
docs/design/task-lifecycle-v2.md §8 — closes R-5, R-6, R-9, R-15, R-20, M-3).

Imported by:
  - ops/scripts/agent/agent-message-handler.py   (handler pickup/result alerts)
  - ops/scripts/fleet/local-orch-fleet-command-verifier.py (timeout alerts)
  - ops/scripts/manage/task-db.py                 (S3: task-event notify)

What this module does:
  - Single token read: TELEGRAM_BOT_TOKEN from ~/.hermes/.env (never code)
  - Recipient: TELEGRAM_HOME_CHANNEL from env / .env (never hardcoded —
    removes the chat id from the public repo)
  - Extended PII scrub gate (R-6/NF-031): strips abs paths, ~/, user@host,
    bare hostnames, IPv4/IPv6 from notify text
  - HTML escaping (parse_mode=HTML)
  - Host-level flock + last-send timestamp file -> global coalescing <=1 msg/2s
    (cross-process — task-db.py is per-invocation, R-5)
  - 429 -> honor Retry-After, bounded retries (2), then drop + count (R-5)
  - Persisted failure counter (~/.hermes-cortex/state/telegram-notify.json),
    surfaced via telegram_notify_health() for the doctor (S7)
  - Logs go to a FILE (state/telegram-notify.log), never cron stdout (R-15)
  - Send is post-commit, time-boxed <=3s per attempt, NON-FATAL — a notify
    failure never rolls back the task write or crashes the caller
  - Quiet-hours window (TASKS_NOTIFY_QUIET=22:00-07:00) defers to a digest
    flushed at window end (R-20)
  - Per-status mute registry (TASKS_NOTIFY_MUTE=in_progress,paused) (R-20)

Token is NEVER logged. Chat id is NEVER logged. Only the state counters and
sanitized messages are persisted.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ── Config ──────────────────────────────────────────────────

COALESCE_WINDOW_S = 2.0          # max 1 msg / 2s (NF-030)
MAX_429_RETRIES = 2              # 1 initial + 2 bounded retries, then drop
RETRY_AFTER_CAP_S = 5.0          # never sleep longer than this on 429
HTTP_TIMEOUT_S = 3.0             # time-boxed per attempt (design <=3s)
MAX_DEFERRED = 50                # quiet-hours digest cap (oldest dropped)

# Paths are resolved LAZILY (via _state_dir()/_env_file() etc.) so tests can
# point TELEGRAM_NOTIFY_STATE_DIR / TELEGRAM_NOTIFY_ENV_FILE at tmp dirs after
# import. Never use import-time path constants in this module.

# ── PII scrub gate (R-6 / NF-031, extended) ─────────────────


def _state_dir() -> Path:
    return Path(os.environ.get("TELEGRAM_NOTIFY_STATE_DIR",
                               Path.home() / ".hermes-cortex" / "state"))


def _state_file() -> Path:
    return _state_dir() / "telegram-notify.json"


def _log_file() -> Path:
    return _state_dir() / "telegram-notify.log"


def _lock_file() -> Path:
    return _state_dir() / "telegram-notify.lock"


def _env_file() -> Path:
    return Path(os.environ.get("TELEGRAM_NOTIFY_ENV_FILE",
                               Path.home() / ".hermes" / ".env"))

# ── PII scrub gate (R-6 / NF-031, extended) ─────────────────

# Absolute paths: /home/..., /Users/..., /var/..., /etc/..., /opt/..., etc.
_ABS_PATH_RE = re.compile(r"(?:/(?:home|Users|var|etc|opt|usr|tmp|root|srv|data))[^\s<>\"']*")
# Tilde paths: ~/...
_TILDE_RE = re.compile(r"~[^\s<>\"']*")
# user@host (host may be bare or FQDN)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+(?::\d+)?\b")
# IPv4
_IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
# IPv6 (compressed + full forms)
_IPV6_RE = re.compile(
    r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
    r"|\b(?:[0-9a-fA-F]{1,4}:){1,7}:"
    r"|\b(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}\b"
    r"|\b::(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}\b"
)
# Bare hostnames: hyphenated lowercase tokens ending in digits (titus-2,
# node-01, web-7). Task ids are UUID-shaped and pass through the format
# helper unscrubbed, so they are never mangled.
_BARE_HOST_RE = re.compile(r"\b[a-z][a-z0-9-]*-[0-9]+\b")
# Dotted hostnames / FQDNs: foo.example.com, bar.local
_FQDN_RE = re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+){1,}\.(?:local|lan|internal|home|server|host|com|net|org|io)\b", re.IGNORECASE)

_SCRUB_RULES = (
    ("<abs-path>", _ABS_PATH_RE),
    ("<home>", _TILDE_RE),
    ("<email>", _EMAIL_RE),
    ("<ip>", _IPV6_RE),
    ("<ip>", _IPV4_RE),
    ("<host>", _BARE_HOST_RE),
    ("<host>", _FQDN_RE),
)


class _RateLimited(Exception):
    """Raised by _send_once on HTTP 429 with Retry-After."""

    def __init__(self, retry_after: float = 2.0):
        try:
            retry_after = float(retry_after)
        except (TypeError, ValueError):
            retry_after = 2.0
        self.retry_after = max(0.0, min(retry_after, RETRY_AFTER_CAP_S))
        super().__init__(f"rate limited (retry in {self.retry_after:.0f}s)")


# ── Logging (R-15: file, never cron stdout) ─────────────────

def _log(msg: str) -> None:
    try:
        _state_dir().mkdir(parents=True, exist_ok=True)
        with _log_file().open("a") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        sys.stderr.write(f"[telegram_notify] {msg}\n")  # fallback — never raise


# ── State (persisted failure counter + coalescing timestamp) ─

def _default_state() -> dict:
    return {
        "failures": 0,
        "last_error": None,
        "last_send": 0.0,
        "sent": 0,
        "coalesced": 0,
        "muted": 0,
        "deferred_count": 0,
        "deferred": [],
        "env_perms_ok": True,
    }


def _load_state() -> dict:
    try:
        data = json.loads(_state_file().read_text())
        state = _default_state()
        state.update({k: v for k, v in data.items() if k in state})
        return state
    except (OSError, json.JSONDecodeError):
        return _default_state()


def _save_state(state: dict) -> None:
    try:
        _state_dir().mkdir(parents=True, exist_ok=True)
        _state_file().write_text(json.dumps(state, indent=2))
    except OSError as e:
        _log(f"state save failed: {e}")


# ── Env load (R-6: chat id from env, never code) ────────────

def _load_env() -> tuple[str, str, bool]:
    """Return (token, chat_id, env_perms_ok).

    Token: TELEGRAM_BOT_TOKEN from ~/.hermes/.env only (never code).
    Chat id: TELEGRAM_HOME_CHANNEL from process env, falling back to .env.
    Never logs either value.
    """
    token = ""
    chat_id = os.environ.get("TELEGRAM_HOME_CHANNEL", "")
    perms_ok = True
    env_file = _env_file()
    try:
        if env_file.exists():
            mode = stat.S_IMODE(env_file.stat().st_mode)
            perms_ok = (mode == 0o600)
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip("'\"")
                elif line.startswith("TELEGRAM_HOME_CHANNEL=") and not chat_id:
                    chat_id = line.split("=", 1)[1].strip().strip("'\"")
    except OSError as e:
        _log(f"env load failed: {e}")
        return "", "", False
    return token, chat_id, perms_ok


# ── Public: scrub gate ──────────────────────────────────────

def scrub_text(text: str) -> str:
    """Strip PII from notify text: abs paths, ~/, user@host, bare/FQDN
    hostnames, IPv4/IPv6. Pure function — no I/O."""
    if not text:
        return text
    out = text
    for replacement, pattern in _SCRUB_RULES:
        out = pattern.sub(replacement, out)
    return out


def html_escape(text: str) -> str:
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))


# ── Public: message format (F-031 / §8) ─────────────────────

# Task lifecycle icons — the status word in every task-event Telegram
# message carries its state icon so the DM digest is scannable at a
# glance. Applies to ALL agents (shared lib, deployed fleet-wide).
STATUS_ICONS = {
    "pending": "⏳",
    "in_progress": "🚧",
    "paused": "⏸️",
    "completed": "✅",
    "cancelled": "❌",
}


def format_task_message(
    agent: str,
    kind: str,
    title: str,
    status: str,
    task_id: str,
    parent_title: str | None = None,
    overdue: bool = False,
) -> str:
    """[agent] story: <icon> status (id)         for story rows
       [agent] story -> slice: <icon> status (id) for slice rows
    Fields: agent, kind, title (scrubbed), status, id. NEVER the body.
    Task id passes through unscrubbed — it is a UUID, not free text.
    Unknown statuses render with no icon (forward-compatible).
    overdue=True appends a ⏰ marker (derived from due date, not a
    stored status — computed by the caller)."""
    clean_title = scrub_text(title or "")
    icon = STATUS_ICONS.get(status, "")
    status_text = f"{icon} {status}".strip()
    if overdue:
        status_text = f"{status_text} · ⏰ overdue"
    if kind == "slice" and parent_title:
        parent = scrub_text(parent_title)
        return f"[{agent}] {parent} → {clean_title}: {status_text} ({task_id})"
    return f"[{agent}] {clean_title}: {status_text} ({task_id})"


# ── Quiet hours (R-20) ──────────────────────────────────────

def _parse_quiet_window(spec: str) -> tuple[float, float] | None:
    """Parse 'HH:MM-HH:MM' into (start_minutes, end_minutes).

    start > end means an overnight window (22:00-07:00). Returns None when
    unset or malformed (no quiet hours enforced)."""
    if not spec:
        return None
    try:
        start_s, end_s = spec.split("-")
        sh, sm = (int(x) for x in start_s.strip().split(":"))
        eh, em = (int(x) for x in end_s.strip().split(":"))
        return (sh * 60 + sm, eh * 60 + em)
    except (ValueError, AttributeError):
        _log(f"TASKS_NOTIFY_QUIET malformed: {spec!r} — quiet hours disabled")
        return None


def _in_quiet_hours(now_ts: float, window: tuple[float, float] | None) -> bool:
    if window is None:
        return False
    start, end = window
    now_min = time.localtime(now_ts).tm_hour * 60 + time.localtime(now_ts).tm_min
    if start <= end:
        return start <= now_min < end
    return now_min >= start or now_min < end  # overnight


def _mute_set(spec: str) -> set[str]:
    return {s.strip() for s in spec.split(",") if s.strip()}


# ── Clock / sleep seams (tests patch these) ─────────────────

def _now() -> float:
    return time.time()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


# ── Send (429 backoff inside) ───────────────────────────────

def _send_once(token: str, chat_id: str, text: str) -> int:
    """One HTTP POST to the Bot API. Raises _RateLimited on 429.
    Time-boxed <=3s per attempt. Returns HTTP status on success."""
    data = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    ).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        if e.code == 429:
            retry_after = float(e.headers.get("Retry-After", 2.0))
            raise _RateLimited(min(retry_after, RETRY_AFTER_CAP_S)) from e
        raise


def _send_with_backoff(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    """Send honoring 429 Retry-After, bounded retries (2), then drop + count.
    Returns (delivered, error_message_or_empty)."""
    attempt = 0
    while True:
        try:
            _send_once(token, chat_id, text)
            return True, ""
        except _RateLimited as e:
            attempt += 1
            if attempt > MAX_429_RETRIES:
                return False, f"429 after {attempt} attempts (retry_after={e.retry_after:.0f}s)"
            _log(f"429 — retry {attempt}/{MAX_429_RETRIES} in {e.retry_after:.0f}s")
            _sleep(e.retry_after)
        # network / other — no retry, count once
        except Exception as e:
            _log(f"send error (no retry): {type(e).__name__}")
            return False, f"{type(e).__name__}: {e}"


# ── Flock (host-level coalescing, cross-process) ────────────

class _flock:
    """Context manager: exclusive advisory lock on LOCK_FILE."""

    def __enter__(self):
        _state_dir().mkdir(parents=True, exist_ok=True)
        self.fh = _lock_file().open("a+")
        fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        try:
            fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        finally:
            self.fh.close()
        return False


# ── Public: notify ──────────────────────────────────────────

def notify(message: str, subject: str = "", status: str | None = None) -> bool:
    """Send a Telegram notification (post-commit, non-fatal).

    Args:
      message: free text — scrubbed + HTML-escaped before send.
      subject: optional prefix line (also scrubbed/escaped).
      status:  task status — if in TASKS_NOTIFY_MUTE, suppressed silently.

    Returns:
      True  — delivered, deferred (quiet hours), or intentionally suppressed
              (muted / coalesced are reported as skipped)
      False — dropped (no token/chat configured, 429 budget exhausted, or
              send error)

    Never raises. Never logs token or chat id. Never prints to stdout.
    """
    try:
        token, chat_id, perms_ok = _load_env()
        if not token or not chat_id:
            _log(f"notify skipped: token={'set' if token else 'MISSING'} "
                 f"chat={'set' if chat_id else 'MISSING'}")
            return False

        # Compose + scrub + escape
        text = f"{subject}\n{message}" if subject else message
        text = html_escape(scrub_text(text))

        with _flock():
            state = _load_state()

            # Mute registry (R-20)
            mute_spec = os.environ.get("TASKS_NOTIFY_MUTE", "")
            if status and status in _mute_set(mute_spec):
                state["muted"] += 1
                state["env_perms_ok"] = perms_ok
                _save_state(state)
                _log(f"notify suppressed (muted status={status})")
                return True

            # Quiet hours (R-20): defer to digest
            quiet_spec = os.environ.get("TASKS_NOTIFY_QUIET", "")
            window = _parse_quiet_window(quiet_spec)
            if _in_quiet_hours(_now(), window):
                state["deferred"].append(text)
                if len(state["deferred"]) > MAX_DEFERRED:
                    state["deferred"] = state["deferred"][-MAX_DEFERRED:]
                state["deferred_count"] = len(state["deferred"])
                state["env_perms_ok"] = perms_ok
                _save_state(state)
                _log("notify deferred (quiet hours)")
                return True

            # Flush deferred digest if window just ended
            if state.get("deferred"):
                digest = state["deferred"]
                state["deferred"] = []
                state["deferred_count"] = 0
                _save_state(state)
                digest_text = html_escape("🔕 quiet-hours digest:\n" + "\n".join(
                    digest if isinstance(digest, list) else [digest]))
                ok, err = _send_with_backoff(token, chat_id, digest_text)
                if ok:
                    state["sent"] += 1
                else:
                    state["failures"] += 1
                    state["last_error"] = f"quiet-hours digest send failed: {err}"
                state["env_perms_ok"] = perms_ok
                _save_state(state)
                _log(f"flushed quiet-hours digest ({len(digest)} msgs)")

            # Coalescing (R-5 / NF-030): <=1 msg/2s, cross-process
            now_ts = _now()
            if now_ts - state.get("last_send", 0.0) < COALESCE_WINDOW_S:
                state["coalesced"] += 1
                state["env_perms_ok"] = perms_ok
                _save_state(state)
                _log("notify coalesced (within 2s window)")
                return False

            # Send
            ok, err = _send_with_backoff(token, chat_id, text)
            if ok:
                state["sent"] += 1
                state["last_send"] = now_ts
                state["env_perms_ok"] = perms_ok
                _save_state(state)
                _log("notify sent")
                return True
            else:
                state["failures"] += 1
                state["last_error"] = err
                state["env_perms_ok"] = perms_ok
                _save_state(state)
                return False
    except Exception as e:
        _log(f"notify unexpected error: {type(e).__name__}")
        # last-resort guard — notify is NEVER fatal
        return False


# ── Public: health surface (doctor S7) ──────────────────────

def telegram_notify_health() -> dict:
    """State summary for the doctor's telegram_notify_health WARN check."""
    state = _load_state()
    return {
        "failures": state.get("failures", 0),
        "last_error": state.get("last_error"),
        "last_send": state.get("last_send", 0.0),
        "sent": state.get("sent", 0),
        "coalesced": state.get("coalesced", 0),
        "muted": state.get("muted", 0),
        "deferred_count": state.get("deferred_count", 0),
        "env_perms_ok": state.get("env_perms_ok", True),
        "log_file": str(_log_file()),
    }


if __name__ == "__main__":
    # CLI self-test: send a message from the command line (no cron stdout)
    import sys
    body = sys.argv[1] if len(sys.argv) > 1 else "self-test ping"
    ok = notify(body, subject="telegram_notify self-test")
    sys.exit(0 if ok else 1)
