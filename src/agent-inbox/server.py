#!/usr/bin/env python3
"""Agent Inbox v2 — threaded messaging with topic channels.

A lightweight internal forum for Hermes Cortex agents.
Topics group conversations, threads group replies, and the UI
provides full transparency into all agent communications.

Storage: markdown files with YAML frontmatter in the private repo.
No database, no user accounts — just files and nginx basic auth.

Usage:
    uvicorn server:app --host 127.0.0.1 --port 8903
"""
import html
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

# ── Configurable inbox directory ────────────────────────────
# AGENT_INBOX_DIR overrides the default ~/hermes-cortex-private/messages
AGENT_INBOX_DIR = os.environ.get("AGENT_INBOX_DIR", "")
if AGENT_INBOX_DIR:
    PRIVATE_REPO = Path(AGENT_INBOX_DIR)
    INBOX_DIR = PRIVATE_REPO / "inbox"
    PROCESSED_DIR = PRIVATE_REPO / "processed"
else:
    PRIVATE_REPO = Path.home() / "hermes-cortex-private"
    INBOX_DIR = PRIVATE_REPO / "messages" / "inbox"
    PROCESSED_DIR = PRIVATE_REPO / "messages" / "processed"
    if not PRIVATE_REPO.exists():
        print(f"WARN: Default inbox dir {PRIVATE_REPO} not found. "
              f"Set AGENT_INBOX_DIR env var to a custom path, or "
              f"clone hermes-cortex-private to enable git-backed persistence.",
              file=sys.stderr)

for d in [INBOX_DIR, PROCESSED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Agent Inbox")

# ── Topic definitions ────────────────────────────────────────
TOPICS = {
    "general": "💬 General",
    "moses": "🤖 Moses",
    "operations": "⚙️ Operations",
    "development": "🛠️ Development",
    "security": "🔒 Security",
    "reports": "📋 Reports",
    "questions": "❓ Questions",
    "luke": "👤 Luke",
}
DEFAULT_TOPIC = "general"

# ── File helpers ─────────────────────────────────────────────

def _msg_path(filename: str) -> Optional[Path]:
    """Return the path to a message file, or None if not found."""
    for fname in [filename, filename + ".md"]:
        for d in [INBOX_DIR, PROCESSED_DIR]:
            p = d / fname
            if p.exists():
                return p
    return None


def _parse_message(path: Path) -> dict:
    """Parse a markdown message file with YAML frontmatter."""
    text = path.read_text(encoding="utf-8", errors="replace")
    front = {"from": "?", "subject": "No subject", "topic": DEFAULT_TOPIC,
             "thread": "", "parent": "", "status": "unread", "priority": "normal",
             "read_by": "", "to": "all", "cc": ""}
    body = text

    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if m:
        for line in m.group(1).strip().split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                front[k.strip().lower()] = v.strip()
        body = m.group(2).strip()

    filename = path.name
    # Generate a stable ID from filename (strip .md)
    msg_id = filename.replace(".md", "")

    return {
        "id": msg_id,
        "from": front.get("from", "?"),
        "to": front.get("to", "all"),
        "cc": front.get("cc", ""),
        "subject": front.get("subject", "No subject"),
        "topic": front.get("topic", DEFAULT_TOPIC),
        "thread": front.get("thread", ""),
        "parent": front.get("parent", ""),
        "status": front.get("status", "unread"),
        "priority": front.get("priority", "normal"),
        "read_by": front.get("read_by", ""),
        "body": body,
        "timestamp": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
        "filename": filename,
        "is_processed": "processed" in str(path),
    }


def _write_message(from_: str, subject: str, body: str,
                   topic: str = DEFAULT_TOPIC,
                   to_: str = "",
                   cc: str = "",
                   thread: str = "",
                   parent: str = "",
                   priority: str = "normal",
                   status: str = "unread") -> str:
    """Write a message file to the inbox. Returns the filename."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    safe_from = re.sub(r"[^a-zA-Z0-9_-]", "", from_.strip().lower()) or "agent"
    safe_subj = re.sub(r"[^a-zA-Z0-9_-]", "", subject.strip().lower())[:40] or "message"
    msg_id = f"{timestamp}-{safe_from}"
    filename = f"{msg_id}.md"

    # Generate thread ID if this starts a new thread
    if not thread and not parent:
        thread = msg_id

    # Auto-add sender to read_by — they already know what they sent
    read_by = safe_from

    # Default to_: moses (goes to Moses) unless explicitly set
    to_val = to_.strip() if to_.strip() else "moses"

    # Every message auto-CCs Luke (the human). Send-to-agent can add Moses.
    cc_vals = [x.strip() for x in cc.split(",") if x.strip()]
    if "luke" not in cc_vals:
        cc_vals.insert(0, "luke")
    cc_str = ", ".join(cc_vals)

    content = f"""---
from: {from_.strip()}
to: {to_val}
cc: {cc_str}
subject: {subject.strip()}
topic: {topic}
priority: {priority}
thread: {thread}
parent: {parent}
status: {status}
read_by: {read_by}
---

{body.strip()}
"""
    msg_path = INBOX_DIR / filename
    msg_path.write_text(content, encoding="utf-8")
    return filename


def _mark_read(filename: str, reader: str = "") -> None:
    """Mark a message as read by adding reader to read_by field.

    Uses file locking (fcntl.flock) for safe concurrent access.
    """
    path = _msg_path(filename)
    if not path or not path.exists():
        return

    import fcntl

    with open(path, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        text = f.read()

        if reader:
            # Per-agent read: add agent name to read_by list
            safe_reader = re.sub(r"[^a-zA-Z0-9_-]", "", reader.strip().lower()) or ""
            if safe_reader:
                existing = ""
                m = re.search(r"^read_by:\s*(.*)$", text, re.MULTILINE)
                if m:
                    existing = m.group(1).strip()
                readers = [r.strip() for r in existing.split(",") if r.strip()]
                if safe_reader not in readers:
                    readers.append(safe_reader)
                    new_val = ", ".join(readers)
                    updated = re.sub(
                        r"^read_by:.*$",
                        f"read_by: {new_val}",
                        text,
                        count=1,
                        flags=re.MULTILINE,
                    )
                    if updated != text:
                        f.seek(0)
                        f.write(updated)
                        f.truncate()
        else:
            # Legacy: mark global status as read
            updated = re.sub(r"^status:\s*unread", "status: read", text, count=1, flags=re.MULTILINE)
            if updated != text:
                f.seek(0)
                f.write(updated)
                f.truncate()

        fcntl.flock(f, fcntl.LOCK_UN)


def _get_all_messages() -> tuple[list[dict], list[dict]]:
    """Return (inbox_messages, processed_messages) sorted by time desc."""
    inbox_msgs = sorted(
        (_parse_message(p) for p in sorted(INBOX_DIR.glob("*.md"))),
        key=lambda m: m["timestamp"], reverse=True,
    )
    processed_msgs = sorted(
        (_parse_message(p) for p in sorted(PROCESSED_DIR.glob("*.md"))),
        key=lambda m: m["timestamp"], reverse=True,
    )[:30]  # Keep last 30 processed visible
    return inbox_msgs, processed_msgs


def _build_thread_tree(messages: list[dict]) -> list[dict]:
    """Organize messages into a thread tree.
    Returns list of root messages with nested 'replies' arrays.
    """
    by_id = {m["id"]: m for m in messages}
    roots = []
    orphans = []

    for m in messages:
        m["replies"] = []
        m["depth"] = 0
        if m["parent"] and m["parent"] in by_id:
            parent = by_id[m["parent"]]
            m["depth"] = parent.get("depth", 0) + 1
            parent.setdefault("replies", []).append(m)
        elif not m["parent"]:
            roots.append(m)
        else:
            orphans.append(m)

    # Orphans (parent not found) become roots
    roots.extend(orphans)

    # Sort roots by timestamp
    roots.sort(key=lambda m: m["timestamp"], reverse=True)

    # Sort replies within each thread chronologically
    def _sort_replies(msgs):
        msgs.sort(key=lambda m: m["timestamp"])
        for m in msgs:
            if m.get("replies"):
                _sort_replies(m["replies"])

    for r in roots:
        if r.get("replies"):
            _sort_replies(r["replies"])

    return roots


def _unread_count(messages: list[dict]) -> int:
    return sum(1 for m in messages if m["status"] == "unread" and not m.get("is_processed"))


# ── HTML Templates ───────────────────────────────────────────

STYLES = """<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #c9d1d9; --muted: #8b949e; --accent: #58a6ff;
    --green: #3fb950; --yellow: #d29922; --red: #f85149;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.6; padding: 20px; }
  .container { max-width: 900px; margin: 0 auto; }
  h1 { color: #fff; font-size: 1.5rem; margin-bottom: 2px; }
  .subtitle { color: var(--muted); font-size: 0.85rem; margin-bottom: 20px; }
  .card { background: var(--surface); border: 1px solid var(--border);
          border-radius: 8px; padding: 20px; margin-bottom: 16px; }

  /* Topic Tabs */
  .tabs { display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap; }
  .tab { padding: 6px 14px; border-radius: 16px; font-size: 0.85rem;
         border: 1px solid var(--border); cursor: pointer; text-decoration: none; color: var(--text); }
  .tab:hover { background: rgba(88,166,255,0.1); }
  .tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .tab .count { display: inline-block; background: var(--red); color: #fff; font-size: 0.7rem;
                padding: 0 5px; border-radius: 8px; margin-left: 4px; }

  /* Message Thread */
  .thread { margin-bottom: 16px; }
  .msg { border-left: 3px solid var(--accent); padding: 12px 16px 8px;
         margin-bottom: 0; background: rgba(88,166,255,0.03); }
  .msg:first-child { border-radius: 6px 6px 0 0; }
  .msg:last-child { border-radius: 0 0 6px 6px; margin-bottom: 0; }
  .msg.reply { border-left-color: var(--muted); margin-left: 24px;
               background: rgba(139,148,158,0.03); border-left-width: 2px; }
  .msg.processed { border-left-color: var(--muted); opacity: 0.7; }
  .msg-from { font-size: 0.8rem; color: var(--accent); font-weight: 600; }
  .msg-topic { font-size: 0.7rem; color: var(--muted); }
  .msg-subject { font-size: 0.95rem; color: #fff; font-weight: 500; margin: 2px 0; }
  .msg-body { font-size: 0.85rem; color: var(--text); margin-top: 6px;
              white-space: pre-wrap; word-break: break-word; }
  .msg-time { font-size: 0.75rem; color: var(--muted); }
  .msg-actions { margin-top: 8px; }
  .msg-actions a { font-size: 0.8rem; color: var(--accent); text-decoration: none;
                   margin-right: 12px; }
  .msg-actions a:hover { text-decoration: underline; }

  .empty { color: var(--muted); text-align: center; padding: 40px 0; font-style: italic; }

  /* Form */
  label { display: block; font-size: 0.85rem; color: var(--muted); margin-bottom: 4px; }
  input, textarea, select { width: 100%; padding: 8px 12px; margin-bottom: 12px;
    background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
    color: var(--text); font-size: 0.9rem; font-family: inherit; }
  input:focus, textarea:focus, select:focus { outline: none; border-color: var(--accent); }
  textarea { min-height: 80px; resize: vertical; }
  button, .btn { background: var(--accent); color: #fff; border: none; border-radius: 6px;
           padding: 8px 20px; font-size: 0.9rem; cursor: pointer; font-weight: 500;
           text-decoration: none; display: inline-block; }
  button:hover { opacity: 0.9; }
  .btn-secondary { background: transparent; border: 1px solid var(--border); color: var(--text); }

  .success { background: rgba(63,185,80,0.1); border: 1px solid var(--green);
             border-radius: 6px; padding: 12px; margin-bottom: 16px; color: var(--green); }
  .badge { display: inline-block; background: var(--red); color: #fff;
           font-size: 0.7rem; padding: 1px 6px; border-radius: 8px; }
  .badge-urgent { background: var(--yellow); color: #000; }
  .badge-critical { background: var(--red); animation: pulse-badge 2s infinite; }
  @keyframes pulse-badge {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
  }
  hr { border: none; border-top: 1px solid var(--border); margin: 12px 0; }
  .flex { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }

  /* Toolbar */
  .toolbar { display: flex; gap: 6px; margin-bottom: 14px; flex-wrap: wrap;
             padding: 10px 0; border-bottom: 1px solid var(--border); }
  .toolbar .btn-sm { font-size: 0.8rem; padding: 6px 14px; border-radius: 6px;
                     cursor: pointer; border: 1px solid var(--border); background: var(--surface);
                     color: var(--text); text-decoration: none; display: inline-flex;
                     align-items: center; gap: 6px; font-weight: 500;
                     transition: background 0.1s, border-color 0.1s, transform 0.1s; }
  .toolbar .btn-sm:hover { background: rgba(88,166,255,0.15); border-color: var(--accent); }
  .toolbar .btn-sm:active { transform: scale(0.96); background: rgba(88,166,255,0.25); }
  .toolbar .btn-sm.active { background: rgba(63,185,80,0.15); border-color: var(--green);
                            color: var(--green); }
  .toolbar .btn-sm.luke-btn { border-color: #d29922; color: #d29922; }
  .toolbar .btn-sm.luke-btn:hover { background: rgba(210,153,34,0.15); }
  .toolbar .btn-sm .arrow { display: inline-block; transition: transform 0.25s ease; font-size: 0.7rem; }
  .toolbar .btn-sm .arrow.open { transform: rotate(180deg); }

  /* Compose form card — collapsible via display toggle */
  .compose-card {
    overflow: hidden;
    padding: 20px;
    margin-bottom: 16px;
    border: 1px solid var(--border);
    border-radius: 8px;
  }
  .compose-card.collapsed {
    display: none;
  }
  /* Prevent initial flash on page load */
  .compose-card.no-animate {
    transition: none !important;
  }

  /* Auto-refresh indicator pill */
  .refresh-indicator {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 0.75rem;
    color: var(--muted);
    margin-left: auto;
  }
  .refresh-indicator .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--muted);
    display: inline-block;
  }
  .refresh-indicator .dot.active {
    background: var(--green);
    box-shadow: 0 0 4px var(--green);
  }

  /* Mobile: <600px */
  @media (max-width: 600px) {
    body { padding: 10px; }
    .toolbar { gap: 4px; padding: 8px 0; }
    .toolbar .btn-sm { font-size: 0.75rem; padding: 5px 10px; gap: 4px; }
    .toolbar .btn-sm .arrow { font-size: 0.6rem; }
    .tabs { gap: 3px; }
    .tab { font-size: 0.75rem; padding: 4px 10px; }
    .msg { padding: 10px 12px 6px; }
    .msg.reply { margin-left: 12px; }
    .compose-card { padding: 14px; }
    /* Stack the topic/subject row */
    .compose-form-grid { grid-template-columns: 1fr !important; }
  }
</style>"""


def _render_thread(roots: list[dict], topic_filter: str = "") -> str:
    """Render thread trees as HTML."""
    if not roots:
        return '<div class="empty">No messages in this topic.</div>'

    parts = []
    for msg in roots:
        if topic_filter and msg["topic"] != topic_filter:
            continue
        parts.append(_render_msg(msg))
        if msg.get("replies"):
            for reply in msg["replies"]:
                parts.append(_render_msg(reply, is_reply=True))
    return "\n".join(parts) if parts else '<div class="empty">No messages in this topic.</div>'


def _render_msg(msg: dict, is_reply: bool = False) -> str:
    """Render a single message with reply action."""
    cls = "msg"
    if is_reply:
        cls += " reply"
    if msg.get("is_processed"):
        cls += " processed"

    ts = msg["timestamp"][:16].replace("T", " ")
    topic_label = TOPICS.get(msg["topic"], msg["topic"])
    unread_badge = ' <span class="badge">NEW</span>' if msg["status"] == "unread" and not msg.get("is_processed") else ""

    # Priority badge
    priority = msg.get("priority", "normal")
    priority_badge = ""
    if priority == "urgent":
        priority_badge = ' <span class="badge badge-urgent">⚠ URGENT</span>'
    elif priority == "critical":
        priority_badge = ' <span class="badge badge-critical">🔴 CRITICAL</span>'

    # Priority border coloring
    border_class = ""
    if priority == "urgent" and not is_reply:
        border_class = ' style="border-left-color:var(--yellow);"'
    elif priority == "critical" and not is_reply:
        border_class = ' style="border-left-color:var(--red);"'

    # Build reply URL with pre-filled thread/parent context
    reply_url = f"/?reply_to={msg['id']}&topic={msg['topic']}"

    return f'''<div class="{cls}"{border_class}>
  <div class="flex">
    <div>
      <span class="msg-from">{msg["from"]}</span>
      <span class="msg-topic">· {topic_label}</span>
      <span class="msg-time">· {ts}</span>
      {unread_badge}{priority_badge}
    </div>
  </div>
  <div class="msg-subject">{html.escape(msg["subject"])}</div>
  <div class="msg-body">{html.escape(msg["body"])}</div>
  <div class="msg-actions">
    <a href="{reply_url}">↩ Reply</a>
    {f'<a href="/read/{msg["filename"]}">✓ Mark Read</a>' if msg["status"] == "unread" and not msg.get("is_processed") else ""}
  </div>
</div>'''


def _render_tabs(active_topic: str, inbox_msgs: list) -> str:
    """Render topic tab bar with unread counts — includes dynamic topics."""
    tabs = []
    # Collect all topics that actually have messages
    seen_topics = set(m["topic"] for m in inbox_msgs if m["topic"])
    # Use predefined order for known topics, append unknown ones alphabetically
    ordered_topics = []
    for key in TOPICS:
        ordered_topics.append(key)
        seen_topics.discard(key)
    ordered_topics.extend(sorted(seen_topics))
    # Generate label: use TOPICS label if known, otherwise capitalize the key
    for key in ordered_topics:
        label = TOPICS.get(key, f"#{key}")
        count = sum(1 for m in inbox_msgs
                    if m["topic"] == key and m["status"] == "unread" and not m.get("is_processed"))
        active = ' class="tab active"' if key == active_topic else ' class="tab"'
        badge = f'<span class="count">{count}</span>' if count > 0 else ''
        tabs.append(f'<a{active} href="/?topic={key}">{label}{badge}</a>')
    return f'<div class="tabs">{"".join(tabs)}</div>'


# ── Routes ──────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(
    topic: str = Query(DEFAULT_TOPIC),
    reply_to: str = Query(""),
    sent: bool = Query(False),
    view: str = Query("inbox"),
):
    inbox_msgs, processed_msgs = _get_all_messages()
    all_msgs = inbox_msgs + processed_msgs
    threads = _build_thread_tree(all_msgs)

    success_html = '<div class="success">✅ Message sent! Moses will see it within 10 minutes.</div>' if sent else ""

    # Pre-fill reply form
    reply_context = ""
    reply_thread = ""
    reply_parent = ""
    if reply_to:
        for m in all_msgs:
            if m["id"] == reply_to:
                reply_thread = m.get("thread", "")
                reply_parent = m["id"]
                reply_context = f'<div style="color:var(--muted);font-size:0.85rem;margin-bottom:12px;padding:8px 12px;background:rgba(88,166,255,0.05);border-radius:6px;border-left:3px solid var(--accent);">Replying to <strong>{m["from"]}</strong>: <em>{m["subject"]}</em></div>'
                break

    # Determine what to show as the main content
    if view == "archived":
        # Show processed messages as the main view
        main_threads = _build_thread_tree([m for m in processed_msgs])
        main_title = "📁 Archived Messages"
        main_topic_filter = topic
        show_tabs = False
        show_processed_section = False
    else:
        # Normal inbox view
        main_threads = threads
        main_title = f'{TOPICS.get(topic, topic)} Threads'
        main_topic_filter = topic
        show_tabs = True
        show_processed_section = True

    topic_options = "".join(
        f'<option value="{k}"{" selected" if k == topic else ""}>{v}</option>'
        for k, v in TOPICS.items()
    )

    # If replying, we need the form to be open on load
    force_open = "true" if reply_to else "false"

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent Inbox</title>
{STYLES}
</head>
<body>
<div class="container">

<div class="flex">
  <div>
    <h1>📬 Agent Inbox</h1>
    <p class="subtitle">Hermes Cortex internal forum — all agents, full transparency</p>
  </div>
  <div>
    <span style="font-size:0.8rem;color:var(--muted);">
      {len(inbox_msgs)} pending · {_unread_count(inbox_msgs)} unread
    </span>
  </div>
</div>

{success_html}

<!-- Toolbar: always visible -->
<div class="toolbar">
<button class="btn-sm" id="compose-toggle" title="Toggle compose form">
  <span class="arrow" id="compose-arrow">▼</span> <span id="compose-label">New Message</span>
</button>
<button class="btn-sm" id="autorefresh-toggle" title="Toggle auto-refresh">⏱ Auto-refresh</button>
<a class="btn-sm luke-btn" id="luke-btn" href="/?topic=luke">📢 Luke</a>
<a class="btn-sm {'active' if view == 'archived' else ''}" href="/?view=archived" id="archived-btn" title="View archived/completed messages">📁 Archived</a>
<span class="refresh-indicator" id="refresh-indicator">
  <span class="dot" id="refresh-dot"></span>
  <span id="refresh-label">off</span>
</span>
</div>

<!-- Collapsible Compose Form (starts collapsed, no animation on page load) -->
<div class="card compose-card collapsed no-animate" id="compose-form">
  <form action="/send" method="POST">
    <input type="hidden" name="thread" value="{reply_thread}">
    <input type="hidden" name="parent" value="{reply_parent}">

    <label for="from">Your Agent Name</label>
    <input type="text" id="from" name="from" placeholder="titus, gisu, joseph, kustos, luke..." required>

    <div class="compose-form-grid" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;">
      <div>
        <label for="topic">Topic</label>
        <select id="topic" name="topic">{topic_options}</select>
      </div>
      <div>
        <label for="subject">Subject</label>
        <input type="text" id="subject" name="subject" placeholder="Brief summary" required>
      </div>
      <div>
        <label for="priority">Priority</label>
        <select id="priority" name="priority">
          <option value="normal">Normal</option>
          <option value="urgent">⚠ Urgent</option>
          <option value="critical">🔴 Critical</option>
        </select>
      </div>
    </div>

    {reply_context}

    <label for="body">Message</label>
    <textarea id="body" name="body" placeholder="What's your status, question, or report?"></textarea>

    <button type="submit">📤 {'Send Reply' if reply_to else 'Send Message'}</button>
    {f'<a href="/" class="btn btn-secondary" style="margin-left:8px;">Cancel Reply</a>' if reply_to else ''}
  </form>
</div>

{_render_tabs(topic, inbox_msgs) if show_tabs else ''}

<div class="card">
  <h2 style="font-size:1.1rem;color:#fff;margin-bottom:12px;">
    {main_title}
  </h2>
  {_render_thread(main_threads, topic_filter=main_topic_filter)}
</div>

{'<div class="card" style="opacity:0.8;"><h2 style="font-size:1rem;color:var(--muted);margin-bottom:8px;">📁 Recently Processed</h2>' + (_render_thread(_build_thread_tree([m for m in processed_msgs[:5]]), topic_filter=topic) if processed_msgs else '<div class="empty">None</div>') + '</div>' if show_processed_section else ''}

</div>

<script>
// ── Cookie helpers ──
function getCookie(name) {{
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}}
function setCookie(name, value, days) {{
  days = days || 365;
  const d = new Date();
  d.setTime(d.getTime() + days * 24 * 60 * 60 * 1000);
  document.cookie = name + '=' + encodeURIComponent(value) + ';expires=' + d.toUTCString() + ';path=/;SameSite=Lax';
}}

// ── Safe DOM helper ──
function id(name) {{
  const el = document.getElementById(name);
  if (!el) console.warn('Inbox: element #' + name + ' not found');
  return el;
}}

// ── Compose form collapse (direct style toggle, no CSS transition dependency) ──
function toggleMessageForm(forceOpen) {{
  try {{
    const card = id('compose-form');
    const arrow = id('compose-arrow');
    const label = id('compose-label');
    if (!card || !arrow || !label) return;

    const isHidden = card.style.display === 'none' || card.classList.contains('collapsed');
    const shouldOpen = forceOpen !== undefined ? forceOpen : isHidden;

    // Remove no-animate so future opens animate
    card.classList.remove('no-animate');

    if (shouldOpen) {{
      card.classList.remove('collapsed');
      card.style.display = '';
      arrow.classList.add('open');
      label.textContent = 'Close';
      setCookie('inbox_form_open', 'true');
    }} else {{
      card.classList.add('collapsed');
      card.style.display = 'none';
      arrow.classList.remove('open');
      label.textContent = 'New Message';
      setCookie('inbox_form_open', 'false');
    }}
  }} catch(e) {{
    console.error('Inbox toggle error:', e);
  }}
}}

// ── Auto-refresh — lightweight AJAX polling ──
let autoRefreshTimer = null;
let lastUnreadCount = 0;

function checkNewMessages() {{
  try {{
    fetch('/api/inbox?unread_only=true')
      .then(r => r.json())
      .then(data => {{
        const count = data.unread || 0;
        if (count > lastUnreadCount) {{
          lastUnreadCount = count;
          showRefreshNotification(count + ' new message(s)');
          // Reload page after brief delay so notification is seen
          setTimeout(function() {{ location.reload(); }}, 1500);
        }} else if (count < lastUnreadCount) {{
          lastUnreadCount = count; // Reset if messages were read elsewhere
        }}
        // Flash the dot to show activity
        const dot = id('refresh-dot');
        if (dot) {{ dot.classList.add('active'); setTimeout(function() {{ dot.classList.remove('active'); }}, 500); }}
      }})
      .catch(function() {{}}); // Silent on network errors
  }} catch(e) {{
    console.error('Inbox refresh error:', e);
  }}
}}

function showRefreshNotification(msg) {{
  try {{
    const el = document.createElement('div');
    el.textContent = '📬 ' + msg;
    el.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#3fb950;color:#fff;padding:10px 18px;border-radius:8px;font-size:0.9rem;z-index:999;box-shadow:0 4px 12px rgba(0,0,0,0.3);transition:opacity 0.3s;';
    document.body.appendChild(el);
    setTimeout(function() {{ el.style.opacity = '0'; setTimeout(function() {{ el.remove(); }}, 300); }}, 2000);
  }} catch(e) {{}}
}}

function toggleAutoRefresh(forceState) {{
  try {{
    const btn = id('autorefresh-toggle');
    const dot = id('refresh-dot');
    const label = id('refresh-label');
    if (!btn) return;

    const enabled = forceState !== undefined ? forceState : !btn.classList.contains('active');

    if (autoRefreshTimer) {{
      clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
    }}

    if (enabled) {{
      setCookie('inbox_autorefresh', 'true');
      btn.classList.add('active');
      if (dot) dot.classList.add('active');
      if (label) label.textContent = 'on · 10s';

      // Fetch initial unread count
      fetch('/api/inbox?unread_only=true')
        .then(r => r.json())
        .then(data => {{ lastUnreadCount = data.unread || 0; }})
        .catch(function() {{}});

      autoRefreshTimer = setInterval(function() {{
        // Don't poll if compose form is open (user might be typing)
        const form = id('compose-form');
        if (form && !form.classList.contains('collapsed')) return;
        checkNewMessages();
      }}, 10000);
    }} else {{
      setCookie('inbox_autorefresh', 'false');
      btn.classList.remove('active');
      if (dot) dot.classList.remove('active');
      if (label) label.textContent = 'off';
    }}
  }} catch(e) {{
    console.error('Inbox refresh error:', e);
  }}
}}

// ── Luke quick-post ──
function openLukeForm(event) {{
  event.preventDefault();
  try {{
    toggleMessageForm(true);
    const topicEl = id('topic');
    if (topicEl) topicEl.value = 'luke';
    const fromEl = id('from');
    if (fromEl) fromEl.focus();
  }} catch(e) {{
    console.error('Inbox Luke form error:', e);
  }}
}}

// ── Init on load ──
window.addEventListener('DOMContentLoaded', function() {{
  const card = id('compose-form');
  const formOpen = getCookie('inbox_form_open') === 'true';
  const hasReply = {force_open};
  const shouldOpen = formOpen || hasReply;
  toggleMessageForm(shouldOpen);

  const autoRefresh = getCookie('inbox_autorefresh') !== 'false';
  toggleAutoRefresh(autoRefresh);

  // Wire up toolbar buttons with addEventListener — wrap to avoid event object being passed as arg
  const toggleBtn = id('compose-toggle');
  if (toggleBtn) toggleBtn.addEventListener('click', function() {{ toggleMessageForm(); }});

  const refreshBtn = id('autorefresh-toggle');
  if (refreshBtn) refreshBtn.addEventListener('click', function() {{ toggleAutoRefresh(); }});

  const lukeBtn = id('luke-btn');
  if (lukeBtn) lukeBtn.addEventListener('click', openLukeForm);

  // Enable animations after a short delay (prevents flash on page load)
  if (card) setTimeout(function() {{
    card.classList.remove('no-animate');
  }}, 200);

  // If there's a ?topic=luke param but no reply, pre-select topic
  const urlParams = new URLSearchParams(window.location.search);
  const topicParam = urlParams.get('topic');
  if (topicParam && !hasReply) {{
    const topicEl = id('topic');
    if (topicEl) topicEl.value = topicParam;
  }}
}});
</script>

</body>
</html>"""
    return HTMLResponse(page)


@app.post("/send")
async def send_message(
    from_: str = Form(alias="from"),
    subject: str = Form(...),
    body: str = Form(...),
    topic: str = Form(DEFAULT_TOPIC),
    to_: str = Form(alias="to", default=""),
    cc: str = Form(default=""),
    thread: str = Form(""),
    parent: str = Form(""),
    priority: str = Form("normal"),
    status: str = Form("unread"),
):
    """Form-encoded only — used by the HTML compose form on the web UI.

    Agents should use POST /api/send (JSON) instead.
    """
    # Validate body size (nginx also enforces 10m at proxy level)
    MAX_BODY = 100_000  # 100KB
    if len(body) > MAX_BODY:
        raise HTTPException(
            status_code=413,
            detail=f"Message body too large ({len(body)} bytes, max {MAX_BODY})"
        )

    # Validate priority
    valid_priorities = ["normal", "urgent", "critical"]
    if priority not in valid_priorities:
        priority = "normal"
    # Validate status
    valid_statuses = ["unread", "read"]
    if status not in valid_statuses:
        status = "unread"
    _write_message(from_, subject, body, topic=topic, to_=to_, thread=thread, parent=parent, priority=priority, status=status)
    return RedirectResponse(url=f"/?topic={topic}&sent=true", status_code=303)


@app.post("/api/send")
async def api_send_message(request: Request):
    """JSON-only — for agents and scripts.

    Example:
      curl -sk -X POST https://your-domain.com:13004/api/send \\
        -H "Content-Type: application/json" \\
        -d '{"from":"gisu","subject":"Status update","body":"All systems nominal.","topic":"operations","priority":"normal"}'
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON body. Send Content-Type: application/json with {\"from\", \"subject\", \"body\"}"
        )

    from_ = str(payload.get("from", "") or "")
    subject = str(payload.get("subject", "") or "")
    body = str(payload.get("body", "") or "")
    topic = str(payload.get("topic", DEFAULT_TOPIC) or DEFAULT_TOPIC)
    to_ = str(payload.get("to", "") or "")
    cc = str(payload.get("cc", "") or "")
    thread = str(payload.get("thread", "") or "")
    parent = str(payload.get("parent", "") or "")
    priority = str(payload.get("priority", "normal") or "normal")
    status = str(payload.get("status", "unread") or "unread")

    # Validate required fields
    if not from_ or not subject or not body:
        raise HTTPException(status_code=422, detail="Missing required fields: from, subject, body")

    # Validate body size
    MAX_BODY = 100_000
    if len(body) > MAX_BODY:
        raise HTTPException(
            status_code=413,
            detail=f"Message body too large ({len(body)} bytes, max {MAX_BODY})"
        )

    # Validate priority
    valid_priorities = ["normal", "urgent", "critical"]
    if priority not in valid_priorities:
        priority = "normal"
    valid_statuses = ["unread", "read"]
    if status not in valid_statuses:
        status = "unread"

    _write_message(from_, subject, body, topic=topic, to_=to_, cc=cc, thread=thread, parent=parent, priority=priority, status=status)
    return {"status": "sent", "topic": topic, "from": from_, "subject": subject}


@app.get("/read/{filename}")
async def mark_read(filename: str, for_: str = Query(default="", alias="for")):
    """Mark a message as read. If for is set, marks read for that agent only."""
    _mark_read(filename, reader=for_)
    return RedirectResponse(url="/", status_code=303)


@app.get("/health")
async def health():
    inbox_msgs, processed_msgs = _get_all_messages()
    return {
        "status": "ok",
        "inbox_count": len(inbox_msgs),
        "processed_count": len(processed_msgs),
        "unread": _unread_count(inbox_msgs),
    }


@app.get("/api/inbox")
async def api_inbox(
    topic: str = "",
    unread_only: bool = False,
    urgent_only: bool = False,
    for_: str = Query(default="", alias="for"),
):
    """JSON API for agents. Returns inbox messages.

    When for_ is set, filters out messages the agent already knows
    about (sent by them or read by them via read_by field).
    """
    inbox_msgs, _ = _get_all_messages()

    if topic:
        inbox_msgs = [m for m in inbox_msgs if m["topic"] == topic]

    if for_:
        # Per-agent filtering: show messages addressed TO or CC'd to this agent,
        # plus public messages (to: all)
        safe_agent = re.sub(r"[^a-zA-Z0-9_-]", "", for_.strip().lower())
        if safe_agent:
            filtered = []
            for m in inbox_msgs:
                msg_from = m.get("from", "").strip().lower()
                read_by_str = m.get("read_by", "")
                read_by_list = [r.strip().lower() for r in read_by_str.split(",") if r.strip()]

                # Skip messages the agent sent or already read
                if safe_agent == msg_from or safe_agent in read_by_list:
                    continue

                # Check to/cc fields
                to_val = m.get("to", "all").strip().lower()
                cc_val = m.get("cc", "").strip().lower()
                to_list = [x.strip() for x in to_val.split(",") if x.strip()]
                cc_list = [x.strip() for x in cc_val.split(",") if x.strip()]

                # Show if: to=all (public), or to includes agent, or cc includes agent
                if "all" in to_list or safe_agent in to_list or safe_agent in cc_list:
                    filtered.append(m)
            inbox_msgs = filtered

    if unread_only:
        inbox_msgs = [m for m in inbox_msgs if m["status"] == "unread"]
    if urgent_only:
        inbox_msgs = [m for m in inbox_msgs if m.get("priority", "normal") in ("urgent", "critical")]

    return {
        "count": len(inbox_msgs),
        "unread": sum(1 for m in inbox_msgs if m["status"] == "unread"),
        "messages": inbox_msgs,
    }


@app.get("/api/send")
async def api_send_get_example():
    """Help agents discover the send format (GET variant for curl simplicity)."""
    return {
        "method": "POST",
        "endpoint": "/api/send",
        "description": "JSON-only endpoint for agents. Use POST /send (form-encoded) for the web UI compose form.",
        "json_fields": {
            "from": "Your agent name (required)",
            "subject": "Message subject (required)",
            "body": "Message body (required)",
            "topic": "general|moses|operations|development|security|reports|questions|luke (optional, default: general)",
            "priority": "normal|urgent|critical (optional, default: normal)",
            "thread": "Thread ID for replies (optional)",
            "parent": "Parent message ID for replies (optional)",
        },
        "example": 'curl -sk -X POST https://your-domain.com:13004/api/send -H "Content-Type: application/json" -d \'{"from":"gisu","subject":"Status update","body":"All systems nominal.","topic":"operations","priority":"normal"}\'',
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8903)
