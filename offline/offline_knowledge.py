#!/usr/bin/env python3
"""
Hermes Cortex — Offline Knowledge Cascade Tool

A CLI that provides cascading knowledge lookup across multiple local sources:
  1. web_cache (semantic search, always checked first)
  2. kiwix-serve (ZIM content — Wikipedia, Wikivoyage, WikiMed, etc.)
  3. gbrain (local knowledge brain via RAG)
  4. LLM native knowledge (always available, no lookup needed)

When online, this acts as a transparent cache layer to save API calls.
When offline, it's the primary knowledge source.

Usage:
  offline_knowledge query <question>
      → Cascade: cache → kiwix → gbrain → fallback info

  offline_knowledge kiwix-search <term>
      → Direct full-text search across all loaded ZIM files

  offline_knowledge kiwix-list
      → List available ZIM content

  offline_knowledge kiwix-status
      → Check if kiwix-serve is running

  offline_knowledge cascade-search <question>
      → Explicit cascade with detailed per-source results

  offline_knowledge stats
      → Show offline knowledge system status

  offline_knowledge generate-library
      → Generate library XML from ZIM files in ~/offline/zim/
"""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# ── Config ──────────────────────────────────────────────────
HOME = Path.home()
CACHE_DIR = HOME / ".hermes" / "web-cache"
CACHE_DB = CACHE_DIR / "cache.db"
CACHE_SCRIPT = HOME / ".hermes" / "web-cache" / "web_cache.py"
ZIM_DIR = HOME / "offline" / "zim"
LIBRARY_FILE = HOME / "offline" / "kiwix-library.xml"
KIWIX_URL = "http://localhost:8080"
BIBLE_DIR = HOME / "offline" / "bible"
HYMNS_DIR = HOME / "offline" / "hymns"

# ── Bun/GBrain path detection ────────────────────────────────
# Try multiple locations: install.sh default, PATH, and Homebrew
def _find_bun():
    """Locate bun binary across common install locations."""
    candidates = [
        HOME / ".bun" / "bin" / "bun",           # install.sh default
    ]
    # Check PATH
    import shutil
    path_bun = shutil.which("bun")
    if path_bun:
        candidates.insert(0, Path(path_bun))
    # Check Homebrew
    try:
        import subprocess
        brew_bun = subprocess.run(
            ["brew", "--prefix", "bun"], capture_output=True, text=True, timeout=5
        )
        if brew_bun.returncode == 0:
            bp = Path(brew_bun.stdout.strip()) / "bin" / "bun"
            if bp.exists():
                candidates.insert(0, bp)
    except Exception:
        pass

    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]  # return default anyway, will fail gracefully later

def _find_gbrain():
    """Locate gbrain binary based on bun location."""
    bun = _find_bun()
    # gbrain is always in the same dir as bun
    gbrain = bun.parent / "gbrain"
    if gbrain.exists():
        return gbrain
    # Also try ~/.bun/bin/gbrain directly
    fallback = HOME / ".bun" / "bin" / "gbrain"
    if fallback.exists():
        return fallback
    return gbrain  # return best guess

BUN_CMD = _find_bun()
GBRAIN_CMD = _find_gbrain()


# ── Kiwix Helpers ───────────────────────────────────────────

def kiwix_status():
    """Check if kiwix-serve Docker container is running."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=kiwix-serve",
             "--format", "{{.Status}}"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return {"running": True, "status": result.stdout.strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return {"running": False, "status": "not running"}


def kiwix_search(term: str, max_results: int = 5):
    """Search kiwix-serve for a term via HTTP API."""
    import urllib.request
    import urllib.parse

    status = kiwix_status()
    if not status["running"]:
        return {"error": "kiwix-serve not running", "results": []}

    try:
        # kiwix-serve search API: /search?content=max&pattern=<term>
        url = f"{KIWIX_URL}/search?content=max&pattern={urllib.parse.quote(term)}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")
            # Parse results from HTML (kiwix-serve returns HTML)
            results = _parse_kiwix_results(html, term, max_results)
            return {"results": results}
    except Exception as e:
        return {"error": str(e), "results": []}


def _parse_kiwix_results(html: str, term: str, max_results: int):
    """Parse kiwix-serve search results from HTML to structured data."""
    import re
    results = []
    # kiwix-serve renders results as <li> with <a href="/...">title</a>
    # and optional snippet in following <p> or <div>
    # Pattern: find links in search results
    for match in re.finditer(
        r'<a\s+href="(/[A-Z][^"]+)"[^>]*>(.*?)</a>',
        html, re.IGNORECASE
    ):
        url = match.group(1)
        title = re.sub(r'<[^>]+>', '', match.group(2)).strip()
        if title and url and len(results) < max_results:
            results.append({
                "title": title,
                "url": f"{KIWIX_URL}{url}",
                "relevance": f"matched '{term}'"
            })
    return results


def _parse_kiwix_article(url: str):
    """Fetch a full article from kiwix-serve by URL."""
    import urllib.request
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")
            # Extract text content (strip HTML tags)
            import re
            # Remove scripts and styles
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
            # Extract text
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:5000]  # Limit to 5000 chars
    except Exception as e:
        return f"Error fetching article: {e}"


def kiwix_list_content():
    """List available ZIM files and their metadata."""
    if not ZIM_DIR.exists():
        return {"zim_files": [], "message": "No ZIM directory found"}
    
    files = []
    for f in sorted(ZIM_DIR.glob("*.zim")):
        size_gb = f.stat().st_size / (1024**3)
        name = f.name
        # Parse useful info from filename
        parts = name.replace(".zim", "").split("_")
        lang = parts[1] if len(parts) > 1 else "?"
        topic = parts[2] if len(parts) > 2 else "all"
        
        # Friendly labels
        labels = {
            "wikivoyage": "🌍 Travel Guide",
            "medicine": "🏥 Medical Reference",
            "wikipedia": "📚 Encyclopedia",
            "wikibooks": "📖 Textbooks",
            "wiktionary": "📝 Dictionary",
            "simple": "🔤 Simple English",
        }
        
        label = "📄 Content"
        for key, lbl in labels.items():
            if key in name:
                label = lbl
                break
        
        files.append({
            "name": name,
            "size_gb": round(size_gb, 2),
            "label": label,
            "path": str(f)
        })
    
    return {
        "zim_files": files,
        "total": len(files),
        "total_size_gb": round(sum(f["size_gb"] for f in files), 2),
        "kiwix_running": kiwix_status()["running"]
    }


def generate_library_xml():
    """Generate library XML from ZIM files in the ZIM directory."""
    if not ZIM_DIR.exists():
        ZIM_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Created {ZIM_DIR} — add .zim files here")
        return False
    
    zim_files = list(ZIM_DIR.glob("*.zim"))
    if not zim_files:
        print(f"No .zim files found in {ZIM_DIR}")
        print("Download some: https://download.kiwix.org/zim/")
        return False
    
    root = ET.Element("library")
    root.set("version", "2")
    
    for zim_file in zim_files:
        book = ET.SubElement(root, "book")
        book.set("id", zim_file.stem)
        book.set("path", f"/zim/{zim_file.name}")
        book.set("language", "eng")  # kiwix-serve auto-detects
        
        title = ET.SubElement(book, "title")
        title.text = zim_file.stem.replace("_", " ").title()
        
        desc = ET.SubElement(book, "description")
        desc_text = "Offline knowledge content"
        if "wikivoyage" in zim_file.name:
            desc_text = "Travel guides for destinations worldwide"
        elif "medicine" in zim_file.name:
            desc_text = "Medical encyclopedia — diseases, treatments, anatomy"
        elif "simple" in zim_file.name:
            desc_text = "Simple English Wikipedia"
        elif "wikibooks" in zim_file.name:
            desc_text = "Open-content textbooks"
        elif "wiktionary" in zim_file.name:
            desc_text = "Dictionary and thesaurus"
        desc.text = desc_text
    
    tree = ET.ElementTree(root)
    tree.write(str(LIBRARY_FILE), encoding="utf-8", xml_declaration=True)
    return True


# ── Web Cache Helper ────────────────────────────────────────

def web_cache_search(query: str):
    """Search web_cache via its CLI."""
    if not CACHE_SCRIPT.exists():
        return {"error": "web_cache not found — run install.sh first"}
    
    try:
        cache_venv = CACHE_DIR / ".venv" / "bin" / "python3"
        if not cache_venv.exists():
            cache_venv = "python3"
        
        result = subprocess.run(
            [str(cache_venv), str(CACHE_SCRIPT), "search", query],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data
        return {"error": result.stderr, "cached": False, "hits": []}
    except Exception as e:
        return {"error": str(e), "cached": False, "hits": []}


# ── GBrain Helper ───────────────────────────────────────────

def gbrain_search(query: str, source: str = None):
    """Search gbrain knowledge base."""
    if not BUN_CMD.exists() or not GBRAIN_CMD.exists():
        return {"error": "gbrain not installed", "results": []}
    
    try:
        cmd = [str(BUN_CMD), str(GBRAIN_CMD), "query", query, "--limit", "3"]
        if source:
            cmd.extend(["--source", source])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return {"results": result.stdout.strip()[:2000]}
        return {"error": result.stderr, "results": []}
    except Exception as e:
        return {"error": str(e), "results": []}


# ── Cascade Query ───────────────────────────────────────────

def cascade_query(question: str, detailed: bool = False):
    """
    Run a cascading knowledge lookup.
    
    Order:
      1. web_cache (semantic search — fastest, zero API cost)
      2. kiwix-serve (ZIM content if available)
      3. gbrain (personal knowledge base)
      4. Fallback info (suggestions for the agent)
    """
    result = {
        "question": question,
        "timestamp": datetime.now().isoformat(),
        "cache": None,
        "kiwix": None,
        "gbrain": None,
        "summary": None,
    }
    
    # Level 1: web_cache
    cache_result = web_cache_search(question)
    result["cache"] = {
        "status": "hit" if cache_result.get("cached") else "miss",
        "hits": cache_result.get("hits", []),
        "count": len(cache_result.get("hits", [])),
    }
    if result["cache"]["status"] == "hit" and result["cache"]["count"] > 0:
        result["summary"] = {
            "source": "web_cache",
            "message": f"Found {result['cache']['count']} cached result(s)",
            "starred": True,
        }
        if not detailed:
            return result
    
    # Level 2: kiwix-serve (ZIM content)
    kiwix_result = kiwix_search(question)
    result["kiwix"] = {
        "status": "hit" if kiwix_result.get("results") else "miss",
        "results": kiwix_result.get("results", []),
        "count": len(kiwix_result.get("results", [])),
        "error": kiwix_result.get("error"),
    }
    if result["kiwix"]["status"] == "hit" and not result["summary"]:
        # Fetch first article content for summary
        if result["kiwix"]["results"]:
            first = result["kiwix"]["results"][0]
            content = _parse_kiwix_article(first["url"])
            result["summary"] = {
                "source": "kiwix",
                "title": first["title"],
                "snippet": content[:500],
                "starred": False,
            }
    
    # Level 3: gbrain
    gbrain_result = gbrain_search(question)
    result["gbrain"] = {
        "status": "found" if gbrain_result.get("results") else "not found",
        "results": gbrain_result.get("results", ""),
    }
    
    # Final summary if nothing found
    if not result["summary"]:
        result["summary"] = {
            "source": "none",
            "message": "No local results found. Agent should use LLM knowledge or web search.",
            "starred": False,
        }
    
    return result


# ── Stats ────────────────────────────────────────────────────

def system_stats():
    """Show comprehensive offline knowledge system status."""
    stats = {
        "web_cache": {"status": "unknown"},
        "kiwix": {"status": "unknown"},
        "zim_content": {"status": "unknown"},
        "gbrain": {"status": "unknown"},
    }
    
    # web_cache
    if CACHE_DB.exists():
        size_mb = CACHE_DB.stat().st_size / (1024**2)
        stats["web_cache"] = {
            "status": "ready",
            "db": str(CACHE_DB),
            "size_mb": round(size_mb, 1),
        }
    else:
        stats["web_cache"] = {"status": "not initialized"}
    
    # kiwix
    kws = kiwix_status()
    stats["kiwix"] = {
        "status": "running" if kws["running"] else "stopped",
        "detail": kws["status"],
    }
    
    # ZIM content
    zc = kiwix_list_content()
    stats["zim_content"] = {
        "status": f"{zc.get('total', 0)} file(s)",
        "total_size_gb": zc.get("total_size_gb", 0),
        "files": [f"{f['label']} — {f['name']} ({f['size_gb']} GB)" for f in zc.get("zim_files", [])],
        "running": zc.get("kiwix_running", False),
    }
    
    # gbrain
    gbrain_found = GBRAIN_CMD.exists() and BUN_CMD.exists()
    stats["gbrain"] = {
        "status": "ready" if gbrain_found else "not installed",
    }
    
    return stats


# ── Bible Search ──────────────────────────────────────────────

def bible_list_translations():
    """List available Bible translations in the bible directory."""
    if not BIBLE_DIR.exists():
        return {"status": "not_found", "translations": []}

    translations = []
    for f in sorted(BIBLE_DIR.glob("*.txt")):
        name = f.stem
        size_kb = f.stat().st_size // 1024
        translations.append({"file": f.name, "name": name, "size_kb": size_kb})

    return {
        "status": "ready" if translations else "empty",
        "dir": str(BIBLE_DIR),
        "count": len(translations),
        "total_size_mb": sum(t["size_kb"] for t in translations) // 1024,
        "translations": translations,
    }


def bible_search(query, lang=None):
    """Search Bible translations. Returns verses matching the query."""
    if not BIBLE_DIR.exists():
        return {"status": "not_found", "error": "Bible directory not found. Run prep-bible.sh first."}

    results = []
    files_to_search = list(BIBLE_DIR.glob("*.txt"))

    if not files_to_search:
        return {"status": "empty", "error": "No Bible text files found. Run: prep-bible.sh"}

    total_searched = 0
    total_matches = 0
    query_lower = query.lower()

    for f in files_to_search:
        # Filter by language code if specified
        if lang:
            # Match language code anywhere in filename (e.g. pg10_en.txt → en)
            if lang not in f.stem.split("_"):
                continue

        total_searched += 1
        local_matches = 0
        verses = []

        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    if query_lower in line.lower():
                        local_matches += 1
                        if len(results) < 50:  # cap total results
                            # Show ~100 chars of context
                            excerpt = line[:200]
                            verses.append(excerpt)
        except Exception as e:
            verses.append(f"[Error reading: {e}]")

        if verses:
            results.append({
                "file": f.name,
                "size_kb": f.stat().st_size // 1024,
                "matches": local_matches,
                "verses": verses[:10],  # max 10 per translation
            })
        total_matches += local_matches

    return {
        "status": "ok",
        "query": query,
        "lang_filter": lang or "all",
        "files_searched": total_searched,
        "total_matches": total_matches,
        "results": results,
    }


# ── Hymn Search ──────────────────────────────────────────────

def hymns_list_translations():
    """List available hymn resources in the hymns directory."""
    if not HYMNS_DIR.exists():
        return {"status": "not_found", "resources": []}

    resources = []
    for f in sorted(HYMNS_DIR.glob("*")):
        if not f.is_file():
            continue
        name = f.name
        # Skip generated index/corpus files for the resource list
        if name.startswith("00-") or name in ("INDEX.md",):
            continue
        size_kb = f.stat().st_size // 1024
        size_mb = f.stat().st_size / (1024**2)
        # Determine type
        ext = f.suffix.lower()
        if ext == ".pdf":
            rtype = "📄 Scores (PDF)"
        elif ext == ".abc":
            rtype = "🎵 Notation (ABC)"
        elif ext == ".mid" or ext == ".midi":
            rtype = "🎶 Audio (MIDI)"
        elif ext == ".xml":
            rtype = "📋 Lyrics (XML)"
        elif ext == ".zip":
            rtype = "📦 Archive"
        elif ext == ".txt":
            rtype = "📝 Lyrics"
        elif ext == ".gif":
            rtype = "🖼️ Score Image"
        else:
            rtype = "📄 File"

        size_str = f"{size_mb:.1f} MB" if size_mb > 1 else f"{size_kb} KB"
        resources.append({"file": name, "type": rtype, "size": size_str})

    return {
        "status": "ready" if resources else "empty",
        "dir": str(HYMNS_DIR),
        "count": len(resources),
        "resources": resources,
    }


def hymns_search(query):
    """Search hymn lyrics across all available text sources."""
    if not HYMNS_DIR.exists():
        return {"status": "not_found", "error": "Hymn directory not found. Run prep-hymns.sh first."}

    results = []

    # Search in the corpus text file (fastest)
    corpus_file = HYMNS_DIR / "00-hymns-corpus.txt"
    if corpus_file.exists():
        query_lower = query.lower()
        hymn_blocks = []
        current_block = []
        current_title = ""
        in_hymn = False
        try:
            with open(corpus_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("=== HYMN "):
                        # Save previous block
                        if current_block:
                            hymn_blocks.append({"title": current_title, "lines": current_block})
                        current_block = []
                        current_title = ""
                        in_hymn = True
                    elif line.startswith("Title:"):
                        current_title = line[6:].strip()
                        current_block.append(line.strip())
                    else:
                        current_block.append(line.strip())

                # Last hymn
                if current_block:
                    hymn_blocks.append({"title": current_title, "lines": current_block})

            # Search
            for hymn in hymn_blocks:
                title = hymn["title"]
                lines = hymn["lines"]
                matching_lines = [l for l in lines if query_lower in l.lower()]
                if matching_lines:
                    results.append({
                        "title": title,
                        "matches": len(matching_lines),
                        "lines": matching_lines[:8],
                    })

        except Exception as e:
            results.append({"error": f"Error reading corpus: {e}"})

    # Fallback: search raw ThML XML
    if not results:
        thml_file = HYMNS_DIR / "openhymnal.201406.xml"
        if thml_file.exists():
            try:
                with open(thml_file, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                query_lower = query.lower()
                # Simple line-by-line search
                lines = content.split("\n")
                matches = [l.strip() for l in lines if query_lower in l.lower() and len(l.strip()) > 10]
                if matches:
                    results.append({
                        "title": "Raw ThML XML",
                        "matches": len(matches),
                        "lines": matches[:8],
                    })
            except Exception as e:
                results.append({"error": f"Error reading ThML: {e}"})

    # Fallback: search PDF metadata (basic filename match)
    if not results:
        pdf_files = list(HYMNS_DIR.glob("*.pdf"))
        if pdf_files:
            results.append({
                "title": "Hymn PDFs available",
                "matches": len(pdf_files),
                "lines": [f.name for f in pdf_files[:5]],
            })

    total_matches = sum(r.get("matches", 0) for r in results)
    return {
        "status": "ok" if results else "empty",
        "query": query,
        "total_matches": total_matches,
        "results": results,
    }


# ── CLI ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Hermes Cortex Offline Knowledge Cascade",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  offline_knowledge query "symptoms of malaria"
  offline_knowledge cascade-search "history of this region"
  offline_knowledge kiwix-search "snake bite treatment"
  offline_knowledge kiwix-status
  offline_knowledge kiwix-list
  offline_knowledge generate-library
  offline_knowledge stats
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command")
    
    # query
    q = subparsers.add_parser("query", help="Cascade knowledge lookup (cache → kiwix → gbrain → suggestion)")
    q.add_argument("question", nargs="+", help="The question to answer")
    
    # cascade-search
    cs = subparsers.add_parser("cascade-search", help="Detailed cascade with per-source results")
    cs.add_argument("question", nargs="+", help="The question to answer")
    
    # kiwix-search
    ks = subparsers.add_parser("kiwix-search", help="Direct ZIM full-text search")
    ks.add_argument("term", nargs="+", help="Search term")
    
    # kiwix-status
    subparsers.add_parser("kiwix-status", help="Check if kiwix-serve is running")
    
    # kiwix-list
    subparsers.add_parser("kiwix-list", help="List available ZIM content")
    
    # generate-library
    subparsers.add_parser("generate-library", help="Generate kiwix library XML from ZIM files")
    
    # stats
    subparsers.add_parser("stats", help="Show offline knowledge system status")

    # bible
    bible = subparsers.add_parser("bible", help="Search Bible translations")
    bible_sub = bible.add_subparsers(dest="bible_command")

    bs = bible_sub.add_parser("search", help="Search Bible verses across translations")
    bs.add_argument("query", nargs="+", help="Search text (word, phrase, or reference)")
    bs.add_argument("--lang", "-l", default=None, help="Filter by language code (e.g. en, es, ko)")

    bible_sub.add_parser("list", help="List available Bible translations")

    # hymns
    hymns = subparsers.add_parser("hymns", help="Search hymn lyrics and resources")
    hymns_sub = hymns.add_subparsers(dest="hymns_command")

    hs = hymns_sub.add_parser("search", help="Search hymn lyrics")
    hs.add_argument("query", nargs="+", help="Search text (title, phrase, or lyric line)")

    hymns_sub.add_parser("list", help="List available hymn resources")

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    if args.command == "query":
        question = " ".join(args.question)
        result = cascade_query(question, detailed=False)
        print(json.dumps(result, indent=2, default=str))
    
    elif args.command == "cascade-search":
        question = " ".join(args.question)
        result = cascade_query(question, detailed=True)
        print(json.dumps(result, indent=2, default=str))
    
    elif args.command == "kiwix-search":
        term = " ".join(args.term)
        result = kiwix_search(term, max_results=10)
        print(json.dumps(result, indent=2, default=str))
    
    elif args.command == "kiwix-status":
        result = kiwix_status()
        if result["running"]:
            print(f"✅ kiwix-serve is running: {result['status']}")
        else:
            print("❌ kiwix-serve is NOT running")
            print("   Start it: docker compose -f offline/kiwix-docker-compose.yml up -d")
    
    elif args.command == "kiwix-list":
        result = kiwix_list_content()
        if result["zim_files"]:
            print(f"\n📚 ZIM Content ({result['total']} files, {result['total_size_gb']} GB total)")
            print("─" * 60)
            for f in result["zim_files"]:
                icon = "✅" if result.get("kiwix_running") else "📄"
                print(f"  {icon} {f['label']}")
                print(f"     {f['name']} ({f['size_gb']} GB)")
            if not result.get("kiwix_running"):
                print("\n⚠️  kiwix-serve not running — start it to query this content.")
        else:
            print("📂 No ZIM files found. Download some:")
            print("   https://download.kiwix.org/zim/")
    
    elif args.command == "generate-library":
        if generate_library_xml():
            print(f"✅ Library file generated: {LIBRARY_FILE}")
            print("   Restart kiwix-serve to pick up changes:")
            print("   docker compose -f offline/kiwix-docker-compose.yml restart")
        else:
            print("❌ No ZIM files found to generate library")
    
    elif args.command == "stats":
        stats = system_stats()
        print("\n🔍 Hermes Cortex — Offline Knowledge System")
        print("=" * 60)
        
        wc = stats["web_cache"]
        if wc["status"] == "ready":
            print(f"\n📦 Web Cache:  ✅ ({wc['size_mb']} MB, {wc['db']})")
        else:
            print(f"\n📦 Web Cache:  ❌ {wc['status']}")
        
        kw = stats["kiwix"]
        icon = "✅" if kw["status"] == "running" else "❌"
        print(f"\n🌐 kiwix-serve: {icon} {kw['status']} ({kw['detail']})")
        
        zc = stats["zim_content"]
        if zc.get("files"):
            print(f"\n📚 ZIM Content: {zc['status']} ({zc['total_size_gb']} GB)")
            for f in zc["files"]:
                print(f"   · {f}")
        else:
            print(f"\n📚 ZIM Content: {zc['status']}")
        
        gb = stats["gbrain"]
        gi = "✅" if gb["status"] == "ready" else "❌"
        print(f"\n🧠 gbrain:     {gi} {gb['status']}")

        # Bible stats
        bible_info = bible_list_translations()
        if bible_info["status"] == "ready":
            print(f"\n📖 Bible:      ✅ {bible_info['count']} translations ({bible_info['total_size_mb']} MB)")
        elif bible_info["status"] == "empty":
            print(f"\n📖 Bible:      ⚪ Empty (run: prep-bible.sh)")
        else:
            print(f"\n📖 Bible:      ❌ Not found")

        # Hymn stats
        hymn_info = hymns_list_translations()
        if hymn_info["status"] == "ready":
            print(f"\n🎵 Hymns:      ✅ {hymn_info['count']} resources")
        elif hymn_info["status"] == "empty":
            print(f"\n🎵 Hymns:      ⚪ Empty (run: prep-hymns.sh)")
        else:
            print(f"\n🎵 Hymns:      ❌ Not found")

        print()

    elif args.command == "bible":
        if args.bible_command == "search":
            query = " ".join(args.query)
            result = bible_search(query, lang=args.lang)
            if result["status"] != "ok":
                print(f"❌ {result.get('error', 'Unknown error')}")
                sys.exit(1)

            print(f"\n📖 Bible Search: \"{result['query']}\" ({result['lang_filter']})")
            print(f"   {result['total_matches']} matches across {result['files_searched']} files\n")
            for r in result["results"]:
                print(f"  📄 {r['file']} ({r['size_kb']} KB) — {r['matches']} matches")
                for v in r["verses"][:5]:
                    print(f"     · {v[:120]}")
                if r["matches"] > len(r["verses"]):
                    print(f"     … ({r['matches']} total matches)")
                print()
            if not result["results"]:
                print("   No matches found.\n")

        elif args.bible_command == "list":
            result = bible_list_translations()
            if result["status"] == "ready":
                print(f"\n📖 Bible Translations ({result['count']} files, {result['total_size_mb']} MB total)")
                print(f"   Directory: {result['dir']}\n")
                for t in result["translations"]:
                    lang_code = t["name"].split("_")[-1] if "_" in t["name"] else "?"
                    print(f"  · {t['name']:30s} {t['size_kb']:>6} KB")
            else:
                print(f"📖 No Bible translations found. Run: prep-bible.sh")

    elif args.command == "hymns":
        if args.hymns_command == "search":
            query = " ".join(args.query)
            result = hymns_search(query)
            if result["status"] == "not_found":
                print(f"❌ {result.get('error', 'Hymn directory not found')}")
                print("   Run: offline/prep-hymns.sh")
                sys.exit(1)

            print(f"\n🎵 Hymn Search: \"{result['query']}\"")
            print(f"   {result['total_matches']} matches in {len(result['results'])} hymn(s)\n")
            for r in result["results"]:
                if "error" in r:
                    print(f"  ⚠️  {r['error']}")
                    continue
                print(f"  🎵 {r['title']} — {r['matches']} match(es)")
                for line in r["lines"][:6]:
                    print(f"     · {line[:140]}")
                if r["matches"] > len(r["lines"]):
                    print(f"     … ({r['matches']} total matches)")
                print()
            if not result.get("results"):
                print("   No matches found.\n")
                print("   Tip: For now, search also works on PDF/ABC filenames.")
                print("   Run 'prep-hymns.sh --lyrics-only' for full lyric search.\n")

        elif args.hymns_command == "list":
            result = hymns_list_translations()
            if result["status"] == "ready":
                print(f"\n🎵 Hymn Resources ({result['count']} files)")
                print(f"   Directory: {result['dir']}\n")
                for r in result["resources"]:
                    print(f"  · {r['type']:20s} {r['file']:40s} {r['size']}")
            else:
                print(f"🎵 No hymn resources found. Run: prep-hymns.sh")


if __name__ == "__main__":
    main()
