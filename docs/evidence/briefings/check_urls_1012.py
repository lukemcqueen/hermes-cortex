#!/usr/bin/env python3
"""Live-check every source URL in the delivered briefing.

Runs against the ACTUAL artifacts (md and pdf), not an intermediate, so a
broken rendered link is caught. Non-2xx is reported, not fatal: publishers
legitimately return 403/paywall codes to bots.
"""
import os
import re
import subprocess

DATE = "2026-10-12"
BASE = os.path.join(os.path.expanduser("~"), ".hermes", "cron", "output",
                      "sustainability-briefing-%s" % DATE)
UA = "Mozilla/5.0 (compatible; kaesa-briefing-verifier)"

md = open(BASE + ".md", encoding="utf-8").read()
r = subprocess.run(["pdftotext", BASE + ".pdf", "-"],
                   capture_output=True, text=True)
pdf_flat = "".join(r.stdout.split())

md_urls = sorted(set(re.findall(r"https?://[^\s)]+", md)))
pdf_urls = sorted(set(re.findall(r"https?://[^\s)]+",
                                 " ".join(r.stdout.split()))))

print("=== url inventory ===")
print("distinct URLs in .md : %d" % len(md_urls))
print("distinct URLs in .pdf: %d" % len(pdf_urls))
only_md = [u for u in md_urls if "".join(u.split()) not in pdf_flat]
print("in .md but NOT in .pdf: %d %s" % (len(only_md), only_md))

print()
print("=== live HTTP check (md urls) ===")
ok = bad = 0
for u in md_urls:
    p = subprocess.run(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "-L",
         "--max-time", "20", "-A", UA, u],
        capture_output=True, text=True)
    code = p.stdout.strip() or "000"
    good = code.startswith(("2", "3"))
    ok += good
    bad += (not good)
    print("%-4s http %s  %s" % ("OK" if good else "WARN", code, u))

print()
print("live: %d reachable, %d non-2xx (of %d)" % (ok, bad, len(md_urls)))
print("NOTE: 403/404 from bot-blocking publishers is not a dead link; a 404")
print("on a URL we render ourselves WOULD be a real defect.")
