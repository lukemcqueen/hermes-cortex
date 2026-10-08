#!/usr/bin/env python3
"""Single-instance lock for cortex-update.sh.

Prevents two concurrent deploys of the SAME repo: both would unlock the same
immutable enforcement files, race on the deploy marker, and interleave copies,
leaving a half-deployed state or an unlocked gate (observed: two
`cortex-update.sh --force-all` processes in parallel on moses).

This is a WRAPPER, not a boilerplate you paste into the deploy script: the lock
must be held for the WHOLE deploy, and a short-lived subprocess acquires-and-
releases within a millisecond. So ``--guard`` is the real mode: the helper
acquires a non-blocking exclusive ``fcntl.flock`` on the lock file, then runs
the deploy script as its OWN CHILD with ``CORTEX_UPDATE_INNER=1`` set, holding
the fd (and thus the flock) until the child exits. The helper's exit code is
the child's. Acquire failure => exit 1 and the deploy script refuses.

Properties (what the fleet needs):

  * per-deploy-home scoping: the lock file is named from
    ``$CORTEX_DEPLOY_HOME/state/cortex-update.lock``, so two sessions on the
    SAME repo share one lock (the second refuses, exit 1) while DIFFERENT repos
    on one server use different lock files and deploy independently — free
    isolation, no extra logic.
  * ``fcntl.flock`` is POSIX and portable to macOS (Titus) — NOT the
    Linux-only ``flock`` command.
  * self-releasing: the fd closes when the helper exits (child done or crashed)
    and the flock drops automatically — no stale-lock deadlock, unlike a bare
    PID file.

Exit codes: 0 = guard ran the deploy to completion (child rc 0); 1 = lock
already held by another deploy (refuse); 2 = usage error.

Invoked from cortex-update.sh ``main()`` (once, after CORTEX_DEPLOY_HOME and the
venv python are resolved), guarded so the inner run skips the wrapper:

    if [[ -z "${CORTEX_UPDATE_INNER:-}" ]]; then
      "${CORTEX_DEPLOY_HOME}/venv/bin/python3" \
        "${CORTEX_DEPLOY_HOME}/scripts/lib/cortex-update-mutex.py" \
        --guard "${CORTEX_DEPLOY_HOME}/state/cortex-update.lock" \
        "$0" "$@" || { echo 'refusing concurrent cortex-update (mutex held)'; exit 1; }
      exit $?   # inner run's exit code
    fi

For tests, ``--hold`` acquires and holds the lock for a few seconds so a peer
process can probe it.
"""
import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path


def _usage() -> int:
    print("usage: cortex-update-mutex.py --guard <lock-file> <script> [args...] "
          "| --hold <lock-file>", file=sys.stderr)
    return 2


def _acquire(lock_path: Path):
    """Open + non-blocking flock the lock file. Returns the open fd on success,
    or None if already held."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def main() -> int:
    args = sys.argv[1:]
    if not args:
        return _usage()
    mode = args[0]
    if mode == "--hold":
        if len(args) < 2:
            return _usage()
        return _hold(Path(args[1]))
    if mode == "--guard":
        if len(args) < 3:
            return _usage()
        lock_path = Path(args[1])
        script = args[2]
        script_args = args[3:]
    else:
        return _usage()

    fd = _acquire(lock_path)
    if fd is None:
        print(f"cortex-update mutex held: another deploy is running "
              f"({lock_path})", file=sys.stderr)
        return 1

    try:
        env = dict(os.environ)
        env["CORTEX_UPDATE_INNER"] = "1"
        # Run the deploy as our child under the held fd. Inherit stdio so the
        # deploy's output streams through; propagate its exit code.
        r = subprocess.run([script, *script_args], env=env)
        return r.returncode
    except FileNotFoundError:
        print(f"cortex-update-mutex: deploy script not found: {script}",
              file=sys.stderr)
        return 2
    finally:
        os.close(fd)  # releases the flock


def _hold(lock_path: Path) -> int:
    fd = _acquire(lock_path)
    if fd is None:
        print(f"cortex-update mutex held ({lock_path})", file=sys.stderr)
        return 1
    try:
        time.sleep(30)  # keep the lock so a peer can probe it
        return 0
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
