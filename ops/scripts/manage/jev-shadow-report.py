#!/usr/bin/env python3
"""What has shadow actually seen, and is routing worth turning on?

Shadow decides and logs but switches nothing, so the ONLY way to know whether
turning routing `on` would help is to read the decision log. This prints that
summary — it is the monitor, and it runs on any host that has the layer.

    jev-shadow-report.py                 last 7 days, human summary
    jev-shadow-report.py --days 1
    jev-shadow-report.py --json          machine-readable
    jev-shadow-report.py --log PATH      a different decisions log

Reads `$HERMES_HOME/logs/jev-decisions.jsonl` (the plugin's own log: decisions
only, never prompt text). Two row kinds matter:

  route           the decision for a turn — tier, specialty, confidence, and
                  whether it WOULD have switched (`routed`)
  route_effective what actually went out (`applied`) — in shadow always false

Exit codes: 0 = reported (including "no decisions yet"), 3 = the log could not be
read (never reported as a clean run), 1 = reserved for a refused report.

WHY THE VERDICT MATTERS MORE THAN THE COUNTS: a log full of `routed: false` on
low confidence means the pools are NOT the lever — Jev is not recognising the
turns as asks, so moving models between pools changes nothing and the fix is what
the turn SHOWS it, not the prices. That is the failure this report exists to make
visible before anyone flips the switch.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

RC_OK = 0
RC_REFUSED = 1
RC_COULD_NOT_VERIFY = 3

# The model the fleet runs today, used as the baseline for the price delta. Override
# with --current; the report says so when it cannot price something.
DEFAULT_CURRENT = "openrouter:deepseek/deepseek-v4.1-flash"


def decisions_log() -> Path:
    home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
    return home / "logs" / "jev-decisions.jsonl"


def load_rows(path: Path, since: float) -> list:
    """Parse the log, skipping blank lines. A malformed line is COUNTED, not hidden."""
    rows, malformed = [], 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(row, dict) and float(row.get("ts") or 0) >= since:
                rows.append(row)
    if malformed:
        print(f"WARNING: {malformed} malformed line(s) skipped", file=sys.stderr)
    return rows


def _price_helper():
    """The doctor's price resolver, so the $ rule has ONE definition.

    Imported by path from the doctor package; if it is not deployed here, the
    report still runs and says prices are unavailable rather than guessing.
    """
    # The doctor package deploys to <deploy root>/scripts/cortex_doctor/, NOT beside
    # this script — looking only next to it made the DEPLOYED report print
    # "price unknown" on a host with a full catalog.
    here = Path(__file__).resolve().parent
    for candidate in (here / "cortex_doctor" / "jev.py",
                      here.parent / "cortex_doctor" / "jev.py"):
        if candidate.is_file():
            path = candidate
            break
    else:
        return None, None
    spec = importlib.util.spec_from_file_location("jev_shadow_price_helper", path)
    if spec is None or spec.loader is None:
        return None, None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._catalog_prices, module._price_for


def _confidence(row) -> "float | None":
    """The decision's confidence, from the field or from the reason it printed.

    Measured on the live log: a low-confidence keep logs `"confidence": null` and puts
    the number in the reason instead (`low confidence 0.02`), so reading the field alone
    reported "n: 0, median: None" on a log that was full of confidence values — and the
    median confidence is the signal this whole report turns on.
    """
    value = row.get("confidence")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    reason = str(row.get("reason") or "")
    match = re.search(r"confidence\s+([0-9]*\.?[0-9]+)", reason)
    return float(match.group(1)) if match else None


def summarise(rows: list, current: str) -> dict:
    routes = [r for r in rows if r.get("kind") == "route"]
    effective = [r for r in rows if r.get("kind") == "route_effective"]
    tiers = Counter(r.get("tier") or "(none)" for r in routes)
    reasons = Counter((r.get("reason") or "?")[:40] for r in routes)
    confidences = [c for c in (_confidence(r) for r in routes) if c is not None]
    confidences.sort()

    def median(values):
        if not values:
            return None
        mid = len(values) // 2
        return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2

    would_switch = Counter(r.get("model") or "?" for r in routes if r.get("routed"))
    applied = sum(1 for r in effective if r.get("applied"))
    return {
        "rows": len(rows),
        "route_rows": len(routes),
        "effective_rows": len(effective),
        "modes": sorted({r.get("mode") for r in rows if r.get("mode")}),
        "routed_true": sum(1 for r in routes if r.get("routed")),
        "applied_true": applied,
        "tiers": dict(tiers.most_common()),
        "confidence": {
            "n": len(confidences),
            "min": confidences[0] if confidences else None,
            "median": median(confidences),
            "max": confidences[-1] if confidences else None,
        },
        "top_reasons": dict(reasons.most_common(5)),
        "would_switch_to": dict(would_switch.most_common()),
        "current": current,
    }


def verdict(summary: dict, prices=None, price_for=None) -> str:
    if not summary["route_rows"]:
        return ("no routing decisions logged yet — the plugin logs one per fresh turn; "
                "if this stays empty, the plugin is not loaded or routing is off")
    if not summary["routed_true"]:
        return (f"{summary['route_rows']} decision(s), none switched or would switch "
                f"(median confidence {summary['confidence']['median']}) — the POOLS are not "
                f"the lever here: Jev is not recognising these turns as asks. Fix what the "
                f"turn shows it, not the model prices.")
    live = "on" in (summary.get("modes") or [])
    verb = "SWITCHED" if live else "would have switched"
    lines = [f"{summary['routed_true']} of {summary['route_rows']} decision(s) {verb}:"]
    for model, count in summary["would_switch_to"].items():
        delta = ""
        if prices is not None and price_for is not None:
            now = price_for(prices, summary["current"])
            then = price_for(prices, model)
            if now and then:
                delta = f" — ${then:.3f}/M vs ${now:.3f}/M ({then / now:.1f}x)"
        lines.append(f"  {count}x → {model}{delta}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log", default=None, help="decisions log (default $HERMES_HOME/logs/jev-decisions.jsonl)")
    ap.add_argument("--days", type=float, default=7.0, help="window in days (default 7)")
    ap.add_argument("--current", default=DEFAULT_CURRENT, help="the model to price against")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    path = Path(args.log).expanduser() if args.log else decisions_log()
    if not path.is_file():
        print(f"COULD NOT VERIFY: no decisions log at {path}", file=sys.stderr)
        print("(the plugin logs one row per routed turn; nothing has been routed on this host yet)",
              file=sys.stderr)
        return RC_COULD_NOT_VERIFY

    import time
    rows = load_rows(path, time.time() - args.days * 86400)
    summary = summarise(rows, args.current)
    # _price_helper returns the two FUNCTIONS; calling the first one is the prices.
    # Getting this backwards made `prices` a function and every price lookup a
    # TypeError — caught by running the report, not by reading it.
    catalog_fn, price_for = _price_helper()
    prices = catalog_fn() if catalog_fn else {}
    summary["verdict"] = verdict(summary, prices, price_for)

    if args.json:
        print(json.dumps(summary, indent=2))
        return RC_OK

    print(f"Jev shadow report — {path}")
    print(f"  window        : {args.days:g} day(s)")
    print(f"  rows          : {summary['rows']} "
          f"({summary['route_rows']} route, {summary['effective_rows']} route_effective)")
    print(f"  modes seen    : {', '.join(summary['modes']) or '(none)'}")
    print(f"  would switch  : {summary['routed_true']}   actually applied: {summary['applied_true']}")
    print(f"  tiers         : {summary['tiers'] or '(none)'}")
    print(f"  confidence    : {summary['confidence']}")
    if summary["top_reasons"]:
        print("  top reasons   :")
        for reason, count in summary["top_reasons"].items():
            print(f"    {count:>4}x {reason}")
    print(f"  current model : {args.current}"
          + (f" (${price_for(prices, args.current):.3f}/M)" if price_for and price_for(prices, args.current) else " (price unknown)"))
    print()
    print("VERDICT:")
    for line in summary["verdict"].splitlines():
        print("  " + line)
    return RC_OK


if __name__ == "__main__":
    sys.exit(main())
