#!/usr/bin/env python3
"""webapp-http-crawl.py — HTTP route crawl + link verification for deployed web apps.

Usage:
    python3 webapp-http-crawl.py --base http://127.0.0.1:13012 --routes / /about /api/v1/auth/me
    python3 webapp-http-crawl.py --base http://127.0.0.1:13012 --routes routes.txt

Reports OK/BAD per URL. Exits non-zero if any route is BAD.
Follows 3xx redirects (final status must be 200-class); 4xx/5xx = BAD.

Stdlib-only (urllib) — runs on any host without extra deps.
"""
import argparse
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser


class TitleParser(HTMLParser):
    """Capture the <title> text from an HTML body."""

    def __init__(self):
        super().__init__()
        self._in_title = False
        self.title = ""

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()


def check_url(base: str, path: str, timeout: int = 20) -> tuple:
    """GET a path over the deployed origin. Returns (ok, status, title, note)."""
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, headers={"User-Agent": "webapp-http-crawl/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = resp.geturl()
            status = resp.status
            body = resp.read(65536).decode("utf-8", errors="replace")
            parser = TitleParser()
            parser.feed(body)
            title = parser.title.strip()
            ok = 200 <= status < 400
            note = ""
            if not ok:
                note = f"status {status}"
            elif status >= 300:
                note = f"redirected -> {final_url}"
            if not title:
                note = (note + "; " if note else "") + "no <title>"
            return ok, status, title, note
    except urllib.error.HTTPError as e:
        return False, e.code, "", f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 — report any transport failure
        return False, 0, "", str(e)


def main() -> int:
    ap = argparse.ArgumentParser(description="HTTP route crawl + link check for a deployed web app")
    ap.add_argument("--base", required=True, help="Deployed origin, e.g. http://127.0.0.1:13012")
    ap.add_argument("--routes", nargs="+", required=True, help="Route paths, or a file containing one path per line")
    ap.add_argument("--timeout", type=int, default=20, help="Per-request timeout seconds")
    args = ap.parse_args()

    # Expand a routes file if the single argument names an existing file
    routes = []
    if len(args.routes) == 1:
        maybe_file = args.routes[0]
        import os
        if os.path.isfile(maybe_file):
            with open(maybe_file) as f:
                routes = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    if not routes:
        routes = args.routes

    bad = 0
    for path in routes:
        ok, status, title, note = check_url(args.base, path, args.timeout)
        tag = "OK " if ok else "BAD"
        line = f"[{tag}] {path} -> {status}"
        if title:
            line += f" <title>{title}</title>"
        if note:
            line += f" ({note})"
        print(line)
        if not ok:
            bad += 1

    print(f"\n{len(routes) - bad}/{len(routes)} routes OK")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
