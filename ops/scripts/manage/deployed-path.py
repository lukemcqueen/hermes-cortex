#!/usr/bin/env python3
"""Where is this repo file DEPLOYED — and is it actually there? Never guess.

WHY THIS EXISTS
---------------
The deployed path of a repo file CANNOT be derived from the repo path: 192 of the ~289
register() entries in cortex-update.sh follow no rule (cortex_lib/paths.py documents this in
its own header, and the repo's deploy skill repeats it). A probe that mirrors the repo
layout under the deploy home therefore checks NOTHING, and pairing it with
``2>/dev/null || echo "<conclusion>"`` prints that failure AS a finding. That is exactly how
the sentence "0 (deployed copy predates this commit)" reached a committed evidence file
while the deployed copy in fact carried the change.

The map is DATA, not a convention: cortex-update.sh's register() lines, written out as
deploy-manifest.tsv. This tool reads that map and answers one question, so an evidence probe
can ask instead of assume.

USAGE
    deployed-path.py <repo-relative-source> [--manifest PATH]

EXIT CODES (a probe can, and should, branch on these)
    0  resolved, and the destination file exists there
    2  COULD NOT RESOLVE — the source has no entry in the deploy map
    3  COULD NOT VERIFY  — the entry exists but nothing is at the destination

stdout carries the destination path ONLY on success. Every failure prints an explicit
COULD NOT RESOLVE / COULD NOT VERIFY line, names the map it inspected, and prints NO path —
there is deliberately no fallback value to mistake for an answer.
"""
import argparse
import os
import sys
from pathlib import Path

_MANIFEST_NAME = "deploy-manifest.tsv"


def _load_read_manifest():
    """Reuse cortex_lib.paths.read_manifest — one parser, one source of truth.

    A second parser here would be a second thing to drift. If it cannot be imported we say
    so and stop; we do not fall back to reading the map by hand.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        for candidate in (parent, parent / "ops" / "scripts"):
            if (candidate / "cortex_lib" / "paths.py").is_file():
                sys.path.insert(0, str(candidate))
                from cortex_lib.paths import read_manifest  # noqa: WPS433
                return read_manifest
    return None


def _find_manifest(explicit):
    """Locate deploy-manifest.tsv. Env first, then the canonical deploy home."""
    if explicit:
        return Path(explicit)
    for env_name in ("CORTEX_DEPLOY_HOME", "HERMES_CORTEX_HOME"):
        base = os.environ.get(env_name)
        if base and (Path(base) / _MANIFEST_NAME).is_file():
            return Path(base) / _MANIFEST_NAME
    home_default = Path.home() / ".hermes-cortex" / _MANIFEST_NAME
    if home_default.is_file():
        return home_default
    return None


def _repo_copy(rel):
    """The repo-side file for `rel`, if we are sitting in a checkout. Reported, never
    returned as the answer: a repo copy is NOT the deployed copy."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / rel
        if candidate.is_file() and (parent / "ops" / "scripts").is_dir():
            return candidate
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", help="repo-relative path, e.g. mcp-servers/loop-gov-mcp.py")
    ap.add_argument("--manifest", default=None, help="explicit deploy-manifest.tsv")
    args = ap.parse_args()

    read_manifest = _load_read_manifest()
    if read_manifest is None:
        print("COULD NOT RESOLVE: cortex_lib.paths.read_manifest is not importable — "
              "cannot read the deploy map. Nothing was checked.")
        return 2

    manifest = _find_manifest(args.manifest)
    if manifest is None or not manifest.is_file():
        print(f"COULD NOT RESOLVE: no {_MANIFEST_NAME} found (looked at CORTEX_DEPLOY_HOME, "
              f"HERMES_CORTEX_HOME, ~/.hermes-cortex/{_MANIFEST_NAME}"
              + (f", {args.manifest}" if args.manifest else "") + "). Nothing was checked.")
        return 2

    mapping = read_manifest(manifest)
    destination = mapping.get(args.source)
    if not destination:
        print(f"COULD NOT RESOLVE: {args.source!r} has no entry in {manifest} "
              f"({len(mapping)} entries). Nothing was checked.")
        repo_copy = _repo_copy(args.source)
        if repo_copy:
            print(f"  (a REPO copy exists at {repo_copy} — that is not the deployed copy)")
        return 2

    destination_path = Path(destination)
    if not destination_path.is_file():
        print(f"COULD NOT VERIFY: {args.source!r} maps to {destination} per {manifest}, "
              f"but nothing is there. The deploy has not put it there (yet).")
        return 3

    print(destination_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
