# Python Repo-Relative Paths for Script Tools

## Problem

Standalone Python scripts within a repo often need to invoke sibling modules
or data files by path. Hardcoding an absolute path ties the script to one
developer's machine layout:

```python
from pathlib import Path
HOME = Path.home()

# BAD — only works on Luke's machine layout
OFFLINE_KNOWLEDGE = HOME / "Developer" / "AI" / "hermes-cortex" / "src" / "offline" / "offline_knowledge.py"
```

Symptoms: the script runs fine for the author but breaks for anyone else
cloning the repo under a different parent directory (or named differently).

## Fix — derive path from `__file__`

```python
from pathlib import Path

# Portable — works from any clone location, any machine
OFFLINE_KNOWLEDGE = Path(__file__).resolve().parent / "offline_knowledge.py"
```

`Path(__file__).resolve()` resolves symlinks and `..` segments to give an
absolute path to the current script. `.parent` goes up one directory level.

## Common variations

| Pattern | Use Case |
|---------|----------|
| `Path(__file__).resolve().parent / "sibling.py"` | Script one level up |
| `Path(__file__).resolve().parent / "subdir" / "target.py"` | Sibling in subdirectory |
| `Path(__file__).resolve().parent.parent / "other_module.py"` | Two levels up |
| `Path(__file__).resolve().parent.parent / "data" / "config.json"` | Data files relative to project root |

## Pitfalls

- **Symlinked scripts**: `__file__` follows the symlink. `Path(__file__).resolve()` resolves it to the real location. Without `.resolve()`, a symlinked script would resolve paths relative to the symlink's location, not the real file's location.
- **Frozen binaries / zipimport / eggs**: `__file__` may not be a regular filesystem path. Not common for repo-tool scripts but worth noting if the tool gets packaged.
- **Don't use `os.getcwd()` or `os.path.dirname(os.path.abspath(sys.argv[0]))`**: Both break when the script is invoked from a different working directory or via a pathless shebang (`python3 script.py`). `__file__` is the only reliable anchor for repo-relative lookups.

## Detection

After cloning the repo to a new location, scan for `HOME /` path constructions
in script files:

```bash
grep -rn 'HOME.*/"' src/offline/*.py
```

Every match is a candidate to switch to `Path(__file__).resolve().parent`.

## Related

- `python-test-env-pitfalls.md` — module-level constants from env vars also suffer from machine-specific hardcoding. The two patterns interact: a script with a hardcoded path won't even import on the wrong machine.
