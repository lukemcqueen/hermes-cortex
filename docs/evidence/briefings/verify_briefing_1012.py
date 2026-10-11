#!/usr/bin/env python3
"""Verification for the 2026-10-12 KAESA sustainability briefing deliverables.

Checks the three artifacts are real, non-trivial, well-formed documents.
Exit 0 = all checks passed.
"""
import os
import re
import subprocess
import sys
import zipfile

DATE = "2026-10-12"
OUT = os.path.expanduser("~/.hermes/cron/output")
BASE = os.path.join(OUT, "sustainability-briefing-%s" % DATE)
FAIL = 0


def chk(label, ok, detail=""):
    global FAIL
    if ok:
        print("PASS  %s :: %s" % (label, detail))
    else:
        print("FAIL  %s :: %s" % (label, detail))
        FAIL = 1


def sh(argv):
    """Run a command with an explicit argument list (no shell, so no
    metacharacter injection). Paths are ours and non-user-controlled, but
    list form is used regardless."""
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=120)
    except Exception as e:  # noqa: BLE001
        class R:
            stdout = ""
            stderr = str(e)
            returncode = 1
        return R()


def norm(s):
    """Collapse ALL whitespace so wrapped text can be substring-matched.

    reportlab hard-wraps long URLs at the line boundary, and PDF extraction
    returns those wraps as newlines. Comparing raw text against an unwrapped
    URL is therefore a probe bug, not an artifact bug — normalise first.
    """
    return re.sub(r"\s+", "", s)


def xesc(s):
    """XML-escape for comparison against OOXML body text ('&' -> '&amp;')."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


print("=== deliverables exist and are non-empty ===")
for ext in ("md", "docx", "pdf"):
    p = "%s.%s" % (BASE, ext)
    chk("exists:%s" % ext, os.path.isfile(p) and os.path.getsize(p) > 0,
        "%s bytes" % (os.path.getsize(p) if os.path.isfile(p) else 0))

print("=== pdf is a real multi-page document with extractable text ===")
r = sh(["file", "-b", "%s.pdf" % BASE])
chk("pdf:type", "PDF document" in r.stdout, r.stdout.strip())
r = sh(["pdfinfo", "%s.pdf" % BASE])
m = re.search(r"Pages:\s+(\d+)", r.stdout)
pages = int(m.group(1)) if m else 0
chk("pdf:pages", pages >= 2, "%d pages" % pages)
r = sh(["pdftotext", "%s.pdf" % BASE, "-"])
words = len(r.stdout.split())
chk("pdf:text", words > 700, "%d words extracted" % words)
# every H2 section heading must survive into the PDF text layer
md = open("%s.md" % BASE, encoding="utf-8").read()
heads = [h[3:].strip() for h in re.findall(r"^## .+$", md, re.M)]
pdf_flat = norm(r.stdout)
missing = [h for h in heads if norm(h) not in pdf_flat]
chk("pdf:all-sections-present", not missing, "missing=%s" % missing)
# and every source URL must be present in the PDF (whitespace-normalised,
# because reportlab wraps long URLs across lines)
urls = sorted(set(re.findall(r"https?://[^\s)]+", md)))
pdf_missing = [u for u in urls if norm(u) not in pdf_flat]
chk("pdf:all-urls-present", not pdf_missing,
    "%d urls, missing=%s" % (len(urls), pdf_missing[:3]))

print("=== docx is a valid OOXML zip with body content ===")
try:
    z = zipfile.ZipFile("%s.docx" % BASE)
    chk("docx:zip", z.testzip() is None, "testzip OK")
    names = z.namelist()
    chk("docx:has-document", "word/document.xml" in names, "word/document.xml")
    body = z.read("word/document.xml").decode("utf-8", "ignore")
    chk("docx:body-tag", "<w:body" in body, "w:body present")
    # python-docx emits <w:p> and <w:p ...>, never '<w:p ' with a trailing
    # space — count the tag prefix, not a space-suffixed form.
    npar = body.count("<w:p>") + body.count("<w:p ")
    chk("docx:paragraphs", npar > 30, "%d paragraphs" % npar)
    # section headings live in escaped XML text (& -> &amp;)
    dmissing = [h for h in heads if xesc(h) not in body]
    chk("docx:all-sections-present", not dmissing, "missing=%s" % dmissing)
except Exception as e:  # noqa: BLE001
    chk("docx:open", False, str(e))

print("=== markdown content integrity ===")
w = len(md.split())
chk("md:words", 600 <= w <= 2600, "%d words (target 600-1200 body)" % w)
chk("md:urls", len(urls) >= 12, "%d unique source URLs" % len(urls))
chk("md:sections", len(heads) >= 5, "%d H2 sections" % len(heads))
chk("md:no-placeholder",
    not re.search(r"TODO|FIXME|XXX|placeholder|Lorem ipsum", md, re.I), "clean")
chk("md:no-truncated-url",
    not re.search(r"https?://[^\s)]*\.\.\.", md), "no ellipsized URLs")
chk("md:no-md-tables", not re.search(r"^\|.+\|$", md, re.M),
    "no pipe tables (cron delivery is chat)")

print("=== every URL is a well-formed absolute https link ===")
bad = [u for u in urls if not u.startswith("https://") or " " in u]
chk("urls:wellformed", not bad, "bad=%s" % bad)

print()
print("RESULT: %s" % ("ALL CHECKS PASSED" if FAIL == 0 else "FAILURES PRESENT"))
sys.exit(FAIL)
