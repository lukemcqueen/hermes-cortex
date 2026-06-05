---
language: python
tags: [file, io, util, pattern]
title: Pathlib Operations
description: Modern filesystem operations using pathlib: Path read/write, glob, mkdir, resolve, stat, and directory traversal.
source: pattern
---

```python
import stat
from pathlib import Path
from typing import Iterator


def ensure_dir(path: str | Path) -> Path:
    """Create a directory (and parents) if it doesn't exist."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_text_safe(path: str | Path, content: str) -> Path:
    """Write text to a file, creating parent directories as needed."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def read_text_safe(path: str | Path) -> str:
    """Read text from a file, raising a clear error if missing."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"No such file: {p.resolve()}")
    return p.read_text(encoding="utf-8")


def fast_glob(root: str | Path, pattern: str = "**/*") -> Iterator[Path]:
    """Yield files matching a glob pattern (default: all files recursively)."""
    yield from Path(root).glob(pattern)


def file_info(path: str | Path) -> dict[str, object]:
    """Return structured stat + metadata about a file."""
    p = Path(path)
    st = p.stat()
    return {
        "path": str(p.resolve()),
        "name": p.name,
        "suffix": p.suffix,
        "stem": p.stem,
        "size": st.st_size,
        "modified": st.st_mtime,
        "created": st.st_ctime,
        "is_dir": p.is_dir(),
        "is_file": p.is_file(),
        "is_symlink": p.is_symlink(),
        "permissions": oct(stat.S_IMODE(st.st_mode)),
    }


def tree(directory: str | Path, prefix: str = "") -> None:
    """Print a recursive directory tree."""
    path = Path(directory)
    entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "-- " if is_last else "|- "
        print(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
        if entry.is_dir():
            extension = "    " if is_last else "|   "
            tree(entry, prefix + extension)


# ---- Example ---- #
if __name__ == "__main__":
    tmp = Path("/tmp/pathlib_demo")
    ensure_dir(tmp / "sub/a")
    write_text_safe(tmp / "hello.txt", "Hello, pathlib!")

    for f in fast_glob(tmp, "**/*"):
        print(f)

    info = file_info(tmp / "hello.txt")
    print(f"\nInfo: {info}")

    # Cleanup
    import shutil
    shutil.rmtree(tmp)

```
