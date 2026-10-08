#!/usr/bin/env python3
"""Tests for cortex-update-mutex.py — the single-instance deploy lock.

THE GAP: cortex-update.sh has no mutex, so two concurrent updates to the SAME
repo can run at once, each unlocking the same immutable enforcement files and
racing on the deploy marker (observed: two `cortex-update.sh --force-all`
processes in parallel on moses). The lock must:

  * REFUSE a second concurrent update to the SAME repo (same lock file).
  * ALLOW simultaneous updates to DIFFERENT repos on the same server (different
    $CORTEX_DEPLOY_HOME -> different lock file).
  * self-release on process exit (even a crash), so no stale-lock deadlock.

Uses Python fcntl.flock (portable to macOS + Linux) — not the Linux-only
`flock` command, because the fleet runs on macOS (Titus).
"""
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MUTEX = REPO / "ops" / "scripts" / "lib" / "cortex-update-mutex.py"


def _child(tmp: Path) -> Path:
    """A tiny child script the guard runs — sleeps briefly and writes its pid so
    the parent can verify it ran under the held lock."""
    s = tmp / "child.sh"
    s.write_text("#!/usr/bin/env bash\nsleep 0.4\necho child-run\n")
    s.chmod(0o755)
    return s


def _run(lock_file: Path, child: Path,
         extra: list | None = None, *, expect_held: bool = False):
    """Run the guard as a subprocess; assert on the expected outcome and return
    the CompletedProcess so callers can inspect stdout/child output."""
    r = subprocess.run(
        [sys.executable, str(MUTEX), "--guard", str(lock_file), str(child),
         *(extra or [])],
        capture_output=True, text=True, timeout=60)
    if expect_held:
        assert r.returncode == 1, (
            f"expected held lock to refuse (rc={r.returncode}): {r.stdout}{r.stderr}")
    else:
        assert r.returncode == 0, (
            f"expected lock acquire + child run (rc={r.returncode}): "
            f"{r.stdout}{r.stderr}")
    return r


def _held(lock_file: Path) -> bool:
    """Open the lock file and try a non-blocking exclusive flock; return True if
    already held by another process."""
    import fcntl
    import os
    fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def test_acquires_and_refuses_a_second_concurrent_holder():
    """A long-held lock must make a second invocation refuse with exit 1, while
    the first holder keeps running — the same-repo concurrency guard."""
    base = Path(tempfile.mkdtemp(prefix="mutex-"))
    lock = base / "cortex-update.lock"
    child = _child(base)
    # Holder acquires via --hold for a controlled window.
    holder = subprocess.Popen(
        [sys.executable, str(MUTEX), "--hold", str(lock)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(0.5)
    try:
        assert _held(lock), "the holder did not acquire the lock"
        _run(lock, child, expect_held=True)   # second instance -> refuse (exit 1)
    finally:
        holder.terminate()
        holder.wait(timeout=10)


def test_guard_runs_the_child_under_the_lock():
    """--guard acquires the lock, runs the deploy child, releases on exit — the
    production shape (deploy under a held fd)."""
    base = Path(tempfile.mkdtemp(prefix="mutex-guard-"))
    lock = base / "cortex-update.lock"
    child = _child(base)
    r = _run(lock, child)
    assert "child-run" in r.stdout, (
        f"deploy child output did not stream through: {r.stdout!r}")
    assert not _held(lock), "guard did not release the lock after the child ran"


def test_releases_automatically_after_process_exit():
    """Self-cleaning: once the holder exits, the lock is acquirable again (no
    stale-lock deadlock). This is the property a PID-file lacks."""
    base = Path(tempfile.mkdtemp(prefix="mutex-rel-"))
    lock = base / "cortex-update.lock"
    child = _child(base)
    _run(lock, child)
    time.sleep(0.2)
    assert not _held(lock), "lock not released after the owner exited"


def test_different_lock_files_do_not_block_each_other():
    """Two DIFFERENT repos (different $CORTEX_DEPLOY_HOME -> different lock
    files) on one server must deploy independently — one must not block the
    other."""
    d1 = Path(tempfile.mkdtemp(prefix="mutex-d1-"))
    d2 = Path(tempfile.mkdtemp(prefix="mutex-d2-"))
    l1 = d1 / "cortex-update.lock"
    l2 = d2 / "cortex-update.lock"
    holder = subprocess.Popen(
        [sys.executable, str(MUTEX), "--hold", str(l1)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(0.5)
    try:
        _run(l2, _child(d2))   # different lock file -> must acquire, not refuse
    finally:
        holder.terminate()
        holder.wait(timeout=10)
    assert not _held(l2), "the short-lived acquirer left the lock held"


def test_missing_lock_dir_is_created():
    """The helper must create the state dir if absent (fresh / minimal install)."""
    base = Path(tempfile.mkdtemp(prefix="mutex-mkdir-"))
    child = _child(base)
    lock = base / "deep" / "nested" / "cortex-update.lock"
    _run(lock, child)
    assert lock.exists(), "lock file was not created under a new dir"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = []
    for fn in tests:
        try:
            fn()
        except AssertionError as e:
            failed.append((fn.__name__, str(e)))
        except Exception as e:  # noqa: BLE001
            failed.append((fn.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(f"FAIL ({len(failed)}/{len(tests)}):")
        for name, msg in failed:
            print(f"  - {name}: {msg}")
        raise SystemExit(1)
    print(f"PASS ({len(tests)}):")
    for fn in tests:
        print(f"  - {fn.__name__}")
    raise SystemExit(0)
