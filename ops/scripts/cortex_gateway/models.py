"""cortex_gateway.models — per-chat model overrides (the `/model` command).

The gateway owns everything the agent cannot own for itself: session identity
(`sessions.py`) and, here, **which model answers this chat**. A CLI agent is
spawned per turn, so "the model this chat uses" is not state the agent can hold
between turns — it has to live where the argv is built, and it has to survive the
`Restart=always` unit, or a model switch would silently evaporate on the next
deploy/restart (the same failure `/new` avoids by persisting its generation).

Scope is deliberately ONE chat, matching the incumbent's session-scoped
`/model <name>`: two chats can run different models at once, and a chat that has
never switched carries no entry at all (so nothing changes for it).
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path


class ModelBook:
    """chat_id → model string. Absent = the backend's configured default."""

    def __init__(self, path):
        self.path = Path(path)
        self._model: dict = {}
        self.load()

    # ── persistence ──────────────────────────────────────────────────────
    def load(self) -> None:
        """Read the book. A damaged file degrades to 'everyone on the default'.

        Failing open is bounded and deliberate: the worst case is that a chat
        that had switched returns to the configured default model. Refusing to
        start would take the whole bot down over one chat's preference.
        """
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        models = raw.get("models") if isinstance(raw, dict) else None
        if not isinstance(models, dict):
            return
        for chat, model in models.items():
            if isinstance(model, str) and model.strip():
                self._model[str(chat)] = model.strip()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"models": self._model}, indent=1, sort_keys=True))
        try:
            # chat ids are personal data; keep the book owner-only.
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        tmp.replace(self.path)

    # ── the interface ────────────────────────────────────────────────────
    def get(self, chat) -> str:
        """The chat's model override, or "" when it is on the default."""
        if chat is None:
            return ""
        return self._model.get(str(chat), "")

    def set(self, chat, model: str) -> str:
        """Pin `chat` to `model`; returns the stored value."""
        if chat is None:
            return ""
        value = str(model or "").strip()
        key = str(chat)
        if value:
            self._model[key] = value
        else:
            self._model.pop(key, None)
        self.save()
        return value

    def clear(self, chat) -> bool:
        """Return the chat to the default. True = there was something to clear."""
        if chat is None:
            return False
        key = str(chat)
        if key not in self._model:
            return False
        self._model.pop(key, None)
        self.save()
        return True

    def count(self) -> int:
        """How many chats have switched away from the default (diagnostics)."""
        return len(self._model)
