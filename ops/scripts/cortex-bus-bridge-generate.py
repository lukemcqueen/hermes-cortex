#!/usr/bin/env python3
r"""
cortex-bus-bridge-generate.py — generate systemd user timer units for simple
no_agent cron jobs (component-hermes-separation S2a).

Reads ~/.hermes/cron/jobs.json, and for each SIMPLE no_agent job (a pure
script job with no context_from/continuity chaining and no model pin — i.e. a
job that needs only a scheduler + a messenger, not the Hermes agent loop),
writes a user-scope systemd pair:

    ~/.config/systemd/user/<name>.service
                      ExecStart=.../cortex-bus-bridge-run.py --name <name> --script <script>
    ~/.config/systemd/user/<name>.timer
                      OnCalendar=<converted-from-cron-expr>

The service unit's stdout/stderr are captured by the bridge-run wrapper and
delivered (non-empty) to the messenger; empty = silent. This removes the
load-bearing coupling "gateway process down → 61 no_agent jobs don't run",
proving S2a on one job at a time.

KillMode=process (2026-10-24)
-----------------------------
Every generated service unit sets `KillMode=process`. A bridge unit is
`Type=oneshot`, whose default `KillMode=control-group` makes systemd tear down
the whole unit cgroup when the tick's ExecStart exits — SIGTERMing any child the
job deliberately detached (e.g. the UPDATE_REQUEST worker spawned with
`start_new_session=True` in agent-message-handler.py). With `control-group`,
that worker died seconds after being spawned and the fleet's UPDATE_REQUEST
protocol could not update ANY host. `KillMode=process` kills only the tick
itself and lets detached children finish. See
skills/devops/detached-worker-pattern and docs/runbooks/cron-bridge-migration.md.

--repair exists because the template alone cannot fix a migrated host: after
migration the Hermes jobs.json entry is REMOVED, so the generator never emits
that unit again and the on-disk file can only be corrected in place.

LIMITS (deliberate):
- ONLY simple no_agent script jobs. LLM jobs, chained jobs (context_from/
  continuity), and job with model pins stay on the Hermes cronjob scheduler.
- This GENERATES the units (+ writes them to ~/.config/systemd/user/); it does
  NOT auto-enable. The caller runs `systemctl --user daemon-reload` then
  `systemctl --user enable --now <name>.timer` per job, in the planned sequence.
- Unit name prefix:  cortex-bridge-  (so `systemctl --user list-timers` groups
  the bridge together and they're unmistakably ours).

Usage:
    python3 cortex-bus-bridge-generate.py                # write all simple units
    python3 cortex-bus-bridge-generate.py --dry-run      # print, don't write
    python3 cortex-bus-bridge-generate.py --only <name>  # one job
    python3 cortex-bus-bridge-generate.py --repair       # add KillMode=process
                                                         # to already-deployed
                                                         # bridge units

Cron→OnCalendar translation: cron has 5 fields (min hour dom mon dow); systemd
OnCalendar uses the same meaning but each field is optional-separated. We map
the common subset: */N → *\/N, explicit numbers stay, and interval-style
(every 5m / every 2h) are parsed from the job.schedule display. Unsupported
expressions are SKIPPED with a warning (never block the whole run).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

_HOME = Path.home()
_JOBS = Path(os.environ.get("CRON_JOBS_FILE", str(_HOME / ".hermes" / "cron" / "jobs.json")))
_UNITS = Path.home() / ".config" / "systemd" / "user"
_RUNNER = "ops/scripts/cortex-bus-bridge-run.py"  # repo-relative; resolved at install
_PREFIX = "cortex-bridge-"
# A bridge unit is Type=oneshot; the default KillMode (control-group) would kill
# any child the job detached when the tick exits. See the module docstring.
_KILLMODE_LINE = "KillMode=process"


def parse_cron(expr: str):
    """Parse a 5-field cron expression into (min, hour, dom, mon, dow), each a
    str (possibly '*/N' or '*'). Returns None on unsupported shapes."""
    f = expr.split()
    if len(f) != 5:
        return None
    return f


def cron_to_oncalendar(expr: str) -> str | None:
    """Best-effort cron→systemd OnCalendar. Returns None if unsupported."""
    fields = parse_cron(expr)
    if fields is None:
        return None
    minute, hour, dom, mon, dow = fields
    # systemd OnCalendar: each unit is optional; we serialize non-* fields in
    # systemd order (hour:minute day-of-month month day-of-week).
    parts = []
    # MM:DD -> systemd "DOW YYYY-MM-DD HH:MM" differs; simplest robust mapping
    # is to emit the five cron fields in systemd's order. systemd accepts
    # "HH:MM", "day-of-month month day-of-week" etc. Map the common cases:
    #   * * * * * -> every minute: OnCalendar=*-*-* *:*:00
    if minute == "*" and hour == "*" and dom == "*" and mon == "*" and dow == "*":
        return "*-*-* *:*:00"
    #   */N * * * * -> every N minutes (systemd: *:0/N:00)
    m = re.fullmatch(r"\*/(\d+)", minute)
    if m and hour == "*" and dom == "*" and mon == "*" and dow == "*":
        return f"*-*-* *:0/{m.group(1)}:00"
    #   0 */N * * * -> every N hours at minute 0 (systemd hourly step is
    #   '*-*-* *:00/N:00' — fires on every Nth hour at :00)
    m2 = re.fullmatch(r"\*/(\d+)", hour)
    if m2 and minute in ("*", "0") and dom == "*" and mon == "*" and dow == "*":
        return f"*-*-* *:00/{m2.group(1)}:00"
    #   M * * * * / 0 * * * * -> every hour at minute M (systemd *:MM:00)
    if re.fullmatch(r"\d+", minute) and hour == "*" \
            and dom == "*" and mon == "*" and dow == "*":
        return f"*-*-* *:{int(minute):02d}:00"
    #   M H * * * -> daily at H:M
    if re.fullmatch(r"\d+", minute) and re.fullmatch(r"\d+", hour) \
            and dom == "*" and mon == "*" and dow == "*":
        return f"*-*-* {int(hour):02d}:{int(minute):02d}:00"
    #   M H1,H2 * * * -> daily at each listed hour (systemd comma list)
    if re.fullmatch(r"\d+", minute) and re.fullmatch(r"\d+(?:,\d+)+", hour) \
            and dom == "*" and mon == "*" and dow == "*":
        hours = ",".join(f"{int(h):02d}" for h in hour.split(","))
        return f"*-*-* {hours}:{int(minute):02d}:00"
    #   M H1-H2 * * * -> daily every hour in range H1..H2 at minute M
    if re.fullmatch(r"\d+", minute) and re.fullmatch(r"\d+-\d+", hour) \
            and dom == "*" and mon == "*" and dow == "*":
        lo, _, hi = hour.partition("-")
        return f"*-*-* {int(lo):02d}..{int(hi):02d}:{int(minute):02d}:00"
    #   M H * * D / D D2 / D-D3 -> weekly on (list of) day(s)
    day_names = {"0": "Sun", "1": "Mon", "2": "Tue", "3": "Wed",
                 "4": "Thu", "5": "Fri", "6": "Sat", "7": "Sun"}
    def _map_dow(field: str) -> str | None:
        # field like '1-5' -> 'Mon..Fri'; '11'-stray handled elsewhere.
        elems: list[str] = []
        for tok in field.split(","):
            if re.fullmatch(r"\d+", tok):
                elems.append(day_names.get(tok, tok))
            elif "-" in tok:
                a, _, b = tok.partition("-")
                if a.isdigit() and b.isdigit() and int(b) < int(a):
                    return None
                elems.append(f"{day_names.get(a, a)}..{day_names.get(b, b)}")
            else:
                return None
        return ",".join(elems)
    if re.fullmatch(r"\d+", minute) and dom == "*" and mon == "*" and dow != "*":
        days = _map_dow(dow)
        if days is None:
            return None
        mm = int(minute)
        # hour may be a single, a list (H1,H2), or a range (H1-H2).
        if re.fullmatch(r"\d+", hour):
            htxt = f"{int(hour):02d}"
        elif re.fullmatch(r"\d+(?:,\d+)+", hour):
            htxt = ",".join(f"{int(h):02d}" for h in hour.split(","))
        elif re.fullmatch(r"\d+-\d+", hour):
            lo, _, hi = hour.partition("-")
            htxt = f"{int(lo):02d}..{int(hi):02d}"
        else:
            return None
        return f"{days} *-*-* {htxt}:{mm:02d}:00"
    # Fall back to the "every N" interval display forms handled separately.
    return None


def instance_interval(schedule: dict) -> str | None:
    """Parse a hermes schedule {kind:'every', every:'2h'} or natural display
    'every 2h' form into a systemd OnCalendar interval string if possible."""
    every = (schedule or {}).get("every")
    if not every and (schedule or {}).get("kind") == "every":
        every = str((schedule or {}).get("every"))
    if not every:
        disp = (schedule or {}).get("display") or ""
        m = re.fullmatch(r"every (\d+)([mh])", disp.strip())
        if m:
            every = m.group(1) + m.group(2)
    if not every:
        return None
    m = re.fullmatch(r"(\d+)([mh])", str(every).strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    if unit == "h":
        return f"*-*-* *:00/{n}:00"
    if unit == "m":
        # >=60m that divides into whole hours (e.g. every 360m = 6h) -> hourly
        # step. Otherwise systemd supports minute-step '*:0/N:00' (fires every
        # N minutes on the :00 phase) — reliable when N divides 60; refuse
        # non-dividing N (e.g. 70) rather than under-fire.
        if n >= 60 and n % 60 == 0:
            return f"*-*-* *:00/{n // 60}:00"
        if 60 % n == 0:
            return f"*-*-* *:0/{n}:00"
        return None
    return None


def job_is_simple(job: dict) -> bool:
    return (bool(job.get("no_agent"))
            and bool(job.get("script"))
            and not job.get("context_from")
            and not job.get("continuity")
            and not job.get("model"))


def unit_needs_killmode(text: str) -> bool:
    """True when a bridge service unit has no explicit KillMode setting.

    An ABSENT directive means systemd's default (control-group for oneshot),
    which kills detached children — the defect this module guards against. A
    unit that explicitly sets any KillMode is honoured as-is (operator override).
    """
    return not re.search(r"(?m)^\s*KillMode\s*=", text)


def with_killmode(text: str) -> str:
    """Return `text` with KillMode=process added when it lacks a KillMode.

    Inserted directly after the `Type=` line so it lands inside the [Service]
    section; if there is no Type= line, before the first ExecStart=. Idempotent:
    a unit that already sets KillMode is returned byte-identical.
    """
    if not unit_needs_killmode(text):
        return text
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    done = False
    for line in lines:
        out.append(line)
        if not done and re.match(r"\s*Type\s*=", line):
            out.append(_KILLMODE_LINE + "\n")
            done = True
    if done:
        return "".join(out)
    # No Type= line (unexpected for a bridge unit): anchor before ExecStart.
    out2: list[str] = []
    for line in out:
        if re.match(r"\s*ExecStart\s*=", line):
            out2.append(_KILLMODE_LINE + "\n")
            break
        out2.append(line)
    else:
        # Neither anchor present — refuse rather than write a malformed unit.
        return text
    out2.extend(out[len(out2):])
    return "".join(out2)


def unit_text(name: str, script: str, runner: str) -> tuple[str, str] | None:
    """Return (service_text, timer_text). Schedule derived from job; returns
    None if we can't translate the schedule (caller skips that job)."""
    # schedule passed in via closure in main; this helper is schedule-free for
    # clarity — the caller injects OnCalendar.
    service = f"""[Unit]
Description=Cortex bridge — {name} (no_agent cron, standalone runner)

[Service]
Type=oneshot
{_KILLMODE_LINE}
ExecStart=/usr/bin/env python3 {runner} --name {name} --script {script}
"""
    return service, ""


def repair_units() -> int:
    """Add KillMode=process to already-deployed bridge service units.

    Needed because a migrated job is REMOVED from jobs.json, so the generator
    can never emit its unit again — only an in-place fix reaches it.

    Never silent about a unit it could not read or write: unreadable/unwritable
    units are counted and named, and the run exits non-zero, so a partial repair
    cannot be mistaken for a complete one (adversarial finding ADV-0-1).
    """
    units = sorted(_UNITS.glob(f"{_PREFIX}*.service")) if _UNITS.is_dir() else []
    repaired, ok, failed = 0, 0, []
    for p in units:
        try:
            text = p.read_text()
        except OSError as e:
            failed.append(f"{p.name} (read: {e.strerror or e})")
            continue
        new = with_killmode(text)
        if new == text:
            ok += 1
            continue
        try:
            p.write_text(new)
        except OSError as e:
            failed.append(f"{p.name} (write: {e.strerror or e})")
            continue
        repaired += 1
    print(f"[bridge] repair: {repaired} unit(s) given {_KILLMODE_LINE}; "
          f"{ok} already correct; {len(units)} scanned")
    if failed:
        print(f"[bridge] repair FAILED for {len(failed)} unit(s): "
              + "; ".join(failed[:5]) + (" …" if len(failed) > 5 else ""),
              file=sys.stderr)
        return 1
    if repaired:
        print("[bridge] next: systemctl --user daemon-reload")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default=None)
    ap.add_argument("--repair", action="store_true",
                    help="add KillMode=process to already-deployed bridge units")
    args = ap.parse_args()

    if args.repair:
        if args.dry_run:
            planned = 0
            for p in sorted(_UNITS.glob(f"{_PREFIX}*.service")) if _UNITS.is_dir() else []:
                try:
                    if unit_needs_killmode(p.read_text()):
                        planned += 1
                except OSError as e:
                    print(f"[bridge] repair: cannot read {p.name}: {e}", file=sys.stderr)
            print(f"[bridge] repair --dry-run: {planned} unit(s) would be updated")
            return 0
        return repair_units()

    if not _JOBS.exists():
        print(f"[bridge] no jobs file at {_JOBS}", file=sys.stderr)
        return 1
    data = json.loads(_JOBS.read_text())
    jobs = data if isinstance(data, list) else data.get("jobs", [])

    repo_root = Path(__file__).resolve().parent.parent.parent  # ops/scripts → repo
    runner_path = repo_root / "ops" / "scripts" / "cortex-bus-bridge-run.py"

    written = 0
    skipped = 0
    for job in jobs:
        name = job.get("name")
        if args.only and name != args.only:
            continue
        if not job_is_simple(job):
            skipped += 1
            continue
        schedule = job.get("schedule") or {}
        expr = schedule.get("expr") or (schedule.get("display") or "")
        oncal = cron_to_oncalendar(expr) if schedule.get("kind") == "cron" \
            else instance_interval(schedule)
        if not oncal:
            print(f"[bridge] skip {name}: unsupported schedule '{expr}'", file=sys.stderr)
            skipped += 1
            continue

        unit = _PREFIX + name
        service_path = _UNITS / f"{unit}.service"
        timer_path = _UNITS / f"{unit}.timer"

        service_text = f"""[Unit]
Description=Cortex bridge — {name} (no_agent cron, standalone runner)

[Service]
Type=oneshot
{_KILLMODE_LINE}
ExecStart=/usr/bin/env python3 {runner_path} --name {name} --script {job.get('script')} --deliver {job.get('deliver') or 'origin'}
"""
        timer_text = f"""[Unit]
Description=Cortex bridge timer — {name}

[Timer]
OnCalendar={oncal}
Persistent=true

[Install]
WantedBy=timers.target
"""
        if args.dry_run:
            print(f"== {unit} ==")
            print(service_path)
            print(service_text)
            print(timer_path)
            print(timer_text)
            written += 1
            continue

        _UNITS.mkdir(parents=True, exist_ok=True)
        service_path.write_text(service_text)
        timer_path.write_text(timer_text)
        written += 1

    print(f"[bridge] generated {written} unit set(s) in {_UNITS}; {skipped} skipped")
    if not args.dry_run and written:
        print("[bridge] next: systemctl --user daemon-reload; then enable per-job timers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
