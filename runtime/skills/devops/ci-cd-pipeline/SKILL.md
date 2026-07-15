---
name: ci-cd-pipeline
version: 1.0.0
category: devops
description: >
  CI/CD pipeline configuration patterns: GitHub Actions, multi-stage
  builds, testing matrices, deployment workflows, secrets management,
  caching strategies, and pipeline optimization.
tags: [ci, cd, github-actions, deployment, automation]
related_skills: [github-pr-workflow, test-driven-development, nextjs-docker-multistage, nginx-web-app-deployment]
---

# CI/CD Pipeline Patterns

## When to Use

Load this skill when:
- Setting up CI for a new project
- Adding deployment automation
- Optimizing slow CI pipelines
- Reviewing pipeline configurations
- Debugging a failing CI run

## Core Principles

### 1. Pipeline Structure

Every CI/CD pipeline follows this flow:

```
[Commit/Push] → [Lint] → [Test] → [Build] → [Deploy/staging] → [Deploy/prod]
                                                          ↕
                                                    [Integration tests]
```

**Separation of concerns:** Each phase is an independent job. A phase failure
stops downstream phases but doesn't block parallel phases.

### 2. GitHub Actions — Standard Layout

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  PYTHON_VERSION: "3.12"
  NODE_VERSION: "20"

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - run: pip install ruff
      - run: ruff check .

  test:
    needs: lint
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: testpass
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - name: Cache dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements*.txt') }}
          restore-keys: |
            ${{ runner.os }}-pip-
      - run: pip install -r requirements-dev.txt
      - run: pytest --cov=./ --cov-report=xml
      - uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t myapp:${{ github.sha }} .
      - run: docker tag myapp:${{ github.sha }} myapp:latest

  deploy-staging:
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Deploy to staging
        run: |
          echo "Deploying ${{ github.sha }} to staging..."
          # ssh, rsync, or kubectl commands

  deploy-production:
    needs: deploy-staging
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    environment: production
    concurrency: production-deploy  # Prevents concurrent deploys
    steps:
      - name: Deploy to production
        run: |
          echo "Deploying ${{ github.sha }} to production..."
```

### 3. Caching Strategy

Cache dependencies, not the full environment:

```yaml
- name: Cache pip
  uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements*.txt') }}
    restore-keys: |
      ${{ runner.os }}-pip-

- name: Cache npm
  uses: actions/cache@v4
  with:
    path: ~/.npm
    key: ${{ runner.os }}-npm-${{ hashFiles('**/package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-npm-

- name: Cache Docker layers
  uses: actions/cache@v4
  with:
    path: /tmp/.buildx-cache
    key: ${{ runner.os }}-buildx-${{ github.sha }}
    restore-keys: |
      ${{ runner.os }}-buildx-
```

**Cache key rule:** Always include a hash of the dependency manifest in the
primary key. Use `restore-keys` for partial fallback.

### 4. Testing Matrix

Test across multiple versions and OS:

```yaml
strategy:
  matrix:
    python-version: ["3.11", "3.12", "3.13"]
    os: [ubuntu-latest, macos-latest]
  fail-fast: false  # Don't cancel other versions on one failure

steps:
  - uses: actions/setup-python@v5
    with:
      python-version: ${{ matrix.python-version }}
  - run: pytest
```

**When to use matrices:**
- ✅ Library that needs compatibility across versions
- ✅ Project used on multiple OS
- ❌ Single-service app deployed to one platform (use one version, save CI time)
- ❌ When matrix multiplies CI time 6x for no benefit

### 5. Deployment Environments

```yaml
environments:
  staging:
    url: https://staging.example.com
    protection_rules:
      - reviewers: [team-leads]
  production:
    url: https://example.com
    protection_rules:
      - reviewers: [deployment-managers]
      - wait_timer: 5  # 5-minute manual approval window
```

**Environment rules:**
- Staging deploys automatically from `main`
- Production requires approval (manual gate)
- Production has concurrency protection (one deploy at a time)
- Each environment has its own secrets scope

### 6. Secrets Management

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Deploy
        env:
          SSH_KEY: ${{ secrets.DEPLOY_SSH_KEY }}
          DB_URL: ${{ secrets.PRODUCTION_DB_URL }}
        run: |
          # Use env vars, never echo them
          rsync -e "ssh -i /dev/stdin" ./dist/ user@server:/app/
```

**Rules:**
- Store secrets in GitHub Secrets, not in code or config files
- Use environment-scoped secrets (staging vs production)
- Never echo or log secret values
- Mask secrets in CI output automatically (GitHub does this)
- Rotate secrets regularly; use a secrets manager for production

### 7. Conditional Execution

```yaml
# Only run deploy when pushing to main (not on PR)
deploy:
  if: github.ref == 'refs/heads/main' && github.event_name == 'push'

# Only run docs job when docs change
docs:
  if: contains(github.event.head_commit.message, '[docs]')

# Skip CI for trivial changes
on:
  push:
    paths-ignore:
      - '**.md'
      - 'docs/**'
```

### 8. Concurrency Control

Prevent race conditions on deployments:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true  # Cancel previous run for same branch
```

### 9. Pipeline Monitoring

```yaml
# Notification on failure
- name: Notify on failure
  if: failure()
  uses: slackapi/slack-github-action@v2
  with:
    webhook: ${{ secrets.SLACK_WEBHOOK }}
    webhook-type: incoming-webhook
    payload: |
      {
        "text": "❌ CI failed: ${{ github.repository }}@${{ github.sha }}"
      }
```

### 10. Docker Multi-Stage Build

```dockerfile
# Build stage
FROM python:3.12-slim AS builder
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Runtime stage
FROM python:3.12-slim
COPY --from=builder /root/.local /root/.local
COPY . /app
WORKDIR /app
ENV PATH=/root/.local/bin:$PATH
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**See also:** `nextjs-docker-multistage` skill for Node/Next.js specifics.

## Pipeline Optimization

| Issue | Fix |
|-------|-----|
| Pipeline takes 20+ minutes | Parallelize independent jobs, cache dependencies |
| Flaky tests | Tag as `integration`, run separately from `unit` |
| Deploying on every commit | Only deploy when `main` branch push, not PR |
| Test matrix runs 12 jobs | Reduce to relevant versions only |
| Secrets in logs | Use `::add-mask::` or ensure no echo of secrets |

## Anti-Patterns

| Anti-pattern | Why it's wrong |
|-------------|----------------|
| Deploying from feature branches | No review gate, bypasses CI |
| One giant job | Can't see which phase failed, slow |
| No caching | Every CI run installs deps from scratch (3-5 min waste) |
| Hardcoded secrets | Visible to anyone with repo access |
| `latest` tag for deploys | Can't roll back to a specific version |
| Deploy without integration tests | Broken on prod despite CI passing |
| Matrix with `fail-fast: true` | Hides compatibility issues in later versions |

## Verification

```yaml
# Run the CI pipeline locally (act)
# https://github.com/nektos/act
# Usage: act -j test
act -j lint
act -j test --secret-file .secrets
```
