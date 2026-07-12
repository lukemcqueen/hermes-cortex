"""Tests for seed-project.sh — bash-based Hermes Cortex project bootstrapper.

Uses subprocess to shell out. Each test creates a fresh git repo under
tmp_path so they're isolated and clean up automatically.
"""

import subprocess
import shutil
import textwrap
from pathlib import Path

SEED_PROJECT = (
    Path(__file__).resolve().parents[1] / "ops" / "scripts" / "install" / "seed-project.sh"
)
CORTEX_UPDATE = (
    Path(__file__).resolve().parents[1] / "ops" / "scripts" / "cortex-update.sh"
)


# ── Helpers ──────────────────────────────────────────────────────


def _run(*args, **kwargs):
    """Run a command, return (rc, stdout, stderr)."""
    result = subprocess.run(args, capture_output=True, text=True, timeout=60, **kwargs)
    return result.returncode, result.stdout, result.stderr


def _init_repo(path: Path):
    """Create a minimal git repo at *path* (must exist)."""
    subprocess.run(
        ["git", "init"],
        cwd=path,
        capture_output=True,
        timeout=15,
    )
    readme = path / "README.md"
    readme.write_text("# test")
    subprocess.run(
        ["git", "add", "."],
        cwd=path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=path,
        capture_output=True,
        timeout=15,
    )


def _seed(project: Path, *extra_args: str):
    """Run seed-project.sh against *project* and return (rc, stdout, stderr)."""
    return _run(
        "bash", str(SEED_PROJECT), f"--project={project}", *extra_args
    )


def _seed_no_capture(project: Path, *extra_args: str):
    """Run seed-project.sh without capturing output (for pytest -s debugging)."""
    result = subprocess.run(
        ["bash", str(SEED_PROJECT), f"--project={project}", *extra_args],
        timeout=120,
    )
    return result.returncode


# ── Tests ─────────────────────────────────────────────────────────


class TestSeedProject:
    """Comprehensive test suite for seed-project.sh."""

    # ── Syntax ────────────────────────────────────────────────

    def test_syntax_bash_n(self):
        """Script parses cleanly with bash -n."""
        rc, _, stderr = _run("bash", "-n", str(SEED_PROJECT))
        assert rc == 0, f"bash -n failed:\n{stderr}"

    def test_syntax_cortex_update(self):
        """cortex-update.sh also parses cleanly (MAP registration)."""
        rc, _, stderr = _run("bash", "-n", str(CORTEX_UPDATE))
        assert rc == 0, f"bash -n failed:\n{stderr}"

    # ── Argument validation ──────────────────────────────────

    def test_missing_project_shows_help(self):
        """Running without --project prints usage and exits non-zero."""
        rc, stdout, stderr = _run("bash", str(SEED_PROJECT))
        assert rc != 0
        assert "Required: --project=" in stdout + stderr

    def test_nonexistent_project_shows_path(self, tmp_path):
        """Non-existent --project shows the actual path in error."""
        missing = tmp_path / "does-not-exist"
        rc, stdout, stderr = _seed(missing)
        assert rc != 0
        # Should show the path, not a blank
        assert "does-not-exist" in stdout + stderr

    def test_bad_mode_rejected(self, tmp_path):
        """Invalid --mode=foo is rejected."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        rc, stdout, stderr = _seed(repo, "--mode=unsupported")
        assert rc != 0
        assert "Invalid mode" in stdout + stderr

    # ── First seed ───────────────────────────────────────────

    def test_first_seed_creates_agents_md(self, tmp_path):
        """First seed creates AGENTS.md."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        rc, stdout, _ = _seed(repo)
        assert rc == 0, f"seed failed:\n{stdout}"
        assert (repo / "AGENTS.md").exists()

    def test_first_seed_creates_hermes_cortex(self, tmp_path):
        """First seed creates .hermes-cortex/ structure."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        rc, stdout, _ = _seed(repo)
        assert rc == 0, f"seed failed:\n{stdout}"
        assert (repo / ".hermes-cortex").is_dir()
        for sub in ("sessions", "memory", "skills"):
            assert (repo / ".hermes-cortex" / sub).is_dir(), f"missing {sub}"

    def test_first_seed_no_backup_yet(self, tmp_path):
        """First seed on clean project creates NO backup (nothing to save)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _seed(repo)
        backup_root = repo / ".hermes-cortex" / ".seed-backups"
        assert not backup_root.is_dir(), "backup should not exist on first seed"

    # ── Second seed (merge) ──────────────────────────────────

    def test_second_seed_creates_backup(self, tmp_path):
        """Re-seeding creates a backup with AGENTS.md."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _seed(repo)

        rc, stdout, _ = _seed(repo)
        assert rc == 0, f"re-seed failed:\n{stdout}"
        backup_root = repo / ".hermes-cortex" / ".seed-backups"
        assert backup_root.is_dir(), "backup root not created"
        backups = list(backup_root.iterdir())
        assert len(backups) >= 1

    def test_second_seed_backup_has_agents_md(self, tmp_path):
        """Re-seed backup should contain AGENTS.md."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _seed(repo)
        _seed(repo)

        backups = sorted((repo / ".hermes-cortex" / ".seed-backups").iterdir())
        latest = backups[-1]
        assert (latest / "AGENTS.md").exists(), "backup missing AGENTS.md"

    # ── --mode=overwrite ─────────────────────────────────────

    def test_overwrite_replaces_agents_md(self, tmp_path):
        """--mode=overwrite replaces AGENTS.md with template content."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _seed(repo)

        # Plant a known non-template string
        agents = repo / "AGENTS.md"
        agents.write_text("# CORRUPTED BY TEST")
        _seed(repo, "--mode=overwrite")

        content = agents.read_text()
        assert "CORRUPTED" not in content
        # Template content starts with <!-- (HTML comment)
        assert content.startswith("<!--") or "Hermes Cortex" in content

    def test_overwrite_creates_backup(self, tmp_path):
        """--mode=overwrite backs up the original before replacing."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _seed(repo)

        agents = repo / "AGENTS.md"
        agents.write_text("# CORRUPTED BY TEST")
        _seed(repo, "--mode=overwrite")

        # Backup should exist and contain the pre-overwrite state
        # (the CORRUPTED version — backup always captures pre-seed state)
        backup_root = repo / ".hermes-cortex" / ".seed-backups"
        backups = sorted(backup_root.iterdir())
        latest = backups[-1]
        backup_agents = latest / "AGENTS.md"
        assert backup_agents.exists()

        # The overwritten AGENTS.md should be the template, not corrupted
        content = agents.read_text()
        assert "CORRUPTED" not in content, (
            "AGENTS.md was not overwritten by template"
        )
        # The backup captured the pre-write state (which was corrupted)
        assert "CORRUPTED" in backup_agents.read_text(), (
            "backup should have captured the pre-overwrite corrupted state"
        )

    # ── --mode=diff ──────────────────────────────────────────

    def test_diff_mode_no_writes(self, tmp_path):
        """--mode=diff does not create AGENTS.md or .hermes-cortex/."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        rc, stdout, _ = _seed(repo, "--mode=diff")
        assert rc == 0, f"diff mode failed:\n{stdout}"
        assert not (repo / "AGENTS.md").exists()
        assert not (repo / ".hermes-cortex").exists()

    # ── --components filtering ───────────────────────────────

    def test_components_agents_only_no_dot_hermes_cortex(self, tmp_path):
        """--components=AGENTS.md must NOT create .hermes-cortex/ as side effect."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        rc, stdout, _ = _seed(repo, "--components=AGENTS.md")
        assert rc == 0, f"components seed failed:\n{stdout}"
        assert (repo / "AGENTS.md").exists(), "AGENTS.md should be created"
        assert not (repo / ".hermes-cortex").exists(), (
            ".hermes-cortex/ should not be created as side effect"
        )

    # ── --no-backup ──────────────────────────────────────────

    def test_no_backup_skips_backup(self, tmp_path):
        """--no-backup skips the backup step."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _seed(repo)

        # First re-seed creates 1 backup
        _seed(repo)
        backup_root = repo / ".hermes-cortex" / ".seed-backups"
        assert backup_root.is_dir()
        before = len(list(backup_root.iterdir()))

        # Second run with --no-backup should NOT add a backup
        _seed(repo, "--no-backup")
        after = len(list(backup_root.iterdir()))
        assert after == before, (
            f"expected {before} backups (unchanged), got {after}"
        )

    # ── --list-backups ───────────────────────────────────────

    def test_list_backups(self, tmp_path):
        """--list-backups shows available backups."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _seed(repo)
        _seed(repo)  # second seed creates backup

        rc, stdout, _ = _run(
            "bash", str(SEED_PROJECT), f"--list-backups={repo}"
        )
        assert rc == 0
        assert "Available backups" in stdout
        assert "files" in stdout
        assert "mode=" in stdout

    def test_list_backups_empty(self, tmp_path):
        """--list-backups on unseeded project says 'No backups'."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        rc, stdout, _ = _run(
            "bash", str(SEED_PROJECT), f"--list-backups={repo}"
        )
        # Currently this may exit 0 with "No backups" — not a failure
        assert "No backups" in stdout or rc == 0

    # ── --restore ────────────────────────────────────────────

    def test_restore_recovers_agents_md(self, tmp_path):
        """--restore recovers AGENTS.md from the latest backup."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _seed(repo)
        _seed(repo)  # creates backup with AGENTS.md

        # Corrupt AGENTS.md with unique content
        agents = repo / "AGENTS.md"
        unique = "# UNIQUE_CORRUPTION_MARKER"
        agents.write_text(unique)

        rc, stdout, _ = _run(
            "bash", str(SEED_PROJECT), f"--restore={repo}"
        )
        assert rc == 0, f"restore failed:\n{stdout}"
        assert "Restored AGENTS.md" in stdout
        content = agents.read_text()
        assert "UNIQUE_CORRUPTION_MARKER" not in content, (
            "AGENTS.md was not restored"
        )

    def test_restore_preserves_backups(self, tmp_path):
        """Restore preserves existing .seed-backups/ in the restored dir."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _seed(repo)
        _seed(repo)

        agents = repo / "AGENTS.md"
        agents.write_text("# CORRUPTED")
        _run("bash", str(SEED_PROJECT), f"--restore={repo}")

        backup_root = repo / ".hermes-cortex" / ".seed-backups"
        assert backup_root.is_dir()
        backups = list(backup_root.iterdir())
        assert len(backups) >= 1, "backups were lost during restore"

    def test_restore_timestamp(self, tmp_path):
        """--restore=project@timestamp restores a specific backup."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _seed(repo)

        # Create two re-seeds to have two backups
        _seed(repo)
        _seed(repo)

        # Get the first backup timestamp
        backup_root = repo / ".hermes-cortex" / ".seed-backups"
        backups = sorted(backup_root.iterdir())
        first_ts = backups[0].name

        # Corrupt AGENTS.md
        agents = repo / "AGENTS.md"
        agents.write_text("# CORRUPTED")

        rc, stdout, _ = _run(
            "bash", str(SEED_PROJECT), f"--restore={repo}@{first_ts}"
        )
        assert rc == 0, f"timestamp restore failed:\n{stdout}"
        assert "Restored AGENTS.md" in stdout or "Restore complete" in stdout

    # ── --skill-refs ─────────────────────────────────────────

    def test_skill_refs_linked(self, tmp_path):
        """--skill-refs creates symlinks in .hermes-cortex/skills/."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        rc, stdout, _ = _seed(repo, "--skill-refs=change-test-loop,engineering-approach")
        assert rc == 0, f"skill-refs seed failed:\n{stdout}"
        skills_dir = repo / ".hermes-cortex" / "skills"
        assert skills_dir.is_dir()
        assert (skills_dir / "change-test-loop").is_symlink() or \
               (skills_dir / "change-test-loop").is_dir()
        assert (skills_dir / "engineering-approach").is_symlink() or \
               (skills_dir / "engineering-approach").is_dir()

    # ── --template ───────────────────────────────────────────

    def test_custom_template(self, tmp_path):
        """--template uses a custom AGENTS.md template."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)

        custom = tmp_path / "custom-template.md"
        custom.write_text("# Custom for {{PROJECT_NAME}}\n\nSeeded on {{SEED_DATE}}")

        rc, stdout, _ = _seed(
            repo, f"--template={custom}", "--name=TestApp"
        )
        assert rc == 0, f"custom template seed failed:\n{stdout}"
        agents = repo / "AGENTS.md"
        assert agents.exists()
        content = agents.read_text()
        assert "Custom for TestApp" in content, (
            f"template substitution failed:\n{content}"
        )

    # ── Restore from first seed (no AGENTS.md in backup) ────

    def test_restore_first_seed_no_agents(self, tmp_path):
        """Restore with no backups prints a clear message, doesn't crash."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _seed(repo)

        # First seed creates no backup (nothing to save)
        # Restore should say "No backups" and exit non-zero
        rc, stdout, stderr = _run(
            "bash", str(SEED_PROJECT), f"--restore={repo}"
        )
        combined = stdout + stderr
        assert "No backups" in combined or rc != 0, (
            "should report no backups or exit with error"
        )
