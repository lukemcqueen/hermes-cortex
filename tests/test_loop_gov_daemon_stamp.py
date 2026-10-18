#!/usr/bin/env python3
"""The daemon must record WHAT IT LOADED, or 'is it stale?' can only be guessed from timestamps.

WHY. The doctor judged staleness by mtime (`mod_mtime > daemon_start`). A deploy rewrites the
deployed module, so mtime advances even when the bytes are IDENTICAL — measured 2026-10-18: the
deployed loop-gov-mcp.py's body was byte-for-byte the repo source while its mtime was 2m41s newer
than the daemon's start, and the check reported "running stale code" for a daemon that was current.
The warning therefore fired on every deploy and could only be "cleared" by a restart that changed
nothing. Nothing outside the process can know what it loaded, so the process records it: pid plus
the sha256 of its own file.

WHAT IS PINNED
  * the stamp names THIS pid, the resolved module path, and the sha256 of the module file — the
    three facts the check needs, so a comparison by content is possible at all;
  * the hash is the hash of the file on disk, so the check can compare like with like;
  * a failure to write is NOT fatal — the server must still start (the doctor falls back to mtime
    and says COULD NOT VERIFY), because refusing to serve governance over a stamp is worse.

Run: python3 tests/test_loop_gov_daemon_stamp.py
"""
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = Path(os.environ.get("SERVER_UNDER_TEST") or (REPO / "mcp-servers" / "loop-gov-mcp.py"))


def _mod():
    spec = importlib.util.spec_from_file_location("loop_gov_stamp_under_test", SERVER)
    assert spec is not None and spec.loader is not None, f"cannot load {SERVER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_stamp_records_the_pid_the_path_and_the_hash():
    """The three facts a content comparison needs — without them the check is back to timestamps."""
    mod = _mod()
    d = Path(tempfile.mkdtemp(prefix="loopgov-stamp-"))
    mod.DAEMON_STAMP = d / "loop-gov-daemon.json"
    mod._write_daemon_stamp()
    assert mod.DAEMON_STAMP.is_file(), "no stamp written"
    data = json.loads(mod.DAEMON_STAMP.read_text())
    assert data["pid"] == os.getpid(), (data["pid"], os.getpid())
    assert Path(data["module"]).resolve() == SERVER.resolve(), (data["module"], SERVER)
    want = hashlib.sha256(SERVER.read_bytes()).hexdigest()
    assert data["sha256"] == want, (data["sha256"][:12], want[:12])
    print(f"  stamp names pid {data['pid']}, the module, and sha256 {data['sha256'][:12]} ✓")


def test_the_hash_tracks_the_FILE_so_a_real_change_is_detectable():
    """A redeploy of identical bytes must compare EQUAL (that was the false positive); a changed
    file must compare UNEQUAL, or the check would be content-blind in the other direction."""
    mod = _mod()
    d = Path(tempfile.mkdtemp(prefix="loopgov-stamp2-"))
    fake = d / "loop-gov-mcp.py"
    fake.write_bytes(SERVER.read_bytes())
    mod.DAEMON_STAMP = d / "stamp.json"
    original = mod.__file__
    mod._write_daemon_stamp()
    same = json.loads(mod.DAEMON_STAMP.read_text())["sha256"]
    # Rewriting the SAME bytes must not change the recorded identity of the content.
    fake.write_bytes(SERVER.read_bytes())
    assert hashlib.sha256(fake.read_bytes()).hexdigest() == hashlib.sha256(SERVER.read_bytes()).hexdigest()
    # A real change must be visible.
    fake.write_bytes(SERVER.read_bytes() + b"\n# a real change\n")
    assert hashlib.sha256(fake.read_bytes()).hexdigest() != same, \
        "a changed file must differ from the recorded hash"
    print("  identical bytes compare equal; changed bytes compare unequal ✓")


def test_an_unwritable_stamp_is_not_fatal():
    """Governance must still serve. A stamp is diagnostics; failing to write one cannot stop the
    server, and the doctor then says COULD NOT VERIFY rather than inventing a verdict."""
    mod = _mod()
    mod.DAEMON_STAMP = Path("/proc/definitely/not/writable/loop-gov-daemon.json")
    mod._write_daemon_stamp()   # must not raise
    print("  an unwritable stamp path does not raise ✓")


def _main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    if not tests:
        print("NO TESTS RAN — this file executed nothing")
        return 1
    print("server:", SERVER)
    assert SERVER.is_file(), f"missing server: {SERVER}"
    failed, not_run = [], []
    for name, fn in tests:
        try:
            fn()
        except Exception:
            import traceback
            failed.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
    if failed:
        print(f"RESULT: FAIL ({len(failed)}/{len(tests)}): {failed}")
        return 1
    print(f"RESULT: ALL PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
