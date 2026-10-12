#!/usr/bin/env python3
"""Enable, write, or check the `/model` picker's list on ANY agent host.

WHY THIS EXISTS. The picker itself is gateway code and arrives with the deploy, but the
LIST is per-host: it is operator taste plus whatever models that host's backend can
actually reach. Without this, enabling the picker on a second host (Titus's pi on macOS,
a worker behind a shim) means hand-editing a live config and hoping the shape is right.

It is deliberately PORTABLE: stdlib only, no PyYAML (the gateway loads its config with
json.loads, so a host needs nothing but python3), no Hermes path, no cortex venv, no
GNU-only flags — so the same file runs on Linux and macOS, in a checkout with or without
the rest of the fleet.

USAGE
  # see the block, change nothing (the default is a dry run):
  python3 gateway-model-list.py --config ~/.hermes-cortex/gateway.yaml --models a/b,c/d

  # take the list from THIS host's pi:
  python3 gateway-model-list.py --config ... --from-pi 'openrouter/*'

  # apply it (merges ONLY the models key, preserves every other key, idempotent):
  python3 gateway-model-list.py --config ... --from-pi 'openrouter/*' --write

  # a fleet sweep: is an existing block sane? (exit 1 = problems)
  python3 gateway-model-list.py --config ... --check

  # a host with no pi, or a list captured elsewhere:
  python3 gateway-model-list.py --config ... --from-file ~/pi-models.txt --write

AFTER --write: restart the gateway. It reads its config once, at startup.

EXIT CODES
  0  ok (dry run printed, check clean, or write succeeded)
  1  a problem: bad config, bad block, or a write that would not be safe
  2  usage error
  3  COULD NOT VERIFY — pi is not on PATH, so no list could be derived. Never a "no
     models" result: the host may have hundreds.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PAGE_SIZE_DEFAULT = 6
#: A model id as pi prints it: at least one slash, dotted/dashed segments allowed.
MODEL_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9._-]+)+")
#: pi's table header is itself shaped like a model id ("provider/model") — skip those.
HEADER_TOKENS = {"provider/model", "model", "models", "name", "id"}
#: Past this, a menu is worse than a command; the operator should curate with --models.
MENU_SANITY_LIMIT = 40


class ConfigNotJSON(Exception):
    """The config could not be read as a JSON object — say so, never a traceback."""


def curate(models):
    """Strip, drop blanks, dedupe — preserving the operator's order."""
    out, seen = [], set()
    for m in models or []:
        s = str(m).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def parse_pi_models(text):
    """Pull model ids out of `pi --list-models` output.

    pi prints "No models matching '<pattern>'." and exits 0 when nothing matched, so the
    OUTCOME is decided from the output, never the exit code — that case is an empty list
    here, not an error.
    """
    return curate(t for t in MODEL_TOKEN.findall(text or "") if t.lower() not in HEADER_TOKENS)


def models_block(models, page_size=PAGE_SIZE_DEFAULT):
    """The `models:` value the gateway reads: `data.get("models")` as a dict or a list."""
    return {"models": {"list": curate(models), "page_size": int(page_size)}}


def read_config(path):
    p = Path(path).expanduser()
    try:
        text = p.read_text()
    except FileNotFoundError:
        raise ConfigNotJSON(f"{p} does not exist — point --config at this host's gateway config")
    except OSError as exc:
        raise ConfigNotJSON(f"{p} could not be read: {exc}")
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ConfigNotJSON(
            f"{p} is not JSON ({exc}). The gateway loads its config with json.loads, so a "
            f"hand-written YAML config must be converted first — or add the models: key by "
            f"hand. Nothing was changed."
        )
    if not isinstance(data, dict):
        raise ConfigNotJSON(
            f"{p}: the top level is {type(data).__name__}, but a gateway config is a JSON "
            f"OBJECT. Nothing was changed."
        )
    return data


def write_models(path, block, page_size=PAGE_SIZE_DEFAULT):
    """Merge the models key into the config. Every other key is left as it was.

    Accepts either shape — the inner `{"list", "page_size"}` or the whole
    `{"models": {...}}` fragment that models_block() returns — because passing one where
    the other is expected is a silent way to write an EMPTY list.
    """
    data = read_config(path)
    inner = block.get("models", block) if isinstance(block, dict) else {}
    data["models"] = {"list": curate(inner.get("list", [])), "page_size": int(page_size)}
    Path(path).expanduser().write_text(json.dumps(data, indent=2) + "\n")
    return data


def check_models(cfg):
    """Problems with a configured block, as strings (empty list = healthy)."""
    if cfg is None:
        return ["no models: key — a bare /model on this host stays text-only"]
    if isinstance(cfg, list):
        cfg = {"list": cfg}  # the daemon accepts a bare list too
    if not isinstance(cfg, dict):
        return [f"models: must be an object or a list, got {type(cfg).__name__}"]
    problems = []
    items = cfg.get("list")
    if not isinstance(items, list):
        problems.append(f"models.list must be a list, got {type(items).__name__}")
        items = []
    if not items:
        problems.append("models.list is empty — a bare /model on this host stays text-only")
    blanks = sum(1 for m in items if not str(m).strip())
    if blanks:
        problems.append(f"{blanks} blank entries — the gateway ignores them (and warns at startup)")
    seen, dups = set(), []
    for m in items:
        s = str(m).strip()
        if s and s in seen and s not in dups:
            dups.append(s)
        seen.add(s)
    if dups:
        problems.append("duplicate entries: " + ", ".join(dups))
    ps = cfg.get("page_size", PAGE_SIZE_DEFAULT)
    if isinstance(ps, bool) or not isinstance(ps, int) or ps < 1:
        problems.append(f"page_size must be an integer >= 1, got {ps!r}")
    return problems


def _from_pi(pi_bin, pattern):
    which = shutil.which(pi_bin)
    if not which:
        print(f"COULD NOT VERIFY — no '{pi_bin}' on PATH, so no list can be derived from this "
              f"host. Use --models with your own list, or --from-file with a capture.",
              file=sys.stderr)
        return None
    argv = [which, "--offline", "--list-models"]
    if pattern:
        argv.append(pattern)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"COULD NOT VERIFY — {which} {' '.join(argv[1:])} failed: {exc}", file=sys.stderr)
        return None
    # Decided from the OUTPUT, not the exit code (pi exits 0 with "No models matching").
    return parse_pi_models(proc.stdout + "\n" + proc.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Enable/check the /model picker's list on this host.")
    ap.add_argument("--config", required=False, help="this host's gateway config (JSON)")
    ap.add_argument("--models", help="comma-separated list to use verbatim")
    ap.add_argument("--from-pi", nargs="?", const="", default=None,
                    help="derive the list from this host's pi (optional pattern, e.g. 'openrouter/*')")
    ap.add_argument("--from-file", help="do the same from a saved `pi --list-models` capture")
    ap.add_argument("--pi", default="pi", help="pi binary (default: pi from PATH)")
    ap.add_argument("--page-size", type=int, default=PAGE_SIZE_DEFAULT)
    ap.add_argument("--write", action="store_true", help="apply the block (default: dry run)")
    ap.add_argument("--check", action="store_true", help="validate the existing block")
    args = ap.parse_args(argv)

    if not args.config:
        print("usage: gateway-model-list.py --config <gateway config> "
              "[--check | --models a,b | --from-pi [pattern] | --from-file path] [--write]",
              file=sys.stderr)
        return 2

    if args.check:
        try:
            data = read_config(args.config)
        except ConfigNotJSON as exc:
            print(str(exc), file=sys.stderr)
            return 1
        problems = check_models(data.get("models"))
        if not problems:
            count = len((data.get("models") or {}).get("list", [])) if isinstance(data.get("models"), dict) else len(data.get("models") or [])
            print(f"ok: models: block healthy ({count} entries)")
            return 0
        for p in problems:
            print(f"problem: {p}")
        return 1

    source = None
    if args.models is not None:
        source = args.models.split(",")
    elif args.from_pi is not None:
        source = _from_pi(args.pi, args.from_pi)
        if source is None:
            return 3
    elif args.from_file:
        try:
            source = parse_pi_models(Path(args.from_file).expanduser().read_text())
        except OSError as exc:
            print(f"{args.from_file} could not be read: {exc}", file=sys.stderr)
            return 1
    else:
        print("nothing to do: pass --check, --models, --from-pi or --from-file", file=sys.stderr)
        return 2

    models = curate(source)
    if not models:
        print("no models to configure (an empty list would leave /model text-only). "
              "Check the pattern, or pass --models with your own list.", file=sys.stderr)
        return 1
    block = models_block(models, args.page_size)

    if args.write:
        try:
            write_models(args.config, {"list": models, "page_size": args.page_size}, args.page_size)
        except ConfigNotJSON as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"wrote models: {len(models)} entries (page_size {args.page_size}) into {args.config}")
        print("next: restart the gateway — it reads its config once, at startup")
        return 0

    print(f"dry run: {len(models)} entries, page_size {args.page_size} — nothing written.")
    if len(models) > MENU_SANITY_LIMIT:
        print(f"note: {len(models)} entries is more than a menu can usefully show "
              f"(> {MENU_SANITY_LIMIT}); curate with --models.")
    print("next: add --write to apply it to %s" % args.config)
    print(json.dumps(block))
    return 0


if __name__ == "__main__":
    sys.exit(main())
