"""Python snippet additions — 8 new snippets completing Python coverage to 25 total."""

SNIPPETS = [
    # ------------------------------------------------------------------ #
    # 1. ASYNCIO / ASYNC-AWAIT PATTERNS
    # ------------------------------------------------------------------ #
    (
        "python/async-patterns.md",
        "python",
        ["async", "pattern", "net", "util"],
        "Async/Await Patterns",
        "Modern asyncio patterns: asyncio.run, gather, create_task, sleep, Semaphore, and as_completed.",
        "pattern",
        r'''
import asyncio
import random


async def fetch_url(name: str, delay: float) -> str:
    """Simulate a non-blocking IO operation."""
    await asyncio.sleep(delay)
    return f"Result from {name} (took {delay:.1f}s)"


async def bounded_fetch(sem: asyncio.Semaphore, name: str, delay: float) -> str:
    """Respect a concurrency limit with a Semaphore."""
    async with sem:
        return await fetch_url(name, delay)


async def main() -> None:
    # --- gather: run many tasks concurrently ---
    results = await asyncio.gather(
        fetch_url("alpha", 0.3),
        fetch_url("beta", 0.1),
        fetch_url("gamma", 0.2),
        return_exceptions=True,
    )
    print("Gather results:", results)

    # --- create_task: fire-and-forget with background tracking ---
    background_tasks = set()
    for i in range(3):
        task = asyncio.create_task(fetch_url(f"bg-{i}", random.uniform(0.05, 0.15)))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    # --- Semaphore: limit concurrency to 2 ---
    sem = asyncio.Semaphore(2)
    tasks = [bounded_fetch(sem, f"item-{i}", random.uniform(0.1, 0.5)) for i in range(6)]
    for coro in asyncio.as_completed(tasks):
        earliest = await coro
        print("Completed:", earliest)

    # --- wait for all background tasks ---
    if background_tasks:
        await asyncio.wait(background_tasks)

    print("Done")


if __name__ == "__main__":
    asyncio.run(main())
'''.strip(),
    ),

    # ------------------------------------------------------------------ #
    # 2. FASTAPI APP WITH AUTO-DOCS
    # ------------------------------------------------------------------ #
    (
        "python/fastapi-app.md",
        "python",
        ["api", "web", "pattern", "util"],
        "FastAPI App with Auto-Docs",
        "FastAPI application skeleton with Pydantic models, GET/POST endpoints, path and query parameters, automatic OpenAPI docs, and dependency injection.",
        "pattern",
        r'''
from typing import Optional

from fastapi import FastAPI, Query, Path, Depends, HTTPException
from pydantic import BaseModel, Field

# ------------------------------------------------------------------ #
# Models
# ------------------------------------------------------------------ #
class Item(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Item name")
    price: float = Field(..., gt=0, description="Price must be positive")
    in_stock: bool = True
    tags: list[str] = []

class ItemResponse(Item):
    id: int

    model_config = {"from_attributes": True}

# ------------------------------------------------------------------ #
# App & in-memory store
# ------------------------------------------------------------------ #
app = FastAPI(
    title="Example API",
    version="1.0.0",
    description="A sample FastAPI app showcasing routing, validation, and auto docs.",
)
store: dict[int, ItemResponse] = {}
counter: int = 0

def get_next_id() -> int:
    global counter
    counter += 1
    return counter

# ------------------------------------------------------------------ #
# Endpoints
# ------------------------------------------------------------------ #
@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Hello from FastAPI"}

@app.get("/items/{item_id}", response_model=ItemResponse)
def get_item(
    item_id: int = Path(..., ge=1, description="The item ID"),
) -> ItemResponse:
    if item_id not in store:
        raise HTTPException(status_code=404, detail="Item not found")
    return store[item_id]

@app.get("/items", response_model=list[ItemResponse])
def list_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    min_price: Optional[float] = Query(None, gt=0),
) -> list[ItemResponse]:
    items = list(store.values())
    if min_price is not None:
        items = [it for it in items if it.price >= min_price]
    return items[skip : skip + limit]

@app.post("/items", response_model=ItemResponse, status_code=201)
def create_item(item: Item) -> ItemResponse:
    item_id = get_next_id()
    new = ItemResponse(id=item_id, **item.model_dump())
    store[item_id] = new
    return new

# ------------------------------------------------------------------ #
# Run with: fastapi dev fastapi-app.py
# Auto-docs at http://127.0.0.1:8000/docs
# ------------------------------------------------------------------ #
'''.strip(),
    ),

    # ------------------------------------------------------------------ #
    # 3. CSV READ/WRITE WITH DICTREADER / DICTWRITER
    # ------------------------------------------------------------------ #
    (
        "python/csv-read-write.md",
        "python",
        ["io", "file", "util", "pattern"],
        "CSV Read/Write with DictReader & DictWriter",
        "Reading and writing CSV files using the csv module with DictReader, DictWriter, type coercion, and error handling.",
        "pattern",
        r'''
import csv
import io
from typing import Optional


# ---- Sample data ---- #
HEADER = ["name", "age", "city"]
ROWS = [
    {"name": "Alice", "age": "30", "city": "New York"},
    {"name": "Bob", "age": "25", "city": "London"},
    {"name": "Charlie", "age": "35", "city": "Tokyo"},
]


def write_csv(filepath: str, rows: list[dict], fieldnames: Optional[list[str]] = None) -> None:
    """Write a list of dictionaries to a CSV file."""
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(filepath: str) -> list[dict[str, str]]:
    """Read a CSV file into a list of dictionaries (all values are strings)."""
    with open(filepath, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def coerce_row(row: dict[str, str], types: dict[str, type]) -> dict:
    """Convert selected string fields to requested Python types."""
    coerced = dict(row)
    for col, typ in types.items():
        val = coerced.get(col)
        if val is not None and val != "":
            coerced[col] = typ(val)
    return coerced


# ---- Example usage ---- #
if __name__ == "__main__":
    import tempfile, os

    # Write
    tmp = os.path.join(tempfile.gettempdir(), "example.csv")
    write_csv(tmp, ROWS, fieldnames=HEADER)
    print(f"Wrote {len(ROWS)} rows to {tmp}")

    # Read
    loaded = read_csv(tmp)
    for row in loaded:
        # Coerce age to int
        typed = coerce_row(row, {"age": int})
        print(f"{typed['name']:>8}  {typed['age']:>3}  {typed['city']}")

    # Cleanup
    os.remove(tmp)
'''.strip(),
    ),

    # ------------------------------------------------------------------ #
    # 4. YAML CONFIG LOADING (PYYAML)
    # ------------------------------------------------------------------ #
    (
        "python/yaml-config.md",
        "python",
        ["config", "file", "util", "io"],
        "YAML Config Loading",
        "Loading, dumping, and merging YAML configuration with PyYAML: safe_load, dump, multi-document streams, and safe YAML includes.",
        "pattern",
        r'''
import os
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    print("PyYAML is required. Install: pip install pyyaml")
    sys.exit(1)


def load_config(path: str) -> dict[str, Any]:
    """Load a single YAML document safely."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_multi(path: str) -> list[dict[str, Any]]:
    """Load all YAML documents from a single file (multi-document stream)."""
    with open(path, "r", encoding="utf-8") as f:
        return list(yaml.safe_load_all(f))


def dump_config(data: dict[str, Any], path: str, *, default_flow_style: bool = False) -> None:
    """Write a dictionary as a clean YAML file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=default_flow_style, sort_keys=False)


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge two config dicts (override wins)."""
    merged = dict(base)
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


# ---- Example ---- #
if __name__ == "__main__":
    import tempfile

    cfg1 = load_config(os.path.join(tempfile.gettempdir(), "nonexistent.yml"))
    print("Empty config:", cfg1)

    base = {"database": {"host": "localhost", "port": 5432}, "debug": False}
    override = {"database": {"port": 15432}, "debug": True}
    merged = deep_merge(base, override)
    dump_config(merged, "/tmp/merged_config.yml")
    print("Merged config written to /tmp/merged_config.yml")
'''.strip(),
    ),

    # ------------------------------------------------------------------ #
    # 5. ENVIRONMENT VARIABLES
    # ------------------------------------------------------------------ #
    (
        "python/env-variables.md",
        "python",
        ["config", "sys", "util", "pattern"],
        "Environment Variables",
        "Reading and managing environment variables with os.environ, os.getenv, python-dotenv, type coercion, and safe defaults.",
        "pattern",
        r'''
import os
import sys
from typing import Optional, TypeVar

T = TypeVar("T")


# ---- Core helpers ---- #
def get_str(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read a string env var, returning default if absent."""
    return os.environ.get(key, default)


def get_int(key: str, default: Optional[int] = None) -> Optional[int]:
    """Read an integer env var, returning default on missing or invalid."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_bool(key: str, default: bool = False) -> bool:
    """Parse a boolean env var (true/1/yes/y => True, everything else => False)."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes", "y")


# ---- Load .env file (if python-dotenv is available) ---- #
def load_dotenv(path: Optional[str] = None) -> None:
    """Load a .env file into os.environ. Falls back to '.env' if path is None."""
    try:
        from dotenv import load_dotenv as _load
        loaded = _load(path) if path else _load()
        if loaded:
            print(f"Loaded environment from {path or '.env'}")
    except ImportError:
        print("python-dotenv not installed; skipping .env loading", file=sys.stderr)


# ---- App config sourced from environment ---- #
class AppConfig:
    def __init__(self) -> None:
        self.host: str = get_str("APP_HOST", "0.0.0.0")  # type: ignore[assignment]
        self.port: int = get_int("APP_PORT", 8000) or 8000
        self.debug: bool = get_bool("APP_DEBUG", False)
        self.database_url: str = os.environ.get(
            "DATABASE_URL",
            "sqlite:///app.db",
        )
        self.secret_key: str = os.environ["SECRET_KEY"]  # will raise KeyError if missing

    def __repr__(self) -> str:
        return (
            f"AppConfig(host={self.host!r}, port={self.port}, "
            f"debug={self.debug}, db={self.database_url!r})"
        )


# ---- Example ---- #
if __name__ == "__main__":
    # Optionally load a .env file
    load_dotenv()

    # Basic usage
    print(f"HOME = {get_str('HOME')}")
    print(f"WORKERS = {get_int('WORKERS', 4)}")
    print(f"ENABLE_CACHE = {get_bool('ENABLE_CACHE', True)}")

    # Structured config -- requires SECRET_KEY to be set
    try:
        cfg = AppConfig()
        print(cfg)
    except KeyError as e:
        print(f"Missing required env var: {e}")
        sys.exit(1)
'''.strip(),
    ),

    # ------------------------------------------------------------------ #
    # 6. PATHLIB OPERATIONS
    # ------------------------------------------------------------------ #
    (
        "python/pathlib-operations.md",
        "python",
        ["file", "io", "util", "pattern"],
        "Pathlib Operations",
        "Modern filesystem operations using pathlib: Path read/write, glob, mkdir, resolve, stat, and directory traversal.",
        "pattern",
        r'''
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
'''.strip(),
    ),

    # ------------------------------------------------------------------ #
    # 7. DATETIME FORMATTING
    # ------------------------------------------------------------------ #
    (
        "python/datetime-formatting.md",
        "python",
        ["util", "pattern", "io"],
        "Datetime Formatting & Parsing",
        "Working with datetime, timezone-aware timestamps, strftime/strptime, timedelta arithmetic, dateutil parser, and ISO 8601 formatting.",
        "pattern",
        r'''
from datetime import datetime, timezone, timedelta
from typing import Optional

try:
    from dateutil import parser as dateutil_parser
    from dateutil.tz import gettz
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False


# ---- Constants ---- #
ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"
HUMAN_FORMAT = "%Y-%m-%d %H:%M:%S %Z"
LOGFILE_FORMAT = "%Y%m%d_%H%M%S"


def now_utc() -> datetime:
    """Return the current UTC time with timezone info."""
    return datetime.now(timezone.utc)


def format_iso(dt: Optional[datetime] = None) -> str:
    """Format a datetime as ISO 8601; defaults to now_utc."""
    return (dt or now_utc()).strftime(ISO_FORMAT)


def parse_iso(text: str) -> datetime:
    """Parse an ISO 8601 string back to a timezone-aware datetime."""
    return datetime.strptime(text, ISO_FORMAT)


def smart_parse(text: str, tz_name: str = "UTC") -> Optional[datetime]:
    """Flexible date parsing using dateutil (if available), falling back to strptime guesses."""
    if HAS_DATEUTIL:
        dt = dateutil_parser.parse(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=gettz(tz_name))
        return dt
    # fallback: try common formats
    for fmt in [ISO_FORMAT, HUMAN_FORMAT, "%Y-%m-%d", "%d/%m/%Y"]:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def human_readable(dt: Optional[datetime] = None) -> str:
    """Return a human-friendly string like '2025-01-15 14:30:00 UTC'."""
    dt = dt or now_utc()
    return dt.strftime(HUMAN_FORMAT)


def time_ago(dt: datetime, reference: Optional[datetime] = None) -> str:
    """Return a relative time description (e.g. '3 hours ago', '2 days ago')."""
    ref = reference or now_utc()
    diff = ref - dt
    seconds = int(diff.total_seconds())
    if seconds < 0:
        return "in the future"
    intervals = [
        (365 * 86400, "year"),
        (30 * 86400, "month"),
        (7 * 86400, "week"),
        (86400, "day"),
        (3600, "hour"),
        (60, "minute"),
    ]
    for divisor, unit in intervals:
        count = seconds // divisor
        if count >= 1:
            return f"{count} {unit}{'s' if count > 1 else ''} ago"
    return "just now"


# ---- Example ---- #
if __name__ == "__main__":
    now = now_utc()
    print("Now (ISO):", format_iso(now))
    print("Now (human):", human_readable(now))
    print("Parsed back:", parse_iso(format_iso(now)))
    print("Time ago (5h back):", time_ago(now - timedelta(hours=5, minutes=20)))

    yesterday = now - timedelta(days=1)
    print("Yesterday:", human_readable(yesterday))

    if HAS_DATEUTIL:
        parsed = smart_parse("Jan 15, 2025 3:30 PM EST")
        print("Parsed (dateutil):", parsed)
'''.strip(),
    ),

    # ------------------------------------------------------------------ #
    # 8. SUBPROCESS MANAGEMENT
    # ------------------------------------------------------------------ #
    (
        "python/subprocess-management.md",
        "python",
        ["sys", "cli", "util", "pattern"],
        "Subprocess Management",
        "Running external commands with subprocess.run, capturing stdout/stderr, piping, timeout, error handling, and shell=False best practices.",
        "pattern",
        r'''
import os
import subprocess
import sys
from typing import Optional


def run(
    cmd: list[str],
    *,
    timeout: Optional[float] = None,
    check: bool = True,
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Run an external command, capture output, and raise on failure by default."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
            input=input_text,
        )
        return result
    except subprocess.CalledProcessError as exc:
        print(f"Command {cmd} failed with exit code {exc.returncode}", file=sys.stderr)
        print(f"stdout: {exc.stdout}", file=sys.stderr)
        print(f"stderr: {exc.stderr}", file=sys.stderr)
        raise
    except FileNotFoundError:
        print(f"Command not found: {cmd[0]}", file=sys.stderr)
        raise


def run_pipe(
    commands: list[list[str]],
    *,
    timeout: Optional[float] = None,
    check: bool = True,
) -> bytes:
    """Chain multiple commands via pipeline (left to right)."""
    prev_stdout: Optional[bytes] = None
    for i, cmd in enumerate(commands):
        stdin = subprocess.PIPE if i == 0 else prev_stdout
        proc = subprocess.Popen(
            cmd,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, stdout, stderr
            )
        prev_stdout = stdout
    return prev_stdout or b""


def stream_output(cmd: list[str]) -> None:
    """Run a command and stream its output line-by-line in real time."""
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as proc:
        for line in proc.stdout:  # type: ignore[union-attr]
            print(line, end="")
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


# ---- Example ---- #
if __name__ == "__main__":
    # Simple capture
    r = run(["echo", "hello subprocess"])
    print("Captured:", r.stdout.strip())

    # With stdin
    r2 = run(["tr", "[:lower:]", "[:upper:]"], input_text="hello world")
    print("Uppercased:", r2.stdout.strip())

    # Pipeline: ps aux | grep python | head -3
    try:
        out = run_pipe(
            [["ps", "aux"], ["grep", "python"], ["head", "-3"]],
            check=False,
        )
        print("Pipeline output:")
        print(out.decode("utf-8", errors="replace"))
    except FileNotFoundError:
        # Windows/macOS compatibility
        print("Pipeline commands not available on this platform", file=sys.stderr)
'''.strip(),
    ),
]
