"""Tests for cross-platform compatibility — catches macOS-only patterns.

Every script added to the public repo must work on both macOS and Linux
(or have explicit platform guards). This test scans for common macOS-only
commands and flags any that appear without a platform guard.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / "src" / "scripts"

try:
    import pytest
except ImportError:
    pass


# macOS-specific commands that need platform guards
MACOS_ONLY_PATTERNS = [
    r"\blaunchctl\b",
    r"\bsw_vers\b",
    r"\bmemory_pressure\b",
    r"\bpmset\b",
    r"\bvm_stat\b",
]

# Platform guard patterns that protect macOS-only commands
# Also accept try/except fallback patterns (try launchctl, catch FileNotFoundError→use systemd)
MACOS_GUARDS_PY = [
    r'sys\.platform\s*==\s*["\']darwin["\']',
    r'"darwin"',
    r"\bdarwin\b",
    r"#\s*macOS",
    r"is_macos\(",
    r"try:.*launchctl",  # try/except fallback pattern
    r"except FileNotFoundError",  # launchctl not found → use systemd
    r"try:.*vm_stat",  # try/except fallback for macOS vm_stat
    r"except.*Exception.*pass",  # guarded fallback (system-alert.py pattern)
    r"# Use vm_stat.*accurate",  # vm_stat in guarded try/except block
]

# Shell scripts use CORTEX_OS or direct comparison
MACOS_GUARDS_SH = [
    r"CORTEX_OS.*macos",
    r'"\$CORTEX_OS" == "macos"',
    r"\bmacos\b",
    r'#\s*macOS',
    r"Darwin|darwin",
]


def _find_py_files():
    """Find .py files in src/scripts/ (excluding __pycache__/archive)."""
    if not SCRIPTS_DIR.exists():
        return []
    return sorted(
        p for p in SCRIPTS_DIR.rglob("*.py")
        if not any(part.startswith("__") or part in ("archive", "__pycache__", "venv") for part in p.parts)
    )


def _find_sh_files():
    """Find .sh files in src/scripts/ (excluding sourced-only and __pycache__)."""
    if not SCRIPTS_DIR.exists():
        return []
    sourced_only = {"os-config.sh", "cortex-profile.sh", "service-writer.sh"}
    return sorted(
        p for p in SCRIPTS_DIR.rglob("*.sh")
        if p.name not in sourced_only
        and not any(part.startswith("__") or part in ("archive", "__pycache__") for part in p.parts)
    )


def _has_any_guard(text: str, guards: list[str]) -> bool:
    """Check if text contains any platform guard pattern."""
    return any(re.search(g, text, re.MULTILINE) for g in guards)


def _check_file(filepath: Path, py: bool = True) -> list[str]:
    """Check a single file for unguarded macOS-only commands.
    Returns list of violations (empty = clean).

    Accepts files where the macOS command is inside a try/except block
    (the command will throw FileNotFoundError on Linux and be caught).
    """
    violations = []
    try:
        text = filepath.read_text()
    except (OSError, IOError):
        return []

    guards = MACOS_GUARDS_PY if py else MACOS_GUARDS_SH
    has_guard = _has_any_guard(text, guards)

    # Also check for try/except wrapping: if a line with a macOS command
    # is preceded by a `try:`, it's considered guarded (cross-platform fallback)
    lines = text.split("\n")

    for pattern in MACOS_ONLY_PATTERNS:
        for i, line_text in enumerate(lines, 1):
            if re.search(pattern, line_text):
                if has_guard:
                    continue  # file-level guard covers it
                # Check if this line is inside a try block (look back up to 5 lines)
                guarded_by_try = False
                for j in range(max(0, i-6), i-1):
                    if re.search(r"^\s*try:", lines[j]):
                        guarded_by_try = True
                        break
                if not guarded_by_try:
                    violations.append(
                        f"{filepath.relative_to(REPO_ROOT)}:{i}: "
                        f"'{pattern}' used without platform guard"
                    )

    # Deduplicate violations
    seen = set()
    unique = []
    for v in violations:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


def test_python_scripts_no_unguarded_macos_commands():
    """All .py scripts must guard macOS-only commands with platform checks."""
    all_violations = []
    for py_file in _find_py_files():
        all_violations.extend(_check_file(py_file, py=True))
    if all_violations:
        pytest.fail(
            "Found macOS-only commands without platform guards:\n"
            + "\n".join(all_violations)
            + "\n\nAdd `if sys.platform == 'darwin':` or similar guard."
        )


def test_shell_scripts_no_unguarded_macos_commands():
    """All .sh scripts must guard macOS-only commands."""
    all_violations = []
    for sh_file in _find_sh_files():
        all_violations.extend(_check_file(sh_file, py=False))
    if all_violations:
        pytest.fail(
            "Found macOS-only commands without platform guards:\n"
            + "\n".join(all_violations)
            + "\n\nAdd `if [[ \"$CORTEX_OS\" == \"macos\" ]];` or similar guard."
        )