"""cortex_gateway.sessions — per-chat session generations (the `/new` command).

`/new` must START A NEW conversation **without destroying the old one** (Luke,
2026-10-03: "archive"). Two facts shape this design:

- **The gateway owns session identity.** It pins `--session-id hc-<agent>-<chat>`
  per chat (`agents.py:_session_id`), so a chat's session is deterministic and
  stable across restarts. That is exactly what makes a rotation expressible: bump a
  number and the derived id changes.
- **Archiving is the DEFAULT here, not extra work.** The agent writes each session
  to its own transcript file and nothing ever removes one. So `/new` only has to
  stop *using* the old id — the old transcript stays where it is. Nothing is
  truncated, renamed or deleted, which is what "archive" means.

Why the generation is PERSISTED and not in-memory: the unit is `Restart=always`, so
an in-memory counter resets on the next restart — the gateway would silently resume
the archived conversation and `/new` would look broken in a way that is very hard
to explain away from the logs.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path


class SessionBook:
    """chat_id → generation. Generation 0 is a chat's original session.

    Generations are monotonic per chat and never reused, so a session id derived
    from one can never collide with a later one.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._gen: dict = {}
        self.load()

    # ── persistence ──────────────────────────────────────────────────────
    def load(self) -> None:
        """Read the book. A damaged file degrades to 'all chats at generation 0'.

        Failing OPEN here is deliberate and bounded: the worst case is that a
        previously-rotated chat resumes its archived session. Refusing to start
        would take the whole bot down to protect one chat's context boundary.
        """
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        gens = raw.get("generations") if isinstance(raw, dict) else None
        if not isinstance(gens, dict):
            return
        for chat, gen in gens.items():
            # bool is an int subclass; True would otherwise read as generation 1.
            if isinstance(gen, int) and not isinstance(gen, bool) and gen >= 0:
                self._gen[str(chat)] = gen

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"generations": self._gen}, indent=1,
                                  sort_keys=True))
        try:
            # chat ids are personal data; keep the book owner-only.
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        tmp.replace(self.path)

    # ── the interface ────────────────────────────────────────────────────
    def generation(self, chat) -> int:
        """The chat's current generation (0 when it has never rotated)."""
        if chat is None:
            return 0
        return self._gen.get(str(chat), 0)

    def rotate(self, chat) -> int:
        """Start a new generation for `chat`; return it.

        The previous generation is left in the book and its transcript is left on
        disk — this is an archive, not a delete. Returns the NEW generation.
        """
        if chat is None:
            return 0
        key = str(chat)
        nxt = self._gen.get(key, 0) + 1
        self._gen[key] = nxt
        self.save()
        return nxt

    def count(self) -> int:
        """How many chats have rotated at least once (for diagnostics)."""
        return sum(1 for g in self._gen.values() if g > 0)
