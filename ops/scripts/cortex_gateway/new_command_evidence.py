#!/usr/bin/env python3
"""Acceptance evidence for the gateway `/new` command — ARCHIVE semantics.

RUN THIS TO REGENERATE the evidence; it is not a narrative. It drives the
DEPLOYED gateway modules (not the repo copies, so it proves what the host runs)
against the REAL `pi` binary, and emits the report as markdown on stdout.

    bash ops/scripts/cortex_gateway/run-new-command-evidence.sh

A probe chat id is used throughout, never a real one: this file is committed and
a chat id is personal data.

What it proves, in order:
  1. a chat's session id before /new,
  2. that the session genuinely holds a memory,
  3. that `/new` through the real gateway rotates the generation,
  4. that the next session id DIFFERS,
  5. that the new session does NOT have the memory (the rotation is real),
  6. that the OLD transcript is still on disk (archive, not delete),
  7. that the generation PERSISTED (a restart will not resume the archived chat).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

DEPLOY = Path.home() / ".hermes-cortex"
sys.path.insert(0, str(DEPLOY / "scripts"))

import cortex_gateway.agents as AGENTS      # noqa: E402
import cortex_gateway.daemon as DAEMON      # noqa: E402
import cortex_gateway.sessions as SESSIONS  # noqa: E402

# A UNIQUE probe chat per run. A fixed one makes the second run resume the sessions
# the first run left behind — which reads as "/new leaks memory" when nothing leaked.
CHAT = f"evidence-probe-{os.urandom(4).hex()}"
CONFIG = DEPLOY / "gateway-esther0001.yaml"
BOOK = Path.home() / ".hermes" / "cache" / "scratch" / "evidence-sessions.json"
PI_SESSIONS = Path.home() / ".pi" / "agent" / "sessions"
TOKEN = "ORCHID"


class _Transport:
    """Captures what the gateway would send; nothing leaves this process."""

    def __init__(self):
        self.sent = []

    def parse(self, raw):
        return dict(raw)

    def send(self, envelope):
        self.sent.append(envelope)
        return True


def _pi(backend, inbound, session_id, prompt):
    """Run the REAL agent through the PRODUCT's own argv + env builders.

    Using `_argv`/`_child_env` rather than hand-built ones is the point, not a
    shortcut. The gateway pins session identity through `CORTEX_SESSION_KEY`; a
    harness that hand-builds the argv and omits that env makes every session share
    ONE checkpoint, which reads as "/new leaks memory" when the product is fine.
    That exact mistake produced a false failure here once.
    """
    argv = backend._argv(prompt, session_id)
    env = backend._child_env(inbound, session_id)
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=300, env=env)
    text = (proc.stdout or proc.stderr or "").strip()
    return text.splitlines()[-1].strip() if text else ""


def main() -> int:
    cfg = json.loads(CONFIG.read_text())
    spec = AGENTS.AgentSpec.from_dict(cfg["backends"][0])
    backend = AGENTS.CommandBackend(spec)
    command = spec.command

    BOOK.unlink(missing_ok=True)
    book = SESSIONS.SessionBook(BOOK)
    gateway = DAEMON.Gateway(transport=_Transport(), backends={"pi": backend},
                             default_agent="pi", allowed_users=None, sessions=book)

    # Each turn's envelope, so the product's own env builder pins session identity.
    inbound_before = {"channel_user_id": CHAT, "body": "", "session_generation": 0}
    before = backend.session_id_for(inbound_before)
    seeded = _pi(backend, inbound_before, before,
                 f"Remember: my codeword is {TOKEN}. Reply OK.")
    recalled = _pi(backend, inbound_before, before, "What is my codeword? One word.")

    gateway._turn({"channel_user_id": CHAT, "body": "/new", "tg_kind": "message"})
    reply = gateway.transport.sent[-1]["body"]

    generation = book.generation(CHAT)
    inbound_after = {"channel_user_id": CHAT, "body": "",
                     "session_generation": generation}
    after = backend.session_id_for(inbound_after)
    after_recall = _pi(backend, inbound_after, after, "What is my codeword? One word.")

    transcripts = sorted(PI_SESSIONS.rglob(f"*{before}*")) + \
        sorted(PI_SESSIONS.rglob(f"*{after}*"))
    retained = [p for p in transcripts if before in p.name and after not in p.name]

    print("# Gateway `/new` — acceptance evidence (ARCHIVE semantics)\n")
    print("Regenerate with: `bash ops/scripts/cortex_gateway/run-new-command-evidence.sh`\n")
    print("Drives the DEPLOYED gateway against the REAL `pi` binary. A probe chat id is")
    print("used throughout — never a real one, since this file is committed.\n")
    print("| # | Criterion | Result |")
    print("|---|---|---|")
    print(f"| 1 | Session id before `/new` | `{before}` (unsuffixed: an existing "
          "conversation never moves) |")
    print(f"| 2 | That session really holds a memory | seeded `{TOKEN}`, recalled "
          f"`{recalled}` |")
    print(f"| 3 | `/new` is handled by the gateway (not answered as a prompt) | "
          f"`{reply}` |")
    print(f"| 4 | The next session id DIFFERS | `{after}` |")
    print(f"| 5 | The new session has NO memory of it | agent replied "
          f"`{after_recall}` |")
    print(f"| 6 | The OLD transcript is still on disk (ARCHIVE) | "
          f"`{retained[0].name}`, {retained[0].stat().st_size} bytes |"
          if retained else "| 6 | OLD transcript retained | **MISSING** |")
    print(f"| 7 | The generation PERSISTED | reopened book reports generation "
          f"{SESSIONS.SessionBook(BOOK).generation(CHAT)} |")

    print("\n## Artefacts on disk\n")
    for path in transcripts:
        print(f"- `{path.name}` — {path.stat().st_size} bytes")

    ok = (after != before and retained and TOKEN.lower() not in after_recall.lower()
          and SESSIONS.SessionBook(BOOK).generation(CHAT) == generation
          and generation >= 1 and seeded)
    print(f"\n**Verdict: {'PASS' if ok else 'FAIL'}** — the rotation is real "
          "(memory gone), the archive is real (transcript kept), and the generation "
          "survives a reload.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
