"""Snippet definition modules.

Each module in this package exports a SNIPPETS list.
generate.py discovers and imports all of them, merges the lists,
and writes the .md files into the corpus directory.

Each snippet: (rel_path, language, tags, title, description, source, code)
  rel_path:  str  — path within corpus dir, e.g. "python/binary-search.md"
  language:  str  — lowercase language name, e.g. "python", "go", "rust"
  tags:      list — ["algorithm", "search", ...]
  title:     str  — short human-readable title
  description: str — one-line description of what the snippet does
  source:    str  — "textbook", "pattern", "framework", "reference"
  code:      str  — the actual code block
"""

import importlib
import pkgutil
from pathlib import Path

BASE = Path(__file__).parent


def discover_snippets():
    """Import all sibling modules and merge their SNIPPETS lists."""
    all_snippets = []
    for mod_info in pkgutil.iter_modules([str(BASE)]):
        if mod_info.name == "__init__":
            continue
        mod = importlib.import_module(f".{mod_info.name}", __package__)
        if hasattr(mod, "SNIPPETS"):
            all_snippets.extend(mod.SNIPPETS)
    return all_snippets
