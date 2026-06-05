#!/usr/bin/env python3
"""
Hermes Cortex — Code Corpus Generator
──────────────────────────────────────
Generates the offline code snippet corpus as structured markdown files.
Each snippet has YAML frontmatter (language, tags, title) and a code block.

Snippets are defined in the snippets/ package — each module exports a SNIPPETS list.
Add a new language by creating a new module under snippets/ and running:

    python3 code-corpus/generate.py

Or at prep time via prep-code.sh.
"""
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from snippets import discover_snippets


def _strip_fences(code):
    """Remove leading/trailing ```lang fences from code strings."""
    # Remove leading fence like ```python or ```csharp or ```zig\n
    code = re.sub(r'^```[a-zA-Z0-9_+#]*\n?', '', code)
    # Remove trailing ``` with optional whitespace
    code = re.sub(r'\n?```\s*$', '', code)
    return code.strip() + '\n'


def generate():
    """Write all snippets to the corpus directory."""
    SNIPPETS = discover_snippets()

    if not SNIPPETS:
        print("  No snippets found in snippets/ package.")
        return 0

    count = 0
    for rel_path, lang, tags, title, desc, source, code in SNIPPETS:
        fp = BASE / rel_path
        fp.parent.mkdir(parents=True, exist_ok=True)

        tags_str = ', '.join(tags)
        # Strip any leading/trailing code fences from snippet code
        code = _strip_fences(code)
        content = f"""---
language: {lang}
tags: [{tags_str}]
title: {title}
description: {desc}
source: {source}
---

```{lang}
{code}
```
"""
        fp.write_text(content)
        count += 1
        print(f"  ✓ {rel_path}")

    # Write an index file
    index = BASE / "INDEX.md"
    lines = ["# Code Corpus Index\n", f"Total snippets: {count}\n", ""]
    lines.append("| # | Language | Title | Tags |")
    lines.append("|---|----------|-------|------|")
    for i, (rel_path, lang, tags, title, desc, _, _) in enumerate(SNIPPETS, 1):
        tag_str = ", ".join(tags[:3])
        lines.append(f"| {i} | {lang} | [{title}]({rel_path}) | {tag_str} |")
    index.write_text("\n".join(lines) + "\n")

    print(f"\n  Generated {count} snippets in {BASE}")
    return count


if __name__ == "__main__":
    generate()
