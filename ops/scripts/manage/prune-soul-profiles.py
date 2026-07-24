#!/usr/bin/env python3
"""
Prune all agent SOUL.md profiles to <20k chars by replacing the
principles/docs sections with the compact template, while preserving
each agent's unique Identity/Mission/Traits/Communication sections.
"""

import os, re, sys
from pathlib import Path

REPO = Path.home() / "hermes-cortex"
PROFILES_DIR = REPO / "profiles" / "personal" / "agent-profiles"
TEMPLATE_PATH = REPO / "docs" / "templates" / "SOUL.md"

# ── Determine the template body after the identity header ──
# We want everything from "## Behavioral Principles" onwards
def get_template_body(template_path: Path) -> str:
    text = template_path.read_text()
    # Find the start of Behavioral Principles
    bp_start = text.find("## Behavioral Principles")
    if bp_start < 0:
        raise ValueError("Template missing ## Behavioral Principles")
    return text[bp_start:]


# ── Extract agent identity sections ──
def get_agent_identity(text: str) -> str:
    """Extract everything from # SOUL.md up to (but not including) ## Behavioral Principles"""
    bp_start = text.find("## Behavioral Principles")
    if bp_start < 0:
        bp_start = text.find("#### 1. Be Thorough")
    if bp_start < 0:
        # Fallback: first 30 lines
        return "\n".join(text.split("\n")[:30]) + "\n"
    return text[:bp_start]


# ── Check size ──
def size_ok(text: str) -> bool:
    return len(text) <= 20000


def main():
    template_body = get_template_body(TEMPLATE_PATH)
    print(f"Template body: {len(template_body)} chars")
    
    profiles = sorted(PROFILES_DIR.glob("*/SOUL.md"))
    results = []
    
    for profile_path in profiles:
        agent = profile_path.parent.name
        original = profile_path.read_text()
        original_size = len(original)
        
        # Extract identity sections
        identity = get_agent_identity(original)
        
        # Build new content
        # Remove trailing whitespace/newlines from identity
        identity = identity.rstrip()
        new_content = identity + "\n\n" + template_body + "\n"
        
        new_size = len(new_content)
        
        if new_size <= 20000:
            profile_path.write_text(new_content)
            results.append((agent, original_size, new_size, "✅"))
        else:
            results.append((agent, original_size, new_size, f"❌ OVER {new_size - 20000} over"))
    
    print(f"\n{'Agent':<12} {'Before':>8} {'After':>8} Status")
    print("-" * 40)
    for name, before, after, status in results:
        print(f"{name:<12} {before:>8} {after:>8} {status}")
    
    # Also update runtime SOUL.md for esther
    runtime = Path.home() / ".hermes" / "SOUL.md"
    if runtime.exists():
        esther_text = runtime.read_text()
        esther_identity = get_agent_identity(esther_text)
        new_runtime = esther_identity.rstrip() + "\n\n" + template_body + "\n"
        if len(new_runtime) <= 20000:
            runtime.write_text(new_runtime)
            print(f"\n{'runtime':<12} {len(esther_text):>8} {len(new_runtime):>8} ✅")
        else:
            print(f"\n{'runtime':<12} {len(esther_text):>8} {len(new_runtime):>8} ❌ OVER")

if __name__ == "__main__":
    main()
