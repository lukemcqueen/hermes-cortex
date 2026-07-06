#!/usr/bin/env python3
"""agent-apply-fixes.py — Read remediation markers, search offline corpus, apply fixes.

no_agent cron script. Runs every 10 minutes.

Strategy:
  1. Scan ~/.hermes/state/remediate/ for inbox-*.txt markers
  2. If none → silent exit (no delivery, no tokens wasted)
  3. Read each marker, extract keywords from subject/body
  4. Search offline code corpus with those keywords
  5. Classify issue from search results → apply deterministic fix
  6. If offline search doesn't match known patterns → log for agent-fixer
  7. Report what was done
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
STATE_DIR = HOME / ".hermes" / "state"
REMEDIATE_DIR = STATE_DIR / "remediate"
DONE_DIR = REMEDIATE_DIR / "done"
SCRIPTS_DIR = HOME / ".hermes" / "scripts"
OFFLINE_CODE = HOME / "hermes-cortex" / "src" / "offline" / "offline_code.py"

KST = timezone(timedelta(hours=9))

# ── Known fix patterns — keywords that map to handlers ──────────
# Each entry: keyword list → handler function name → display name
FIX_PATTERNS = {
    "nginx":      ("fix_nginx_issue", "nginx"),
    "service":    ("fix_service_restart", "service"),
    "disk":       ("fix_disk_space", "disk"),
    "ollama":     ("fix_ollama_stale", "ollama"),
    "web_cache":  ("fix_web_cache_cleanup", "web_cache"),
    "cert":       ("fix_cert_issue", "certificate"),
}


def kst_now() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def log(msg: str):
    print(msg, file=sys.stderr)


def run_cmd(cmd: str, timeout: int = 30) -> tuple[str, str, int]:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            shell=True, executable="/bin/bash",
        )
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", f"timed out after {timeout}s", -1
    except Exception as e:
        return "", str(e), -1


# ── Import fix handlers from agent-remediate-apply.py ──────────
def _import_fix_handlers():
    """Dynamically import fix functions from agent-remediate-apply.py."""
    remediate_path = SCRIPTS_DIR / "agent-remediate-apply.py"
    if not remediate_path.exists():
        log(f"⚠️  agent-remediate-apply.py not found at {remediate_path}")
        return {}
    
    import importlib.util
    spec = importlib.util.spec_from_file_location("remediate", remediate_path)
    if spec is None or spec.loader is None:
        log("⚠️  Could not load agent-remediate-apply.py as module")
        return {}
    
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    
    handlers = {}
    for attr in dir(mod):
        if attr.startswith("fix_") and callable(getattr(mod, attr)):
            handlers[attr] = getattr(mod, attr)
    return handlers


# ── Offline corpus search ──────────────────────────────────────
def search_offline(query: str, timeout: int = 30) -> str:
    """Search offline code corpus. Returns raw output or empty string."""
    if not OFFLINE_CODE.exists():
        log(f"⚠️  offline_code.py not found at {OFFLINE_CODE}")
        return ""
    
    result = subprocess.run(
        [sys.executable, str(OFFLINE_CODE), "search", query],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        log(f"⚠️  offline_code search failed: {result.stderr.strip()[:200]}")
        return ""
    return result.stdout


def classify_issue(text: str) -> list[tuple[str, str, float]]:
    """Classify a text (subject + body) against known fix patterns.
    
    Returns list of (pattern_key, handler_name, confidence) sorted by confidence.
    Uses offline corpus search + keyword matching.
    """
    text_lower = text.lower()
    matches = []
    
    # 1. Quick keyword match (fast path)
    for keyword, (handler, label) in FIX_PATTERNS.items():
        if keyword in text_lower:
            matches.append((keyword, handler, 0.8))
    
    # 2. Offline corpus search (deep path) — only if no keyword match
    if not matches:
        # Extract key terms: filter out common words, take meaningful ones
        words = re.findall(r'[a-zA-Z][a-zA-Z0-9_-]{2,}', text_lower)
        stopwords = {"the", "and", "for", "are", "not", "but", "has", "have",
                     "from", "that", "this", "with", "what", "when", "where",
                     "which", "there", "their", "will", "been", "could",
                     "should", "would", "about", "into", "over", "after",
                     "still", "also", "been", "than", "then", "some", "them",
                     "fix", "need", "help", "issue", "problem", "error",
                     "please", "check", "agent"}
        terms = [w for w in words if w not in stopwords and len(w) > 2]
        if terms:
            query = " ".join(terms[:5])
            log(f"  🔍 Offline search: '{query}'")
            results = search_offline(query)
            
            # Check if any result mentions known patterns
            for keyword, (handler, label) in FIX_PATTERNS.items():
                if keyword in results.lower()[:2000]:
                    confidence = 0.6  # lower confidence from indirect match
                    matches.append((keyword, handler, confidence))
                    break
    
    return matches


# ── Fix dispatch ──────────────────────────────────────────────
FIX_HANDLERS_MAP: dict[str, callable] = {}


def apply_fix(marker: dict, handlers: dict) -> tuple[str | None, list]:
    """Try to apply a fix based on marker content. Returns (result, classifications)."""
    subject = marker.get("subject", "")
    body = marker.get("body", "")
    text = f"{subject} {body}"
    
    # Try to classify
    classifications = classify_issue(text)
    if not classifications:
        return None, []
    
    best_keyword, best_handler, confidence = classifications[0]
    handler_fn = handlers.get(best_handler)
    
    if handler_fn:
        context = {"service": best_keyword}
        # For service restart, try to extract service name
        if best_keyword == "service":
            # Look for a service name in the body
            for word in re.findall(r'[a-zA-Z][a-zA-Z0-9_-]{2,}', body.lower()):
                if word.endswith((".service", ".socket", ".timer")):
                    context["service"] = word
                    break
        
        log(f"  🔧 Applying fix for '{best_keyword}' (confidence={confidence})")
        try:
            result = handler_fn(context)
            if result:
                return f"[{best_keyword}] {result}", classifications
        except Exception as e:
            log(f"  ❌ Handler {best_handler} failed: {e}")
    
    return None, classifications


# ── Marker reading ────────────────────────────────────────────
def scan_markers() -> list[dict]:
    """Scan ~/.hermes/state/remediate/ for pending inbox markers."""
    if not REMEDIATE_DIR.exists():
        return []
    
    markers = []
    for f in sorted(REMEDIATE_DIR.iterdir()):
        if f.name.startswith("inbox-") and f.suffix == ".txt":
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                marker = parse_marker(content, f)
                markers.append(marker)
            except Exception as e:
                log(f"⚠️  Error reading {f.name}: {e}")
    
    return markers


def parse_marker(content: str, path: Path) -> dict:
    """Parse a marker file into structured fields."""
    marker = {
        "filename": path.name,
        "path": str(path),
    }
    
    for line in content.splitlines():
        if line.startswith("from="):
            marker["sender"] = line[5:].strip()
        elif line.startswith("subject="):
            marker["subject"] = line[8:].strip()
        elif line.startswith("file="):
            marker["file"] = line[5:].strip()
        elif line.startswith("---"):
            # End of header — everything after is body
            break
    
    # Extract body — everything after first ---
    parts = content.split("---", 1)
    if len(parts) > 1:
        marker["body"] = parts[1].strip()
    else:
        marker["body"] = ""
    
    return marker


def mark_done(marker: dict):
    """Move a marker to done/ directory."""
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(marker["path"])
    dst = DONE_DIR / src.name
    try:
        src.rename(dst)
        log(f"  ✅ Moved {src.name} to done/")
    except Exception as e:
        log(f"  ⚠️  Could not move {src.name}: {e}")


# ── Main ──────────────────────────────────────────────────────
def main() -> int:
    log(f"🔧 agent-apply-fixes at {kst_now()}")
    
    # 1. Import fix handlers
    handlers = _import_fix_handlers()
    if not handlers:
        log("⚠️  No fix handlers available — nothing to do")
        return 0
    
    # 2. Scan for pending markers
    markers = scan_markers()
    if not markers:
        log("📭 No pending remediation markers — silent exit")
        return 0  # Silent = no output for no_agent
    
    log(f"📋 Found {len(markers)} pending marker(s)")
    
    # 3. Process each marker
    fixed = []
    unknown = []
    failed = []
    
    for marker in markers:
        sender = marker.get("sender", "unknown")
        subject = marker.get("subject", "No subject")
        log(f"  ── From: {sender} — {subject}")
        
        result, classifications = apply_fix(marker, handlers)
        
        if result:
            fixed.append((marker, result))
            log(f"    ✅ {result}")
        else:
            if classifications:
                failed.append((marker, f"No handler for {classifications[0][0]}"))
                log(f"    ❌ Could not fix — no handler available")
            else:
                unknown.append(marker)
                log(f"    ❓ Unknown issue type — will defer to agent-fixer")
        
        mark_done(marker)
    
    # 4. Output report
    lines = []
    if fixed:
        lines.append(f"🔧 agent-apply-fixes ran at {kst_now()}")
        for marker, result in fixed:
            lines.append(f"  ✅ {result}")
        lines.append("")
    
    if failed:
        lines.append(f"  ❌ {len(failed)} issue(s) could not be fixed:")
        for marker, reason in failed:
            lines.append(f"     - {marker.get('subject', '?')}: {reason}")
        lines.append("")
    
    if unknown:
        lines.append(f"  ❓ {len(unknown)} issue(s) deferred to agent-fixer (unknown type):")
        for marker in unknown:
            lines.append(f"     - {marker.get('sender', '?')}: {marker.get('subject', '?')[:80]}")
        lines.append("")
    
    if lines:
        print("\n".join(lines).strip())
    
    return 0 if not failed else 0  # Don't fail — just report


if __name__ == "__main__":
    sys.exit(main())
