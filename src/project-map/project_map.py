#!/usr/bin/env python3
"""
Hermes Cortex — Project Map (Static Analysis)
───────────────────────────────────────────────
Builds a dependency graph and structural map for any project.
The agent reads this before making multi-file changes instead
of guessing which files a change affects.

Usage:
  project-map analyze              → Full analysis, write project-map.json
  project-map analyze --watch      → Analyze + watch for changes
  project-map status               → Show current map info
  project-map stats                → Summary stats of project

Output: .hermes-cortex/project-map.json or project-map.json
"""

import argparse
import ast
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Config ──────────────────────────────────────────────────

DEFAULT_EXCLUDES = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".egg-info", "dist", "build", ".next", ".turbo",
    "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "site-packages", ".hermes", ".hermes-cortex/memory", ".gbrain",
}

EXTENSION_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".sql": "sql",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c-header",
    ".css": "css",
    ".scss": "scss",
    ".html": "html",
    ".dockerfile": "docker",
    ".tf": "terraform",
    ".nix": "nix",
}

FRAMEWORK_PATTERNS = {
    "fastapi": [r"from fastapi import", r"from fastapi\.", r"FastAPI\(\)"],
    "flask": [r"from flask import", r"Flask\("],
    "django": [r"django\.", r"from django", r"DJANGO_SETTINGS"],
    "react": [r"from react", r"import React", r"createRoot"],
    "nextjs": [r"next/", r"create-next-app"],
    "express": [r"express\(\)", r"from express"],
    "spring": [r"@SpringBoot", r"org\.springframework"],
    "rails": [r"Rails\.", r"rails new"],
    "docker": [r"FROM\s+\w+", r"docker-compose"],
    "vue": [r"from vue", r"createApp", r"<template>"],
    "svelte": [r"svelte", r"<script.*context=\"module\""],
}

ROUTE_DECORATORS = [
    r"app\.(get|post|put|delete|patch|route)",
    r"router\.(get|post|put|delete|patch|route)",
]


# ── Core Analysis ───────────────────────────────────────────

def analyze_project(project_root: str) -> dict:
    """Full project analysis. Returns structured project map."""
    root = Path(project_root).resolve()
    if not root.exists():
        return {"error": f"Path not found: {root}"}

    files = _discover_files(root)
    modules = []
    entry_points = []
    route_patterns = []
    models = []
    tests = []
    all_imports = {}
    dep_graph = defaultdict(list)
    reverse_dep_graph = defaultdict(list)
    languages = defaultdict(int)
    total_lines = 0

    for file_path in files:
        rel = file_path.relative_to(root)
        ext = file_path.suffix.lower()
        lang = EXTENSION_LANGUAGES.get(ext, "other") if ext else "other"

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            lines = content.count("\n") + 1
            total_lines += lines
            languages[lang] += 1

            # Detect entry points
            if file_path.name in ("main.py", "app.py", "index.js", "index.ts",
                                   "server.js", "server.ts", "cli.py", "main.go",
                                   "install.sh", "Dockerfile"):
                entry_points.append(str(rel))

            # Detect Dockerfiles (case-insensitive)
            if file_path.name.upper() == "DOCKERFILE" or file_path.name.endswith(".dockerfile"):
                entry_points.append(str(rel))

            # Parse imports based on language
            if lang == "python":
                _analyze_python(file_path, content, rel, modules, route_patterns,
                                models, tests, all_imports)

            elif lang in ("javascript", "typescript"):
                _analyze_js_ts(file_path, content, rel, modules, route_patterns,
                               tests, all_imports, lang)

            elif lang == "go":
                _analyze_generic(file_path, content, rel, modules, r'import\s+\(', r'func\s+\w+', tests)

            elif lang == "rust":
                _analyze_generic(file_path, content, rel, modules, r'use\s+\w+', r'fn\s+\w+', tests)

            elif lang in ("yaml", "json"):
                _check_config_files(file_path, content, rel, modules)

            else:
                # Shell, SQL, etc.
                _analyze_generic(file_path, content, rel, modules,
                                 r'^#\s*(include|import|source)\s+', r'^\w+\s*\(\)\s*\{', tests)

        except Exception as e:
            modules.append({
                "path": str(rel),
                "type": "error",
                "error": str(e),
            })

    # Build dependency graph
    for mod in modules:
        path = mod["path"]
        for imp in mod.get("imports", []):
            dep_graph[str(path)].append(imp)
            reverse_dep_graph[imp].append(str(path))

    # Detect framework
    framework = _detect_framework(modules)

    # Find .hermes-cortex dir
    hc_dir = root / ".hermes-cortex"
    has_hc = hc_dir.exists()

    return {
        "project": root.name,
        "root": str(root),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "has_hermes_cortex": has_hc,
        "stats": {
            "files": len(files),
            "lines": total_lines,
            "languages": dict(sorted(languages.items(), key=lambda x: -x[1])),
            "modules": len(modules),
            "tests": len(tests),
            "routes": len(route_patterns),
            "models": len(models),
            "entry_points": len(entry_points),
        },
        "framework": framework,
        "entry_points": sorted(set(entry_points)),
        "routes": route_patterns,
        "models": models,
        "tests": tests,
        "modules": modules,
        "dependency_graph": dict(dep_graph),
        "reverse_dep_graph": dict(reverse_dep_graph),
    }


def _discover_files(root: Path, max_files: int = 2000) -> list:
    """Discover project files, respecting common excludes."""
    files = []
    excluded_names = DEFAULT_EXCLUDES | {".git"}  # always exclude .git

    try:
        for path in root.rglob("*"):
            # Skip any path inside an excluded directory
            if any(part in excluded_names for part in path.parts):
                continue
            if path.is_file():
                # Skip hidden files at root level except allowed ones
                if path.name.startswith(".") and path.parent == root:
                    if path.name not in (".hermes-cortex", ".github"):
                        continue
                ext = path.suffix.lower()
                if ext in EXTENSION_LANGUAGES or not ext:
                    files.append(path)
                if len(files) >= max_files:
                    break
    except PermissionError:
        pass
    return files


# ── Per-Language Analyzers ──────────────────────────────────

def _analyze_python(file_path: Path, content: str, rel: Path,
                    modules: list, routes: list, models: list,
                    tests: list, all_imports: dict):
    """Analyze a Python file using AST."""
    imports = []
    functions = []
    classes = []
    is_test = False

    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError:
        modules.append({"path": str(rel), "type": "python", "imports": [], "error": "syntax_error"})
        return

    for node in ast.walk(tree):
        # Imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

        # Functions
        elif isinstance(node, ast.FunctionDef):
            func_info = {"name": node.name, "line": node.lineno}
            # Check decorators
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call):
                    if isinstance(dec.func, ast.Attribute):
                        dec_name = f"{ast.unparse(dec.func)}"
                        func_info["decorator"] = dec_name
                        # Check for route decorators
                        for pattern in ROUTE_DECORATORS:
                            if re.search(pattern, dec_name):
                                route_info = {
                                    "path": str(rel),
                                    "function": node.name,
                                    "line": node.lineno,
                                    "decorator": dec_name,
                                }
                                # Try to extract URL from decorator args
                                if dec.args:
                                    try:
                                        route_info["url"] = ast.literal_eval(dec.args[0])
                                    except Exception:
                                        pass
                                routes.append(route_info)
            functions.append(func_info)

        # Classes
        elif isinstance(node, ast.ClassDef):
            class_info = {"name": node.name, "line": node.lineno}
            # Check bases
            for base in node.bases:
                try:
                    class_info.setdefault("bases", []).append(ast.unparse(base))
                except Exception:
                    pass
            # Check for Pydantic/DB model patterns
            bases_str = " ".join(class_info.get("bases", []))
            if any(x in bases_str for x in ("BaseModel", "Model", "Document", "db.Model", "DeclarativeBase")):
                fields = []
                for item in ast.iter_child_nodes(node):
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        try:
                            ann = ast.unparse(item.annotation) if item.annotation else "?"
                            fields.append({"name": item.target.id, "type": ann})
                        except Exception:
                            fields.append({"name": item.target.id, "type": "?"})
                model_info = {
                    "path": str(rel),
                    "name": node.name,
                    "line": node.lineno,
                    "bases": class_info.get("bases", []),
                    "fields": fields,
                }
                models.append(model_info)
            classes.append(class_info)

        # Test detection
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            if node.name.startswith("test") or node.name.endswith("Test"):
                is_test = True

    mod_type = "test" if is_test else "module"
    modules.append({
        "path": str(rel),
        "type": mod_type,
        "language": "python",
        "imports": imports,
        "functions": functions,
        "classes": classes,
        "lines": content.count("\n") + 1 if content else 0,
    })
    if is_test:
        tests.append(str(rel))

    all_imports[str(rel)] = imports


def _analyze_js_ts(file_path: Path, content: str, rel: Path,
                   modules: list, routes: list, tests: list,
                   all_imports: dict, lang: str):
    """Analyze JS/TS files with regex."""
    imports = []
    functions = []
    classes = []
    is_test = False

    # Extract imports
    for m in re.finditer(r'(?:import|require)\s+[\s\S]*?(?:from\s+)?[\'"]([^\'"]+)[\'"]', content):
        imports.append(m.group(1))

    # Extract functions
    for m in re.finditer(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(', content):
        functions.append({"name": m.group(1), "line": content[:m.start()].count("\n") + 1})

    # Arrow functions
    for m in re.finditer(r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(', content):
        functions.append({"name": m.group(1), "line": content[:m.start()].count("\n") + 1, "style": "arrow"})

    # Extract classes
    for m in re.finditer(r'(?:export\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?', content):
        c = {"name": m.group(1), "line": content[:m.start()].count("\n") + 1}
        if m.group(2):
            c["extends"] = m.group(2)
        classes.append(c)

    # Express/Next routes
    for m in re.finditer(r'(?:router|app)\.(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)[\'"]', content):
        routes.append({
            "path": str(rel),
            "method": m.group(1),
            "url": m.group(2),
            "line": content[:m.start()].count("\n") + 1,
        })

    # Test detection
    if re.search(r'(describe|it|test|expect)\s*\(', content):
        is_test = True

    mod_type = "test" if is_test else "module"
    modules.append({
        "path": str(rel),
        "type": mod_type,
        "language": lang,
        "imports": imports,
        "functions": functions,
        "classes": classes,
        "lines": content.count("\n") + 1 if content else 0,
    })
    if is_test:
        tests.append(str(rel))

    all_imports[str(rel)] = imports


def _analyze_generic(file_path: Path, content: str, rel: Path,
                     modules: list, import_pattern: str,
                     func_pattern: str, tests: list):
    """Generic analyzer for languages without dedicated parsers."""
    imports = []
    functions = []

    for m in re.finditer(import_pattern, content, re.MULTILINE):
        imports.append(content[m.start():m.end()].strip()[:80])

    for m in re.finditer(func_pattern, content):
        functions.append({"name": m.group(1), "line": content[:m.start()].count("\n") + 1})

    modules.append({
        "path": str(rel),
        "type": "module",
        "imports": imports,
        "functions": functions,
        "classes": [],
        "lines": content.count("\n") + 1 if content else 0,
    })


def _check_config_files(file_path: Path, content: str, rel: Path, modules: list):
    """Analyze YAML/JSON config files for structure."""
    info = {"path": str(rel), "type": "config", "imports": []}
    ext = file_path.suffix.lower()

    if ext == ".json":
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                info["keys"] = list(data.keys())[:20]
            elif isinstance(data, list):
                info["items"] = len(data)
        except json.JSONDecodeError:
            pass

    elif ext in (".yml", ".yaml"):
        # Basic YAML structure detection
        top_keys = set()
        for m in re.finditer(r'^(\w[\w-]*):', content, re.MULTILINE):
            top_keys.add(m.group(1))
        if top_keys:
            info["keys"] = list(top_keys)[:20]

        # Detect Docker Compose
        if "services" in top_keys:
            info["type"] = "docker-compose"
        # Detect GitHub Actions
        if "jobs" in top_keys or "steps" in top_keys:
            info["type"] = "github-actions"

    modules.append(info)


# ── Framework Detection ──────────────────────────────────────

def _detect_framework(modules: list) -> dict:
    """Detect frameworks used in the project."""
    all_text = ""
    for mod in modules:
        all_text += json.dumps(mod)

    detected = {}
    for framework, patterns in FRAMEWORK_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, all_text, re.IGNORECASE):
                detected[framework] = detected.get(framework, 0) + 1
                break

    return {
        "primary": max(detected, key=detected.get) if detected else None,
        "all": dict(sorted(detected.items(), key=lambda x: -x[1])),
    }


# ── CLI ──────────────────────────────────────────────────────

def _find_project_root(start: str = None) -> Path:
    """Walk up from cwd to find project root (has .git or .hermes-cortex)."""
    start = Path(start or os.getcwd()).resolve()
    for parent in [start] + list(start.parents):
        if (parent / ".git").exists() or (parent / ".hermes-cortex").exists():
            return parent
        # Also check for common project files
        if (parent / "package.json").exists() or (parent / "pyproject.toml").exists() or \
           (parent / "setup.py").exists() or (parent / "Cargo.toml").exists() or \
           (parent / "go.mod").exists() or list(parent.glob("*.sln")):
            return parent
    return start


def _write_map(project_root: Path, data: dict):
    """Write project map to .hermes-cortex/ or project root."""
    hc_dir = project_root / ".hermes-cortex"
    if not hc_dir.exists():
        hc_dir.mkdir(parents=True, exist_ok=True)

    map_path = hc_dir / "project-map.json"

    # Prune bulky embeddings for storage (only keep summary)
    output = {
        "project": data["project"],
        "root": data["root"],
        "analyzed_at": data["analyzed_at"],
        "has_hermes_cortex": data["has_hermes_cortex"],
        "stats": data["stats"],
        "framework": data["framework"],
        "entry_points": data["entry_points"],
        "routes": data["routes"],
        "models": data["models"],
        "tests": data["tests"],
        # Modules keep only path, type, language
        "modules": [{"path": m["path"], "type": m.get("type"), "language": m.get("language")}
                    for m in data["modules"]],
        # Keep full dep graph
        "dependency_graph": data["dependency_graph"],
        "reverse_dep_graph": data["reverse_dep_graph"],
    }

    map_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    return str(map_path)


def _format_status(data: dict) -> str:
    """Human-readable status of a project."""
    s = data.get("stats", {})
    fw = data.get("framework", {})
    lines = [
        f"📁 Project:  {data.get('project', '?')}",
        f"   Files:    {s.get('files', 0)} ({s.get('lines', 0)} lines)",
        f"   Modules:  {s.get('modules', 0)}",
        f"   Routes:   {s.get('routes', 0)}",
        f"   Models:   {s.get('models', 0)}",
        f"   Tests:    {s.get('tests', 0)}",
        f"   Entry:    {len(data.get('entry_points', []))} point(s)",
    ]
    if fw.get("primary"):
        lines.append(f"   Framework: {fw['primary']}")
    if data.get("routes"):
        lines.append(f"\n   🛣️  Routes:")
        for r in data["routes"][:10]:
            url = r.get("url", r.get("method", "?"))
            lines.append(f"      {r['path']}:{r.get('function', r.get('function', '?'))} → /{url}")
    if data.get("models"):
        lines.append(f"\n   📐 Models:")
        for m in data["models"][:10]:
            fields = len(m.get("fields", []))
            lines.append(f"      {m['name']} ({fields} fields) @ {m['path']}")
    return "\n".join(lines)


def main(args: Optional[list] = None):
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="project-map",
        description="Build a structural map of any project — imports, routes, models, dependencies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # analyze
    ap = sub.add_parser("analyze", help="Full project analysis")
    ap.add_argument("path", nargs="?", default=None, help="Project root path (default: auto-detect)")
    ap.add_argument("--output", "-o", help="Output path (default: .hermes-cortex/project-map.json)")

    # status
    sp = sub.add_parser("status", help="Show current project map")
    sp.add_argument("path", nargs="?", default=None, help="Project root path")

    # stats
    stp = sub.add_parser("stats", help="Quick project stats (no analysis, just file counting)")
    stp.add_argument("path", nargs="?", default=None, help="Project root path")

    parsed = parser.parse_args(args)

    if not parsed.command:
        parser.print_help()
        return

    # Resolve project root
    if parsed.path:
        proj_root = Path(parsed.path).resolve()
    else:
        proj_root = _find_project_root()

    if parsed.command == "analyze":
        print(f"🔍 Analyzing project: {proj_root.name}")
        print(f"   Root: {proj_root}")
        data = analyze_project(str(proj_root))
        if "error" in data:
            print(f"❌ {data['error']}")
            sys.exit(1)

        out_path = _write_map(proj_root, data)
        print(f"✅ Written: {out_path}")
        print(f"\n{_format_status(data)}")

    elif parsed.command == "status":
        # Read existing map
        candidates = [
            proj_root / ".hermes-cortex" / "project-map.json",
            proj_root / "project-map.json",
        ]
        for c in candidates:
            if c.exists():
                data = json.loads(c.read_text(encoding="utf-8"))
                print(f"\n📋 Project Map ({c.name})")
                print(f"   Last analyzed: {data.get('analyzed_at', '?')[:19]}")
                print(f"\n{_format_status(data)}")
                return
        print(f"📭 No project map found for {proj_root}")
        print("   Run: project-map analyze")

    elif parsed.command == "stats":
        files = _discover_files(proj_root)
        lang_count = defaultdict(int)
        total_lines = 0
        for f in files:
            ext = f.suffix.lower()
            lang = EXTENSION_LANGUAGES.get(ext, "other")
            lang_count[lang] += 1
            try:
                total_lines += len(f.read_text(encoding="utf-8", errors="replace").splitlines())
            except Exception:
                pass

        print(f"\n📊 Project Stats: {proj_root.name}")
        print(f"   Root: {proj_root}")
        print(f"   Total files: {len(files)}")
        print(f"   Total lines: {total_lines:,}")
        print(f"\n   Languages:")
        for lang, count in sorted(lang_count.items(), key=lambda x: -x[1])[:15]:
            print(f"     {lang:15s} {count}")
        print()
        print(f"   Run 'project-map analyze' for full analysis (routes, models, dependencies).")
        print()


if __name__ == "__main__":
    main()
