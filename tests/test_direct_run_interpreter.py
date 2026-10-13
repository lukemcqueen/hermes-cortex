"""A script that RUNS a python file must choose its interpreter the way a probe does.

`test_venv_env_contamination.py` covers one half of the class: `python -c 'import X'`.
This covers the other half: `python3 somescript.py`.

The rule is CAPABILITY, not caution. A file that imports only STDLIB needs no special
interpreter — the stdlib travels with whatever interpreter was resolved, so a bare `python3`
is fine. A file that imports a THIRD-PARTY module needs one that HAS it, because the choice
is otherwise made by PATH and by an inherited PYTHONPATH.

Measured on esther 2026-10-13: the agent session puts
`~/.hermes/tools/python-3.14.7+.../bin` ahead of `/usr/bin` on PATH, so inside a session a bare
`python3` is that 3.14 tools interpreter — which has no yaml, no mcp, no pytest. And it exports
PYTHONPATH at a 3.14 Hermes install environment, which can shadow the target's own packages.
Neither is a hypothetical: both broke this host's tooling the same night, in two different
shapes (a probe that "failed", and a validator that blamed a valid file).

stdlib-only files are deliberately NOT flagged. Flagging them would train the next reader to
add ceremony to lines that cannot break.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STDLIB = set(getattr(sys, "stdlib_module_names", ()))

# A run of a python FILE: `python3 x.py`, `python3 ./x.py`, `python3 "$dir/x.py"`.
RUN = re.compile(r"""(?<![\w-])python3?\s+["']?([\w./${}-]*\.py)""")
# Either the shared arbiter, or an explicit declared interpreter.
ARBITER = ("python-with-module.sh", "CORTEX_PYTHON")

SHELL_GLOBS = ("ops/**/*.sh", "scripts/**/*.sh", "**/*.service", "**/*.plist", "**/*.timer")


def _imports(path: Path) -> set[str]:
    """Top-level module names the file imports (third-party detection only needs roots)."""
    try:
        tree = ast.parse(path.read_text(errors="replace"))
    except (SyntaxError, OSError):
        return set()
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            mods.add(node.module.split(".")[0])
    return mods


def _local_files(mod: str, shell: Path) -> list[Path]:
    """Files that DEFINE `mod` locally. A module shipped beside the script is not third-party —
    and this is not a technicality: `cortex-doctor.py` imports `cortex_doctor`, which lives next
    to it. Treating local packages as third-party would flag every entry script in the repo.

    Three shapes count as local, because the repo uses all three: `<mod>.py`, a package with
    `__init__.py`, and a DIRECTORY OF MODULES that the entry script puts on sys.path (`lib`,
    which carries no `__init__.py`). Missing the third shape would report `lib` as a missing
    dependency and the check would cry wolf on every entry script.
    """
    for base in (shell.parent, REPO / "ops" / "scripts" / "lib", REPO):
        for candidate in (base / f"{mod}.py", base / mod / "__init__.py"):
            if candidate.is_file():
                return [candidate]
    for pattern in (f"**/{mod}.py", f"**/{mod}/__init__.py"):
        for candidate in sorted(REPO.glob(pattern)):
            if candidate.parts[:1] not in {("docs",), (".git",)} and "docs" not in candidate.parts:
                return [candidate]
    for candidate in sorted(REPO.glob(f"**/{mod}/*.py")):
        if "docs" not in candidate.parts:
            return [candidate]          # a dir-as-package: its imports decide, not its name
    return []


def _unresolved_third_party(entry: Path, shell: Path, cap: int = 60) -> set[str]:
    """Modules the entry file ultimately needs that are NEITHER stdlib NOR defined locally.

    Local modules are EXPANDED rather than trusted: `cortex-doctor.py` imports the cortex_doctor
    package, and it is the package's own imports that decide which interpreter can run it. A
    check that reads only the entry file would call a yaml-importing program stdlib-only.
    """
    todo, seen, unknown = [entry], {entry}, set()
    while todo and len(seen) < cap:
        current = todo.pop()
        for mod in _imports(current):
            if mod in STDLIB:
                continue
            local = _local_files(mod, shell)
            if not local:
                unknown.add(mod)
                continue
            for f in local:
                if f in seen:
                    continue
                seen.add(f)
                todo.append(f)
                extra = [p for p in f.parent.rglob("*.py") if p not in seen][:40]
                todo.extend(extra)
    return unknown


def _candidate_files():
    seen = set()
    for pattern in SHELL_GLOBS:
        for path in REPO.glob(pattern):
            rel = str(path.relative_to(REPO))
            if rel.startswith(("docs/", ".git/")) or rel in seen:
                continue
            seen.add(rel)
            yield rel, path


def _resolve(shell: Path, target: str) -> Path | None:
    if not target or "$" in target:
        return None                        # dynamic path: no static verdict to give
    for candidate in (shell.parent / target, REPO / target.lstrip("./")):
        if candidate.is_file():
            return candidate
    return None


def test_every_direct_run_of_a_third_party_importing_file_uses_the_arbiter():
    offenders = []
    for rel, shell in sorted(_candidate_files()):
        for n, line in enumerate(shell.read_text(errors="replace").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue                    # a run named in a comment executes nothing
            m = RUN.search(line)
            if not m or any(a in line for a in ARBITER):
                continue
            f = _resolve(shell, m.group(1))
            if f is None:
                continue
            third_party = _unresolved_third_party(f, shell)
            if third_party:
                offenders.append(
                    f"{rel}:{n}: bare `python3` runs {f.name}, which imports "
                    f"{', '.join(sorted(third_party))} — resolve it via "
                    f"python-with-module.sh (capability-decided, env-clean)"
                )
    assert not offenders, (
        "direct runs whose interpreter choice decides whether they work:\n  "
        + "\n  ".join(offenders)
    )
