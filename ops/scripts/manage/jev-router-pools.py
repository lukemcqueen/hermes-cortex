#!/usr/bin/env python3
"""The router pricing list, and the tool that keeps the pools honest about it.

The decision that spends money is "which model does this turn get", and it is made
by POOL ORDER — first fit wins. Order was hand-edited once and immediately cost a
6.5x model at the head of medium/coding. So the order lives in ONE reviewable
artifact with the PRICES attached:

    config/jev-router-models.json   the fleet policy: ordered candidates per
                                    tier/specialty, each with $/M from the catalog,
                                    the baseline we run, and a per-tier ceiling

This tool validates the live pools against it, or rebuilds them from it.

    jev-router-pools.py                 --check: drift, unlisted models, $ delta
    jev-router-pools.py --check --json
    jev-router-pools.py --write         rebuild $HERMES_HOME/jev/routing.json
    jev-router-pools.py --refresh       re-price the list from the catalog

Exit codes: 0 = matches the list (or was written), 1 = findings, 3 = could not verify.

WHY A LIST AND NOT JUST THE POOLS: prices move. The catalog refreshed mid-session
and our own baseline went from a stale $0.35/M read to $0.56/M; a pool ordered once
and never re-priced silently becomes wrong. The list carries the alternatives too,
so promoting a cheaper model is an edit to one file, and the doctor's cost guard
plus this check make a dearer head visible without anyone remembering to look.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Mapping

RC_OK = 0
RC_FINDINGS = 1
RC_COULD_NOT_VERIFY = 3

# Reasoning-effort levels the effort.py ladder can name (see the upstream plugin's
# jevkit/effort.py:KNOWN_LEVELS). Used only for the selftest's defensive check; the
# plugin clamps anything an endpoint does not support.
EFFORT_LEVELS = ("none", "low", "medium", "high", "xhigh", "max")

REPO_ROOT = Path(__file__).resolve().parents[3]   # ops/scripts/manage/ -> repo root


def default_list() -> Path:
    """The pricing list, from the repo checkout or the deployed copy.

    Two locations because this script runs from both: the repo tree during
    development, and `~/.hermes-cortex/scripts/manage/` after a deploy — where the
    list lives at the deploy root, not beside the script.
    """
    for candidate in (REPO_ROOT / "config" / "jev-router-models.json",
                      Path.home() / ".hermes-cortex" / "config" / "jev-router-models.json"):
        if candidate.is_file():
            return candidate
    return REPO_ROOT / "config" / "jev-router-models.json"


DEFAULT_LIST = default_list()


def routing_path() -> Path:
    home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
    return home / "jev" / "routing.json"


def blended(price: dict) -> float:
    """$/M on the SAME basis everywhere: input + output, per million tokens."""
    try:
        return float(price.get("in", 0)) + float(price.get("out", 0))
    except (TypeError, ValueError):
        return 0.0


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except OSError as exc:
        return None, f"cannot read {path}: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"{path} is not valid JSON: {exc}"


def check(list_doc: dict, live: dict) -> list:
    """Findings where the live pools disagree with the list. Never mutates."""
    findings = []
    baseline = list_doc.get("baseline")
    prices = list_doc.get("prices") or {}
    base_price = blended(prices.get(baseline, {}))
    policy = list_doc.get("policy") or {}
    live_tiers = live.get("tiers") or {}

    for tier, specs in (list_doc.get("tiers") or {}).items():
        ceiling = (policy.get(tier) or {}).get("max_multiple_of_baseline")
        for spec, want in specs.items():
            got = ((live_tiers.get(tier) or {}).get(spec)) or []
            if not got:
                findings.append({"tier": tier, "specialty": spec, "kind": "missing",
                                 "detail": "pool absent from the live routing.json"})
                continue
            if got != want:
                head, want_head = got[0], want[0]
                got_price = blended(prices.get(head, {}))
                want_price = blended(prices.get(want_head, {}))
                findings.append({
                    "tier": tier, "specialty": spec, "kind": "order",
                    "detail": (f"live head {head} (${got_price:.3f}/M) != list head "
                               f"{want_head} (${want_price:.3f}/M)"),
                    "delta_usd_per_m": round(got_price - want_price, 4),
                })
            for model in got:
                if model not in prices:
                    findings.append({"tier": tier, "specialty": spec, "kind": "unlisted",
                                     "detail": f"{model} is not in the pricing list"})
            head_price = blended(prices.get(got[0], {}))
            if ceiling is not None and base_price and head_price > base_price * float(ceiling):
                findings.append({
                    "tier": tier, "specialty": spec, "kind": "ceiling",
                    "detail": (f"head {got[0]} is ${head_price:.3f}/M, above the "
                               f"{float(ceiling):g}x baseline ceiling (${base_price:.3f}/M)"),
                    "delta_usd_per_m": round(head_price - base_price, 4),
                })
    # Reasoning-effort policy is policy too: a list that enables effort must see it
    # reflected in the live routing.json, or a host runs without the cost control it
    # thinks it has. Silently absent on an older list (no effort block) -> no check.
    effort = list_doc.get("effort")
    if isinstance(effort, Mapping) and effort.get("enabled"):
        live_effort = live.get("effort")
        if not isinstance(live_effort, Mapping):
            findings.append({"tier": "-", "specialty": "-", "kind": "effort",
                             "detail": "effort enabled in the list but the live routing.json has "
                                       "no effort block (run --write)"})
        else:
            for key in ("enabled", "levels", "models", "excluded"):
                if live_effort.get(key) != effort.get(key):
                    findings.append({"tier": "-", "specialty": "-", "kind": "effort-drift",
                                     "detail": f"live effort.{key} != list effort.{key} "
                                               f"(run --write)"})
                    break
    return findings


def rebuild(list_doc: dict, live: dict, available=None) -> dict:
    """The live pools + effort policy, from the list (pools filtered to what this host can call)."""
    out = json.loads(json.dumps(live))  # deep copy: everything else is preserved
    # The effort block is policy the same way the pool ORDER is: it is not written by
    # hand on each host. Project it from the list so a host cannot drift from it.
    if isinstance(list_doc.get("effort"), Mapping):
        out["effort"] = json.loads(json.dumps(list_doc["effort"]))
    tiers = out.setdefault("tiers", {})
    skipped = []
    for tier, specs in (list_doc.get("tiers") or {}).items():
        tiers.setdefault(tier, {})
        for spec, want in specs.items():
            if available is None:
                tiers[tier][spec] = list(want)
                continue
            keep = [m for m in want if m in available]
            if not keep:
                skipped.append(f"{tier}/{spec}")
                continue
            tiers[tier][spec] = keep
    return out, skipped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", default=str(DEFAULT_LIST), help="the pricing list")
    ap.add_argument("--routing", default=None, help="live routing.json (default $HERMES_HOME/jev/routing.json)")
    ap.add_argument("--write", action="store_true", help="rewrite the live pools from the list")
    ap.add_argument("--refresh", action="store_true", help="re-price the list from the catalog cache")
    ap.add_argument("--selftest", action="store_true",
                    help="assert this list's own invariants and exit (no live state read)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    list_path = Path(args.list).expanduser()
    doc, reason = read_json(list_path)
    if doc is None:
        print(f"COULD NOT VERIFY: {reason}", file=sys.stderr)
        return RC_COULD_NOT_VERIFY

    if args.selftest:
        return _selftest(doc)

    if args.refresh:
        return _refresh(list_path, doc, args)

    live_path = Path(args.routing).expanduser() if args.routing else routing_path()
    live, reason = read_json(live_path)
    if live is None:
        print(f"COULD NOT VERIFY: {reason}", file=sys.stderr)
        return RC_COULD_NOT_VERIFY

    if args.write:
        updated, skipped = rebuild(doc, live)
        live_path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {live_path} from {list_path}")
        if skipped:
            print(f"  WARNING: no listed model available for: {', '.join(skipped)}", file=sys.stderr)
        return RC_OK

    findings = check(doc, live)
    if args.json:
        print(json.dumps({"list": str(list_path), "routing": str(live_path),
                          "findings": findings}, indent=2))
    else:
        base_price = blended((doc.get("prices") or {}).get(doc.get("baseline"), {}))
        print(f"router pricing list : {list_path} (captured {doc.get('captured')})")
        print(f"baseline            : {doc.get('baseline')} = ${base_price:.3f}/M")
        print(f"live pools          : {live_path}")
        if not findings:
            print("\nno findings — every pool matches the list")
        else:
            print(f"\n{len(findings)} finding(s):")
            for f in findings:
                delta = f" (${f['delta_usd_per_m']:+.3f}/M)" if "delta_usd_per_m" in f else ""
                print(f"  [{f['kind']}] {f['tier']}/{f['specialty']}: {f['detail']}{delta}")
    return RC_FINDINGS if findings else RC_OK


def _selftest(doc: dict) -> int:
    """Assert the list's own invariants. Re-runnable on a host with no test suite.

    Committed because the script is load-bearing for what may be routed: a reviewer is
    right to refuse "the tests pass" as a claim with no run behind it. This runs the
    same invariants the repo's tests pin, straight from the artifact.
    """
    prices = doc.get("prices") or {}
    base = doc.get("baseline")
    base_price = blended(prices.get(base, {}))
    tiers = doc.get("tiers") or {}
    policy = doc.get("policy") or {}
    failures = []

    if not base_price:
        failures.append(f"baseline {base!r} has no price in the list")
    for tier, specs in tiers.items():
        if tier == "hard":
            continue
        ceiling = (policy.get(tier) or {}).get("max_multiple_of_baseline")
        for spec, models in specs.items():
            if not models:
                failures.append(f"{tier}/{spec} is empty")
                continue
            head = blended(prices.get(models[0], {}))
            if base_price and head >= base_price:
                failures.append(f"{tier}/{spec} head {models[0]} is not cheaper than the baseline")
            if ceiling is not None and base_price:
                for model in models:
                    price = blended(prices.get(model, {}))
                    if price > base_price * float(ceiling):
                        failures.append(f"{tier}/{spec} model {model} is ${price:.3f}/M, above the "
                                        f"{float(ceiling):g}x ceiling")
    simple_ceiling = (policy.get("simple") or {}).get("max_multiple_of_baseline")
    if simple_ceiling is not None and base_price:
        for spec, models in (tiers.get("simple") or {}).items():
            for model in models:
                if blended(prices.get(model, {})) > base_price * float(simple_ceiling):
                    failures.append(f"simple/{spec} {model} breaks the simple ceiling")
    routed = {m for specs in tiers.values() for models in specs.values() for m in models}
    named = set(doc.get("candidates") or {}) | set(doc.get("rejected") or {})
    for model in sorted(set(prices) - routed - named):
        failures.append(f"{model} is priced but neither routed nor named")
    if set(doc.get("candidates") or {}) & set(doc.get("rejected") or {}):
        failures.append("a model is both a candidate and rejected")
    # The hard budget is an ABSOLUTE $/M cap: a multiple of the baseline silently changes
    # meaning when the baseline gets cheaper, and would evict good models for no reason.
    hard_cap = (policy.get("hard") or {}).get("max_price_usd_per_m")
    whitelist = set(doc.get("hard_whitelist") or {})
    if (policy.get("hard") or {}).get("whitelist_only"):
        if not whitelist:
            failures.append("hard is whitelist_only but hard_whitelist is empty")
        for spec, models in (tiers.get("hard") or {}).items():
            for model in models:
                if model not in whitelist:
                    failures.append(f"hard/{spec} routes {model}, which is not on the hard whitelist")
    if hard_cap is not None:
        # `rejected` is exempt on purpose: it exists to record WHY a dear model is not
        # routed, price and all. Everything else must be inside the budget.
        for model, entry in prices.items():
            if model in (doc.get("rejected") or {}):
                continue
            price = blended(entry)
            if price > float(hard_cap):
                failures.append(f"{model} is ${price:.3f}/M, above the ${float(hard_cap):.2f}/M "
                                f"hard cap, but is still present in the list - expensive models "
                                f"must not be listed at all")
    expected_heads = {f"{t}/{s}" for t, specs in tiers.items() for s in specs}
    missing = expected_heads - set((doc.get("derivation") or {}).get("heads") or {})
    if missing:
        failures.append(f"heads with no derivation: {sorted(missing)}")
    effort = doc.get("effort")
    if isinstance(effort, Mapping) and effort.get("enabled"):
        levels = effort.get("levels")
        if not isinstance(levels, list) or len(levels) != 4:
            failures.append(f"effort.levels must be 4 (trivial/routine/substantial/expert): {levels!r}")
        elif any(level not in EFFORT_LEVELS for level in levels):
            failures.append(f"effort.levels names an unknown level: {levels}")
        routed = {m for specs in tiers.values() for spec_models in specs.values() for m in spec_models}
        declared = {m for m in (effort.get("models") or {})}
        excluded = set(effort.get("excluded") or {})
        uncovered = routed - declared - excluded
        if uncovered:
            failures.append(f"routed models with no effort decision (declare or exclude): {sorted(uncovered)}")
        for model, supported in (effort.get("models") or {}).items():
            if not isinstance(supported, list) or not supported or any(
                    level not in EFFORT_LEVELS for level in supported):
                failures.append(f"effort.models[{model}] is not a non-empty list of known levels: {supported!r}")
        for model, entry in (effort.get("excluded") or {}).items():
            if not isinstance(entry, Mapping) or not entry.get("reason") or not entry.get("evidence"):
                failures.append(f"effort.excluded[{model}] must carry reason and evidence: {entry!r}")

    if failures:
        print(f"SELFTEST FAILED ({len(failures)}):")
        for f in failures:
            print("  -", f)
        return RC_FINDINGS
    print(f"SELFTEST PASSED — {len(tiers)} tiers, {len(routed)} routed model(s), "
          f"baseline ${base_price:.3f}/M, every non-hard head cheaper, every simple pool "
          f"within its ceiling, {len(whitelist)} model(s) on the hard whitelist and nothing "
          f"dearer than ${float(hard_cap or 0):.2f}/M listed at all")
    return RC_OK


def _refresh(list_path: Path, doc: dict, args) -> int:
    """Re-price every listed model from the catalog cache (no network)."""
    cache = Path(os.environ.get("JEV_CATALOG_CACHE")
                 or (Path.home() / ".cache" / "jev" / "models_dev.json"))
    raw, reason = read_json(cache)
    if raw is None:
        print(f"COULD NOT VERIFY: {reason}", file=sys.stderr)
        return RC_COULD_NOT_VERIFY
    prices, missing = {}, []
    for model in sorted(set(doc.get("prices") or {}) | {
            m for specs in (doc.get("tiers") or {}).values() for models in specs.values() for m in models}):
        provider, _, bare = model.partition(":")
        entry = ((raw.get(provider) or {}).get("models") or {}).get(bare)
        cost = (entry or {}).get("cost") or {}
        if not entry or not cost:
            missing.append(model)
            continue
        try:
            prices[model] = {"in": float(cost.get("input", 0)), "out": float(cost.get("output", 0)),
                             "cache_read": float(cost.get("cache_read", 0))}
        except (TypeError, ValueError):
            missing.append(model)
    import datetime
    doc["prices"] = prices
    doc["captured"] = datetime.date.today().isoformat()
    list_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"refreshed {len(prices)} price(s) in {list_path} (captured {doc['captured']})")
    if missing:
        print(f"  WARNING: no catalog price for: {', '.join(missing)}", file=sys.stderr)
    return RC_OK


if __name__ == "__main__":
    sys.exit(main())
