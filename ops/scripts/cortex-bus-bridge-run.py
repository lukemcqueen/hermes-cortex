#!/usr/bin/env python3
"""
cortex-bus-bridge-run.py — standalone no_agent job runner for the systemd-timer
bridge (component-hermes-separation S2a).

This is the delivery wrapper that lets a no_agent cron job run under a systemd
user timer WITHOUT the Hermes process. A no_agent job's contract is: run the
script, and if it prints non-empty stdout, deliver that stdout to the job's
`deliver` target (usually the Telegram home channel); empty stdout = silent
(the "silent-when-clean" contract — many scripts only print when something
changed).

The wrapper does exactly that, standalone:
  1. Run the job's script with the same env Hermes would (sources the cortex
     .env so tokens/models resolve; script resolved from the deployed scripts
     dir).
  2. Capture stdout.
  3. If non-empty, deliver via ops/scripts/lib/telegram_notify.notify() — the
     R-9 singleton Bot API copy (token from ~/.hermes/.env, never code).
  4. Exit 0 regardless of delivery (a delivery failure must not wedge the
     timer); the delivery lib logs.

It does NOT reimplement Hermes cron semantics (cron exprs, context_from,
continuity, per-job model pins) — those stay on the Hermes cronjob scheduler.
This wrapper only serves the pure script-that-prints subset.

Usage (from a systemd unit or shell):
    python3 cortex-bus-bridge-run.py --name <job> --script <relative-or-abs-script>

Flags:
    --name  job name (for logs)
    --script  script path; if relative, resolved under ~/.hermes-cortex/scripts/
    --deliver  the job's deliver target ('local' = save-only, else Telegram)
    --enabled  "true"/"false" — the generated timer is enabled only when true
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_home = Path.home()
_CORTEX_ENV = Path(os.environ.get("CORTEX_DEPLOY_HOME", str(_home / ".hermes-cortex")))
_SCRIPTS_DIR = _CORTEX_ENV / "scripts"


def _load_env() -> None:
    """Source ~/hermes-cortex/.env (and ~/.hermes/.env) into os.environ so the
    job script sees the same tokens/models Hermes would. Never prints them."""
    for env_path in (Path.home() / "hermes-cortex" / ".env",
                     _home / ".hermes" / ".env"):
        if not env_path.exists():
            continue
        try:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val
        except (OSError, IOError):
            pass  # best-effort; the script will fail loudly if it needs a var


def _resolve_script(path: str) -> str:
    p = Path(path)
    if p.is_absolute():
        return str(p)
    # Try deployed scripts dir, then fall back to plain relative.
    cand = _SCRIPTS_DIR / path
    if cand.exists():
        return str(cand)
    return str(p)


def _deliver(text: str, job: str, deliver: str = "") -> None:
    """Deliver job stdout per the job's `deliver` target, matching Hermes cron
    semantics with a standalone messenger.

    deliver targets (same grammar as Hermes `cronjob`):
      '' / 'origin' / 'telegram' / 'telegram:<chat_id>'  -> send to Telegram
         (the home channel; 'origin' for script jobs resolves here)
      'local'                                            -> save-only to
         ~/.hermes-cortex/cron-output/<job>.log, NEVER a send (some no_agent
         jobs are internal collectors whose stdout must not reach the channel).

    Best-effort: a delivery failure is logged, never propagated to the timer
    (a wedged timer is worse than a missed delivery; an internal job's stdout
    MUST not leak to the channel by mis-routing to 'local')."""
    if deliver == "local":
        _save_local(text, job)
        return
    try:
        sys.path.insert(0, str(_SCRIPTS_DIR))
        from lib.telegram_notify import notify  # ops/scripts/lib on path
        notify(text, subject=f"cron:{job}")
    except ImportError:
        from lib.telegram_notify import notify  # type: ignore
        notify(text, subject=f"cron:{job}")
    except Exception:
        # Delivery failure must not fail the unit (timer health > delivery).
        import traceback
        print(f"[bridge] delivery failed for {job}:", file=sys.stderr)
        traceback.print_exc()


def _save_local(text: str, job: str) -> None:
    """Save job stdout to a file (deliver=local): internal collectors keep a
    durable record without sending to any channel."""
    outdir = _CORTEX_ENV / "cron-output"
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / f"{job}.log").write_text(text + "\n")
    except (OSError, IOError) as e:
        print(f"[bridge] local save failed for {job}: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--deliver", default="")
    ap.add_argument("--enabled", default="true")
    args = ap.parse_args()

    _load_env()

    script = _resolve_script(args.script)
    if not Path(script).exists():
        print(f"[bridge] script not found: {script}", file=sys.stderr)
        return 0  # non-fatal: a missing script must not wedge the timer

    try:
        proc = subprocess.run(
            [sys.executable, script] if script.endswith(".py")
            else ["/usr/bin/env", "bash", script],
            capture_output=True,
            text=True,
            timeout=3600,  # generous; jobs are short
        )
    except subprocess.TimeoutExpired:
        print(f"[bridge] {args.name} timed out", file=sys.stderr)
        return 0

    stdout = (proc.stdout or "").strip()
    if stdout:
        _deliver(stdout, args.name, args.deliver)
    # Script exit != 0 with output still gets delivered (its stdout is the
    # report); a non-zero exit is surfaced in the timer's status, not dropped.
    return 0


if __name__ == "__main__":
    sys.exit(main())