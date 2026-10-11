#!/usr/bin/env python3
"""Write a hash manifest for the 2026-10-12 briefing deliverables so a
reviewer can re-verify the exact artifacts that were delivered.

Usage:  .venv-brief/bin/python manifest_1012.py
Writes: docs/evidence/briefings/sustainability-briefing-2026-10-12.sha256
"""
import hashlib
import os

DATE = "2026-10-12"
OUT = os.path.expanduser("~/.hermes/cron/output")
EVID = os.path.expanduser("~/hermes-cortex/docs/evidence/briefings")
os.makedirs(EVID, exist_ok=True)

FILES = [
    "sustainability-briefing-%s.md" % DATE,
    "sustainability-briefing-%s.docx" % DATE,
    "sustainability-briefing-%s.pdf" % DATE,
]

lines = [
    "# SHA-256 manifest — KAESA sustainability briefing %s" % DATE,
    "# Re-verify with:  sha256sum -c sustainability-briefing-%s.sha256" % DATE,
    "# Deliverables live in ~/.hermes/cron/output/ ; repo copies are here.",
    "",
]

for f in FILES:
    p = os.path.join(OUT, f)
    if not os.path.isfile(p):
        lines.append("MISSING  %s" % f)
        continue
    h = hashlib.sha256(open(p, "rb").read()).hexdigest()
    lines.append("%s  %s" % (h, f))
    # copy the artifact into the repo as auditable evidence
    with open(p, "rb") as src, open(os.path.join(EVID, f), "wb") as dst:
        dst.write(src.read())
    print("hashed + copied: %s  %s" % (h[:16], f))

# copy the reproducible build/verify tooling alongside.
# NOTE: copy FROM the repo (canonical, path-neutral) TO cron output, not the
# reverse — an earlier run copied the cron-output copies over the repo's fixed
# ones and silently reinstated hardcoded /home paths in committed evidence.
import shutil
TOOLS = ("verify_briefing_1012.py", "make_briefing_files_1012.py",
         "make_src_1012.py", "check_urls_1012.py",
         "sources_manifest_1012.py", "manifest_1012.py")
for tool in TOOLS:
    repo_copy = os.path.join(EVID, tool)
    if os.path.isfile(repo_copy):
        # repo is canonical -> refresh cron output from it
        shutil.copy2(repo_copy, os.path.join(OUT, tool))
        print("synced cron<-repo:", tool)
    else:
        src = os.path.join(OUT, tool)
        if os.path.isfile(src):
            shutil.copy2(src, repo_copy)
            print("seeded repo<-cron:", tool)

mpath = os.path.join(EVID, "sustainability-briefing-%s.sha256" % DATE)
open(mpath, "w").write("\n".join(lines) + "\n")
print("\nmanifest:", mpath)
print("\n".join(lines))
