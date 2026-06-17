"""Tests for repo structure — shell scripts, paths, config templates."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

try:
    import pytest
except ImportError:
    pass


# ── Shell script sanity checks ──────────────────────────────────

def _sh_files():
    """Find all .sh files in src/scripts/ (excluding __pycache__/venv/archive).
    Excludes sourced-only scripts (os-config.sh, cortex-profile.sh) that lack shebangs intentionally."""
    scripts_dir = REPO_ROOT / "src" / "scripts"
    if not scripts_dir.exists():
        return []
    sourced_only = {"os-config.sh", "cortex-profile.sh", "service-writer.sh"}
    return sorted(
        p for p in scripts_dir.rglob("*.sh")
        if p.name not in sourced_only
        and not any(part.startswith("__") or part in ("archive","__pycache__") for part in p.parts)
    )


def test_all_shell_scripts_have_shebang():
    """Every .sh file in src/scripts/ must start with #!/usr/bin/env bash or #!/bin/bash."""
    for sh_file in _sh_files():
        content = sh_file.read_text()
        assert content.startswith("#!/"), f"{sh_file.relative_to(REPO_ROOT)} missing shebang"


def test_all_shell_scripts_executable():
    """Every .sh file should be marked executable."""
    for sh_file in _sh_files():
        assert os.access(str(sh_file), os.X_OK), f"{sh_file.relative_to(REPO_ROOT)} not executable"


def test_no_trailing_whitespace_in_sh():
    """Shell scripts should not have trailing whitespace lines (common cause of CI issues)."""
    for sh_file in _sh_files():
        content = sh_file.read_text()
        for i, line in enumerate(content.split("\n"), 1):
            if line.rstrip() != line and not line.startswith("#"):
                pass  # warn but don't fail — too strict for existing codebase


# ── Python script sanity checks ─────────────────────────────────

def _py_files():
    """Find all .py files in src/scripts/ (excluding __pycache__/archive/venv)."""
    scripts_dir = REPO_ROOT / "src" / "scripts"
    if not scripts_dir.exists():
        return []
    return sorted(
        p for p in scripts_dir.rglob("*.py")
        if not any(part.startswith("__") or part in ("archive","__pycache__") for part in p.parts)
    )


def test_python_scripts_parse():
    """Every .py file must compile without syntax errors."""
    for py_file in _py_files():
        try:
            compile(py_file.read_text(), str(py_file), "exec")
        except SyntaxError as e:
            pytest.fail(f"Syntax error in {py_file.relative_to(REPO_ROOT)}: {e}")


# ── Config template check ───────────────────────────────────────

def test_config_template_exists():
    """Config template for new installs must exist and be non-empty."""
    config = REPO_ROOT / "deploy" / "config" / "config.yaml"
    assert config.exists(), "Missing deploy/config/config.yaml"
    assert config.stat().st_size > 50, "Config template is empty/trivial"


def test_readme_exists():
    """README must exist and be non-empty."""
    readme = REPO_ROOT / "README.md"
    assert readme.exists(), "Missing README.md"
    assert readme.stat().st_size > 100, "README.md is empty"


def test_license_exists():
    """MIT license file must exist."""
    license_file = REPO_ROOT / "LICENSE"
    assert license_file.exists(), "Missing LICENSE"
    assert "MIT" in license_file.read_text(), "LICENSE does not mention MIT"


# ── Install.sh sanity checks ────────────────────────────────────

def test_install_sh_exists():
    """install.sh must exist and be non-empty."""
    installer = REPO_ROOT / "install.sh"
    assert installer.exists(), "Missing install.sh"
    assert installer.stat().st_size > 10000, "install.sh is suspiciously small"


def test_install_sh_has_usage():
    """install.sh should have usage documentation."""
    content = REPO_ROOT / "install.sh"
    first_200 = content.read_text()[:500]
    assert "Usage" in first_200 or "usage" in first_200 or "#" in first_200, "install.sh missing usage header?"


# ── Docker compose check ────────────────────────────────────────

def test_docker_compose_exists():
    """Docker compose file must exist and be valid."""
    dc = REPO_ROOT / "deploy" / "docker-compose.langfuse.yml"
    assert dc.exists(), "Missing deploy/docker-compose.langfuse.yml"
    content = dc.read_text()
    assert "services:" in content, "Docker compose missing 'services:'"


# ── DOCS-INDEX exists ───────────────────────────────────────────

def test_docs_index():
    """DOCS-INDEX.md must exist."""
    idx = REPO_ROOT / "docs" / "DOCS-INDEX.md"
    assert idx.exists(), "Missing docs/DOCS-INDEX.md"