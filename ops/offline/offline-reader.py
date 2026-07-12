#!/usr/bin/env python3
"""
Hermes Cortex — Offline Reader
────────────────────────────────
A lightweight local web server for browsing Bible translations and
hymns completely offline. Zero external dependencies — Python stdlib only.

Usage:
    python3 ops/offline/offline-reader.py              # Port 8081, open browser
    python3 ops/offline/offline-reader.py --port 9090  # Custom port
    python3 ops/offline/offline-reader.py --no-browser # Don't open browser

Then visit http://localhost:8081 in any browser.
Works completely offline.
"""
import argparse
import html
import http.server
import json
import os
import re
import socket
import sys
import urllib.parse
from pathlib import Path
from io import StringIO

HOME = Path.home()
BIBLE_DIR = HOME / "offline" / "bible"
HYMNS_DIR = HOME / "offline" / "hymns"
PORT = 8081


# ── Bible JSON Loader ────────────────────────────────────────

def load_bible_json(filepath):
    """Load a structured Bible JSON file. Returns the full data dict or None."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def scan_bible_translations():
    """Find all Bible files and return metadata. Prefers .json, falls back to .txt."""
    if not BIBLE_DIR.exists():
        return {"status": "not_found", "translations": []}

    translations = []
    seen_stems = set()

    # First pass: JSON files (structured, preferred)
    for f in sorted(BIBLE_DIR.glob("*.json")):
        stem = f.stem
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        size_kb = f.stat().st_size // 1024
        size_mb = f.stat().st_size / (1024**2)
        # Try to read metadata from JSON
        lang_code = "en"
        translation_name = stem
        books = 0
        chapters = 0
        verses = 0
        try:
            with open(f, "r", encoding="utf-8") as jf:
                meta = json.load(jf).get("meta", {})
            if meta.get("lang"):
                lang_code = meta["lang"]
            if meta.get("translation"):
                translation_name = meta["translation"]
            books = meta.get("total_books", 0)
            chapters = meta.get("total_chapters", 0)
            verses = meta.get("total_verses", 0)
        except Exception:
            pass

        translations.append({
            "file": f.name,
            "name": translation_name,
            "lang": lang_code,
            "size_kb": size_kb,
            "size_mb": round(size_mb, 1),
            "format": "json",
            "books": books,
            "chapters": chapters,
            "verses": verses,
        })

    # Second pass: .txt files not already covered by a .json
    for f in sorted(BIBLE_DIR.glob("*.txt")):
        stem = f.stem
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        size_kb = f.stat().st_size // 1024
        size_mb = f.stat().st_size / (1024**2)
        name = stem
        lang_code = "en"
        parts = name.split("_")
        if len(parts) > 1:
            code = parts[-1]
            if len(code) <= 5:
                lang_code = code
        translations.append({
            "file": f.name,
            "name": name,
            "lang": lang_code,
            "size_kb": size_kb,
            "size_mb": round(size_mb, 1),
            "format": "txt",
        })

    return {"status": "ready", "translations": translations}


def _parse_language_label(code):
    """Map language code to display name."""
    labels = {
        "en": "English", "af": "Afrikaans", "ar": "Arabic",
        "bg": "Bulgarian", "ceb": "Cebuano", "cs": "Czech",
        "da": "Danish", "de": "German", "el": "Greek",
        "es": "Spanish", "fa": "Persian", "fi": "Finnish",
        "fr": "French", "gu": "Gujarati", "he": "Hebrew",
        "hi": "Hindi", "hu": "Hungarian", "id": "Indonesian",
        "is": "Icelandic", "it": "Italian", "ja": "Japanese",
        "ko": "Korean", "la": "Latin", "ml": "Malayalam",
        "mr": "Marathi", "my": "Burmese", "ne": "Nepali",
        "nl": "Dutch", "no": "Norwegian", "pa": "Punjabi",
        "pl": "Polish", "pt": "Portuguese", "ro": "Romanian",
        "ru": "Russian", "sk": "Slovak", "so": "Somali",
        "sq": "Albanian", "sr": "Serbian", "sv": "Swedish",
        "sw": "Swahili", "ta": "Tamil", "te": "Telugu",
        "th": "Thai", "tl": "Tagalog", "tr": "Turkish",
        "uk": "Ukrainian", "ur": "Urdu", "vi": "Vietnamese",
        "zh": "Chinese", "zh-hk": "Chinese (HK)", "zh-tw": "Chinese (TW)",
    }
    return labels.get(code, code)


def load_bible_books(filepath):
    """Load book list from a Bible JSON file (fast, no verse data)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    books = data.get("books", [])
    return [
        {"abbr": b["abbr"], "name": b["name"], "testament": b.get("testament", "old")}
        for b in books
    ]


# ── Hymn Parsers ────────────────────────────────────────────

def scan_hymns():
    """List available hymn resources."""
    if not HYMNS_DIR.exists():
        return {"status": "not_found", "hymns": [], "has_pdf": False}

    resources = []
    has_pdf = False
    for f in sorted(HYMNS_DIR.glob("*")):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext == ".pdf":
            has_pdf = True
            resources.append({"file": f.name, "type": "📄 Scores (PDF)"})
        elif ext == ".abc":
            resources.append({"file": f.name, "type": "🎵 Notation (ABC)"})
        elif ext == ".xml":
            resources.append({"file": f.name, "type": "📋 Lyrics (XML)"})
        elif ext == ".txt" and "hymns-corpus" in f.name:
            resources.append({"file": f.name, "type": "📝 Lyrics Corpus"})

    # Read lyrics from corpus or XML
    hymns = []
    corpus_file = HYMNS_DIR / "00-hymns-corpus.txt"
    if corpus_file.exists():
        hymns = parse_hymn_corpus(corpus_file)

    return {
        "status": "ready",
        "resources": resources,
        "has_pdf": has_pdf,
        "hymns": hymns,
        "hymn_count": len(hymns),
    }


def parse_hymn_corpus(filepath):
    """Parse the generated hymn corpus into a structured list."""
    hymns = []
    current = None

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("=== HYMN "):
                if current:
                    hymns.append(current)
                current = {"title": "", "author": "", "meter": "", "tune": "", "lyrics": []}
            elif current is not None:
                if stripped.startswith("Title:"):
                    current["title"] = stripped[6:].strip()
                elif stripped.startswith("Author:"):
                    current["author"] = stripped[7:].strip()
                elif stripped.startswith("Meter:"):
                    current["meter"] = stripped[6:].strip()
                elif stripped.startswith("Tune:"):
                    current["tune"] = stripped[5:].strip()
                elif stripped == "---":
                    pass
                elif stripped and not stripped.startswith("#"):
                    current["lyrics"].append(stripped)

    if current:
        hymns.append(current)

    return hymns


# ── HTTP Server ─────────────────────────────────────────────

class ReaderHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for the offline reader web UI."""

    def log_message(self, format, *args):
        """Quiet logging."""
        pass

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_html(self, html_content, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))

    def _send_error_html(self, title, message, status_code=404):
        html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} — Offline Reader</title>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
        background:#1a1a2e;color:#e0e0e0;padding:2rem;max-width:600px;margin:auto}}
  h1{{color:#e94560}} p{{color:#aaa}} a{{color:#4fc3f7}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p>{html.escape(message)}</p>
<p><a href="/">← Back to Home</a></p>
</body></html>"""
        self._send_html(html, status=status_code)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # ── API Routes ──

        # Home page
        if path == "/":
            self._send_html(self._render_home())
            return

        # API: List Bible translations
        if path == "/api/bible/list":
            self._send_json(scan_bible_translations())
            return

        # API: Get books for a translation
        if path == "/api/bible/books":
            file_name = query.get("file", [None])[0]
            if not file_name:
                self._send_json({"error": "Missing 'file' parameter"}, 400)
                return
            fp = BIBLE_DIR / file_name
            if not fp.exists() or not fp.is_file():
                self._send_json({"error": f"File not found: {file_name}"}, 404)
                return
            try:
                books = load_bible_books(fp)
                self._send_json({"status": "ok", "books": books})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: Read a chapter
        if path == "/api/bible/read":
            file_name = query.get("file", [None])[0]
            book_abbr = query.get("book", [None])[0]
            chapter_str = query.get("chapter", ["1"])[0]

            if not file_name or not book_abbr:
                self._send_json({"error": "Missing parameters"}, 400)
                return

            fp = BIBLE_DIR / file_name
            if not fp.exists():
                self._send_json({"error": "File not found"}, 404)
                return

            try:
                chapter_num = int(chapter_str)

                # Try JSON first
                if fp.suffix.lower() == ".json":
                    data = load_bible_json(fp)
                    if data:
                        for b in data.get("books", []):
                            if b["abbr"] == book_abbr:
                                for ch in b.get("chapters", []):
                                    if ch["n"] == chapter_num:
                                        self._send_json({
                                            "status": "ok",
                                            "book": b["name"],
                                            "abbr": b["abbr"],
                                            "chapter": chapter_num,
                                            "verses": [{"verse": v["n"], "text": v["t"]} for v in ch["v"]],
                                            "total_chapters": len(b["chapters"]),
                                        })
                                        return
                                self._send_json({"error": f"Chapter {chapter_num} not found"}, 404)
                                return
                        self._send_json({"error": f"Book {book_abbr} not found"}, 404)
                        return

                # Fallback: try .txt with same stem
                txt_fp = fp.with_suffix(".txt")
                if txt_fp.exists():
                    from bible_parse import parse_bible_file
                    data = parse_bible_file(str(txt_fp))
                    if data:
                        for b in data.get("books", []):
                            if b["abbr"] == book_abbr:
                                for ch in b.get("chapters", []):
                                    if ch["n"] == chapter_num:
                                        self._send_json({
                                            "status": "ok",
                                            "book": b["name"],
                                            "abbr": b["abbr"],
                                            "chapter": chapter_num,
                                            "verses": [{"verse": v["n"], "text": v["t"]} for v in ch["v"]],
                                            "total_chapters": len(b["chapters"]),
                                        })
                                        return

                self._send_json({"error": "Could not load translation"}, 500)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: Bible search
        if path == "/api/bible/search":
            q = query.get("q", [""])[0]
            file_name = query.get("file", [None])[0]
            if not q:
                self._send_json({"error": "Missing 'q' parameter"}, 400)
                return
            try:
                results = []
                if file_name:
                    files_to_search = [BIBLE_DIR / file_name]
                else:
                    # Prefer JSON files, fall back to txt
                    files_to_search = sorted(BIBLE_DIR.glob("*.json")) or sorted(BIBLE_DIR.glob("*.txt"))
                for fp in files_to_search:
                    if not fp.exists() or not fp.is_file():
                        continue

                    matches = []
                    ql = q.lower()

                    # Search JSON files
                    if fp.suffix.lower() == ".json":
                        try:
                            data = json.loads(fp.read_text(encoding="utf-8"))
                            for book in data.get("books", []):
                                for ch in book.get("chapters", []):
                                    for v in ch.get("v", []):
                                        if ql in v.get("t", "").lower():
                                            matches.append({
                                                "ref": f"{book['abbr']} {ch['n']}:{v['n']}",
                                                "text": v["t"][:200]
                                            })
                                            if len(matches) >= 20:
                                                break
                                    if len(matches) >= 20:
                                        break
                                if len(matches) >= 20:
                                    break
                        except Exception:
                            pass

                    # Search TXT files (grep)
                    if not matches and fp.suffix.lower() == ".txt":
                        with open(fp, "r", encoding="utf-8", errors="replace") as f:
                            for line in f:
                                if ql in line.lower():
                                    matches.append(line.strip()[:200])
                                    if len(matches) >= 10:
                                        break

                    if matches:
                        results.append({"file": fp.name, "matches": matches})
                self._send_json({"status": "ok", "query": q, "results": results})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        # API: List hymns
        if path == "/api/hymns/list":
            self._send_json(scan_hymns())
            return

        # API: Search hymns
        if path == "/api/hymns/search":
            q = query.get("q", [""])[0]
            if not q:
                self._send_json({"error": "Missing 'q' parameter"}, 400)
                return
            data = scan_hymns()
            results = []
            for h in data.get("hymns", []):
                ql = q.lower()
                if (ql in h.get("title", "").lower() or
                    ql in h.get("author", "").lower() or
                    any(ql in l.lower() for l in h.get("lyrics", [])[:20])):
                    results.append(h)
                    if len(results) >= 30:
                        break
            self._send_json({"status": "ok", "query": q, "results": results,
                             "count": len(results)})
            return

        # Static files: PDFs
        if path.startswith("/hymns/pdf/"):
            pdf_name = path[len("/hymns/pdf/"):]
            fp = HYMNS_DIR / pdf_name
            if fp.exists() and fp.suffix.lower() == ".pdf":
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(fp.stat().st_size))
                self.end_headers()
                with open(fp, "rb") as f:
                    self.wfile.write(f.read())
                return

        # API: Kiwix/Reference search
        if path == "/api/kiwix/status":
            try:
                import subprocess
                result = subprocess.run(
                    ["docker", "ps", "--filter", "name=kiwix-serve",
                     "--format", "{{.Status}}"],
                    capture_output=True, text=True, timeout=5
                )
                running = result.returncode == 0 and bool(result.stdout.strip())
                self._send_json({"running": running, "url": "http://localhost:8080"})
            except Exception as e:
                self._send_json({"running": False, "error": str(e)})
            return

        if path == "/api/kiwix/search":
            import urllib.request
            q = query.get("q", [""])[0]
            if not q:
                self._send_json({"error": "Missing 'q' parameter"}, 400)
                return
            try:
                url = f"http://localhost:8080/search?content=max&pattern={urllib.parse.quote(q)}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    html_content = resp.read().decode("utf-8")
                # Extract simple search result links
                import re
                results = []
                for match in re.finditer(
                    r'<a\s+href="(/[A-Z][^"]+)"[^>]*>(.*?)</a>',
                    html_content, re.IGNORECASE
                ):
                    link = match.group(1)
                    title = re.sub(r'<[^>]+>', '', match.group(2)).strip()
                    if title and len(results) < 20:
                        results.append({"title": title, "url": f"http://localhost:8080{link}"})
                self._send_json({"status": "ok", "query": q, "results": results,
                                 "count": len(results)})
            except Exception as e:
                self._send_json({"status": "error", "error": str(e), "results": []})
            return

        # 404
        self._send_error_html("Not Found", f"No route for: {path}", status_code=404)

    # ── Render Home Page ──

    def _render_home(self):
        bible = scan_bible_translations()
        hymns = scan_hymns()
        bible_count = len(bible.get("translations", []))
        bible_size = sum(t.get("size_mb", 0) for t in bible.get("translations", []))
        hymn_count = hymns.get("hymn_count", 0)

        # Check kiwix status
        kiwix_available = False
        try:
            import subprocess
            r = subprocess.run(
                ["docker", "ps", "--filter", "name=kiwix-serve",
                 "--format", "{{.Status}}"],
                capture_output=True, text=True, timeout=3
            )
            kiwix_available = r.returncode == 0 and bool(r.stdout.strip())
        except Exception:
            pass

        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Offline Reader — Hermes Cortex</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
        background:#1a1a2e;color:#e0e0e0;min-height:100vh}}
  .container{{max-width:900px;margin:auto;padding:2rem 1.5rem}}
  h1{{font-size:1.8rem;font-weight:700;color:#e94560;margin-bottom:.3rem}}
  .subtitle{{color:#888;font-size:.9rem;margin-bottom:2rem}}
  .cards{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1.2rem}}
  @media(max-width:700px){{.cards{{grid-template-columns:1fr}}}}
  .card{{background:#16213e;border-radius:12px;padding:1.5rem;transition:transform .15s}}
  .card:hover{{transform:translateY(-2px)}}
  .card h2{{font-size:1.2rem;margin-bottom:.5rem}}
  .card p{{color:#aaa;font-size:.85rem;line-height:1.5}}
  .card .count{{font-size:2rem;font-weight:700;color:#4fc3f7;margin:.5rem 0}}
  .btn{{display:inline-block;padding:.5rem 1.2rem;border-radius:8px;
        text-decoration:none;font-size:.85rem;font-weight:500;margin-top:.8rem}}
  .btn-blue{{background:#0f3460;color:#4fc3f7}}
  .btn-green{{background:#1a4332;color:#66bb6a}}
  .btn-orange{{background:#3d2b1f;color:#ffa726}}
  .btn:hover{{opacity:.9}}
  .status-dot{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}}
  .dot-ready{{background:#66bb6a}} .dot-empty{{background:#ffa726}} .dot-missing{{background:#e94560}}
  .footer{{margin-top:3rem;padding-top:1.5rem;border-top:1px solid #2a2a4a;
           color:#666;font-size:.8rem;text-align:center}}

  /* Bible reader styles */
  .reader{{display:none}}
  .reader.active{{display:block}}
  .back-link{{color:#4fc3f7;text-decoration:none;font-size:.85rem;display:inline-block;margin-bottom:1rem}}
  .back-link:hover{{text-decoration:underline}}
  select, input[type=text]{{background:#0f3460;color:#e0e0e0;border:1px solid #2a2a4a;
        border-radius:6px;padding:.5rem .8rem;font-size:.9rem;width:100%;margin-bottom:.8rem}}
  select option{{background:#16213e}}
  label{{display:block;color:#aaa;font-size:.8rem;margin-bottom:.3rem;margin-top:.8rem}}
  .verse-num{{color:#4fc3f7;font-weight:600;margin-right:.4rem;font-size:.85rem}}
  .verse{{margin-bottom:.4rem;line-height:1.7}}
  .chapter-nav{{display:flex;gap:.5rem;flex-wrap:wrap;margin:1rem 0}}
  .chapter-nav a{{padding:.3rem .6rem;border-radius:4px;background:#0f3460;
                 color:#aaa;text-decoration:none;font-size:.8rem}}
  .chapter-nav a.active{{background:#e94560;color:#fff;font-weight:600}}
  .chapter-nav a:hover{{background:#1a1a4e;color:#fff}}
  .book-list a{{display:block;padding:.4rem .6rem;border-radius:4px;color:#ccc;
               text-decoration:none;font-size:.85rem;border-left:2px solid transparent}}
  .book-list a:hover{{background:#0f3460;border-left-color:#4fc3f7}}
  .book-list .ot{{border-left-color:#e94560}} .book-list .nt{{border-left-color:#4fc3f7}}
  .testament-label{{color:#666;font-size:.7rem;text-transform:uppercase;letter-spacing:1px;
                    margin-top:1rem;margin-bottom:.3rem}}

  .hymn-list a{{display:block;padding:.5rem .6rem;border-radius:6px;color:#ccc;
               text-decoration:none;font-size:.9rem;border-bottom:1px solid #2a2a4a}}
  .hymn-list a:hover{{background:#0f3460;color:#fff}}
  .hymn-list .hymn-author{{color:#888;font-size:.75rem}}
  .hymn-lyrics{{font-family:'Georgia',serif;line-height:1.8;color:#ddd;margin-top:1rem}}
  .hymn-lyrics .stanza{{margin-bottom:1rem}}

  .search-box{{display:flex;gap:.5rem;margin-bottom:1rem}}
  .search-box input{{flex:1}}
  .search-box button{{padding:.5rem 1rem;border-radius:6px;border:none;cursor:pointer;font-weight:600}}
  .result-item{{padding:.5rem;border-bottom:1px solid #2a2a4a;font-size:.85rem}}
  .result-item em{{color:#4fc3f7;font-style:normal}}
  .bible-ref{{color:#66bb6a;font-weight:500}}
</style>
</head>
<body>
<div class="container">

  <div id="home-view">
    <h1>📖 Offline Reader</h1>
    <p class="subtitle">Browse scriptures, hymns, and reference — completely offline</p>
    <div class="cards">
      <div class="card">
        <h2>📖 Bible</h2>
        <p><span class="status-dot {'dot-ready' if bible_count else 'dot-empty'}"></span>
           {bible_count} translation{'s' if bible_count != 1 else ''}
           ({bible_size:.0f} MB)</p>
        <div class="count">{bible_count}</div>
        <a href="#" class="btn btn-blue" onclick="showBible()">Open Reader →</a>
      </div>
      <div class="card">
        <h2>🎵 Hymns</h2>
        <p><span class="status-dot {'dot-ready' if hymn_count else 'dot-empty'}"></span>
           {hymn_count} hymn{'s' if hymn_count != 1 else ''}
           {' + PDF scores' if hymns.get('has_pdf') else ''}</p>
        <div class="count">{hymn_count}</div>
        <a href="#" class="btn btn-green" onclick="showHymns()">Browse Hymns →</a>
      </div>
      <div class="card">
        <h2>📚 Reference</h2>
        <p><span id="ref-status-dot" class="status-dot dot-empty"></span>
           <span id="ref-status-text">Checking…</span></p>
        <div class="count" id="ref-count">—</div>
        <a href="#" class="btn btn-orange" onclick="showReference()">Search Wiki →</a>
      </div>
    </div>

    <!-- Global search bar -->
    <div style="margin-top:1.5rem;background:#16213e;border-radius:12px;padding:1.2rem">
      <label style="color:#aaa;font-size:.85rem;font-weight:500">Search everything</label>
      <div class="search-box" style="margin-top:.5rem">
        <input type="text" id="global-search-input" placeholder="Search Bible, hymns, or reference…" onkeydown="if(event.key==='Enter')globalSearch()">
        <button class="btn btn-blue" onclick="globalSearch()">Search</button>
      </div>
      <div id="global-search-results"></div>
    </div>
  </div>

  <!-- ─── Bible Reader ─── -->
  <div id="bible-reader" class="reader">
    <a href="#" class="back-link" onclick="showHome()">← Back to Home</a>
    <h2 id="bible-title">📖 Bible Reader</h2>

    <div id="bible-lang-select">
      <label>Translation</label>
      <select id="bible-file" onchange="loadBooks()">
        <option value="">Loading translations…</option>
      </select>
    </div>

    <div id="bible-books" style="display:none">
      <label>Book</label>
      <div id="book-list" class="book-list"></div>
    </div>

    <div id="bible-chapter" style="display:none">
      <div id="chapter-nav" class="chapter-nav"></div>
      <div id="chapter-content"></div>
    </div>

    <div id="bible-search" style="margin-top:1rem">
      <label>Search this translation</label>
      <div class="search-box">
        <input type="text" id="bible-search-input" placeholder="Search verses…" onkeydown="if(event.key==='Enter')bibleSearch()">
        <button class="btn btn-blue" onclick="bibleSearch()">Search</button>
      </div>
      <div id="bible-search-results"></div>
    </div>
  </div>

  <!-- ─── Hymn Browser ─── -->
  <div id="hymn-view" class="reader">
    <a href="#" class="back-link" onclick="showHome()">← Back to Home</a>
    <h2>🎵 Hymns</h2>

    <div class="search-box">
      <input type="text" id="hymn-search-input" placeholder="Search hymns…" onkeydown="if(event.key==='Enter')hymnSearch()">
      <button class="btn btn-green" onclick="hymnSearch()">Search</button>
    </div>

    <div id="hymn-list" class="hymn-list"></div>
    <div id="hymn-detail" style="display:none"></div>
  </div>

  <!-- ─── Reference Tab ─── -->
  <div id="reference-view" class="reader">
    <a href="#" class="back-link" onclick="showHome()">← Back to Home</a>
    <h2>📚 Reference</h2>
    <p style="color:#888;font-size:.85rem;margin-bottom:1rem">
      Search Wikipedia, WikiMed, Wikivoyage and other ZIM content
      served by kiwix-serve.
    </p>

    <div class="search-box">
      <input type="text" id="ref-search-input" placeholder="Search reference content…" onkeydown="if(event.key==='Enter')refSearch()">
      <button class="btn btn-orange" onclick="refSearch()">Search</button>
    </div>

    <div id="ref-status" style="margin-bottom:1rem;font-size:.85rem;color:#888">
      <span id="ref-check">Checking kiwix-serve status…</span>
    </div>

    <div id="ref-results"></div>

    <div id="ref-article" style="display:none;margin-top:1rem">
      <a href="#" class="back-link" onclick="refBack();return false">← Back to results</a>
      <div id="ref-article-content"></div>
    </div>
  </div>

</div>

<script>
// ── Navigation ──
function showHome() {{
    document.querySelectorAll('.reader').forEach(r => r.classList.remove('active'));
    document.getElementById('home-view').style.display = 'block';
}}
function showBible() {{
    document.getElementById('home-view').style.display = 'none';
    document.getElementById('bible-reader').classList.add('active');
    loadTranslations();
}}
function showHymns() {{
    document.getElementById('home-view').style.display = 'none';
    document.getElementById('hymn-view').classList.add('active');
    loadHymnList();
}}
function showReference() {{
    document.getElementById('home-view').style.display = 'none';
    document.getElementById('reference-view').classList.add('active');
    document.getElementById('ref-check').textContent = 'Checking kiwix-serve status…';
    document.getElementById('ref-results').innerHTML = '';
    document.getElementById('ref-article').style.display = 'none';
    checkKiwix();
}}

// ── Reference / Kiwix ──
function checkKiwix() {{
    fetch('/api/kiwix/status')
        .then(r => r.json())
        .then(data => {{
            const check = document.getElementById('ref-check');
            const dot = document.getElementById('ref-status-dot');
            const txt = document.getElementById('ref-status-text');
            const count = document.getElementById('ref-count');
            if (data.running) {{
                check.innerHTML = '✅ kiwix-serve is running at <a href="http://localhost:8080" target="_blank" style="color:#4fc3f7">localhost:8080</a>';
                if (dot) {{ dot.className = 'status-dot dot-ready'; txt.textContent = 'kiwix-serve running'; }}
                if (count) count.textContent = '✓';
            }} else {{
                check.textContent = '❌ kiwix-serve is not running. Start it with: docker compose -f hermes-cortex/offline/kiwix-docker-compose.yml up -d';
                if (dot) {{ dot.className = 'status-dot dot-missing'; txt.textContent = 'Not running'; }}
                if (count) count.textContent = '✗';
            }}
        }})
        .catch(err => {{
            document.getElementById('ref-check').textContent = 'Could not check kiwix-serve: ' + err;
        }});
}}

let refData = {{}};

function refSearch() {{
    const q = document.getElementById('ref-search-input').value.trim();
    const resultsDiv = document.getElementById('ref-results');
    if (!q) {{ resultsDiv.innerHTML = ''; return; }}
    resultsDiv.innerHTML = '<p style="color:#888">Searching…</p>';
    document.getElementById('ref-article').style.display = 'none';
    fetch('/api/kiwix/search?q=' + encodeURIComponent(q))
        .then(r => r.json())
        .then(data => {{
            if (data.status === 'error' || !data.results || !data.results.length) {{
                if (data.status === 'error') {{
                    resultsDiv.innerHTML = '<p style="color:#e94560">' + htmlEscape(data.error || 'Could not reach kiwix-serve') + '</p>';
                }} else {{
                    resultsDiv.innerHTML = '<p style="color:#888">No results found for "' + htmlEscape(q) + '"</p>';
                }}
                return;
            }}
            refData.lastResults = data.results;
            let html = '<p style="color:#888;font-size:.85rem;margin-bottom:.5rem">' + data.count + ' result(s) for "' + htmlEscape(q) + '"</p>';
            data.results.forEach((r, i) => {{
                const cleanTitle = r.title.replace(/<[^>]+>/g, '');
                html += '<div class="result-item"><a href="' + htmlEscape(r.url) + '" target="_blank" style="color:#4fc3f7;text-decoration:none;font-weight:500">' +
                        htmlEscape(cleanTitle) + '</a> <span style="color:#666;font-size:.75rem">[opens in new tab]</span></div>';
            }});
            resultsDiv.innerHTML = html;
        }})
        .catch(err => {{
            resultsDiv.innerHTML = '<p style="color:#e94560">Search failed: ' + err + '</p>';
        }});
}}

function refBack() {{
    document.getElementById('ref-article').style.display = 'none';
    document.getElementById('ref-results').style.display = 'block';
}}

// ── Global Search ──
let globalSearchData = {{}};

function globalSearch() {{
    const q = document.getElementById('global-search-input').value.trim();
    const resultsDiv = document.getElementById('global-search-results');
    if (!q) {{ resultsDiv.innerHTML = ''; return; }}
    resultsDiv.innerHTML = '<p style="color:#888">Searching Bible, hymns, and reference…</p>';

    Promise.all([
        // Bible search (first translation)
        fetch('/api/bible/list').then(r => r.json()).then(bibleData => {{
            if (bibleData.translations && bibleData.translations.length) {{
                return fetch('/api/bible/search?q=' + encodeURIComponent(q) + '&file=' + encodeURIComponent(bibleData.translations[0].file)).then(r => r.json());
            }}
            return {{ results: [] }};
        }}),
        // Hymn search
        fetch('/api/hymns/search?q=' + encodeURIComponent(q)).then(r => r.json()),
        // Reference search
        fetch('/api/kiwix/search?q=' + encodeURIComponent(q)).then(r => r.json()).catch(() => ({{ results: [], status: 'error' }}))
    ])
    .then(([bibleResult, hymnResult, refResult]) => {{
        let html = '';
        let total = 0;

        // Bible results
        if (bibleResult.results && bibleResult.results.length) {{
            total += 1;
            html += '<p style="color:#4fc3f7;font-size:.85rem;font-weight:500;margin-top:.5rem">📖 Bible</p>';
            bibleResult.results.slice(0, 3).forEach(r => {{
                r.matches.slice(0, 3).forEach(m => {{
                    const hl = m.replace(new RegExp('(' + q.replace(/[.*+?^${{}}()|[\]\\\\]/g, '\\\\$&') + ')', 'gi'), '<em>$1</em>');
                    html += '<div class="result-item">' + hl + '</div>';
                }});
            }});
        }}

        // Hymn results
        if (hymnResult.results && hymnResult.results.length) {{
            total += hymnResult.results.length;
            html += '<p style="color:#66bb6a;font-size:.85rem;font-weight:500;margin-top:.5rem">🎵 Hymns (' + hymnResult.results.length + ')</p>';
            hymnResult.results.slice(0, 5).forEach(h => {{
                html += '<div class="result-item"><span class="bible-ref">' + htmlEscape(h.title || '') + '</span>' +
                        (h.author ? ' <span style="color:#888">— ' + htmlEscape(h.author) + '</span>' : '') + '</div>';
            }});
        }}

        // Reference results
        if (refResult.results && refResult.results.length) {{
            total += refResult.results.length;
            html += '<p style="color:#ffa726;font-size:.85rem;font-weight:500;margin-top:.5rem">📚 Reference (' + refResult.results.length + ')</p>';
            refResult.results.slice(0, 5).forEach(r => {{
                const cleanTitle = r.title.replace(/<[^>]+>/g, '');
                html += '<div class="result-item"><a href="' + htmlEscape(r.url) + '" target="_blank" style="color:#4fc3f7">' + htmlEscape(cleanTitle) + '</a></div>';
            }});
        }}

        if (!total) {{
            html = '<p style="color:#888">No matches found across Bible, hymns, or reference.</p>';
        }}

        resultsDiv.innerHTML = html;
    }})
    .catch(err => {{
        resultsDiv.innerHTML = '<p style="color:#e94560">Search error: ' + err + '</p>';
    }});
}}

// ── Bible: Translation Select ──
let bibleData = {{}};

function loadTranslations() {{
    fetch('/api/bible/list')
        .then(r => r.json())
        .then(data => {{
            const sel = document.getElementById('bible-file');
            sel.innerHTML = '';
            if (data.status !== 'ready' || !data.translations.length) {{
                sel.innerHTML = '<option>No Bible translations found. Run prep-bible.sh</option>';
                return;
            }}
            data.translations.forEach(t => {{
                const opt = document.createElement('option');
                opt.value = t.file;
                const langLabel = '{_parse_language_label("en")}'.replace('en', t.lang);
                opt.textContent = t.name + ' (' + t.size_mb + ' MB)';
                sel.appendChild(opt);
            }});
            bibleData.translations = data.translations;
            if (data.translations.length) loadBooks();
        }});
}}

function loadBooks() {{
    const file = document.getElementById('bible-file').value;
    if (!file) return;
    bibleData.currentFile = file;
    document.getElementById('bible-books').style.display = 'none';
    document.getElementById('bible-chapter').style.display = 'none';

    fetch('/api/bible/books?file=' + encodeURIComponent(file))
        .then(r => r.json())
        .then(data => {{
            if (!data.books || !data.books.length) {{
                document.getElementById('book-list').innerHTML = '<p style=\\"color:#888\\">Could not parse book structure. Try another translation.</p>';
                return;
            }}
            bibleData.books = data.books;
            let html = '<div class=\\"testament-label\\">Old Testament</div>';
            let otBooks = data.books.filter(b => b.testament === 'old');
            otBooks.forEach(b => {{
                html += '<a href=\\"#\\" class=\\"ot\\" onclick=\\"selectBook(\\'' + b.abbr + '\\')\\">' + htmlEscape(b.name) + '</a>';
            }});
            html += '<div class=\\"testament-label\\">New Testament</div>';
            let ntBooks = data.books.filter(b => b.testament === 'new');
            ntBooks.forEach(b => {{
                html += '<a href=\\"#\\" class=\\"nt\\" onclick=\\"selectBook(\\'' + b.abbr + '\\')\\">' + htmlEscape(b.name) + '</a>';
            }});
            document.getElementById('book-list').innerHTML = html;
            document.getElementById('bible-books').style.display = 'block';
        }});
}}

function selectBook(abbr) {{
    bibleData.currentBook = abbr;
    const file = bibleData.currentFile;
    document.getElementById('chapter-content').innerHTML = '<p style=\\"color:#888\\">Loading…</p>';

    // Show chapter 1
    fetch('/api/bible/read?file=' + encodeURIComponent(file) + '&book=' + abbr + '&chapter=1')
        .then(r => r.json())
        .then(data => {{
            if (data.error) {{
                document.getElementById('chapter-content').innerHTML = '<p style=\\"color:#e94560\\">' + htmlEscape(data.error) + '</p>';
                return;
            }}
            // Chapter nav
            let nav = '';
            for (let i = 1; i <= data.total_chapters; i++) {{
                nav += '<a href=\\"#\\" ' + (i === 1 ? 'class=\\"active\\"' : '') + ' onclick=\\"loadChapter(' + i + ');return false\\">' + i + '</a>';
            }}
            document.getElementById('chapter-nav').innerHTML = nav;
            document.getElementById('bible-books').style.display = 'none';
            document.getElementById('bible-chapter').style.display = 'block';
            document.getElementById('bible-title').textContent = data.book + ' ' + data.chapter;
            renderChapter(data.verses);
        }});
}}

function loadChapter(chapter) {{
    const file = bibleData.currentFile;
    const abbr = bibleData.currentBook;
    fetch('/api/bible/read?file=' + encodeURIComponent(file) + '&book=' + abbr + '&chapter=' + chapter)
        .then(r => r.json())
        .then(data => {{
            if (data.error) return;
            // Update active chapter
            document.querySelectorAll('#chapter-nav a').forEach(a => a.classList.remove('active'));
            const navLinks = document.querySelectorAll('#chapter-nav a');
            if (navLinks[chapter - 1]) navLinks[chapter - 1].classList.add('active');
            document.getElementById('bible-title').textContent = data.book + ' ' + data.chapter;
            renderChapter(data.verses);
        }});
}}

function renderChapter(verses) {{
    let html = '';
    verses.forEach(v => {{
        html += '<div class=\\"verse\\"><span class=\\"verse-num\\">' + v.verse + '</span>' + htmlEscape(v.text) + '</div>';
    }});
    document.getElementById('chapter-content').innerHTML = html;
}}

function bibleSearch() {{
    const q = document.getElementById('bible-search-input').value.trim();
    const file = bibleData.currentFile;
    const resultsDiv = document.getElementById('bible-search-results');
    if (!q) {{ resultsDiv.innerHTML = ''; return; }}
    resultsDiv.innerHTML = '<p style=\\"color:#888\\">Searching…</p>';
    let url = '/api/bible/search?q=' + encodeURIComponent(q);
    if (file) url += '&file=' + encodeURIComponent(file);
    fetch(url)
        .then(r => r.json())
        .then(data => {{
            if (!data.results || !data.results.length) {{
                resultsDiv.innerHTML = '<p style=\\"color:#888\\">No matches found.</p>';
                return;
            }}
            let html = '';
            data.results.forEach(r => {{
                html += '<p style=\\"color:#4fc3f7;font-size:.85rem;margin-top:.5rem\\">📄 ' + htmlEscape(r.file) + '</p>';
                r.matches.forEach(m => {{
                    const highlighted = m.replace(new RegExp('(' + q.replace(/[.*+?^${{}}()|[\]\\\\]/g, '\\\\$&') + ')', 'gi'), '<em>$1</em>');
                    html += '<div class=\\"result-item\\">' + highlighted + '</div>';
                }});
            }});
            resultsDiv.innerHTML = html;
        }});
}}

// ── Hymns ──
function loadHymnList() {{
    fetch('/api/hymns/list')
        .then(r => r.json())
        .then(data => {{
            const list = document.getElementById('hymn-list');
            if (!data.hymns || !data.hymns.length) {{
                list.innerHTML = '<p style=\\"color:#888\\">No hymns found. Run prep-hymns.sh</p>';
                return;
            }}
            bibleData.hymns = data.hymns;
            let html = '';
            // PDF link if available
            if (data.has_pdf) {{
                html += '<p style=\\"margin-bottom:.8rem\\"><a href=\\"/hymns/pdf/OpenHymnal2014.06.pdf\\" target=\\"_blank\\" style=\\"color:#ffa726\\">📄 View Full Hymnal PDF →</a></p>';
            }}
            data.hymns.forEach((h, i) => {{
                html += '<a href=\\"#\\" onclick=\\"showHymn(' + i + ');return false\\">' +
                        htmlEscape(h.title || 'Untitled') +
                        (h.author ? ' <span class=\\"hymn-author\\">— ' + htmlEscape(h.author) + '</span>' : '') +
                        '</a>';
            }});
            list.innerHTML = html;
        }});
}}

function showHymn(index) {{
    const h = bibleData.hymns[index];
    if (!h) return;
    document.getElementById('hymn-list').style.display = 'none';
    const detail = document.getElementById('hymn-detail');
    let html = '<a href=\\"#\\" class=\\"back-link\\" onclick=\\"backToHymns();return false\\">← Back to list</a>';
    html += '<h3>' + htmlEscape(h.title || 'Untitled') + '</h3>';
    if (h.author) html += '<p style=\\"color:#888;font-size:.85rem\\">' + htmlEscape(h.author) + '</p>';
    if (h.meter) html += '<p style=\\"color:#666;font-size:.8rem\\">Meter: ' + htmlEscape(h.meter) + '</p>';
    if (h.tune) html += '<p style=\\"color:#666;font-size:.8rem\\">Tune: ' + htmlEscape(h.tune) + '</p>';
    html += '<div class=\\"hymn-lyrics\\">';
    let stanza = '';
    h.lyrics.forEach(line => {{
        if (line.trim() === '') {{
            if (stanza) {{ html += '<div class=\\"stanza\\">' + stanza + '</div>'; stanza = ''; }}
        }} else {{
            stanza += htmlEscape(line) + '<br>';
        }}
    }});
    if (stanza) html += '<div class=\\"stanza\\">' + stanza + '</div>';
    html += '</div>';
    detail.innerHTML = html;
    detail.style.display = 'block';
}}

function backToHymns() {{
    document.getElementById('hymn-detail').style.display = 'none';
    document.getElementById('hymn-list').style.display = 'block';
}}

function hymnSearch() {{
    const q = document.getElementById('hymn-search-input').value.trim();
    const list = document.getElementById('hymn-list');
    if (!q) {{ loadHymnList(); return; }}
    list.innerHTML = '<p style=\\"color:#888\\">Searching…</p>';
    fetch('/api/hymns/search?q=' + encodeURIComponent(q))
        .then(r => r.json())
        .then(data => {{
            if (!data.results || !data.results.length) {{
                list.innerHTML = '<p style=\\"color:#888\\">No hymns match "' + htmlEscape(q) + '"</p>';
                return;
            }}
            // Build new hymn list from search results
            bibleData.hymns = data.results;
            let html = '<p style=\\"color:#888;font-size:.85rem;margin-bottom:.5rem\\">' + data.count + ' hymn(s) match "' + htmlEscape(q) + '"</p>';
            data.results.forEach((h, i) => {{
                html += '<a href=\\"#\\" onclick=\\"showHymn(' + i + ');return false\\">' +
                        htmlEscape(h.title || 'Untitled') +
                        (h.author ? ' <span class=\\"hymn-author\\">— ' + htmlEscape(h.author) + '</span>' : '') +
                        '</a>';
            }});
            list.innerHTML = html;
        }});
}}

// ── Utilities ──
function htmlEscape(s) {{
    if (!s) return '';
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

// Auto-open Bible if translations are ready (for instant loading feel)

// On load: check kiwix status for home page reference card
(function() {{
    fetch('/api/kiwix/status')
        .then(r => r.json())
        .then(data => {{
            const dot = document.getElementById('ref-status-dot');
            const txt = document.getElementById('ref-status-text');
            const count = document.getElementById('ref-count');
            if (data.running) {{
                if (dot) {{ dot.className = 'status-dot dot-ready'; }}
                if (txt) txt.textContent = 'kiwix-serve: ready';
                if (count) count.textContent = '✓';
            }} else {{
                if (dot) {{ dot.className = 'status-dot dot-missing'; }}
                if (txt) txt.textContent = 'Not available';
                if (count) count.textContent = '✗';
            }}
        }})
        .catch(() => {{}});
}})();

</script>
</body></html>"""

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def find_free_port(start=8081):
    """Find an available port starting from start."""
    port = start
    while port < start + 100:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            port += 1
    return start  # Give up and return original


def main():
    parser = argparse.ArgumentParser(
        description="Hermes Cortex — Offline Reader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 offline/offline-reader.py              # Port 8081, open browser
  python3 offline/offline-reader.py --port 9090  # Custom port
  python3 offline/offline-reader.py --no-browser # Don't open browser
        """,
    )
    parser.add_argument("--port", "-p", type=int, default=PORT,
                        help=f"Port to listen on (default: {PORT})")
    parser.add_argument("--no-browser", action="store_true",
                        help="Don't open browser automatically")
    args = parser.parse_args()

    port = find_free_port(args.port)
    server = http.server.HTTPServer(("127.0.0.1", port), ReaderHandler)

    bible = scan_bible_translations()
    hymns = scan_hymns()

    print()
    print("  ╔═══════════════════════════════════════════╗")
    print("  ║   📖 Offline Reader                      ║")
    print("  ║   Hermes Cortex — Browse offline content  ║")
    print("  ╚═══════════════════════════════════════════╝")
    print()

    bc = len(bible.get("translations", []))
    hc = hymns.get("hymn_count", 0)
    bsize = sum(t.get("size_mb", 0) for t in bible.get("translations", []))
    has_pdf = hymns.get("has_pdf", False)

    print(f"  📖  Bible:    {bc} translation(s) ({bsize:.0f} MB)")
    print(f"  🎵  Hymns:    {hc} hymn(s)" + (" + PDF scores" if has_pdf else ""))
    print()
    print(f"  🌐  Open:     http://localhost:{port}")
    print()
    print(f"  💡  Press Ctrl+C to stop the server")
    print()

    if not args.no_browser:
        import webbrowser
        webbrowser.open(f"http://localhost:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down…")
        server.shutdown()


if __name__ == "__main__":
    main()
