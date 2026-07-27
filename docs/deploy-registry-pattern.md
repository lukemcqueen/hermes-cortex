# Deploy Registry Pattern

## Overview

The **Deploy Registry Pattern** is a deployment architecture for Hermes Cortex that uses a **multi-repo** strategy: a public MIT-licensed repository holds shared tooling and brain logic, while a private companion repository contains environment-specific configuration, secrets, and deployment metadata. This split enables open-source collaboration without exposing sensitive infrastructure details.

---

## Table of Contents

- [Repository Topology](#repository-topology)
- [Branching Strategy](#branching-strategy)
- [Sync Workflow: Private → Public](#sync-workflow-private--public)
- [cortex-profile.sh: Hermetic Project Profiles](#cortex-profilersh-hermetic-project-profiles)
- [gbrain: Isolated Sources](#gbrain-isolated-sources)
- [Directory Layout](#directory-layout)
- [Setup Guide](#setup-guide)
- [Operations Guide](#operations-guide)
- [Security Considerations](#security-considerations)

---

## Repository Topology

| Repository | Visibility | License | Contents |
|---|---|---|---|
| `hermes-cortex` | **Public** | MIT | Brain code, profiles, deploy scripts, documentation |
| `hermes-cortex-private` | **Private** | Proprietary | Secrets, per-environment config, encrypted credentials |

### Public Repo (`hermes-cortex`)

- MIT licensed — anyone can fork, use, and contribute.
- Contains all brain sources (`gbrain/`), deploy orchestration, profile definitions, and this document.
- CI/CD runs public tests and linting.
- Brain data resides on `brain-*` branches (see [Branching Strategy](#branching-strategy)).

### Private Repo (`hermes-cortex-private`)

- Tightly access-controlled.
- Stores environment-specific configuration (e.g., `staging.env`, `production.env`).
- Holds encrypted secrets (API keys, tokens, SSH keys) managed via `sops` or `age`.
- Never checked into the public repo — the sync workflow ensures only non-sensitive artifacts cross the boundary.

---

## Branching Strategy

### Public Repo Branches

| Branch Pattern | Purpose |
|---|---|
| `main` | Stable release line. All deployable code is merged here after review. |
| `brain-*` | Brain data branches. Each `brain-*` branch holds the artifact output of a `gbrain` source (e.g., `brain-agent`, `brain-tools`). These are the deployable units consumed by the registry. |
| `develop` | Integration branch for feature work. |
| `feature/*` | Topic branches for individual changes. |

### Private Repo Branches

| Branch Pattern | Purpose |
|---|---|
| `main` | Current state of secrets and config, kept in sync with public `main`. |
| `env/*` | Environment overlays (`env/staging`, `env/production`). |
| `brain-*` | Mirrors of public `brain-*` branches, augmented with private config overlays. |

### Brain Branch Lifecycle

1. A developer creates a feature branch off `develop` in the public repo.
2. Changes to brain logic are committed under `gbrain/`.
3. On merge to `develop`, CI builds the brain artifact and pushes it to a `brain-*` branch.
4. On merge to `main`, the brain branch is tagged and the private repo syncs it in.

---

## Sync Workflow: Private → Public

The sync direction is **private → public**: the private repo is the authoritative source for production deployment, but non-sensitive changes flow upstream to the public repo.

```
┌─────────────────────┐       sync       ┌────────────────────┐
│  hermes-cortex       │ ◄─────────────── │  hermes-cortex      │
│  (public, MIT)      │    (upstream)    │  (private)          │
│                     │                  │                     │
│  gbrain/            │                  │  config/            │
│  profiles/          │                  │  secrets/           │
│  docs/              │                  │  env/               │
│  brain-* branches   │                  │  brain-* overlays   │
└─────────────────────┘                  └────────────────────┘
```

### Sync Script

A script at `scripts/sync-upstream.sh` handles the one-way sync:

```bash
#!/usr/bin/env bash
# scripts/sync-upstream.sh — Sync public repo changes into the private repo
set -euo pipefail

PUBLIC_REMOTE="${1:-origin}"
PRIVATE_REMOTE="${2:-private}"

echo "=== Sync: Public → Private ==="

# Fetch both remotes
git fetch "$PUBLIC_REMOTE" --prune
git fetch "$PRIVATE_REMOTE" --prune

# Sync main branch
git checkout main
git pull "$PUBLIC_REMOTE" main
git push "$PRIVATE_REMOTE" main

# Sync brain-* branches
for branch in $(git branch -r | grep "$PUBLIC_REMOTE/brain-" | sed "s|$PUBLIC_REMOTE/||"); do
    echo "Syncing $branch"
    git checkout "$branch"
    git pull "$PUBLIC_REMOTE" "$branch"
    # Apply private config overlays if they exist
    if git show "$PRIVATE_REMOTE/$branch":config/overlay.yaml &>/dev/null; then
        git merge "$PRIVATE_REMOTE/$branch" --no-edit || true
    fi
    git push "$PRIVATE_REMOTE" "$branch"
done

# Return to main
git checkout main
echo "=== Sync complete ==="
```

### Triggering a Sync

- **Automatic**: A GitHub Actions / GitLab CI workflow runs the sync script on every push to `main` or `brain-*` branches in the public repo.
- **Manual**: Run `scripts/sync-upstream.sh` from the private repo clone after pulling the latest public changes.

### What Does NOT Sync

- Files listed in `.syncignore` (e.g., `secrets/*.age`, `config/production/*`).
- Any path containing `.secret` or `.private` in its name.
- Environment-specific overlays that would leak infrastructure details.

---

## cortex-profile.sh: Hermetic Project Profiles

`cortex-profile.sh` is the entry point for **hermetic project profiles** — self-contained environment definitions that isolate one project's toolchain, variables, and dependencies from another's.

### Structure

Each profile lives in `profiles/<name>/` and includes:

```
profiles/<name>/
├── cortex-profile.sh      # Sourced by the Hermes shell to set up the environment
├── .env                   # Project-specific environment variables (no secrets)
├── activate               # Activation hook
├── deactivate             # Deactivation hook
├── tools/                 # Local tool wrappers / pinned versions
└── README.md
```

### How It Works

```bash
# cortex-profile.sh — Hermetic project profile loader
# Source this in your shell or via Hermes' --profile flag

HERMES_PROFILE="${HERMES_PROFILE:-default}"
PROFILE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export HERMES_PROFILE_DIR="$PROFILE_DIR"
export PATH="$PROFILE_DIR/tools:$PATH"

# Load project environment (non-secret)
if [[ -f "$PROFILE_DIR/.env" ]]; then
    set -a
    source "$PROFILE_DIR/.env"
    set +a
fi

# Run activation hook
if [[ -f "$PROFILE_DIR/activate" ]]; then
    source "$PROFILE_DIR/activate"
fi

echo "Hermes profile [${HERMES_PROFILE}] loaded from ${PROFILE_DIR}"
```

### Activation

```bash
# Activate a profile explicitly
source profiles/my-project/cortex-profile.sh

# Or via Hermes CLI
hermes --profile my-project
```

### Hermetic Isolation

- Each profile sets `$PATH`, `$PYTHONPATH`, `$NODE_PATH`, and other environment variables **only for that session**.
- Profiles cannot leak variables into other profiles — the deactivation hook restores the prior environment.
- Tool versions are pinned per profile in `tools/`, avoiding global version conflicts.

---

## gbrain: Isolated Sources

**gbrain** ("grouped brain") is the source directory structure for all brain logic. Each subdirectory under `gbrain/` is a self-contained module that can be built and deployed independently.

### Directory Layout

```
gbrain/
├── agent/                  # Agent brain — decision-making and planning
│   ├── main.gbrain         # Entry point
│   ├── rules/              # Decision rules
│   └── tests/
├── tools/                  # Tool brain — defines tool interfaces and registries
│   ├── main.gbrain
│   ├── registries/         # Tool registry definitions
│   └── tests/
├── memory/                 # Memory brain — persistence and recall
│   ├── main.gbrain
│   ├── stores/             # Memory storage backends
│   └── tests/
└── cortex/                 # Core brain — Hermes Cortex integration
    ├── main.gbrain
    ├── profiles/           # Profile-aware cortex logic
    └── tests/
```

### Building a Brain

```bash
# Build all brains
hermes build-gbrain --all

# Build a specific brain
hermes build-gbrain gbrain/agent

# Output lands on brain-agent branch
```

### Key Properties

- **Isolated**: Each brain has its own dependency manifest and build pipeline. A change to `gbrain/tools` does not affect `gbrain/agent`.
- **Testable**: Each brain ships with its own test suite. CI runs tests per brain in parallel.
- **Deployable**: Built artifacts are pushed to `brain-*` branches and can be deployed independently via the registry.

---

## Directory Layout

Below is the full suggested layout for both repos.

### Public Repo (`hermes-cortex`)

```
hermes-cortex/
├── README.md
├── LICENSE                    # MIT
├── CONTRIBUTING.md
├── gbrain/                    # Isolated brain sources
│   ├── agent/
│   ├── tools/
│   ├── memory/
│   └── cortex/
├── profiles/                  # Hermetic project profiles
│   ├── default/
│   ├── staging/
│   └── production/
├── scripts/                   # Deploy and sync scripts
│   ├── sync-upstream.sh
│   ├── deploy-brain.sh
│   └── verify-profile.sh
├── docs/                      # Documentation
│   └── deploy-registry-pattern.md
├── tests/                     # Integration and E2E tests
├── .github/                   # CI/CD workflows
│   └── workflows/
│       ├── sync.yaml
│       ├── build.yaml
│       └── test.yaml
├── .gitignore
└── .syncignore                # Files excluded from private → public sync
```

### Private Repo (`hermes-cortex-private`)

```
hermes-cortex-private/
├── README.md
├── config/                    # Per-environment configuration
│   ├── staging.env
│   ├── production.env
│   └── overlay.yaml           # Overrides applied during sync
├── secrets/                   # Encrypted secrets (sops/age)
│   ├── staging.age
│   └── production.age
├── env/                       # Environment descriptors
│   ├── staging/
│   │   ├── terraform.tfvars
│   │   └── kustomization.yaml
│   └── production/
│       ├── terraform.tfvars
│       └── kustomization.yaml
├── profiles/                  # Profile overlays (secrets-aware)
│   └── production/
│       └── .env.encrypted
├── scripts/                   # Private deployment scripts
│   └── deploy.sh
├── .syncignore                # Mirror of public .syncignore
└── .gitignore
```

---

## Setup Guide

### 1. Create the Public Repository

```bash
mkdir hermes-cortex && cd hermes-cortex
git init
git remote add origin git@github.com:your-org/hermes-cortex.git
# Create initial structure as shown above
git add .
git commit -m "Initial public repo scaffold"
git push -u origin main
```

### 2. Create the Private Repository

```bash
mkdir hermes-cortex-private && cd hermes-cortex-private
git init
git remote add private git@github.com:your-org/hermes-cortex-private.git
# Create private structure as shown above
git add .
git commit -m "Initial private repo scaffold"
git push -u private main
```

### 3. Link the Repositories

In the private repo clone, add the public repo as a remote:

```bash
cd hermes-cortex-private
git remote add public git@github.com:your-org/hermes-cortex.git
git fetch public
git merge public/main --allow-unrelated-histories -m "Sync initial public state"
git push private main
```

### 4. Configure Sync Workflow

Copy `.github/workflows/sync.yaml` into the public repo:

```yaml
# .github/workflows/sync.yaml
name: Sync to Private Repo

on:
  push:
    branches:
      - main
      - brain-*

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Sync upstream
        run: |
          git remote add private https://x-access-token:${{ secrets.SYNC_TOKEN }}@github.com/your-org/hermes-cortex-private.git
          bash scripts/sync-upstream.sh origin private
```

### 5. Set Up Brain Branches

```bash
# From the public repo
git checkout -b brain-agent        # Scaffold from gbrain/agent build
git checkout -b brain-tools        # Scaffold from gbrain/tools build
git checkout -b brain-memory       # Scaffold from gbrain/memory build
git checkout main
```

---

## Operations Guide

### Daily Workflow

1. **Develop** brain logic in `gbrain/` on a `feature/*` branch.
2. **Build** the brain locally: `hermes build-gbrain gbrain/<name>`.
3. **Push** the feature branch and open a PR against `develop`.
4. **CI** builds the brain artifact and pushes it to the corresponding `brain-*` branch.
5. **Merge** `develop` → `main` when ready.
6. **Sync** triggers automatically, pushing `main` and `brain-*` branches to the private repo.
7. **Deploy** from the private repo using `scripts/deploy.sh`.

### Deploying a Brain

```bash
# On the private repo
./scripts/deploy.sh \
    --brain agent \
    --env production \
    --version v1.2.3
```

The deploy script:
1. Checks out the matching `brain-agent` branch.
2. Applies the environment config overlay from `config/overlay.yaml`.
3. Decrypts secrets from `secrets/production.age`.
4. Runs the deployment (e.g., push to a registry, restart services).
5. Tags the deployment: `deploy-agent-production-v1.2.3`.

### Verifying a Profile

```bash
hermes --profile staging verify-profile
```

This runs the `verify-profile.sh` script, which checks:
- All required environment variables are set.
- Required tools are present in `$PATH`.
- The private repo remote is reachable.
- Secrets can be decrypted (if age/sops key is available).

---

## Security Considerations

| Concern | Mitigation |
|---|---|
| **Secret leakage via sync** | `.syncignore` blocks secret files; CI scans for accidental secrets before pushing. |
| **Unauthorized access to private repo** | Strict GitHub/GitLab access controls; SSH key rotation; branch protection rules. |
| **Sync token compromise** | Use a short-lived deploy token with minimal scope; rotate regularly. |
| **Brain branch tampering** | Branch protection on `brain-*` branches; signed commits required. |
| **Profile injection** | Hermetic profiles are sourced with `set -a` / `set +a`; deactivation hooks restore state. |
| **Supply chain** | Pin tool versions in profile `tools/`; verify checksums on build artifacts. |

### `.syncignore` Template

```gitignore
# .syncignore — Files that must NOT flow from public to private
secrets/
*.age
*.sops
.env.encrypted
config/production/
config/staging/
**/*.secret
**/*.private
```

---

## Related Resources

- [Hermes Cortex Documentation](https://hermes-agent.nousresearch.com/docs)
- [SOPS — Mozilla's Secrets Ops](https://github.com/mozilla/sops)
- [age — Simple modern file encryption](https://age-encryption.org/)

---

## FAQ

**Q: Why private → public sync and not the reverse?**
A: The private repo contains secrets that must never enter the public repo. Syncing public→private and then stripping secrets is error-prone. Private→public ensures only sanitized content reaches the open-source repo.

**Q: Can I use this pattern with a mono-repo?**
A: Yes — use `.syncignore` and branch-permissions to simulate the same isolation within a single repository. However, the multi-repo approach is cleaner for MIT + proprietary separation.

**Q: How do I rotate the sync token?**
A: Generate a new fine-grained access token with `contents:write` scope on the private repo, update the `SYNC_TOKEN` secret in the public repo's CI settings, and revoke the old token.

**Q: What if a brain branch diverges between repos?**
A: The sync script uses `--no-edit` merge commits for config overlays. If a conflict occurs, the sync workflow fails and alerts. Resolve by manually merging in the private repo and pushing upstream.
