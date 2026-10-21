#!/usr/bin/env python3
"""check-latest-briefing — gate: does the LAST DELIVERED sustainability briefing
satisfy the canonical contract?

The briefing cron generates its artifacts and delivers them; nothing used to
check what was DELIVERED, so a format drift (0 line-start `Source:` lines,
word count outside 600-1200) ran for a week unnoticed. This script is the
machine gate for that: it runs the CANONICAL checker
(`ops/scripts/sustainability/verify_briefing.py`, sibling of this file) instead
of re-implementing its rules, so the gate and the evidence pipeline cannot
drift apart.

Watchdog contract (one shot, no daemon):
  exit 0, empty stdout  → the newest delivered briefing PASSES, or this host
                          does not run an enabled briefing cron (not applicable)
  exit 1, report        → it FAILS the canonical checker, or is STALE
  exit 3, report        → COULD NOT VERIFY (cron enabled but no artifact for a
                          day it should have produced one, or the canonical
                          checker could not be loaded/run)

Usage:
    python3 check-latest-briefing.py                       # defaults
    python3 check-latest-briefing.py --date 2026-10-20     # re-check one day
    python3 check-latest-briefing.py --dir D --jobs J --checker C --today YYYY-MM-DD
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import re
import sys
from pathlib import Path

EXIT_PASS, EXIT_FAIL, EXIT_UNVERIFIABLE = 0, 1, 3
JOB_NAME_FRAGMENT = "sustainability-briefing"
ARTIFACT_RE = re.compile(r"^sustainability-briefing-(\d{4}-\d{2}-\d{2})\.md$")
DEFAULT_DIR = Path.home() / ".hermes" / "cron" / "output"
DEFAULT_JOBS = Path.home() / ".hermes" / "cron" / "jobs.json"
DEFAULT_MAX_AGE_DAYS = 2


def _report(lines: list[str]) -> None:
    print("\n".join(lines))


def _indent(text: str, pad: str = "   ") -> list[str]:
    return [pad + ln for ln in text.strip().splitlines() if ln.strip()]


def _parse_date(raw: str):
    """A date, or None when the value is not one (never a traceback)."""
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


def _artifact_dates(out_dir: Path) -> list[str]:
    """Delivered briefing dates present in the output dir, oldest first."""
    dates = []
    if not out_dir.is_dir():
        return dates
    for p in out_dir.iterdir():
        m = ARTIFACT_RE.match(p.name)
        if m:
            dates.append(m.group(1))
    return sorted(dates)


def _enabled_briefing_job(jobs_path: Path) -> str | None:
    """Name of an enabled job that produces the briefing, else None.

    Raises OSError/ValueError when the jobs file cannot be read or parsed —
    the caller reports that as COULD NOT VERIFY rather than guessing.
    """
    data = json.loads(jobs_path.read_text())
    jobs = data.get("jobs", data if isinstance(data, list) else [])
    for job in jobs:
        name = str(job.get("name", ""))
        if JOB_NAME_FRAGMENT in name and job.get("enabled", True):
            return name
    return None


def _load_checker(path: Path):
    spec = importlib.util.spec_from_file_location("canonical_verify_briefing", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load checker at {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # inert: entrypoint is behind __main__
    return mod


def _run_checker(checker: Path, date: str, out_dir: Path) -> tuple[int, str]:
    mod = _load_checker(checker)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mod.main(date, str(out_dir))
    return (int(rc) if isinstance(rc, int) else 2), buf.getvalue()


def _run_checker_guarded(checker: Path, date: str, out_dir: Path):
    """(rc, output) from the canonical checker, or (None, None) + a report.

    A checker that cannot run (unreadable module, corrupt delivered artifact
    tripping its parser) must be reported as COULD NOT VERIFY — never a
    traceback, and never silence.
    """
    try:
        return _run_checker(checker, date, out_dir)
    except Exception as exc:                      # noqa: BLE001 — reported below
        _report([f"⚠️ COULD NOT VERIFY briefing delivery for {date} — the "
                 f"canonical checker raised {type(exc).__name__}: {exc}"])
        return None, None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="gate the delivered briefing")
    ap.add_argument("--dir", default=str(DEFAULT_DIR),
                    help="delivered-artifact directory")
    ap.add_argument("--jobs", default=str(DEFAULT_JOBS),
                    help="hermes cron jobs.json (applicability)")
    ap.add_argument("--checker", default=str(Path(__file__).resolve().parent /
                                            "verify_briefing.py"),
                    help="canonical checker to run")
    ap.add_argument("--date", default=None,
                    help="check this delivered date explicitly (skips applicability)")
    ap.add_argument("--today", default=None, help="reference date (default: today)")
    ap.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    args = ap.parse_args(argv)

    out_dir = Path(os.path.expanduser(args.dir))
    jobs_path = Path(os.path.expanduser(args.jobs))
    checker = Path(os.path.expanduser(args.checker))
    today = _parse_date(args.today) if args.today else dt.date.today()
    if today is None:
        _report([f"⚠️ COULD NOT VERIFY briefing delivery — --today "
                 f"{args.today!r} is not a YYYY-MM-DD date"])
        return EXIT_UNVERIFIABLE

    if not checker.is_file():
        _report([f"⚠️ COULD NOT VERIFY briefing delivery — canonical checker "
                 f"missing at {checker}"])
        return EXIT_UNVERIFIABLE

    if args.date:
        target = args.date
        if target not in _artifact_dates(out_dir):
            _report([f"⚠️ COULD NOT VERIFY briefing delivery — no delivered "
                     f"artifacts for {target} in {out_dir}"])
            return EXIT_UNVERIFIABLE
    else:
        try:
            job_name = _enabled_briefing_job(jobs_path)
        except (OSError, ValueError) as exc:
            _report([f"⚠️ COULD NOT VERIFY briefing delivery — cannot read "
                     f"{jobs_path}: {type(exc).__name__}: {exc}"])
            return EXIT_UNVERIFIABLE
        if job_name is None:
            return EXIT_PASS                       # not applicable: silent
        dates = _artifact_dates(out_dir)
        if not dates:
            _report([f"⚠️ COULD NOT VERIFY briefing delivery — cron "
                     f"'{job_name}' is enabled but {out_dir} holds no delivered "
                     f"briefing artifacts"])
            return EXIT_UNVERIFIABLE
        target = dates[-1]
        newest = _parse_date(target)
        if newest is None:
            _report([f"⚠️ COULD NOT VERIFY briefing delivery — newest artifact "
                     f"name carries no parsable date: {target}"])
            return EXIT_UNVERIFIABLE
        age = (today - newest).days
        if age > args.max_age_days:
            _report([f"❌ Delivered briefing is STALE — newest artifact is "
                     f"{target} ({age} days old, today {today}); cron "
                     f"'{job_name}' is enabled"])
            return EXIT_FAIL

    rc, output = _run_checker_guarded(checker, target, out_dir)
    if rc is None:
        return EXIT_UNVERIFIABLE
    output = output or ""
    if rc == 0:
        return EXIT_PASS                            # silent on pass
    if rc == 1:
        _report([f"❌ Delivered briefing FAILED the canonical checker — "
                 f"sustainability-briefing-{target}.md",
                 f"   checker: {checker}",
                 *_indent(output)])
        return EXIT_FAIL
    _report([f"⚠️ COULD NOT VERIFY briefing delivery for {target} — the "
             f"canonical checker returned {rc}, which is neither pass nor fail",
             *_indent(output)])
    return EXIT_UNVERIFIABLE


if __name__ == "__main__":
    sys.exit(main())
