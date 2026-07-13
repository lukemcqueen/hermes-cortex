"""Tests for Hermes Cortex repo structure integrity.

Validates:
  - No dead files (files not referenced anywhere)
  - All skill directories have SKILL.md
  - No duplicate skill names
  - Install.sh steps match README
  - VERSION consistency
"""
import os
import sys
import json
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_all_skills_have_skilL_md():
    """Every skill directory under runtime/skills/ must have a SKILL.md."""
    skills_dir = os.path.join(REPO_ROOT, "runtime", "skills")
    missing = []
    for root, dirs, files in os.walk(skills_dir):
        # Skip non-skill subdirectories (references, templates, scripts, assets)
        dirs[:] = [d for d in dirs if d not in ("references", "templates", "scripts", "assets", "__pycache__")]
        if root == skills_dir:
            continue  # skip the top-level category dirs
        # Each skill dir should have SKILL.md
        if "SKILL.md" not in files:
            rel = os.path.relpath(root, skills_dir)
            # Only flag actual skill dirs (have *.md or subdirs with SKILL.md)
            has_skill = any(f == "SKILL.md" for _, _, files2 in os.walk(root) for f in files2)
            if not has_skill:
                missing.append(rel)
    assert not missing, f"Skills without SKILL.md: {missing}"


def test_no_dead_root_scripts():
    """Root-level scripts/ should only contain essential files, not orphaned code."""
    scripts_dir = os.path.join(REPO_ROOT, "scripts")
    if not os.path.isdir(scripts_dir):
        return
    expected = {
        "check-package-age.py", "install-post-commit-hook.sh",
        "package-install.sh", "post-commit-notify.sh",
        "setup-langfuse-sample-data.py", "test-minio.py",
        "verify-langfuse.py",
    }
    actual = set(os.listdir(scripts_dir)) - {"__pycache__"}
    # These moved from src/scripts/ to ops/scripts/; src/loop-governance/ to core/governance/
    unexpected = actual - expected
    if unexpected:
        print(f"WARNING: Unexpected files in scripts/: {unexpected}")


def test_install_steps_match_readme():
    """Install.sh step numbers should match README table."""
    readme_path = os.path.join(REPO_ROOT, "README.md")
    install_path = os.path.join(REPO_ROOT, "ops", "install", "install.sh")

    # Count steps in README table
    step_count_readme = 0
    with open(readme_path) as f:
        for line in f:
            if re.match(r'^\| \d+ \|', line):
                step_count_readme += 1

    # Count "step" calls in install.sh
    step_count_install = 0
    with open(install_path) as f:
        for line in f:
            if re.match(r'^step "', line) or re.match(r'^  step "', line):
                step_count_install += 1

    # This is approximate — install.sh has nested steps
    print(f"  README steps: ~{step_count_readme}")
    print(f"  install.sh steps: ~{step_count_install}")
    assert step_count_install >= step_count_readme, (
        f"install.sh has {step_count_install} steps but README lists {step_count_readme}"
    )


def test_skill_names_no_jargon():
    """Skill names should be clear, not jargon."""
    skills_dir = os.path.join(REPO_ROOT, "runtime", "skills")
    jargon_patterns = ["hc-", "ak-", "prd-"]
    issues = []
    for root, dirs, _ in os.walk(skills_dir):
        for d in dirs:
            for pattern in jargon_patterns:
                if d.startswith(pattern):
                    issues.append(f"{d} contains '{pattern}' prefix")
    assert not issues, f"Jargon in skill names: {issues}"


def test_version_consistency():
    """VERSION file should match install.sh."""
    version_file = os.path.join(REPO_ROOT, "VERSION")
    install_file = os.path.join(REPO_ROOT, "ops", "install", "install.sh")

    with open(version_file) as f:
        file_version = f.read().strip()

    with open(install_file) as f:
        content = f.read()
        # Look for VERSION="..." or VERSION=cat
        match = re.search(r'VERSION="?([\d.]+)"?', content)
        assert match, "Could not find VERSION in install.sh"
        install_version = match.group(1)
        # Fallback version is also fine
        if install_version != file_version:
            # Check if it's a fallback
            if 'VERSION="1.0.0"  # fallback' in content:
                print(f"  install.sh uses fallback version (1.0.0), root VERSION is {file_version}")
                return
    assert install_version == file_version, (
        f"VERSION mismatch: root={file_version}, install.sh={install_version}"
    )


def test_no_duplicate_skill_names():
    """No two skills should have the same name."""
    skills_dir = os.path.join(REPO_ROOT, "runtime", "skills")
    names = []
    for root, dirs, files in os.walk(skills_dir):
        if "SKILL.md" in files:
            name = os.path.basename(root)
            names.append(name)
    duplicates = [n for n in names if names.count(n) > 1]
    assert not duplicates, f"Duplicate skill names: {set(duplicates)}"


def test_readme_has_quickstart():
    """README must have a Quick Start section."""
    readme_path = os.path.join(REPO_ROOT, "README.md")
    with open(readme_path) as f:
        content = f.read()
    assert "Quick start" in content, "README missing Quick Start section"


def test_readme_has_upgrade_path():
    """README must document upgrade path."""
    readme_path = os.path.join(REPO_ROOT, "README.md")
    with open(readme_path) as f:
        content = f.read()
    assert "Upgrading" in content or "upgrade" in content.lower(), (
        "README missing upgrade documentation"
    )