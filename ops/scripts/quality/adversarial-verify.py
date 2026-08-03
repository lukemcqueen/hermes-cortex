#!/usr/bin/env python3
"""
adversarial-verify.py — Adversarial Verification CLI.

Systematically attempts to break code BEFORE it ships.
Covers A1 (surface scan), A2 (input fuzzing + cheat detection +
static OWASP patterns), A3 (state corruption + dependency sabotage),
and A4 (concurrency + invariants + property-based templates).

Usage:
    adversarial-verify.py --file <path> --level A1
    adversarial-verify.py --file <path> --level A2 [--json]
    adversarial-verify.py --dir <path> --level A2
    adversarial-verify.py --dir <path> --level A2 --gate
    adversarial-verify.py --file <path> --level A4 --gate

Maturity Levels:
    A1 — Attack Surface Enumeration (static analysis)
    A2 — Input Fuzzing + Cheat Detection + Static OWASP patterns
    A3 — A2 + State Corruption + Dependency Sabotage detection
    A4 — A3 + Concurrency races + Invariant violations + Property templates
    A5 — A4 (evidence packaging via --output)

Exit codes:
    0 — No adversarial findings
    1 — Findings detected
    2 — Error (file not found, etc.)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────

FINDING_ID_COUNTER = 0


def next_finding_id() -> str:
    global FINDING_ID_COUNTER
    FINDING_ID_COUNTER += 1
    date = datetime.now().strftime("%Y-%m-%d")
    return f"ADV-{date}-{FINDING_ID_COUNTER:03d}"


# ── Phase 1: Attack Surface Enumeration ─────────────────────────

SENSITIVE_KEYWORDS = {
    "input": [
        r"(def |async def )\w+\(.*\)",
        r"request\.(get|post|put|delete|patch)",
        r"\.query\b", r"\.params\b", r"\.body\b", r"\.data\b",
        r"input\(.*\)", r"sys\.argv", r"argparse", r"click\.(command|option|argument)",
        r"@app\.(route|get|post|put|delete)", r"@\.(get|post|put|delete)\(",
        r"\.env\b", r"os\.environ",
    ],
    "state": [
        r"db\.|database|postgres|mysql|sqlite|redis|mongo",
        r"cache\.|memcache|redis",
        r"open\(.*\)", r"\.write\(.*\)", r"\.read\(.*\)",
        r"session\[", r"state\[", r"store\.",
    ],
    "dependency": [
        r"import\s+\w+",
        r"from\s+\w+\s+import",
        r"requests\.", r"httpx\.", r"aiohttp\.", r"urllib",
        r"boto3|google\.cloud|azure|aws",
        r"smtplib|sendmail",
        r"subprocess\.", r"os\.system",
    ],
    "concurrency": [
        r"threading\.|Thread\(|ThreadPool",
        r"asyncio\.|async\s+def|await\b",
        r"multiprocessing\.|Process\(",
        r"global\b|nonlocal\b",
        r"\.lock\(\)|\.acquire\(\)|\.release\(\)",
        r"queue\.|Queue\(",
    ],
}


def analyze_attack_surface(file_path: str) -> dict:
    """Analyze a file for attack surface indicators.

    Returns structured attack surface with line numbers.
    """
    try:
        with open(file_path) as f:
            lines = f.readlines()
    except IOError as e:
        return {"error": str(e), "inputs": [], "state": [], "dependencies": [], "concurrency": []}

    filename = Path(file_path).name
    surface = {"file": filename, "path": file_path, "inputs": [], "state": [], "dependencies": [], "concurrency": []}

    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        for category, patterns in SENSITIVE_KEYWORDS.items():
            for pattern in patterns:
                if re.search(pattern, stripped, re.IGNORECASE):
                    # Map singular category names to plural surface keys
                    surface_key = {"input": "inputs", "dependency": "dependencies"}.get(category, category)
                    surface[surface_key].append({
                        "line": lineno,
                        "code": stripped[:120],
                        "category": category,
                    })
                    break  # one match per line per category

    # Deduplicate
    for category in ["inputs", "state", "dependencies", "concurrency"]:
        seen = set()
        unique = []
        for item in surface[category]:
            key = (item["line"], item["code"])
            if key not in seen:
                seen.add(key)
                unique.append(item)
        surface[category] = unique

    return surface


# ── Phase 2: Input Fuzzing (A2) ────────────────────────────────

def _find_func_defs(lines: list[str]) -> list[dict]:
    """Find function definitions and their parameters."""
    funcs = []
    for lineno, line in enumerate(lines, 1):
        m = re.match(r"^(async\s+)?def\s+(\w+)\s*\((.*)\)\s*:", line.strip())
        if m:
            params_str = m.group(3)
            params = []
            for p in re.split(r",\s*(?![^()]*\))", params_str):
                p = p.strip()
                if p and p != "self" and p != "cls":
                    # Split on : to get name and type hint
                    parts = p.split(":")
                    name = parts[0].strip()
                    type_hint = parts[1].strip() if len(parts) > 1 else "any"
                    # Check default
                    default = None
                    if "=" in name:
                        name, default = name.split("=", 1)
                        name = name.strip()
                        default = default.strip()
                    params.append({"name": name, "type_hint": type_hint, "default": default})
            funcs.append({"name": m.group(2), "line": lineno, "params": params})
    return funcs


BOUNDARY_INPUTS = {
    "str": ["", "a", "a" * 1000, "a" * 10001, None, "' OR '1'='1", "<script>alert(1)</script>",
            "a" * 256, "test@test.com", "invalid-email", "../etc/passwd"],
    "int": [-1, 0, 1, 2**31 - 1, 2**31, 2**63 - 1, "not-an-integer", None, 1.5],
    "float": [-1.0, 0.0, 1.0, 1e308, -1e308, float("inf"), float("nan"), None, "not-a-float"],
    "bool": [None, "true", 1, 0, "false"],
    "list": [[], [1], list(range(1000)), None, "not-a-list"],
    "dict": [{}, {"key": "value"}, None, "not-a-dict"],
    "any": [None, "", -1, 0, "a" * 10000, [], {}, True, False],
}


def generate_fuzz_inputs(funcs: list[dict]) -> list[dict]:
    """Generate fuzz inputs for each function's parameters."""
    fuzz_cases = []
    for func in funcs:
        for param in func["params"]:
            type_hint = param["type_hint"].lower()
            # Map common type names
            type_map = {
                "str": "str", "string": "str", "text": "str",
                "int": "int", "integer": "int", "number": "int",
                "float": "float", "double": "float",
                "bool": "bool", "boolean": "bool",
                "list": "list", "array": "list",
                "dict": "dict", "dict[str, any]": "dict", "object": "dict",
            }
            mapped = type_map.get(type_hint, "any")
            candidates = BOUNDARY_INPUTS.get(mapped, BOUNDARY_INPUTS["any"])

            for val in candidates:
                fuzz_cases.append({
                    "function": func["name"],
                    "parameter": param["name"],
                    "expected_type": type_hint,
                    "value": val,
                    "value_repr": repr(val),
                })
    return fuzz_cases


def detect_cheat_patterns(file_path: str, lines: list[str]) -> list[dict]:
    """Detect known cheat patterns in the code.

    Code-only detection: cheat patterns (empty excepts, type suppression)
    are source-code constructs — docs, configs, and prose must not be
    flagged for code examples they contain.

    NOTE (2026-08-01): the previous empty-except regex
    `except\\s*(?:\\w+\\s*)*:` used nested quantifiers and was
    catastrophically slow (exponential backtracking) on any file
    containing 'except' followed by a long word/space run — the
    pre-commit adversarial gate hung for minutes on ordinary files.
    Replaced with linear, bounded patterns. Bare `except:` (swallows
    everything) stays HIGH (gate blocker); a typed exception swallow is
    a maintainability smell → MEDIUM (reported, does not block).
    """
    # Cheat patterns are code constructs — only scan actual code files
    if Path(file_path).suffix not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
        return []
    findings = []
    content = "".join(lines)

    # Pattern 1: Empty except blocks (multi-line: except:\\n    pass)
    # Linear: `[^\\n:]*` bounded to the rest of the line — no nested quantifiers.
    empty_excepts = re.findall(
        r"except\b[^\n:]*:\s*(?:\n[ \t]*)?(?:pass|#.*)(?:\n|$)",
        content,
    )
    # Pattern 1b: Single-line: except: pass  (or _ = None)
    inline_swallows = re.findall(
        r"except\b[^\n:]*:\s*(?:pass|_ = None)\s*(?:#|$)",
        content,
    )
    if empty_excepts or inline_swallows:
        total = len(empty_excepts) + len(inline_swallows)
        # Bare `except:` swallows ALL exceptions — genuine blocker.
        # Typed except with pass/comment — smell, not a security blocker.
        has_bare = any(
            re.match(r"except\s*:", e) for e in (empty_excepts + inline_swallows)
        )
        findings.append({
            "finding_id": next_finding_id(),
            "technique": "cheat-detection",
            "pattern": "error-swallow",
            "detail": (
                f"Empty except block(s) detected: {total} occurrence(s)"
                + (" (includes bare except: — swallows every exception)" if has_bare else "")
            ),
            "severity": "high" if has_bare else "medium",
        })

    # Pattern 2: Type suppression
    if "type: ignore" in content or "@ts-ignore" in content:
        count = content.count("type: ignore") + content.count("@ts-ignore")
        findings.append({
            "finding_id": next_finding_id(),
            "technique": "cheat-detection",
            "pattern": "type-suppression",
            "detail": f"Type suppression found: {count} occurrence(s)",
            "severity": "medium",
        })

    # Pattern 3: Globally suppressed linting
    if "# flake8: noqa" in content or "pylint: disable=all" in content:
        findings.append({
            "finding_id": next_finding_id(),
            "technique": "cheat-detection",
            "pattern": "lint-suppression",
            "detail": "Global lint suppression detected",
            "severity": "low",
        })

    # Pattern 4: No docstring or comment
    if not content.strip().startswith(("#!", "# ", "'''", "\"\"\"")):
        if not re.search(r'""".*""".*', content) and not re.search(r"'''.*'''.*", content):
            pass  # Common for scripts, not a cheat pattern per se

    return findings


# ── Phase 2b: Static Security Pattern Detection ─────────────────
# Closes the gap (2026-08-03): adversarial-verify was fuzz + cheat
# detection only — it MISSED classic OWASP static patterns
# (command injection, eval, shell=True RCE, pickle deserialization,
# SQL injection, arbitrary file deletion). A vulnerable file and a
# clean file produced nearly identical results and the A2 gate passed
# both. These patterns are rated critical/high so the existing gate
# (block on critical/high) catches them.

STATIC_SECURITY_PATTERNS = [
    # (regex, pattern name, severity, detail)
    # Command injection via os.system / os.popen with concatenation
    (r"""os\.(system|popen)\([^)]*['\"]\s*\+""",
     "command-injection", "critical",
     "os.system/os.popen with string concatenation — command injection"),
    (r"""os\.(system|popen)\([^)]*f['\"]""",
     "command-injection", "critical",
     "os.system/os.popen with f-string — command injection"),
    # subprocess with shell=True and interpolated input
    (r"""subprocess\.(call|run|Popen|check_output|check_call)\([^)]*shell\s*=\s*True""",
     "shell-true-rce", "critical",
     "subprocess shell=True — command injection when args contain input"),
    # eval / exec of dynamic input
    (r"""(?<![.\w])(eval|exec)\([^)]*""",
     "dangerous-eval", "critical",
     "eval/exec on dynamic input — code execution"),
    # Unsafe deserialization
    (r"""pickle\.(loads|load)\(""",
     "unsafe-deserialization", "critical",
     "pickle.loads/load — arbitrary code execution on untrusted data"),
    (r"""yaml\.load\([^)]*""",
     "unsafe-yaml", "high",
     "yaml.load without SafeLoader — arbitrary code execution"),
    # SQL injection: string-concatenated query
    (r"""(execute|executemany)\([^)]*['\\"]\s*\+""",
     "sql-injection", "critical",
     "SQL query built by string concatenation — SQL injection"),
    # Arbitrary file deletion — only flag when the path is DYNAMIC
    # (concatenated or f-string). os.remove("fixed/path") is legitimate
    # cleanup, not an injection vector.
    (r"""os\.(remove|unlink)\([^)]*['\"]\s*\+""",
     "arbitrary-delete", "high",
     "os.remove/os.unlink with concatenated path — arbitrary file deletion"),
    (r"""os\.(remove|unlink)\([^)]*f['\"]""",
     "arbitrary-delete", "high",
     "os.remove/os.unlink with f-string path — arbitrary file deletion"),
    (r"""shutil\.rmtree\([^)]*['\"]\s*\+""",
     "arbitrary-delete", "high",
     "shutil.rmtree with concatenated path — arbitrary directory deletion"),
    # Hardcoded credentials (in code, not tests)
    (r"""(password|passwd|secret|api[_-]?key|token)\s*=\s*['\"][^'\"]{12,}['\"]""",
     "hardcoded-credential", "high",
     "hardcoded credential literal (12+ chars)"),
]

# Code constructs that indicate the value is NOT attacker-controlled
# (e.g. os.remove("config.old") with a literal path is benign).
_SAFE_CALLER_PREFIX = r"(?:#|//)\s*"


def detect_static_security_patterns(file_path: str, lines: list[str]) -> list[dict]:
    """Detect classic OWASP static vulnerability patterns in code.

    Code-only: skips docs/configs/prose. Patterns are regex-based on
    source lines; a finding is emitted per matching line with its
    real line number so the gate message points at the offending code.
    """
    suffix = Path(file_path).suffix
    if suffix not in {".py", ".js", ".jsx", ".ts", ".tsx", ".rb", ".php"}:
        return []
    findings = []
    skip_lines = _string_only_lines(lines)
    for lineno, line in enumerate(lines, 1):
        stripped = line.rstrip("\n")
        if lineno in skip_lines:
            continue
        # Skip pure comments and docstring-ish lines
        if stripped.lstrip().startswith(("#", "//", "/*", "*", "'''", '"""')):
            continue
        # Inline exemption: `# adversarial-ignore: <pattern>` (or * for all)
        # on the SAME line as the code suppresses findings for that line —
        # strict by default, documented override only.
        ignore_marker = re.search(
            r"#\s*adversarial-ignore:\s*([\w-]+|\*)", stripped
        )
        for regex, name, severity, detail in STATIC_SECURITY_PATTERNS:
            if ignore_marker and (
                ignore_marker.group(1) == "*" or ignore_marker.group(1) == name
            ):
                continue
            try:
                if re.search(regex, stripped):
                    findings.append({
                        "finding_id": next_finding_id(),
                        "technique": "static-pattern",
                        "pattern": name,
                        "severity": severity,
                        "detail": detail,
                        "file": Path(file_path).name,
                        "line": lineno,
                        "code": stripped.strip()[:120],
                    })
            except re.error:
                continue  # never let a bad pattern crash the gate

    # f-string SQL: flag only when the f-string interpolates a NON-constant.
    # execute(f"...{EMBED_DIMS}...") with an all-caps module constant is
    # legitimate; execute(f"...{user_id}...") is injection. Multi-line
    # f-strings need statement-level scanning.
    findings.extend(_detect_fstring_sql(file_path, lines, skip_lines))
    return findings


_FSTRING_SQL_START = re.compile(
    r"(execute|executemany)\([^)]*f(['\"]{1,3})", re.IGNORECASE,
)


def _detect_fstring_sql(file_path: str, lines: list[str], skip_lines: set[int]) -> list[dict]:
    """Scan f-string SQL for NON-constant interpolation.

    A single-line regex cannot see interpolations inside a triple-quoted
    f-string (the execute( line and the {var} lines differ), so we walk
    the statement: open quote, collect body until the matching close, and
    flag only when a {…} expression contains a lowercase identifier (a
    runtime value) rather than an all-caps constant.
    """
    findings = []
    for lineno, line in enumerate(lines, 1):
        stripped = line.rstrip("\n")
        if lineno in skip_lines or stripped.lstrip().startswith("#"):
            continue
        m = _FSTRING_SQL_START.search(stripped)
        if not m:
            continue
        if _line_exempt(stripped, "sql-injection"):
            continue
        quote = m.group(2)
        qpos = stripped.find(quote, m.end() - len(quote))
        if qpos == -1:
            continue
        body = stripped[qpos + len(quote):]
        if quote in ("'''", '"""'):
            close = body.find(quote)
            consumed = lineno
            while close == -1 and consumed < len(lines):
                consumed += 1
                body += lines[consumed - 1].rstrip("\n")
                close = body.rfind(quote)
        interps = re.findall(r"\{([^{}]+)\}", body)
        dynamic = [e for e in interps
                   if re.search(r"[a-z_]", e) and not re.fullmatch(r"[A-Z0-9_]+", e)]
        if not dynamic:
            continue  # no interpolation, or only constants — safe
        findings.append({
            "finding_id": next_finding_id(),
            "technique": "static-pattern",
            "pattern": "sql-injection",
            "severity": "high",
            "detail": ("SQL query built by f-string with dynamic interpolation "
                       f"({', '.join(dynamic[:3])}) — SQL injection"),
            "file": Path(file_path).name,
            "line": lineno,
            "code": stripped.strip()[:120],
        })
    return findings


# ── Phase 2c: State Corruption + Dependency Sabotage (A3) ─────────
# A3 attacks the STATE layer: mutation points that can silently lose
# data or crash mid-operation, and external dependencies that can hang
# or fail. Static detection flags the ANTIPATTERNS; runtime simulation
# (monkey-patching the call to raise) is documented in the skill.

# Inline exemption helper shared by all A3/A4 detectors.
def _line_exempt(stripped: str, pattern: str) -> bool:
    """True if the line carries `# adversarial-ignore: <pattern|*>`."""
    m = re.search(r"#\s*adversarial-ignore:\s*([\w-]+|\*)", stripped)
    return bool(m and (m.group(1) == "*" or m.group(1) == pattern))


def _string_only_lines(lines: list[str]) -> set[int]:
    """Line numbers (1-based) whose content lies ENTIRELY inside a
    triple-quoted string (docstrings, embedded snippet blobs).

    Corpus files store PHP/Ruby/JS example snippets inside triple-quoted
    Python strings; a line-based scanner must not flag snippet content as
    if it were our code. Tracks ''' and \"\"\" state per line; a line that
    opens and closes on the same line, or has code before the opening
    quote, is treated as code.
    """
    inside = set()
    in_tq: str | None = None
    for i, raw in enumerate(lines, 1):
        s = raw.rstrip("\n")
        if in_tq:
            idx = s.find(in_tq)
            if idx == -1:
                inside.add(i)
                continue
            s = s[idx + 3:]
            in_tq = None
        stripped = s.strip()
        if stripped.startswith(('"""', "'''")):
            tq = stripped[:3]
            rest = stripped[3:]
            if tq in rest:
                continue  # opens and closes same line — trailing content is code
            in_tq = tq
            inside.add(i)
            continue
        # Inline triple-quote open with content after it (e.g. SNIPPETS = ["""...)
        for tq in ('"""', "'''"):
            idx = s.find(tq)
            if idx != -1:
                rest = s[idx + 3:]
                if tq in rest:
                    s = rest[rest.find(tq) + 3:]
                else:
                    in_tq = tq
                break
    return inside


def _func_bodies(lines: list[str]) -> list[dict]:
    """Return function bodies as {name, start, end, params, text} by indentation."""
    bodies = []
    for lineno, line in enumerate(lines, 1):
        m = re.match(r"^(async\s+)?def\s+(\w+)\s*\((.*)\)\s*:", line.strip())
        if not m:
            continue
        name = m.group(2)
        params = [p.strip().split(":")[0].strip().split("=")[0].strip()
                  for p in re.split(r",\s*(?![^()]*\))", m.group(3))
                  if p.strip() and p.strip() not in ("self", "cls")]
        indent = len(line) - len(line.lstrip())
        body_lines = []
        end = lineno
        for j in range(lineno, len(lines)):
            nxt = lines[j]
            if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= indent:
                break
            body_lines.append(nxt.rstrip("\n"))
            end = j + 1
        bodies.append({"name": name, "params": params, "start": lineno,
                       "end": end, "text": "\n".join(body_lines)})
    return bodies


# State-mutation calls (db/session/cursor objects). A commit without any
# try/except in the enclosing function means a mid-operation failure
# leaves the state half-written with no rollback path.
_STATE_MUTATION_RE = re.compile(
    r"\.(commit|flush)\(\)|\.save\(\)",
)
# Network dependencies that can hang indefinitely without a timeout.
_DEP_NO_TIMEOUT_RE = re.compile(
    r"(requests|httpx|aiohttp)\.(get|post|put|delete|patch|head|request)\("
    r"|urllib\.request\.urlopen\(",
)
_SUBPROCESS_RE = re.compile(
    r"subprocess\.(run|call|check_output|check_call|Popen)\(",
)


def detect_state_corruption_patterns(file_path: str, lines: list[str]) -> list[dict]:
    """Detect A3 state-corruption / dependency-sabotage antipatterns.

    Code-only. Three patterns:
      - state-mutation-unhandled (medium): .commit()/.flush()/.save() with
        no try/except in the enclosing function — half-written state on failure.
      - dep-timeout-missing (medium): requests/httpx/aiohttp/urllib call with
        no timeout= on the same line — unbounded hang risk.
      - subprocess-no-timeout (low): subprocess call with no timeout=.
    """
    if Path(file_path).suffix not in {".py", ".pyw"}:
        return []
    findings = []
    bodies = _func_bodies(lines)
    skip_lines = _string_only_lines(lines)

    # Pattern 1: state mutation outside try/except
    for lineno, line in enumerate(lines, 1):
        stripped = line.rstrip("\n")
        if lineno in skip_lines:
            continue
        if stripped.lstrip().startswith(("#", "//", "/*", "*", "'''", '"""')):
            continue
        if not _STATE_MUTATION_RE.search(stripped):
            continue
        if _line_exempt(stripped, "state-mutation-unhandled"):
            continue
        # Find enclosing function; if none (module level), assume unhandled
        # unless the file has a try/except somewhere.
        enclosing = next((b for b in bodies if b["start"] < lineno <= b["end"]), None)
        if enclosing and re.search(r"\btry\s*:", enclosing["text"]):
            continue
        if not enclosing and re.search(r"\btry\s*:", "\n".join(lines)):
            continue
        findings.append({
            "finding_id": next_finding_id(),
            "technique": "state-corruption",
            "pattern": "state-mutation-unhandled",
            "severity": "medium",
            "detail": f"{stripped.strip()[:80]} — no error handling; failure leaves partial state",
            "file": Path(file_path).name,
            "line": lineno,
            "code": stripped.strip()[:120],
        })

    # Pattern 2: network dependency without timeout
    for lineno, line in enumerate(lines, 1):
        stripped = line.rstrip("\n")
        if lineno in skip_lines:
            continue
        if stripped.lstrip().startswith(("#", "//", "/*", "*", "'''", '"""')):
            continue
        if not _DEP_NO_TIMEOUT_RE.search(stripped):
            continue
        if "timeout" in stripped or _line_exempt(stripped, "dep-timeout-missing"):
            continue
        findings.append({
            "finding_id": next_finding_id(),
            "technique": "dependency-sabotage",
            "pattern": "dep-timeout-missing",
            "severity": "medium",
            "detail": f"{stripped.strip()[:80]} — no timeout; network hang blocks forever",
            "file": Path(file_path).name,
            "line": lineno,
            "code": stripped.strip()[:120],
        })

    # Pattern 3: subprocess without timeout
    for lineno, line in enumerate(lines, 1):
        stripped = line.rstrip("\n")
        if lineno in skip_lines:
            continue
        if stripped.lstrip().startswith(("#", "//", "/*", "*", "'''", '"""')):
            continue
        if not _SUBPROCESS_RE.search(stripped):
            continue
        if "timeout" in stripped or _line_exempt(stripped, "subprocess-no-timeout"):
            continue
        findings.append({
            "finding_id": next_finding_id(),
            "technique": "dependency-sabotage",
            "pattern": "subprocess-no-timeout",
            "severity": "low",
            "detail": f"{stripped.strip()[:80]} — no timeout; child process can hang forever",
            "file": Path(file_path).name,
            "line": lineno,
            "code": stripped.strip()[:120],
        })

    return findings


# ── Phase 2d: Concurrency + Invariants + Property-Based (A4) ──────

_THREADING_RE = re.compile(
    r"import\s+threading|from\s+threading|threading\.|Thread\(|ThreadPoolExecutor\("
    r"|import\s+asyncio|from\s+asyncio|asyncio\.|async\s+def"
    r"|import\s+multiprocessing|multiprocessing\.|Process\(",
)
_LOCK_RE = re.compile(r"\.lock\(|Lock\(\)|RLock\(|Semaphore\(|with\s+\w*_?lock\b")
_GLOBAL_MUTATION_RE = re.compile(r"\b(\w+)\s*(\+=|-=|\*=|/=|\^=|\|=|&=|<<=|>>=|=)")


def detect_concurrency_patterns(file_path: str, lines: list[str]) -> list[dict]:
    """Detect A4 concurrency antipatterns.

    Code-only. Two patterns:
      - shared-global-race (high): a `global X` declaration whose X is
        mutated inside a function, in a file that uses threads/async, with
        NO lock anywhere — classic lost-update race on shared state.
      - toctou-delete (medium): os.path.exists(P) followed by
        os.remove/unlink/rmtree(P) in the same function — check-then-act
        race; the path can change between check and delete.
    """
    if Path(file_path).suffix not in {".py", ".pyw"}:
        return []
    findings = []
    content = "\n".join(lines)
    skip_lines = _string_only_lines(lines)

    # Threading evidence must come from CODE, not regex-literal lines
    # (e.g. a pattern table containing r"(def |async def )..." would
    # otherwise make the gate flag ITSELF) and not docstring blobs.
    def _strip_code(line: str) -> str:
        """Remove string literals (incl. raw r'') and trailing comments."""
        s = re.sub(r"\b[rRbB]?(['\"])(?:\\.|(?!\1).)*\1", "", line)
        return re.sub(r"#.*$", "", s)

    def _has_threading() -> bool:
        for lineno, line in enumerate(lines, 1):
            if lineno in skip_lines:
                continue
            if _THREADING_RE.search(_strip_code(line)):
                return True
        return False

    # Pattern 1: shared mutable global in a threaded file, no lock
    if _has_threading() and not _LOCK_RE.search(content):
        for lineno, line in enumerate(lines, 1):
            stripped = line.rstrip("\n")
            m = re.match(r"^\s*global\s+([\w, ]+)", stripped)
            if not m:
                continue
            if lineno in skip_lines:
                continue
            if _line_exempt(stripped, "shared-global-race"):
                continue
            names = [n.strip() for n in m.group(1).split(",")]
            mutated = []
            for name in names:
                for l2 in lines:
                    mm = re.search(rf"\b{re.escape(name)}\b\s*(\+=|-=|\*=|/=|=)", _strip_code(l2))
                    if mm and f"global {name}" not in l2:
                        mutated.append(name)
                        break
            if mutated:
                findings.append({
                    "finding_id": next_finding_id(),
                    "technique": "concurrency",
                    "pattern": "shared-global-race",
                    "severity": "high",
                    "detail": (f"global {', '.join(mutated)} mutated in threaded file "
                               "with no lock — lost-update race"),
                    "file": Path(file_path).name,
                    "line": lineno,
                    "code": stripped.strip()[:120],
                })

    # Pattern 2: check-then-delete TOCTOU within the same function
    for body in _func_bodies(lines):
        body_lines = body["text"].split("\n")
        base = body["start"]
        checked = {}  # var name -> first check line (relative)
        for i, bl in enumerate(body_lines):
            if base + i in skip_lines:
                continue
            m = re.search(r"os\.path\.(exists|isfile|isdir)\(\s*([\w.\[\]]+)\s*\)", bl)
            if m:
                checked.setdefault(m.group(2), i)
        for i, bl in enumerate(body_lines):
            if base + i in skip_lines:
                continue
            m = re.search(r"os\.(remove|unlink)\(\s*([\w.\[\]]+)\s*\)|shutil\.rmtree\(\s*([\w.\[\]]+)\s*\)", bl)
            if not m:
                continue
            var = m.group(2) or m.group(3)
            if var in checked and not _line_exempt(bl, "toctou-delete"):
                findings.append({
                    "finding_id": next_finding_id(),
                    "technique": "concurrency",
                    "pattern": "toctou-delete",
                    "severity": "medium",
                    "detail": (f"os.path.exists({var}) then delete — TOCTOU race; "
                               "path can change between check and delete"),
                    "file": Path(file_path).name,
                    "line": base + i,
                    "code": bl.strip()[:120],
                })
    return findings


# Invariant violations: implicit assumptions the code makes that a
# boundary input can break.
_DIVISION_RE = re.compile(r"/\s*([a-zA-Z_]\w*)")


def detect_invariant_patterns(file_path: str, lines: list[str]) -> list[dict]:
    """Detect A4 invariant violations.

    Code-only. Two patterns:
      - unguarded-division (medium): dividing by a function parameter with
        no zero-check (`if x == 0`, `if not x`) and no ZeroDivisionError
        handler in the function — crashes on zero input.
      - bare-dict-access (low): `d[key]` on a parameter without .get() —
        KeyError on missing key.
    """
    if Path(file_path).suffix not in {".py", ".pyw"}:
        return []
    findings = []
    bodies = _func_bodies(lines)
    skip_lines = _string_only_lines(lines)

    for body in bodies:
        body_lines = body["text"].split("\n")
        base = body["start"]
        has_zero_guard = bool(
            re.search(r"\bif\s+(not\s+)?\w+\s*(==\s*0|is\s+None|<=?\s*0)\b"
                      r"|except\s+(ZeroDivisionError|Exception)", body["text"])
        )
        # Pattern 1: division by param without guard
        for i, bl in enumerate(body_lines):
            if base + i in skip_lines:
                continue
            if bl.lstrip().startswith("#"):
                continue
            if "//" in bl and "://" not in bl:
                continue
            for pn in body["params"]:
                if not re.search(rf"/\s*\(?\s*{re.escape(pn)}\b", bl):
                    continue
                if _line_exempt(bl, "unguarded-division"):
                    continue
                if has_zero_guard:
                    continue
                findings.append({
                    "finding_id": next_finding_id(),
                    "technique": "invariant",
                    "pattern": "unguarded-division",
                    "severity": "medium",
                    "detail": f"{bl.strip()[:80]} — division by param '{pn}' with no zero-guard",
                    "file": Path(file_path).name,
                    "line": base + i,
                    "code": bl.strip()[:120],
                })
                break
        # Pattern 2: bare dict access on a parameter
        for i, bl in enumerate(body_lines):
            if base + i in skip_lines:
                continue
            if bl.lstrip().startswith("#"):
                continue
            if ".get(" in bl:
                continue
            for pn in body["params"]:
                if re.search(rf"\b{re.escape(pn)}\[[\"']", bl) and _line_exempt(bl, "bare-dict-access"):
                    break
                if not re.search(rf"\b{re.escape(pn)}\[[\"']", bl):
                    continue
                findings.append({
                    "finding_id": next_finding_id(),
                    "technique": "invariant",
                    "pattern": "bare-dict-access",
                    "severity": "low",
                    "detail": f"{bl.strip()[:80]} — bare dict access on '{pn}'; KeyError if key missing",
                    "file": Path(file_path).name,
                    "line": base + i,
                    "code": bl.strip()[:120],
                })
                break
    return findings


# Property-based breaking (A4): for PURE functions, emit property
# templates the implementer can falsify (determinism, idempotence,
# roundtrip). Static tool cannot execute — it packages the properties.
_IMPURE_RE = re.compile(
    r"\b(open|print|input|exec|eval)\s*\(|os\.|sys\.|subprocess|requests|httpx"
    r"|\.write\(|\.commit\(|random\.|datetime\.now|time\.time|uuid\.|global\s",
)


def generate_property_checks(file_path: str, lines: list[str]) -> list[dict]:
    """Emit A4 property-based templates for pure functions (info severity).

    A function is 'pure' when it takes at least one parameter, returns a
    value, and touches no I/O / time / randomness / global state. For each
    such function, an info finding lists falsifiable properties.
    """
    if Path(file_path).suffix not in {".py", ".pyw"}:
        return []
    findings = []
    skip_lines = _string_only_lines(lines)
    for body in _func_bodies(lines):
        if body["start"] in skip_lines:
            continue
        text = body["text"]
        if not body["params"]:
            continue
        if not re.search(r"\breturn\b", text):
            continue
        if _IMPURE_RE.search(text):
            continue
        props = [
            f"determinism: {body['name']}(x) == {body['name']}(x) for same x",
            f"idempotence: {body['name']}({body['name']}(x)) == {body['name']}(x)",
            "boundary: survives -1, 0, 1, huge, None, nan, inf inputs",
        ]
        findings.append({
            "finding_id": next_finding_id(),
            "technique": "property-based",
            "pattern": "property-template",
            "severity": "info",
            "detail": f"pure function '{body['name']}()' — falsify: " + "; ".join(props),
            "file": Path(file_path).name,
            "line": body["start"],
            "code": text.strip().splitlines()[0][:120] if text.strip() else body["name"],
        })
    return findings


# ── Level dispatch ────────────────────────────────────────────────

def run_level(filepath: str, level: str) -> list[dict]:
    """Run all detectors for a maturity level on a single file.

    A1: surface only (no findings emitted — enumeration only).
    A2: fuzz + cheat + static OWASP patterns.
    A3: A2 + state corruption + dependency sabotage.
    A4/A5: A3 + concurrency + invariants + property templates.
    """
    findings: list[dict] = []
    try:
        with open(filepath) as f:
            lines = f.readlines()
    except IOError:
        return findings

    if level in ("A2", "A3", "A4", "A5"):
        funcs = _find_func_defs(lines)
        for fuzz in generate_fuzz_inputs(funcs)[:20]:
            findings.append({
                "finding_id": next_finding_id(),
                "technique": "input-fuzzing",
                "target": f"{filepath}:{fuzz['function']}()",
                "parameter": fuzz["parameter"],
                "expected_type": fuzz["expected_type"],
                "value_repr": fuzz["value_repr"],
                "severity": "info" if fuzz["value"] is not None else "medium",
            })
        findings.extend(detect_cheat_patterns(filepath, lines))
        findings.extend(detect_static_security_patterns(filepath, lines))
    if level in ("A3", "A4", "A5"):
        findings.extend(detect_state_corruption_patterns(filepath, lines))
    if level in ("A4", "A5"):
        findings.extend(detect_concurrency_patterns(filepath, lines))
        findings.extend(detect_invariant_patterns(filepath, lines))
        findings.extend(generate_property_checks(filepath, lines))
    return findings


# ── Main ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Adversarial Verification CLI")
    parser.add_argument("--file", "-f", help="File to analyze")
    parser.add_argument("--dir", "-d", help="Directory to analyze (all .py files)")
    parser.add_argument("--level", "-l", choices=["A0", "A1", "A2", "A3", "A4", "A5"],
                        default="A1", help="Adversarial maturity level (default: A1)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--gate", action="store_true",
                        help="Gate mode: block commit if critical/high findings exist (pre-commit hook integration)")
    parser.add_argument("--output", help="Save findings JSON to file")
    args = parser.parse_args()

    if not args.file and not args.dir:
        parser.print_help()
        sys.exit(2)

    # Collect files
    files = []
    if args.file:
        files.append(args.file)
    if args.dir:
        for root, _, filenames in os.walk(args.dir):
            for fn in filenames:
                if fn.endswith(".py") and not fn.startswith("__"):
                    files.append(os.path.join(root, fn))

    if not files:
        print("No files to analyze.", file=sys.stderr)
        sys.exit(2)

    all_findings = []
    all_surfaces = {}

    for filepath in files:
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}", file=sys.stderr)
            continue

        if not args.json:
            print(f"\n── {filepath} ──")
            print(f"   Level: {args.level}")

        # Phase 1: Attack Surface Enumeration (A1+)
        surface = analyze_attack_surface(filepath)
        all_surfaces[filepath] = surface

        totals = {k: len(v) for k, v in surface.items() if k in ("inputs", "state", "dependencies", "concurrency")}

        if not args.json:
            print(f"   Attack Surface:")
            for category in ("inputs", "state", "dependencies", "concurrency"):
                count = totals.get(category, 0)
                icon = "⚠️" if count > 0 else "✅"
                print(f"     {icon} {category.capitalize()}: {count} item(s)")

        if args.level in ("A1",):
            continue

        # Phase 2: Level-dispatched detection (A2+)
        try:
            with open(filepath) as f:
                lines = f.readlines()
        except IOError:
            continue

        level_findings = run_level(filepath, args.level)

        funcs = _find_func_defs(lines)
        fuzz_inputs = generate_fuzz_inputs(funcs)

        if not args.json:
            if funcs:
                print(f"   Functions: {len(funcs)}")
                for fn in funcs[:5]:
                    params = ", ".join(p["name"] for p in fn["params"])
                    print(f"     - {fn['name']}({params})")
                if len(funcs) > 5:
                    print(f"     ... and {len(funcs) - 5} more")
            print(f"   Fuzz inputs generated: {len(fuzz_inputs)}")

        all_findings.extend(level_findings)

    # Phase 3: Evidence Packaging
    summary = {
        "files_analyzed": len(files),
        "level": args.level,
        "total_findings": len(all_findings),
        "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
        "findings": all_findings[:50],
        "surfaces": all_surfaces,
        "timestamp": datetime.now().isoformat(),
    }
    for finding in all_findings:
        sev = finding.get("severity", "info")
        if sev in summary["severity_counts"]:
            summary["severity_counts"][sev] += 1

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        counts = summary["severity_counts"]
        print(f"\n📊 Summary: {len(files)} file(s), {len(all_findings)} finding(s)")
        if any(counts.values()):
            for sev in ("critical", "high", "medium", "low", "info"):
                if counts[sev]:
                    icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}[sev]
                    print(f"   {icon} {sev.capitalize()}: {counts[sev]}")
        else:
            print("   ✅ No findings — but standard tests should still pass!")

        if any(counts.get(s, 0) > 0 for s in ("critical", "high")):
            print("\n🔴 Critical/high findings — block release until resolved.")
        elif any(counts.get(s, 0) > 0 for s in ("medium",)):
            print("\n🟡 Medium findings — fix before shipping.")
        elif all_findings:
            print("\nℹ️  Low/info findings — review before shipping.")

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(summary, indent=2, default=str))
        if not args.json:
            print(f"\n   Findings saved to: {output_path}")

    has_blockers = any(f.get("severity") in ("critical", "high") for f in all_findings)

    if args.gate:
        if has_blockers:
            print("\n🔴 GATE_BLOCKED — critical/high findings detected")
            print("   Pre-commit adversarial gate rejected this change.")
            print("   Fix findings before committing — no bypass flags.")
            print("   Do NOT use git commit --no-verify — it is logged and audited.")
            sys.exit(1)
        else:
            print("\n✅ GATE_PASSED — no critical/high findings")
            sys.exit(0)
    else:
        sys.exit(1 if has_blockers else 0)


if __name__ == "__main__":
    main()
