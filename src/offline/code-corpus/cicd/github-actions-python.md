---
language: yaml
tags: [github-actions, ci, cd, pipeline, python]
title: GitHub Actions for Python Projects
description: Complete GitHub Actions CI/CD pipelines for Python including test and lint pipelines, matrix builds, dependency caching, PyPI publishing, and secrets management
source: pattern
---

# GitHub Actions for Python Projects

## Basic Test and Lint Pipeline

```yaml
name: Python CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      
      - name: Lint with flake8
        run: |
          flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
          flake8 . --count --exit-zero --max-complexity=10 --max-line-length=100 --statistics
      
      - name: Check formatting with black
        run: |
          black --check --diff .
      
      - name: Lint with pylint
        run: |
          pylint src/ --fail-under=8.0
      
      - name: Type check with mypy
        run: |
          mypy src/ --strict
      
      - name: Test with pytest
        run: |
          python -m pytest tests/ -v --cov=src/ --cov-report=term-missing --cov-report=xml
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
          fail_ci_if_error: false
```

## Matrix Builds for Multiple Python Versions

```yaml
name: Python Matrix CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        python-version: ['3.9', '3.10', '3.11', '3.12']
        os: [ubuntu-latest, windows-latest, macos-latest]
        exclude:
          # Skip Windows on Python 3.12 for faster CI
          - os: windows-latest
            python-version: '3.12'
        include:
          # Add an extra job for the latest versions
          - os: ubuntu-latest
            python-version: '3.12'
            experimental: true
    
    continue-on-error: ${{ matrix.experimental || false }}
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: 'pip'
      
      - name: Display Python version
        run: python -c "import sys; print(sys.version)"
      
      - name: Install system dependencies (Linux)
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install -y libxml2-dev libxslt1-dev
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"
      
      - name: Run tests
        run: |
          python -m pytest tests/ -v --cov=src/ --cov-report=xml -n auto
      
      - name: Upload coverage
        if: runner.os == 'Linux' && matrix.python-version == '3.11'
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
```

## Caching Dependencies

```yaml
name: Python CI with Caching

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Cache pip dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements*.txt', '**/pyproject.toml', '**/setup.cfg') }}
          restore-keys: |
            ${{ runner.os }}-pip-
      
      - name: Cache pre-commit hooks
        uses: actions/cache@v4
        with:
          path: ~/.cache/pre-commit
          key: ${{ runner.os }}-pre-commit-${{ hashFiles('.pre-commit-config.yaml') }}
          restore-keys: |
            ${{ runner.os }}-pre-commit-
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      
      - name: Run pre-commit hooks
        run: |
          pip install pre-commit
          pre-commit run --all-files || echo "Pre-commit checks completed"
      
      - name: Test with pytest
        run: |
          python -m pytest tests/ -v --cov=src/
```

## Publish to PyPI

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]
  workflow_dispatch:
    inputs:
      environment:
        description: 'Environment to publish to'
        required: true
        default: 'testpypi'
        type: choice
        options:
          - testpypi
          - pypi

jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.environment || 'pypi' }}
    permissions:
      id-token: write  # Required for trusted publishing
    
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install build tools
        run: |
          python -m pip install --upgrade pip
          pip install build twine
      
      - name: Build distribution packages
        run: |
          python -m build
      
      - name: Verify distribution
        run: |
          twine check dist/*
      
      - name: Publish to Test PyPI
        if: github.event.inputs.environment == 'testpypi' || github.event_name == 'release'
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/
          skip-existing: true
      
      - name: Publish to PyPI
        if: github.event.inputs.environment == 'pypi' || github.event_name == 'release'
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://upload.pypi.org/legacy/
```

## Secrets Management

```yaml
name: Deploy with Secrets

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      
      - name: Decrypt secrets
        run: |
          # Decrypt using GPG key stored as a GitHub secret
          echo "${{ secrets.GPG_PASSPHRASE }}" | gpg --batch --yes --passphrase-fd 0 \
            --decrypt secrets.tar.gpg > secrets.tar
          tar -xvf secrets.tar
        env:
          GPG_PASSPHRASE: ${{ secrets.GPG_PASSPHRASE }}
      
      - name: Run deployment
        run: |
          python deploy.py
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          AWS_REGION: us-east-1
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          API_KEY: ${{ secrets.API_KEY }}
          SENTRY_DSN: ${{ secrets.SENTRY_DSN }}
```

## Full CI/CD Pipeline with Docker

```yaml
name: Python Full CI/CD

on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      
      - name: Run linters
        run: |
          black --check --diff src/ tests/
          isort --check-only --diff src/ tests/
          flake8 src/ tests/
          mypy src/
  
  test:
    needs: lint
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']
    
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: testdb
          POSTGRES_USER: testuser
          POSTGRES_PASSWORD: testpass
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      redis:
        image: redis:7
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      
      - name: Run tests
        run: |
          python -m pytest tests/ -v --cov=src/ --cov-report=xml -n auto
        env:
          DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb
          REDIS_URL: redis://localhost:6379/0
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
  
  build-and-push:
    needs: test
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Log in to registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha
      
      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

## Reusable Workflow

```yaml
# .github/workflows/python-ci-reusable.yml
name: Python CI Reusable

on:
  workflow_call:
    inputs:
      python-version:
        required: false
        type: string
        default: '3.11'
      run-lint:
        required: false
        type: boolean
        default: true
      run-type-check:
        required: false
        type: boolean
        default: true
      upload-coverage:
        required: false
        type: boolean
        default: false
      test-command:
        required: false
        type: string
        default: 'python -m pytest tests/ -v --cov=src/'
    secrets:
      CODECOV_TOKEN:
        required: false

jobs:
  ci:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ inputs.python-version }}
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"
      
      - name: Lint
        if: inputs.run-lint
        run: |
          flake8 src/ tests/
          black --check --diff src/ tests/
      
      - name: Type check
        if: inputs.run-type-check
        run: |
          mypy src/
      
      - name: Test
        run: ${{ inputs.test-command }}
      
      - name: Upload coverage
        if: inputs.upload-coverage
        uses: codecov/codecov-action@v4
        with:
          token: ${{ secrets.CODECOV_TOKEN }}


# Usage in a project:
# .github/workflows/my-project-ci.yml
# name: My Project CI
#
# on:
#   push:
#     branches: [main]
#   pull_request:
#     branches: [main]
#
# jobs:
#   ci:
#     uses: ./.github/workflows/python-ci-reusable.yml
#     with:
#       python-version: '3.11'
#       run-lint: true
#       upload-coverage: true
#     secrets:
#       CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}
```

## Pre-commit Configuration (Companion)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-json
      - id: check-toml
      - id: detect-private-key

  - repo: https://github.com/psf/black
    rev: 24.4.2
    hooks:
      - id: black
        language_version: python3.11

  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
        name: isort (python)

  - repo: https://github.com/pycqa/flake8
    rev: 7.1.0
    hooks:
      - id: flake8
        additional_dependencies: [flake8-docstrings]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: [types-requests]
```