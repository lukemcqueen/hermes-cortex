"""cortex_gateway.restarts — "the gateway restarted while you were away" markers.

``/restart`` replies once and then EXITS the process; systemd brings it back. So the
human's last evidence of the restart is a message that arrived *before* it, and
nothing afterwards — which makes "did it actually restart?" unanswerable from the
chat. The AGENT cannot answer it either, and this is the trap: the session is
deliberately preserved across a gateway restart, so the agent still holds the whole
conversation and reasonably says "no, I didn't restart".

Measured 2026-10-08: Luke pressed /restart, the unit really did restart
(``NRestarts=1``, new MainPID, 5s gap), and when he then asked the agent "did you
restart?" it answered "No, I didn't restart. I still have our conversation
context…" — true of the SESSION, false about the GATEWAY, and the only thing the
human could see. Hence this book:

- the chat is MARKED when its /restart is handled;
- the FIRST reply sent to that chat afterwards carries a one-line footer naming the
  restart, and the agent receives the same fact with its prompt so it cannot
  contradict it;
- the marker is consumed exactly once, and expires, so a restart nobody came back to
  ask about does not resurface days later dressed as news.

Persisted, because the process that would have remembered it is the one that exits.
"""
from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path

# Long enough to survive an overnight restart, short enough that a marker nobody
# consumed stops being "new". A day-old restart is history, not an event.
TTL_S = 24 * 60 * 60


class RestartBook:
    """chat_id → {"ts": epoch, "pid": int}. Absent = no unseen restart."""

    def __init__(self, path, ttl_s: int = TTL_S):
        self.path = Path(path)
        self.ttl_s = ttl_s
        self._marks: dict = {}
        self.load()

    # ── persistence ──────────────────────────────────────────────────────
    def load(self) -> None:
        """Read the book. A damaged file degrades to 'no unseen restart'.

        Failing open is bounded: the worst case is a chat missing one footer line.
        Refusing to start would take the whole bot down over a notice.
        """
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        marks = raw.get("restarts") if isinstance(raw, dict) else None
        if not isinstance(marks, dict):
            return
        for chat, mark in marks.items():
            if isinstance(mark, dict) and isinstance(mark.get("ts"), (int, float)):
                self._marks[str(chat)] = {"ts": float(mark["ts"]),
                                          "pid": mark.get("pid"),
                                          "announced": bool(mark.get("announced"))}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"restarts": self._marks}, indent=1, sort_keys=True))
        try:
            # chat ids are personal data; keep the book owner-only.
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        tmp.replace(self.path)

    # ── the interface ────────────────────────────────────────────────────
    def mark(self, chat, pid: int | None = None, ts: float | None = None) -> None:
        """Record that `chat` pressed /restart (call this BEFORE the reply is sent)."""
        if chat is None:
            return
        self._marks[str(chat)] = {"ts": float(ts if ts is not None else time.time()),
                                  "pid": pid, "announced": False}
        self.save()

    def mark_announced(self, chat) -> None:
        """The gateway sent the "I am back" message itself; the chat needs no footer.

        The marker is NOT cleared: the agent still has to be told the gateway
        restarted, or it answers "no" on the next turn (see models of failure in the
        module docstring). Cleared when that turn's reply is sent.
        """
        if chat is None:
            return
        mark = self._marks.get(str(chat))
        if mark is None:
            return
        mark["announced"] = True
        self.save()

    def unannounced(self) -> list:
        """Fresh markers still needing a startup announcement: ``[(chat_key, mark)]``.

        Only the UNANNOUNCED ones, or every later startup would repeat the news. The
        marker itself survives the announcement (the agent still needs the fact).
        """
        out = []
        for chat in list(self._marks):
            mark = self.pending(chat)
            if mark and not mark.get("announced"):
                out.append((chat, mark))
        return out

    def pending(self, chat) -> dict | None:
        """The chat's unseen restart, or None — EXPIRING a stale marker on the way.

        Expiry happens here rather than in a sweep because this is the only reader:
        a marker nobody consumed must not be reported as news much later.
        """
        if chat is None:
            return None
        key = str(chat)
        mark = self._marks.get(key)
        if not mark:
            return None
        if time.time() - float(mark["ts"]) > self.ttl_s:
            self.clear(chat)
            return None
        return mark

    def clear(self, chat) -> None:
        if chat is None:
            return
        if self._marks.pop(str(chat), None) is not None:
            self.save()

    def count(self) -> int:
        return len(self._marks)
