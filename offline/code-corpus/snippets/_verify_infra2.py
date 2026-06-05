"""Verify infra2 snippets — run on server side to confirm."""
import sys
sys.path.insert(0, '/Users/luke/hermes-cortex/offline/code-corpus/snippets')
from infra2_snippets import SNIPPETS
print(f"Total snippets: {len(SNIPPETS)}")
for i, (rel_path, lang, tags, title, desc, source, code) in enumerate(SNIPPETS, 1):
    print(f"{i:2d}. [{lang:11s}] {title:40s} -> {rel_path}")
print("Languages:", sorted(set(s[1] for s in SNIPPETS)))
nix_count = sum(1 for s in SNIPPETS if s[1] == "nix")
ps_count = sum(1 for s in SNIPPETS if s[1] == "powershell")
print(f"Nix: {nix_count}, PowerShell: {ps_count}")
