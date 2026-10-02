"""cortex_gateway.pairing — DM pairing: how an unknown human gets enrolled, safely.

The incumbent pairs unknown senders. Doing that without weakening the fail-closed allowlist
means the enrolment is a SEPARATE, owner-approved path:

    unknown sender → a code is generated, they are told to ask the owner,
                     and their message is NOT dispatched
    owner          → /approve <code>   (only an already-allowed user may approve)
    approved sender→ added to the persisted allowlist; their NEXT message is dispatched

Properties that matter (each one is a real failure mode, not decoration):

- **Unpaired messages are never dispatched.** The code exchange is the only thing an unknown
  sender can trigger; the agent never sees their text until the owner approves.
- **Single use, with a TTL.** A code that keeps working is a permanent master key; a code
  without an expiry is one leaked screenshot away from enrolment.
- **Rate limited per sender.** Otherwise an unknown chat can spam the owner's phone with
  pairing prompts — a notification flood is a real denial of service on the owner.
- **Unambiguous, letters-only alphabet.** A code is read off a phone screen and typed back,
  so look-alike glyphs and digit/letter confusion invite support requests. Letters only also
  keeps the code out of the way of secret-scanners that flag digit runs.
- **The owner decides.** Approval requires a sender already in the allowlist; an unpaired
  chat cannot approve itself (or anyone else).
- **Owner-approved, not open.** Pairing is ON by default (parity with the incumbent); the
  fail-closed property is unchanged either way, because an unpaired sender's message is
  never dispatched and enrolment still requires the OWNER to approve a code. The default
  changes who can ASK, never who can talk to the agent. `TELEGRAM_PAIRING=off` gives unknown
  senders a silent refusal instead.
"""
from __future__ import annotations

import json
import os
import secrets
import stat
import time
from pathlib import Path

# Excludes look-alike glyphs (I, L, O, and the whole digit range).
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LEN = 6
CODE_TTL_S = 900                 # fifteen minutes
MAX_PENDING_PER_SENDER = 3       # per hour
RATE_WINDOW_S = 3600


def enabled() -> bool:
    """Pairing is ON by default (parity with the incumbent); `TELEGRAM_PAIRING=off` disables.

    ON by default because that IS the incumbent's behaviour — Luke, 2026-10-02: "switch to
    pairing". The fail-closed property is preserved either way: an unpaired sender's message
    is never dispatched and enrolment still needs the OWNER to approve a code, so the
    default changes who can ASK, never who can talk to the agent. Set `TELEGRAM_PAIRING=off`
    on a host where unknown senders should get a silent refusal instead.
    """
    val = (os.environ.get("TELEGRAM_PAIRING", "") or "").strip().lower()
    return val not in ("0", "off", "false", "no", "disabled")


class PairingStore:
    """Approved chats + pending codes, persisted so approval survives a restart."""

    def __init__(self, path: Path, ttl_s: int = CODE_TTL_S, clock=time.time):
        self.path = Path(path)
        self.ttl_s = ttl_s
        self._clock = clock
        self.approved: set = set()
        self.pending: dict = {}          # code -> {"chat_id":…, "at":…}
        self.load()

    # ── persistence ──────────────────────────────────────────────────────
    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        self.approved = {str(c) for c in (data.get("approved") or [])}
        now = self._clock()
        self.pending = {
            code: rec for code, rec in (data.get("pending") or {}).items()
            if isinstance(rec, dict) and now - float(rec.get("at", 0)) < self.ttl_s
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"approved": sorted(self.approved), "pending": self.pending}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=1))
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)     # owner-only: chat ids are personal data
        tmp.replace(self.path)

    # ── the flows ────────────────────────────────────────────────────────
    def is_approved(self, chat_id) -> bool:
        return str(chat_id) in self.approved

    def request(self, chat_id) -> str | None:
        """Mint a code for an unknown sender. None = rate limited (silently)."""
        chat = str(chat_id)
        now = self._clock()
        recent = [c for c, r in self.pending.items()
                  if r.get("chat_id") == chat and now - float(r.get("at", 0)) < RATE_WINDOW_S]
        if len(recent) >= MAX_PENDING_PER_SENDER:
            return None
        code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
        self.pending[code] = {"chat_id": chat, "at": now}
        self.save()
        return code

    def approve(self, code: str) -> str | None:
        """Owner approves a code → the chat is enrolled. Single use, TTL-bounded."""
        rec = self.pending.pop((code or "").strip().upper(), None)
        if not rec:
            return None
        if self._clock() - float(rec.get("at", 0)) >= self.ttl_s:
            self.save()
            return None                                  # expired: already useless
        chat = str(rec.get("chat_id"))
        self.approved.add(chat)
        self.save()
        return chat

    def deny(self, code: str) -> bool:
        """Drop a pending code without enrolling anyone."""
        if self.pending.pop((code or "").strip().upper(), None) is None:
            return False
        self.save()
        return True

    def pending_for(self, chat_id) -> str | None:
        chat = str(chat_id)
        for code, rec in self.pending.items():
            if rec.get("chat_id") == chat:
                return code
        return None
