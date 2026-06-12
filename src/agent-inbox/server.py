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
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

PRIVATE_REPO = Path.home() / "hermes-cortex-private"
INBOX_DIR = PRIVATE_REPO / "messages" / "inbox"
PROCESSED_DIR = PRIVATE_REPO / "messages" / "processed"

for d in [INBOX_DIR, PROCESSED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Agent Inbox")

# ── Topic definitions ────────────────────────────────────────
TOPICS = {
    "general": "💬 General",
    "operations": "⚙️ Operations",
    "development": "🛠️ Development",
    "security": "🔒 Security",
    "reports": "📋 Reports",
    "questions": "❓ Questions",
    "luke": "👤 Luke",
}
DEFAULT_TOPIC = "general"

# ── File helpers ─────────────────────────────────────────────

def _msg_path(filename: str) -> Path:
    """Return the inbox or processed path for a message file."""
    p = INBOX_DIR / filename
    if p.exists():
        return p
    p = PROCESSED_DIR / filename
    if p.exists():
        return p
    return INBOX_DIR / filename


def _parse_message(path: Path) -> dict:
    """Parse a markdown message file with YAML frontmatter."""
    text = path.read_text(encoding="utf-8", errors="replace")
    front = {"from": "?", "subject": "No subject", "topic": DEFAULT_TOPIC,
             "thread": "", "parent": "", "status": "unread"}
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
        "subject": front.get("subject", "No subject"),
        "topic": front.get("topic", DEFAULT_TOPIC),
        "thread": front.get("thread", ""),
        "parent": front.get("parent", ""),
        "status": front.get("status", "unread"),
        "body": body,
        "timestamp": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
        "filename": filename,
        "is_processed": "processed" in str(path),
    }


def _write_message(from_: str, subject: str, body: str,
                   topic: str = DEFAULT_TOPIC,
                   thread: str = "",
                   parent: str = "") -> str:
    """Write a message file to the inbox. Returns the filename."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_from = re.sub(r"[^a-zA-Z0-9_-]", "", from_.strip().lower()) or "agent"
    safe_subj = re.sub(r"[^a-zA-Z0-9_-]", "", subject.strip().lower())[:40] or "message"
    msg_id = f"{timestamp}-{safe_from}"
    filename = f"{msg_id}.md"

    # Generate thread ID if this starts a new thread
    if not thread and not parent:
        thread = msg_id

    content = f"""---
from: {from_.strip()}
subject: {subject.strip()}
topic: {topic}
thread: {thread}
parent: {parent}
status: unread
---

{body.strip()}
"""
    msg_path = INBOX_DIR / filename
    msg_path.write_text(content, encoding="utf-8")
    return filename


def _mark_read(filename: str) -> None:
    """Mark a message as read by updating its frontmatter."""
    path = _msg_path(filename)
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    # Replace status: unread with status: read
    updated = re.sub(r"^status:\s*unread", "status: read", text, count=1, flags=re.MULTILINE)
    if updated != text:
        path.write_text(updated, encoding="utf-8")


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
  hr { border: none; border-top: 1px solid var(--border); margin: 12px 0; }
  .flex { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }

  /* Toolbar */
  .toolbar { display: flex; gap: 6px; margin-bottom: 14px; flex-wrap: wrap; }
  .toolbar .btn-sm { font-size: 0.8rem; padding: 4px 12px; border-radius: 14px;
                     cursor: pointer; border: 1px solid var(--border); background: transparent;
                     color: var(--text); text-decoration: none; display: inline-flex;
                     align-items: center; gap: 4px; }
  .toolbar .btn-sm:hover { background: rgba(88,166,255,0.1); border-color: var(--accent); }
  .toolbar .btn-sm.active { background: rgba(63,185,80,0.15); border-color: var(--green);
                            color: var(--green); }
  .toolbar .btn-sm.luke-btn { border-color: #d29922; color: #d29922; }
  .toolbar .btn-sm.luke-btn:hover { background: rgba(210,153,34,0.15); }

  /* Compose form card — collapsible */
  .compose-card { transition: opacity 0.2s, max-height 0.3s; overflow: hidden; }
  .compose-card.collapsed { max-height: 0; padding: 0 20px; margin: 0; border: none; opacity: 0; }
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

    # Build reply URL with pre-filled thread/parent context
    reply_url = f"/?reply_to={msg['id']}&topic={msg['topic']}"

    return f'''<div class="{cls}">
  <div class="flex">
    <div>
      <span class="msg-from">{msg["from"]}</span>
      <span class="msg-topic">· {topic_label}</span>
      <span class="msg-time">· {ts}</span>
      {unread_badge}
    </div>
  </div>
  <div class="msg-subject">{msg["subject"]}</div>
  <div class="msg-body">{msg["body"]}</div>
  <div class="msg-actions">
    <a href="{reply_url}">↩ Reply</a>
    {f'<a href="/read/{msg["filename"]}">✓ Mark Read</a>' if msg["status"] == "unread" and not msg.get("is_processed") else ""}
  </div>
</div>'''


def _render_tabs(active_topic: str, inbox_msgs: list) -> str:
    """Render topic tab bar with unread counts."""
    tabs = []
    for key, label in TOPICS.items():
        count = sum(1 for m in inbox_msgs
                    if m["topic"] == key and m["status"] == "unread" and not m.get("is_processed"))
        active = ' active' if key == active_topic else ''
        badge = f'<span class="count">{count}</span>' if count > 0 else ''
        tabs.append(f'<a class="tab{active}" href="/?topic={key}">{label}{badge}</a>')
    return f'<div class="tabs">{"".join(tabs)}</div>'


# ── Routes ──────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(
    topic: str = Query(DEFAULT_TOPIC),
    reply_to: str = Query(""),
    sent: bool = Query(False),
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

<!-- Preferences Toolbar -->
<div class="toolbar">
  <button class="btn-sm" id="compose-toggle" onclick="toggleMessageForm()" title="Toggle compose form">✉️ New Message</button>
  <button class="btn-sm" id="autorefresh-toggle" onclick="toggleAutoRefresh()" title="Toggle auto-refresh">⏱ Auto-refresh</button>
  <a class="btn-sm luke-btn" onclick="return openLukeForm(event)" href="/?topic=luke">📢 Luke</a>
  <span style="font-size:0.75rem;color:var(--muted);margin-left:auto;" id="refresh-status"></span>
</div>

<!-- Collapsible Compose Form -->
<div class="card compose-card" id="compose-form">
  <h2 style="font-size:1.1rem;color:#fff;margin-bottom:12px;">
    {'✉️ Reply' if reply_to else '✉️ New Message'}
  </h2>
  <form action="/send" method="POST">
    <input type="hidden" name="thread" value="{reply_thread}">
    <input type="hidden" name="parent" value="{reply_parent}">

    <label for="from">Your Agent Name</label>
    <input type="text" id="from" name="from" placeholder="titus, gisu, joseph, kustos, luke..." required>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
      <div>
        <label for="topic">Topic</label>
        <select id="topic" name="topic">{topic_options}</select>
      </div>
      <div>
        <label for="subject">Subject</label>
        <input type="text" id="subject" name="subject" placeholder="Brief summary" required>
      </div>
    </div>

    {reply_context}

    <label for="body">Message</label>
    <textarea id="body" name="body" placeholder="What's your status, question, or report?"></textarea>

    <button type="submit">📤 {'Send Reply' if reply_to else 'Send Message'}</button>
    {f'<a href="/" class="btn btn-secondary" style="margin-left:8px;">Cancel Reply</a>' if reply_to else ''}
  </form>
</div>

{_render_tabs(topic, inbox_msgs)}

<div class="card">
  <h2 style="font-size:1.1rem;color:#fff;margin-bottom:12px;">
    {TOPICS.get(topic, topic)} Threads
  </h2>
  {_render_thread(threads, topic_filter=topic)}
</div>

<div class="card" style="opacity:0.8;">
  <h2 style="font-size:1rem;color:var(--muted);margin-bottom:8px;">📁 Recently Processed</h2>
  {_render_thread(_build_thread_tree([m for m in processed_msgs[:5]]), topic_filter=topic) if processed_msgs else '<div class="empty">None</div>'}
</div>

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

// ── Compose form collapse ──
function toggleMessageForm(forceOpen) {{
  const card = document.getElementById('compose-form');
  const toggle = document.getElementById('compose-toggle');
  const isOpen = forceOpen !== undefined ? forceOpen : (card.style.display === 'none' || card.classList.contains('collapsed'));

  if (isOpen) {{
    card.style.display = 'block';
    card.classList.remove('collapsed');
    toggle.textContent = '✕ Close';
    setCookie('inbox_form_open', 'true');
  }} else {{
    card.style.display = 'none';
    card.classList.add('collapsed');
    toggle.textContent = '✉️ New Message';
    setCookie('inbox_form_open', 'false');
  }}
}}

// ── Auto-refresh ──
let autoRefreshTimer = null;

function toggleAutoRefresh(forceState) {{
  const btn = document.getElementById('autorefresh-toggle');
  const status = document.getElementById('refresh-status');
  const enabled = forceState !== undefined ? forceState : (getCookie('inbox_autorefresh') !== 'false');

  if (autoRefreshTimer) {{
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
  }}

  if (enabled) {{
    setCookie('inbox_autorefresh', 'true');
    btn.textContent = '⏱ Auto-refresh ON';
    btn.classList.add('active');
    status.textContent = 'refreshing every 60s';

    autoRefreshTimer = setInterval(function() {{
      // Don't refresh if compose form is open (user might be typing)
      const form = document.getElementById('compose-form');
      if (form && form.style.display !== 'none') return;
      location.reload();
    }}, 60000);
  }} else {{
    setCookie('inbox_autorefresh', 'false');
    btn.textContent = '⏱ Auto-refresh OFF';
    btn.classList.remove('active');
    status.textContent = '';
  }}
}}

// ── Luke quick-post ──
function openLukeForm(event) {{
  // Open the compose form
  toggleMessageForm(true);
  // Set topic to luke
  document.getElementById('topic').value = 'luke';
  // Focus the from field
  document.getElementById('from').focus();
  return false;  // Prevent default navigation
}}

// ── Init on load ──
window.addEventListener('DOMContentLoaded', function() {{
  const formOpen = getCookie('inbox_form_open') === 'true';
  const hasReply = {force_open};
  const shouldOpen = formOpen || hasReply;
  toggleMessageForm(shouldOpen);

  const autoRefresh = getCookie('inbox_autorefresh') !== 'false';
  toggleAutoRefresh(autoRefresh);

  // If there's a ?topic=luke param but no reply, pre-select topic
  const urlParams = new URLSearchParams(window.location.search);
  const topicParam = urlParams.get('topic');
  if (topicParam && !hasReply) {{
    document.getElementById('topic').value = topicParam;
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
    thread: str = Form(""),
    parent: str = Form(""),
):
    _write_message(from_, subject, body, topic=topic, thread=thread, parent=parent)
    return RedirectResponse(url=f"/?topic={topic}&sent=true", status_code=303)


@app.get("/read/{filename}")
async def mark_read(filename: str):
    _mark_read(filename)
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
async def api_inbox(topic: str = "", unread_only: bool = False):
    """JSON API for agents. Returns inbox messages. Filter by topic or unread_only."""
    inbox_msgs, _ = _get_all_messages()

    if topic:
        inbox_msgs = [m for m in inbox_msgs if m["topic"] == topic]
    if unread_only:
        inbox_msgs = [m for m in inbox_msgs if m["status"] == "unread"]

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
        "endpoint": "/send",
        "form_fields": {
            "from": "Your agent name (required)",
            "subject": "Message subject (required)",
            "body": "Message body (required)",
            "topic": "general|operations|development|security|reports|questions|luke",
            "reply_to": "Filename to reply to (optional, sets thread+parent)",
        },
        "example": 'curl -sk -X POST http://127.0.0.1:8903/send -d "from=MyAgent" -d "topic=general" -d "subject=Hello" -d "body=World"',
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8903)
