#!/usr/bin/env python3
"""Derive the .src.md layout: every source URL moved onto its own line.

The delivered .md keeps the compact inline "(url)" citations a reader wants
in chat. The .src.md is the input to the DOCX/PDF converter, which needs
each URL on its own line so <nobr> at 8pt can render it without reportlab
hyphen-splitting it (probed: inline justified URLs cannot be preserved).
"""
import re

DATE = "2026-10-12"
BASE = "/home/esther/.hermes/cron/output/sustainability-briefing-%s" % DATE
md = open(BASE + ".md", encoding="utf-8").read()

out = []
for line in md.split("\n"):
    if line.strip().startswith("http"):
        out.append(line)
        continue
    # pull every "(https://...)" out of the line, leave a marker, then emit
    urls = re.findall(r"\((https?://[^\s)]+)\)", line)
    if not urls:
        out.append(line)
        continue
    stripped = re.sub(r"\s*\(https?://[^\s)]+\)", "", line).rstrip()
    out.append(stripped)
    for i, u in enumerate(urls):
        if i == 0 and not stripped.startswith("- **"):
            # keep the "Sources:" label readable
            out.append(u)
        else:
            out.append(u)

text = "\n".join(out)
# collapse 3+ blank lines
text = re.sub(r"\n{3,}", "\n\n", text)
open(BASE + ".src.md", "w", encoding="utf-8").write(text)

n_urls = len(re.findall(r"^https?://", text, re.M))
print("src md written:", BASE + ".src.md")
print("urls on their own line:", n_urls)
print("blank-line blocks collapsed")
