#!/usr/bin/env python3
"""
merge-agents-md.py — Merge project-specific sections into seeded AGENTS.md

Usage:
  python3 merge-agents-md.py <old-file> < new-template.md

Reads the old AGENTS.md, identifies any H2+ sections that aren't part of the
standard template (plus customized Commands and Project Notes content), and
injects them into the new template content after '## Project Notes'.

Exit code: 0 if merge succeeded (content on stdout), 1 if no merge needed.
"""

import re
import sys

# Template H2 sections — anything outside these is project-specific
TEMPLATE_H2 = {
    'Quick Reference', 'Quick Start', 'Conventions',
    'Architecture', 'Project Rules',
    'Relationship to SOUL.md', 'Agent Notes',
}


def parse_sections(text):
    """Parse markdown into list of (level, heading, body) tuples."""
    sections = []
    pattern = re.compile(r'^(#{2,})\s+(.+)$', re.MULTILINE)
    last_pos = 0
    last_heading = '__preamble__'
    last_level = 0

    for m in pattern.finditer(text):
        if last_heading != '__preamble__' or last_pos > 0:
            sections.append((last_level, last_heading, text[last_pos:m.start()]))
        last_level = len(m.group(1))
        last_heading = m.group(2).strip()
        last_pos = m.end()  # body starts after heading line

    sections.append((last_level, last_heading, text[last_pos:]))
    return sections


def is_default_commands(body):
    """Check if Commands section has default template content."""
    return './run up' in body


def is_default_notes(body):
    """Check if Project Notes section is the default placeholder."""
    stripped = body.strip().rstrip('*(').strip()
    if not stripped:
        return True
    placeholder = 'Add project-specific conventions, architecture, dev setup'
    return placeholder in stripped


def merge(old_path, new_content):
    """Merge project-specific content from old file into new template."""
    with open(old_path) as f:
        old_text = f.read()

    old_sections = parse_sections(old_text)
    custom_sections = []
    commands_content = None
    project_notes_content = None

    for level, heading, body in old_sections:
        heading_clean = heading.split(' —')[0].strip()

        if heading_clean in TEMPLATE_H2:
            if heading_clean == 'Commands' and body.strip():
                cmds = body.strip()
                if not is_default_commands(cmds):
                    commands_content = cmds
            elif heading_clean == 'Project Notes' and body.strip():
                notes = body.strip()
                if not is_default_notes(notes):
                    project_notes_content = notes
        elif heading_clean != '__preamble__':
            # Custom section — preserve it
            marker = '#' * level
            custom_sections.append(f'\n\n{marker} {heading}{body}')

    # Check if there's anything to inject
    if not any([project_notes_content, commands_content, custom_sections]):
        return None  # No custom content found — no merge needed

    # Find '## Project Notes' in the new content
    notes_marker = '## Project Notes'
    notes_pos = new_content.find(notes_marker)
    if notes_pos < 0:
        # No Project Notes section — append at end
        notes_end = len(new_content.rstrip()) + 1
    else:
        # Find end of Project Notes section
        after_notes = new_content[notes_pos + len(notes_marker):]
        next_h2 = after_notes.find('\n## ')
        if next_h2 >= 0:
            notes_end = notes_pos + len(notes_marker) + next_h2
        else:
            notes_end = len(new_content)

    # Build injection block
    injection_parts = []
    if project_notes_content:
        injection_parts.append(project_notes_content)
    if commands_content:
        injection_parts.append(f'\n\n## Custom Commands\n\n{commands_content}')
    if custom_sections:
        injection_parts.extend(cs.strip() for cs in custom_sections)

    injection = '\n\n'.join(injection_parts)
    if not injection:
        return None

    merged = new_content[:notes_end] + '\n\n' + injection + new_content[notes_end:]
    return merged


def main():
    if len(sys.argv) < 2:
        print("Usage: merge-agents-md.py <old-file>", file=sys.stderr)
        print("New template content on stdin.", file=sys.stderr)
        sys.exit(1)

    old_path = sys.argv[1]
    new_content = sys.stdin.read()

    result = merge(old_path, new_content)
    if result is None:
        sys.exit(0)  # No merge needed — caller should use template as-is

    sys.stdout.write(result)


if __name__ == '__main__':
    main()
