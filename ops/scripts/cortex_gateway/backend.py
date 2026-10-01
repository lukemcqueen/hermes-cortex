"""cortex_gateway.backend — the BackendAdapter seam (CR2).

The seam an agent backend implements so the gateway dispatches an inbound
envelope and collects the reply. **hermes is the first adapter; pi and
steadfaste plug into the SAME seam** — the gateway's poll → dispatch → reply
loop never changes.

Contract (mirrors the TransportAdapter discipline, ADR-0005):

- ``dispatch(envelope) -> Optional[dict]`` — hand the inbound envelope to the
  agent and return the reply envelope, or ``None`` if the agent has nothing to
  say this turn (silent-when-clean is a legitimate outcome).
- Routing and channel formatting live in the gateway, NEVER in the backend.
  A backend only: receive an envelope, return an envelope.
- The reply envelope must round-trip through ``gateway_envelope.validate`` —
  the seam guarantees the contract at both boundaries.

Structural subclassing: any object with ``start/stop/dispatch/health`` is a
BackendAdapter (the ``__subclasshook__``), so a foreign backend passes the same
conformance door without inheriting from us. Abstractmethod enforcement still
forces OUR adapters to implement all four.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

_METHODS = ("start", "stop", "dispatch", "health")


class BackendAdapter(ABC):
    """Interface every agent backend implements (hermes / pi / steadfaste).

    Swapping the agent is a NEW BackendAdapter — the gateway, the routing
    table, and the transport never change (the interop invariant).
    """

    @classmethod
    def __subclasshook__(cls, subclass):
        """Structural conformance: any object with the four methods is a
        backend (a foreign backend passes the same door without inheriting)."""
        if cls is BackendAdapter:
            if all(callable(getattr(subclass, m, None)) for m in _METHODS):
                return True
        return NotImplemented

    @abstractmethod
    def start(self) -> None:
        """Connect the backend (spawn/attach the agent session)."""

    @abstractmethod
    def stop(self) -> None:
        """Tear the backend down (release the agent session)."""

    @abstractmethod
    def dispatch(self, envelope: dict) -> Optional[dict]:
        """Hand an inbound envelope to the agent; return its reply or None."""

    @abstractmethod
    def health(self) -> dict:
        """Backend liveness/readiness probe."""

    def poll_replies(self, max_n: int = 5) -> list:
        """Collect completed outbound reply envelopes (async backends only).

        Sync backends answer inside ``dispatch`` and leave this empty; async
        backends (hermes over the bus, a long-running pi/steadfaste turn)
        override it to drain their reply queue. Not abstract — an async-only
        method that sync backends inherit as a no-op.
        """
        return []
