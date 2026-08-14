#!/usr/bin/env python3
"""test-bus-forwarder-dedup.py — Regression test for the mirror re-forward loop.

Reproduces the 2026-08-12 duplicate-delivery bug and proves the fix:

  BUG: _sync_direction skipped a message whose dedup key already existed on the
  destination WITHOUT recording it in `seen`. When the real consumer (worker
  handler) archived the destination copy, the next tick re-forwarded the
  lingering backup copy back to the primary — fresh msg_id, same corr. The loop
  repeated every consumer tick: gisu received 3 identical EXECs (corr
  send-ba7f68e22d6a), joseph 3×, UPDATE_REQUESTs 2–3× fleet-wide, and a task
  row stayed pending ~10h.

  FIX: record the dkey in `seen` on the dest-hit skip. Each logical message
  forwards at most once per direction per host — a consumed copy is DELIVERED,
  not a gap to re-warm.

This test drives _sync_direction with a mock bus adapter (no live peer
needed) and asserts:
  1. First tick: message on source, dest already has it → skipped, dkey in seen.
  2. Second tick: dest copy archived by the consumer, source copy lingers
     (the warm-standby mirror) → must NOT re-forward (dkey in seen).

Run: cd hermes-cortex && python3 tests/test-bus-forwarder-dedup.py
"""

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FWD_PATH = REPO / "ops" / "scripts" / "orch-bus" / "orch-bus-forwarder.py"

# Filename has hyphens → not importable by name; load via importlib.
_spec = importlib.util.spec_from_file_location("orch_bus_forwarder", FWD_PATH)
fwd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fwd)  # type: ignore[union-attr]

# QUEUES is populated in main() at runtime; the tests exercise _sync_direction
# directly, so scope it to the queue the mocks use.
fwd.QUEUES = ["inbox_gisu"]

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")


class MockBus:
    """In-memory bus: pending + archived message sets per queue."""

    def __init__(self):
        self.pending: dict[str, list[dict]] = {}
        self.archived: dict[str, list[dict]] = {}
        self._seq = 0

    def enqueue(self, queue: str, body: dict) -> str:
        self._seq += 1
        msg = {"msg_id": f"mock-{self._seq:04d}", "body": body}
        self.pending.setdefault(queue, []).append(msg)
        return msg["msg_id"]

    def consume(self, queue: str) -> None:
        """The real consumer (worker handler) archives the destination copy."""
        msgs = self.pending.get(queue, [])
        if msgs:
            m = msgs.pop(0)
            self.archived.setdefault(queue, []).append(m)


def build_body(corr: str, subject: str = "EXEC") -> dict:
    return {
        "from": "esther", "to": "gisu", "topic": "command",
        "subject": subject, "correlation_id": corr,
        "body": json.dumps({"command": "cortex-doctor.py", "params": ["--quiet"], "timeout": 120}),
    }


class ForwarderHarness:
    """Monkeypatches fwd's transport with a two-bus mock, preserving state
    across ticks exactly like the real forwarder's state file."""

    def __init__(self):
        self.source = MockBus()
        self.dest = MockBus()
        self.dest_unreachable = False  # tri-state None for _dest_has (peer outage sim)
        self.state: dict = {"seen_local_to_peer": [], "total_local_to_peer": 0}
        self._orig = (fwd._peek_bus, fwd._send_bus, fwd._archive_bus, fwd._dest_has_key)

    def _peek(self, url, token, auth, queue, limit=50):
        return list(self.source.pending.get(queue, []))

    def _send(self, url, token, auth, queue, body):
        self.dest.enqueue(queue, body)
        return True, "ok"

    def _archive(self, url, token, auth, queue, msg_id):
        src = self.source.pending.get(queue, [])
        for i, m in enumerate(src):
            if m.get("msg_id") == msg_id:
                src.pop(i)
                self.source.archived.setdefault(queue, []).append(m)
                return True
        return False

    def _dest_has(self, url, token, auth, queue, dkey):
        # Mirror the real _dest_has_key: compare the FULL dedup key
        # (_dedup_key prefixes with "corr:"), not the raw correlation_id.
        # Tri-state: True (pending), False (reachable, absent), or None when
        # the harness simulates an unreachable destination (peer outage).
        if getattr(self, "dest_unreachable", False):
            return None
        for m in self.dest.pending.get(queue, []):
            b = fwd._parse_body(m.get("body", {}))
            if fwd._dedup_key(m, b) == dkey:
                return True
        return False

    def tick(self, direction: str = "local_to_peer", can_archive: bool = False):
        fwd._peek_bus = self._peek
        fwd._send_bus = self._send
        fwd._archive_bus = self._archive
        fwd._dest_has_key = self._dest_has
        try:
            return fwd._sync_direction(
                self.state, "src", "t", "", "dst", "t", "",
                direction, can_archive_source=can_archive)
        finally:
            fwd._peek_bus, fwd._send_bus, fwd._archive_bus, fwd._dest_has_key = self._orig

    def seen(self) -> list:
        return self.state.get("seen_local_to_peer", [])


def test_mirror_loop_breaks():
    """THE regression: consumed dest copy must not be re-forwarded."""
    print("\n═══ Test 1: Mirror re-forward loop (2026-08-12 bug) ═══")
    corr = "send-ba7f68e22d6a"
    h = ForwarderHarness()
    # Tick 1: backup (source) holds the mirrored copy; primary (dest) already
    # has the original pending. Forwarder must skip AND record in seen.
    h.source.enqueue("inbox_gisu", build_body(corr))
    h.dest.enqueue("inbox_gisu", build_body(corr))
    fwd_list, errs = h.tick()
    check("tick1: no re-forward when dest has it pending", len(fwd_list) == 0, f"{fwd_list}")
    check("tick1: dkey recorded in seen (THE FIX)", f"corr:{corr}" in h.seen(), f"seen={h.seen()}")
    check("tick1: source mirror copy retained (warm standby)",
          len(h.source.pending["inbox_gisu"]) == 1)

    # Consumer processes + archives the dest (primary) copy.
    h.dest.consume("inbox_gisu")
    check("consumer archived primary copy", len(h.dest.pending.get("inbox_gisu", [])) == 0)

    # Tick 2: source copy still lingers (nothing consumes the backup mirror);
    # dest no longer has it. OLD behavior re-forwarded → duplicate.
    fwd_list, errs = h.tick()
    check("tick2: NO duplicate re-forward (bug fixed)", len(fwd_list) == 0, f"fwd={fwd_list}")
    check("tick2: dest still empty", len(h.dest.pending.get("inbox_gisu", [])) == 0)


def test_forward_still_works():
    """Control: a genuinely new message (not on dest) still forwards once."""
    print("\n═══ Test 2: Normal forward still works (control) ═══")
    h = ForwarderHarness()
    h.source.enqueue("inbox_gisu", build_body("send-fresh-uuid-1"))
    fwd_list, errs = h.tick()
    check("new message forwarded", len(fwd_list) == 1, f"{fwd_list}")
    check("dkey added to seen after forward", "corr:send-fresh-uuid-1" in h.seen())
    check("dest has the copy", len(h.dest.pending.get("inbox_gisu", [])) == 1)

    # Second tick: source copy still there, dest has it → skip, no duplicate.
    fwd_list, _ = h.tick()
    check("second tick skips (already seen)", len(fwd_list) == 0)


def test_backup_drain_still_works():
    """Control: failover drain (backup→primary after recovery) still archives
    the source copy and forwards to the recovering primary."""
    print("\n═══ Test 3: Failover drain still works (control) ═══")
    h = ForwarderHarness()  # source = backup that accumulated messages
    h.source.enqueue("inbox_gisu", build_body("send-failover-1"))
    fwd_list, errs = h.tick(can_archive=True)
    check("stranded message forwarded to recovering primary", len(fwd_list) == 1, f"{fwd_list}")
    check("dest received it", len(h.dest.pending.get("inbox_gisu", [])) == 1)
    check("backup source copy archived after drain (can_archive_source)",
          len(h.source.pending.get("inbox_gisu", [])) == 0)


def test_stale_mirror_sweep():
    """2026-08-14: mirrored-back copies on the backup bus of messages the
    primary has CONSUMED are archived — the backup mirror no longer grows
    forever (inbox_orchestrator hit 199 pending, 3rd fleet sighting)."""
    print("\n═══ Test 4: Stale-mirror sweep (2026-08-14 fix) ═══")
    corr = "send-stale-mirror-1"
    h = ForwarderHarness()  # source = backup (Esther), dest = primary (Moses)
    # Tick 1: mirror copy on backup; original pending on primary.
    h.source.enqueue("inbox_gisu", build_body(corr))
    h.dest.enqueue("inbox_gisu", build_body(corr))
    fwd_list, _ = h.tick(can_archive=True)
    check("tick1: dest-hit, no forward", len(fwd_list) == 0, f"{fwd_list}")
    check("tick1: copy retained while original pending (failover snapshot)",
          len(h.source.pending["inbox_gisu"]) == 1)
    # Primary handler consumes the original.
    h.dest.consume("inbox_gisu")
    # Tick 2: OLD code skipped forever (stranded mirror). NEW code archives it.
    fwd_list, _ = h.tick(can_archive=True)
    check("tick2: NO duplicate re-forward of stale mirror", len(fwd_list) == 0, f"{fwd_list}")
    check("tick2: stale mirror ARCHIVED (THE FIX)",
          len(h.source.pending.get("inbox_gisu", [])) == 0,
          f"still pending: {h.source.pending.get('inbox_gisu')}")
    check("tick2: dest stays empty (no duplicate)",
          len(h.dest.pending.get("inbox_gisu", [])) == 0)


def test_stale_mirror_kept_while_primary_pending():
    """Failover safety: the backup copy stays while the original is still
    pending on the primary (it may be needed if the primary dies)."""
    print("\n═══ Test 5: Copy kept while original still pending ═══")
    corr = "send-stale-mirror-2"
    h = ForwarderHarness()
    h.source.enqueue("inbox_gisu", build_body(corr))
    h.dest.enqueue("inbox_gisu", build_body(corr))
    h.tick(can_archive=True)          # dest-hit → seen
    # Original STILL pending on primary → copy must be kept.
    fwd_list, _ = h.tick(can_archive=True)
    check("copy retained (original still pending on primary)",
          len(h.source.pending.get("inbox_gisu", [])) == 1)


def test_stale_mirror_kept_when_peer_unreachable():
    """Failover safety: never archive blind during a peer outage — the local
    copy may be the only snapshot of an unconsumed message."""
    print("\n═══ Test 6: Copy kept when peer unreachable ═══")
    corr = "send-stale-mirror-3"
    h = ForwarderHarness()
    h.source.enqueue("inbox_gisu", build_body(corr))
    h.dest.enqueue("inbox_gisu", build_body(corr))
    h.tick(can_archive=True)          # dest-hit → seen
    h.dest.consume("inbox_gisu")      # primary consumed it…
    h.dest_unreachable = True         # …but now the peer cannot be reached
    fwd_list, _ = h.tick(can_archive=True)
    check("copy retained when peer unreachable (never archive blind)",
          len(h.source.pending.get("inbox_gisu", [])) == 1,
          f"pending={h.source.pending.get('inbox_gisu')}")


if __name__ == "__main__":
    print("test-bus-forwarder-dedup.py — mirror re-forward loop regression")
    test_mirror_loop_breaks()
    test_forward_still_works()
    test_backup_drain_still_works()
    test_stale_mirror_sweep()
    test_stale_mirror_kept_while_primary_pending()
    test_stale_mirror_kept_when_peer_unreachable()
    print(f"\n═══ Summary: {PASS} passed, {FAIL} failed ═══")
    sys.exit(1 if FAIL else 0)
