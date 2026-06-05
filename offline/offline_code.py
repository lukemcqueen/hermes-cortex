#!/usr/bin/env python3
"""
Hermes Cortex — Offline Code Assistant
───────────────────────────────────────
Local code snippet RAG: search a curated corpus of algorithms, patterns,
and API examples, then generate code using Ollama.

Two-tier system:
  - Small model (1.5B-3B) + RAG ≈ productivity of 7B model
  - All data stays on your machine

Usage:
  offline_code search "flask rest api"         → Find relevant snippets
  offline_code gen "binary search tree rust"   → Generate code using Ollama
  offline_code index                           → (Re)build the search index
  offline_code stats                           → Show corpus stats

Requirements: Python 3.10+, Ollama running with nomic-embed-text
Optional: qwen2.5-coder:1.5b (or higher) for code generation
"""
import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
import unicodedata
from pathlib import Path

HOME = Path.home()
CORPUS_DIR = Path(__file__).parent / "code-corpus"
INDEX_DB = HOME / "offline" / "code-index.json"
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
GEN_MODEL = "qwen2.5-coder:1.5b"


# ── Corpus Loading ──────────────────────────────────────────

def load_snippets():
    """Load all snippet markdown files from the corpus directory."""
    snippets = []
    for md_file in sorted(CORPUS_DIR.rglob("*.md")):
        if md_file.name == "INDEX.md":
            continue
        content = md_file.read_text(encoding="utf-8")
        meta, code = parse_snippet(content)
        if meta and code:
            snippets.append({
                "path": str(md_file.relative_to(CORPUS_DIR)),
                "language": meta.get("language", "unknown"),
                "title": meta.get("title", md_file.stem),
                "tags": meta.get("tags", []),
                "description": meta.get("description", ""),
                "source": meta.get("source", ""),
                "code": code,
            })
    return snippets


def parse_snippet(content):
    """Parse YAML frontmatter + code block from a snippet file."""
    # Extract frontmatter --- ... ---
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not fm_match:
        return None, None

    meta = {}
    for line in fm_match.group(1).split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            # Parse list values like tags: [a, b, c]
            if value.startswith("[") and value.endswith("]"):
                value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",")]
            meta[key] = value

    # Extract first code block
    code_match = re.search(r"```[a-zA-Z0-9_+#]*\n(.*?)```", content, re.DOTALL)
    code = code_match.group(1).strip() if code_match else ""

    return meta, code


# ── Embedding (Ollama) ──────────────────────────────────────

def _ollama_embed(texts):
    """Get embeddings from Ollama for a list of texts (batched)."""
    if isinstance(texts, str):
        texts = [texts]

    BATCH_SIZE = 10
    all_embeddings = []

    import urllib.request

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        try:
            body = json.dumps({"model": EMBED_MODEL, "input": batch}).encode()
            req = urllib.request.Request(
                f"{OLLAMA_URL}/api/embed",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
            batch_embeddings = data.get("embeddings", [])
            all_embeddings.extend(batch_embeddings)
            print(f"  Embedded batch {i//BATCH_SIZE + 1}/{(len(texts) + BATCH_SIZE - 1)//BATCH_SIZE} ({len(batch_embeddings)} embeddings)", end="\r", file=sys.stderr)
        except Exception as e:
            print(f"\n  Embedding error at batch {i//BATCH_SIZE + 1}: {e}", file=sys.stderr)
            return []

    print(file=sys.stderr)  # newline after progress
    return all_embeddings


def _ensure_embed_model():
    """Ensure nomic-embed-text is pulled in Ollama."""
    try:
        import urllib.request
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            models = json.loads(resp.read().decode()).get("models", [])
        for m in models:
            if EMBED_MODEL in m.get("name", ""):
                return True
        print(f"  Pulling {EMBED_MODEL} (one-time download)...")
        body = json.dumps({"model": EMBED_MODEL}).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/pull", data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300):
            pass
        return True
    except Exception as e:
        print(f"  Model error: {e}", file=sys.stderr)
        return False


# ── Index ───────────────────────────────────────────────────

def cmd_index(force=False):
    """Build or rebuild the search index as a JSON file with embeddings."""
    snippets = load_snippets()
    if not snippets:
        print("No snippets found in corpus.")
        return

    print(f"Loaded {len(snippets)} snippets from corpus.")

    # Check if index exists and is current
    if INDEX_DB.exists() and not force:
        with open(INDEX_DB) as f:
            existing = json.load(f)
        if len(existing.get("snippets", [])) == len(snippets):
            print(f"Index is current ({len(snippets)} snippets). Use --force to rebuild.")
            return

    if not _ensure_embed_model():
        print("Cannot proceed without embedding model.")
        return

    # Build embedding texts
    embed_texts = []
    for s in snippets:
        tag_str = ", ".join(s["tags"]) if isinstance(s["tags"], list) else s["tags"]
        text = f"Language: {s['language']}\nTitle: {s['title']}\n"
        text += f"Tags: {tag_str}\nDescription: {s['description']}\n"
        text += f"Code:\n{s['code'][:2000]}"
        embed_texts.append(text)

    print(f"Generating {len(embed_texts)} embeddings with {EMBED_MODEL}...")
    embeddings = _ollama_embed(embed_texts)

    if not embeddings or len(embeddings) != len(snippets):
        print(f"Embedding failed: got {len(embeddings)} embeddings for {len(snippets)} snippets")
        return

    # Build index JSON
    index_data = {
        "model": EMBED_MODEL,
        "dim": len(embeddings[0]),
        "count": len(snippets),
        "snippets": [],
    }
    for i, s in enumerate(snippets):
        tag_str = ", ".join(s["tags"]) if isinstance(s["tags"], list) else s["tags"]
        index_data["snippets"].append({
            "id": i + 1,
            "path": s["path"],
            "language": s["language"],
            "title": s["title"],
            "tags": tag_str,
            "description": s["description"],
            "source": s["source"],
            "code": s["code"],
            "embedding": embeddings[i],
        })

    INDEX_DB.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_DB, "w") as f:
        json.dump(index_data, f)

    print(f"Indexed {len(snippets)} snippets ({len(embeddings)} vectors, {len(embeddings[0])} dimensions)")
    print(f"DB: {INDEX_DB} ({INDEX_DB.stat().st_size / 1024:.0f} KB)")


def _cosine_similarity(a, b):
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0
    return dot / (na * nb)


def _load_index():
    """Load the search index JSON."""
    if not INDEX_DB.exists():
        return None
    with open(INDEX_DB) as f:
        return json.load(f)


# ── Search ──────────────────────────────────────────────────

def cmd_search(query, limit=5, lang=None):
    """Search the code corpus for snippets matching a query."""
    index = _load_index()
    if not index:
        print("Index not found. Run: offline_code index")
        return

    snippets = index.get("snippets", [])
    terms = query.lower().split()

    # Embed the query ONCE for semantic search
    q_emb = _ollama_embed(query)
    q_emb = q_emb[0] if q_emb else None

    # Score each snippet by keyword match + semantic
    results = []
    for s in snippets:
        if lang and s["language"] != lang:
            continue
        text = f"{s['title']} {s['tags']} {s['description']} {s['code']}".lower()
        kw_score = sum(1 for t in terms if t in text)

        # Semantic score using pre-computed query embedding
        sem_score = 0
        if q_emb and s.get("embedding"):
            try:
                sem_score = _cosine_similarity(s["embedding"], q_emb)
            except Exception:
                pass

        if kw_score > 0 or sem_score > 0:
            score = max(kw_score / len(terms) * 100, sem_score * 100)
            results.append((score, s))

    results.sort(key=lambda r: r[0], reverse=True)

    if not results:
        print("No matching snippets found.")
        return

    print(f"\nFound {len(results)} matching snippet(s)\n")
    for i, (score, s) in enumerate(results[:limit], 1):
        lang = s["language"]
        title = s["title"]
        tags = s["tags"]
        desc = s["description"]
        code = s["code"]

        print(f"─── [{i}] {title} ───")
        print(f"  Language: {lang}  |  Tags: {tags}  |  Score: {score:.0f}%")
        if desc:
            print(f"  {desc}")
        print()
        code_lines = code.split("\n")
        for line in code_lines[:12]:
            print(f"    {line}")
        if len(code_lines) > 12:
            print(f"    … ({len(code_lines) - 12} more lines)")
        print()


# ── Generate ────────────────────────────────────────────────

def cmd_generate(query, model=None, limit=3):
    """Search corpus, then ask Ollama to generate code based on context."""
    model = model or GEN_MODEL

    # First, find relevant snippets
    index = _load_index()
    if not index:
        print("Index not found. Running without RAG context.")
        snippets = []
    else:
        # Quick keyword search over the loaded index
        terms = query.lower().split()
        scored = []
        for s in index.get("snippets", []):
            text = f"{s['title']} {s['tags']} {s['description']} {s['code']}".lower()
            kw_score = sum(1 for t in terms if t in text)
            if kw_score > 0:
                scored.append((kw_score, s))
        scored.sort(key=lambda r: r[0], reverse=True)
        snippets = [s for _, s in scored[:limit]]

    # Build prompt
    prompt_parts = []
    if snippets:
        prompt_parts.append("Here are some relevant code patterns to reference:\n")
        for s in snippets[:limit]:
            prompt_parts.append(f"--- {s['title']} ({s['language']}) ---")
            prompt_parts.append(s["code"])
            prompt_parts.append("")
        prompt_parts.append("---")

    prompt_parts.append(f"Generate {query}.")
    prompt_parts.append("Return ONLY working code with brief comments. No extra explanation.")
    full_prompt = "\n".join(prompt_parts)

    # Call Ollama
    try:
        import urllib.request
        body = json.dumps({
            "model": model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 2048,
            }
        }).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        print(f"\n  Generating with {model}...\n")
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
        output = data.get("response", "")
        # Clean up the output (remove thinking tags if any)
        output = re.sub(r'<think>.*?</think>', '', output, flags=re.DOTALL).strip()
        # Print just the code
        print(output)
        print()
    except Exception as e:
        print(f"Generation failed: {e}")
        print("Make sure Ollama is running and the model is pulled:")
        print(f"  ollama pull {model}")


# ── Stats ───────────────────────────────────────────────────

def cmd_stats():
    """Show corpus and index statistics."""
    snippets = load_snippets()
    print(f"\n📚 Code Corpus")
    print(f"   Snippets:   {len(snippets)}")
    if snippets:
        langs = {}
        tags = {}
        for s in snippets:
            l = s["language"]
            langs[l] = langs.get(l, 0) + 1
            for t in (s["tags"] if isinstance(s["tags"], list) else [s["tags"]]):
                tags[t] = tags.get(t, 0) + 1
        print(f"   Languages:  {', '.join(f'{k}={v}' for k, v in sorted(langs.items()))}")
        print(f"   Top tags:   {', '.join(sorted(tags, key=tags.get, reverse=True)[:8])}")

    index = _load_index()
    if index:
        size_kb = INDEX_DB.stat().st_size / 1024
        count = len(index.get("snippets", []))
        dim = index.get("dim", "?")
        print(f"\n🔍 Search Index")
        print(f"   Indexed:    {count} snippets ({dim} dims)")
        print(f"   DB size:    {size_kb:.0f} KB")
        print(f"   DB path:    {INDEX_DB}")
    else:
        print(f"\n🔍 Search Index: not built (run 'offline_code index')")

    # Check models
    try:
        import urllib.request
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            models = [m.get("name", "") for m in json.loads(resp.read().decode()).get("models", [])]
        emb_ok = any(EMBED_MODEL in m for m in models)
        gen_ok = any("qwen2.5-coder" in m for m in models)
        print(f"\n🤖 Ollama Models")
        print(f"   {EMBED_MODEL}:     {'✅' if emb_ok else '❌'} (pull: ollama pull {EMBED_MODEL})")
        print(f"   Code gen:   {'✅' if gen_ok else '⚠️  not pulled'} (pull: ollama pull {GEN_MODEL})")
        if models:
            print(f"   Available:  {', '.join(models[:5])}")
    except Exception:
        print(f"\n🤖 Ollama: ❌ not running")
    print()


# ── CLI ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Offline Code Assistant — search & generate from curated code corpus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              offline_code search "flask rest api with sqlite"
              offline_code gen "binary search tree in rust" --model qwen2.5-coder:3b
              offline_code index
              offline_code index --force
              offline_code stats
        """),
    )
    sub = parser.add_subparsers(dest="command")

    # Search
    s = sub.add_parser("search", help="Search the code corpus")
    s.add_argument("query", nargs="+", help="Search terms")
    s.add_argument("--limit", "-n", type=int, default=5, help="Max results")
    s.add_argument("--lang", "-l", help="Filter by language")

    # Generate
    g = sub.add_parser("gen", help="Generate code using Ollama + RAG context")
    g.add_argument("query", nargs="+", help="What to generate")
    g.add_argument("--model", "-m", default=None, help=f"Ollama model (default: {GEN_MODEL})")
    g.add_argument("--limit", "-n", type=int, default=3, help="Number of RAG context snippets")

    # Index
    i = sub.add_parser("index", help="(Re)build the search index")
    i.add_argument("--force", "-f", action="store_true", help="Force rebuild even if current")

    # Stats
    sub.add_parser("stats", help="Show corpus and index statistics")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "search":
        cmd_search(" ".join(args.query), limit=args.limit, lang=args.lang)
    elif args.command == "gen":
        cmd_generate(" ".join(args.query), model=args.model, limit=args.limit)
    elif args.command == "index":
        cmd_index(force=args.force)
    elif args.command == "stats":
        cmd_stats()


if __name__ == "__main__":
    main()
