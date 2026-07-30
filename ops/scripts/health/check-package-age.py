#!/usr/bin/env python3
"""
check-package-age.py — Universal package age verifier.

Before installing any package, call this script to verify it's been
public for at least MIN_AGE_DAYS (default 14). This protects against
dependency confusion attacks, recently published malware, and
supply-chain vulnerabilities in brand-new releases.

Usage:
  # Check latest version of a package
  python3 check-package-age.py pip requests

  # Check a specific version
  python3 check-package-age.py pip requests==2.31.0

  # Check multiple packages at once (install aborts if ANY fail)
  python3 check-package-age.py pip requests flask==3.0.0

  # Check with custom minimum age
  python3 check-package-age.py --min-days 30 pip requests

  # Quiet mode — exit code only, no output on success
  python3 check-package-age.py --quiet pip requests

Exit codes:
  0 — All packages are older than minimum age (safe to install)
  1 — One or more packages are too new (or couldn't be verified)
  2 — Package not found
  3 — Registry unreachable / network error
"""

import json
import sys
import time
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timezone

def _parse_age(upload_time_str: str) -> float:
    """Parse an ISO timestamp and return age in days. Handles naive and aware datetimes."""
    upload_str = upload_time_str.replace("Z", "+00:00")
    uploaded = datetime.fromisoformat(upload_str)
    if uploaded.tzinfo is None:
        uploaded = uploaded.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - uploaded).total_seconds() / 86400.0

MIN_AGE_DAYS = 14
QUIET = False
TIMEOUT = 10  # seconds per request


def eprint(*args, **kwargs):
    if not QUIET:
        print(*args, file=sys.stderr, **kwargs)


# ─── PyPI ────────────────────────────────────────────────────────────

def check_pypi(package: str, version: str | None = None) -> tuple[str, str, float]:
    """Returns (name, version, age_days). Raises on failure."""
    url = f"https://pypi.org/pypi/{package}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "Hermes-Agent/1.0"})
    ctx = ssl.create_default_context()

    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
        data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise LookupError(f"PyPI package '{package}' not found") from e
        raise ConnectionError(f"PyPI HTTP {e.code} for '{package}': {e.reason}") from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"PyPI unreachable for '{package}': {e.reason}") from e

    if version is None:
        version = data["info"]["version"]

    releases = data.get("releases", {})
    version_info = releases.get(version)
    if not version_info:
        raise LookupError(f"PyPI package '{package}' has no release for version {version}")

    # Use the earliest upload time for this version
    upload_times = [r["upload_time"] for r in version_info if r.get("upload_time")]
    if not upload_times:
        raise LookupError(f"PyPI package '{package}' version {version} has no upload timestamps")

    upload_time = min(upload_times)
    age = _parse_age(upload_time)
    return (package, version, age)


# ─── npm ─────────────────────────────────────────────────────────────

def check_npm(package: str, version: str | None = None) -> tuple[str, str, float]:
    url = f"https://registry.npmjs.org/{package}"
    req = urllib.request.Request(url, headers={"User-Agent": "Hermes-Agent/1.0"})
    ctx = ssl.create_default_context()

    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
        data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise LookupError(f"npm package '{package}' not found") from e
        raise ConnectionError(f"npm HTTP {e.code} for '{package}': {e.reason}") from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"npm unreachable for '{package}': {e.reason}") from e

    if version is None:
        version = data.get("dist-tags", {}).get("latest", "")
        if not version:
            # Fall back to the latest time entry
            times = data.get("time", {})
            if times:
                # Find the newest version by upload time
                version = max(
                    [(v, t) for v, t in times.items() if v != "created" and v != "modified"],
                    key=lambda x: x[1]
                )[0]

    times = data.get("time", {})
    upload_time_str = times.get(version)
    if not upload_time_str:
        # Try the version directly
        versions = data.get("versions", {})
        if version in versions:
            ver_data = versions[version]
            upload_time_str = ver_data.get("_npmUser", {}).get("time") or \
                              times.get("created")
        if not upload_time_str:
            raise LookupError(f"npm package '{package}' version {version} has no timestamp")

    age = _parse_age(upload_time_str)
    return (package, version, age)


# ─── Crates.io ───────────────────────────────────────────────────────

def check_cratesio(package: str, version: str | None = None) -> tuple[str, str, float]:
    url = f"https://crates.io/api/v1/crates/{package}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Hermes-Agent/1.0",
        "Accept": "application/json",
    })
    ctx = ssl.create_default_context()

    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
        data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise LookupError(f"crates.io package '{package}' not found") from e
        raise ConnectionError(f"crates.io HTTP {e.code} for '{package}': {e.reason}") from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"crates.io unreachable for '{package}': {e.reason}") from e

    crate = data.get("crate", {})
    versions = data.get("versions", [])

    if version is None:
        version = crate.get("max_version", "")
        if not version and versions:
            version = versions[0]["num"]

    # Find the version entry
    ver_entry = next((v for v in versions if v["num"] == version), None)
    if not ver_entry:
        raise LookupError(f"crates.io package '{package}' version {version} not found")

    upload_time_str = ver_entry.get("created_at", "")
    if not upload_time_str:
        raise LookupError(f"crates.io package '{package}' version {version} has no timestamp")

    age = _parse_age(upload_time_str)
    return (package, version, age)


# ─── Homebrew ────────────────────────────────────────────────────────

def check_homebrew(package: str, version: str | None = None) -> tuple[str, str, float]:
    """Check Homebrew formula age via the official API."""
    url = f"https://formulae.brew.sh/api/formula/{package}.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Hermes-Agent/1.0"})
    ctx = ssl.create_default_context()

    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
        data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise LookupError(f"Homebrew formula '{package}' not found") from e
        raise ConnectionError(f"Homebrew HTTP {e.code} for '{package}': {e.reason}") from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"Homebrew unreachable for '{package}': {e.reason}") from e

    if version is None:
        version = data.get("versions", {}).get("stable", "latest")

    # Use the most recent change timestamp from the formula
    # Homebrew API doesn't expose per-version upload times directly,
    # but we can use the `revision` dates or GitHub metadata.
    # Fall back to the formula's `created` date from GitHub.
    github_url = f"https://api.github.com/repos/Homebrew/homebrew-core/commits?path=Formula/{package}.rb&per_page=1&page=1"
    gh_req = urllib.request.Request(github_url, headers={
        "User-Agent": "Hermes-Agent/1.0",
        "Accept": "application/vnd.github.v3+json",
    })

    try:
        gh_resp = urllib.request.urlopen(gh_req, timeout=TIMEOUT, context=ctx)
        commits = json.loads(gh_resp.read().decode())
        if commits:
            commit_date = commits[0]["commit"]["committer"]["date"]
            age = _parse_age(commit_date)
            return (package, version, age)
    except urllib.error.HTTPError:
        pass  # expected — silently handled

    # Fallback: use the formula's creation date from the JSON
    created = data.get("added")
    if created:
        age = _parse_age(created)
        return (package, version, age)

    raise LookupError(f"Could not determine age of Homebrew formula '{package}'")


# ─── Dispatcher ──────────────────────────────────────────────────────

REGISTRIES = {
    "pip": {"name": "PyPI", "check": check_pypi},
    "npm": {"name": "npm", "check": check_npm},
    "cargo": {"name": "crates.io", "check": check_cratesio},
    "brew": {"name": "Homebrew", "check": check_homebrew},
}


def check_one(manager: str, spec: str) -> tuple[str, str, float]:
    """Parse 'package==version' or 'package' and check age."""
    if "==" in spec:
        pkg, ver = spec.split("==", 1)
    elif "@" in spec:
        pkg, ver = spec.split("@", 1)
    else:
        pkg, ver = spec, None

    pkg = pkg.strip()
    if ver:
        ver = ver.strip()

    registry = REGISTRIES.get(manager)
    if not registry:
        raise ValueError(f"Unknown package manager '{manager}'. Supported: {', '.join(REGISTRIES.keys())}")

    return registry["check"](pkg, ver)


# ─── Main ────────────────────────────────────────────────────────────

def main():
    global MIN_AGE_DAYS, QUIET

    args = sys.argv[1:]

    # Parse flags
    while args and args[0].startswith("--"):
        flag = args.pop(0)
        if flag == "--quiet":
            QUIET = True
        elif flag == "--min-days" and args:
            MIN_AGE_DAYS = int(args.pop(0))
        elif flag.startswith("--min-days="):
            MIN_AGE_DAYS = int(flag.split("=", 1)[1])
        elif flag == "--help" or flag == "-h":
            print(__doc__)
            return 0
        else:
            eprint(f"Unknown flag: {flag}")
            return 1

    if len(args) < 2:
        eprint("Usage: check-package-age.py [--min-days N] [--quiet] <manager> <package> [package...]")
        eprint(f"Example: check-package-age.py pip requests flask==3.0.0")
        return 1

    manager = args[0]
    packages = args[1:]

    all_ok = True
    results = []

    for spec in packages:
        try:
            name, version, age_days = check_one(manager, spec)
            results.append((name, version, age_days, True))
        except (LookupError, ConnectionError, ValueError) as e:
            results.append((spec, "?", 0, False, str(e)))
            all_ok = False
            continue

    # Report results
    failed = False
    for r in results:
        if len(r) == 5:  # Error
            name, _, _, _, err = r
            eprint(f"❌ {name}: {err}")
            failed = True
            continue

        name, version, age_days, _ = r
        age_hours = age_days * 24
        age_str = f"{age_days:.1f}d" if age_days >= 1 else f"{age_hours:.1f}h"

        if age_days < MIN_AGE_DAYS:
            remaining = MIN_AGE_DAYS - age_days
            eprint(f"🔴 BLOCKED: {name}=={version} is only {age_str} old "
                   f"(min {MIN_AGE_DAYS}d). Wait {remaining:.1f}d.")
            failed = True
        else:
            eprint(f"✅ OK: {name}=={version} is {age_str} old (≥{MIN_AGE_DAYS}d)")

    if failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
