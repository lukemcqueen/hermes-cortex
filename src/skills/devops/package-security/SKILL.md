---
name: package-security
description: >
  Age-gated package installation protection. Before installing any
  package with pip, npm, brew, or cargo, verify it's been public
  for at least 14 days. Blocks supply-chain attacks on brand-new
  releases (dependency confusion, account takeover, malware).
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [security, packages, supply-chain, pip, npm, brew, cargo]
    related_skills: [system-watchdog, security-audit-panel, macos-monterey-server-hardening]
scripts:
  - check-package-age.py
  - package-install.sh
---

# Package Security — 14-Day Age Gate

## Overview

Every package install is a trust decision. A brand-new package (or a
new version of an existing package) could be:

- **Account takeover** — attacker publishes malicious version under
  a compromised maintainer account
- **Dependency confusion** — attacker publishes a package with the
  same name as an internal package but on the public registry
- **Typosquatting** — attacker publishes a similar-sounding name
- **Zero-day supply chain** — attacker exploits a vulnerability in
  a package's CI/CD pipeline

This skill enforces a **14-day cooling-off period** before any new
package or version can be installed. If a legitimate update is needed
sooner, you can bypass with `BYPASS_AGE_CHECK=1`.

## How It Works

```
You (or a script) says: pip install requests==3.0.0
                                │
                                ▼
    check-package-age.py ────── queries registry API (PyPI/npm/crates.io/Homebrew)
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
              Age ≥ 14d                Age < 14d
              │                       │
              ▼                       ▼
         INSTALL ✅              BLOCKED 🔴
                                "Wait X.X more days"
```

## Installation

The checker and wrappers are at:

| File | Purpose |
|------|---------|
| `~/.hermes/scripts/check-package-age.py` | Core age checker (PyPI, npm, crates.io, Homebrew) |
| `~/.hermes/scripts/package-install.sh` | Shell wrapper (symlinked as pip-safe, npm-safe, etc.) |
| `~/.hermes/scripts/pip-safe` | → symlink to package-install.sh |
| `~/.hermes/scripts/npm-safe` | → symlink to package-install.sh |
| `~/.hermes/scripts/brew-safe` | → symlink to package-install.sh |
| `~/.hermes/scripts/cargo-safe` | → symlink to package-install.sh |

## Usage

### From the Agent (Preferred)

Always use the `*-safe` wrappers when installing packages:

```bash
# Instead of: pip install requests
# Use:
pip-safe install requests

# Instead of: npm install express
# Use:
npm-safe install express

# Instead of: brew install curl
# Use:
brew-safe install curl
```

### From the Shell (with aliases)

If the aliases from `.aliases` are loaded, `pip`, `npm`, `brew`, and
`cargo` are redirected to the safe wrappers automatically.

### Bypassing (Emergency Use Only)

When you explicitly need a package that's less than 14 days old:

```bash
# Method 1: Environment variable (any shell)
BYPASS_AGE_CHECK=1 pip-safe install urgent-package

# Method 2: Unsafe alias (if .aliases loaded)
pip-unsafe install urgent-package
```

**Only bypass when:** you trust the specific package, verified the
publisher's identity, and understand the risk.

## Supported Registries

| Manager | Registry | API Used |
|---------|----------|----------|
| `pip` | PyPI | `pypi.org/pypi/{name}/json` → `releases[version][].upload_time` |
| `npm` | npmjs | `registry.npmjs.org/{name}` → `time[version]` |
| `brew` | Homebrew | `formulae.brew.sh/api/formula/{name}.json` → `added` or GitHub commit date |
| `cargo` | crates.io | `crates.io/api/v1/crates/{name}` → `versions[].created_at` |

## Custom Minimum Age

```bash
# Stricter: 30-day minimum
MIN_AGE_DAYS=30 pip-safe install requests

# Permanent override in ~/.aliases
export MIN_AGE_DAYS=30
```

## Agent Rules

When asked to install any package:

1. **ALWAYS** use `*-safe` wrappers (the skill auto-loads and the agent
   knows to use them)
2. If a package is blocked by age, report **how long to wait** and
   **suggest an alternative** (older compatible version)
3. When debugging a "package not found" error, check if the package name
   is misspelled (typosquatting protection is a side benefit of the age gate)
4. For CI/CD or automated deploys, pin exact versions that are already
   older than 14 days to avoid blocking fresh builds

## Common Scenarios

### Latest version is blocked, older version works

```bash
# Find the latest version that passes the age gate
python3 ~/.hermes/scripts/check-package-age.py pip package==X.Y.Z

# Install the older version
pip-safe install package==X.Y.Z
```

### CI pipeline blocked by a fresh dependency

In CI, the age gate could block fresh builds of a project that depends
on a just-published transitive dependency. Mitigation:

```bash
# In CI scripts, set BYPASS_AGE_CHECK for your OWN packages only
# (not for transitive dependencies — those are your responsibility)
export BYPASS_AGE_CHECK=1
```

Better: pin all dependencies with `pip freeze > requirements.txt` so
version resolution uses already-vetted versions.

### Brew formula not found

Homebrew formulas added in the last 14 days may not be fully indexed
by the API. Try:

```bash
# Check if the formula exists at all
brew search formula-name

# If it exists but is too new, use the unsafe path
brew-unsafe install formula-name
```

## Verification

```bash
# Check that the checker exists and responds
python3 ~/.hermes/scripts/check-package-age.py --help

# Check a known-old package
python3 ~/.hermes/scripts/check-package-age.py pip requests
# → ✅ OK: requests==X.Y.Z is NNN.Nd old (≥14d)

# Check a non-existent package
python3 ~/.hermes/scripts/check-package-age.py pip nonexistent-pkg
# → ❌ none...: PyPI package 'nonexistent-pkg' not found
```

## Pitfalls

- **Alias recursion:** If `pip` is aliased to `pip-safe`, and `pip-safe`
  calls `exec pip`, the alias triggers again → infinite loop. The
  wrapper script uses *direct binary paths* for the final exec.
- **Network dependency:** The age check requires internet access. If
  offline, all packages are blocked. Set `BYPASS_AGE_CHECK=1` if you
  trust the offline source.
- **Rate limits:** PyPI and npm have rate limits on their JSON APIs.
  The checker respects a 10-second timeout per request.
- **Brew doesn't have per-version timestamps:** The checker falls back
  to the formula's creation date or the most recent GitHub commit on
  the formula file. This is approximate for very old formulas but
  precise enough for the 14-day gate.
- **New package, first-ever release:** The checker handles this correctly
  — the first release's upload timestamp is compared against the gate.
- **Multiple packages in one install:** The wrapper checks ALL packages
  before proceeding. If one fails, none are installed.
