# Agent Inbox Codebase — Issues Report

Review date: 2026-06-17
Files reviewed: 10 files across server.py, nginx config, shell wrappers, sensor scripts, test script, wrapper generator

## Issue Summary

| Category | Count | Critical | High | Medium | Low |
|----------|-------|----------|------|--------|-----|
| Security | 2 | 1 | 1 | 0 | 0 |
| Reliability | 3 | 0 | 2 | 1 | 0 |
| UX | 3 | 0 | 0 | 2 | 1 |
| Architecture | 3 | 0 | 1 | 2 | 0 |
| Performance | 2 | 0 | 0 | 1 | 1 |
| Missing Features | 6 | 0 | 0 | 3 | 3 |
| **Total** | **19** | **1** | **4** | **9** | **5** |

---

## SECURITY

### S-01 [CRITICAL] — CSP blocks all inline JavaScript when served through nginx

**File:** `deploy/nginx/hermes-zone-defs.conf` lines 26-28
**Applies to:** `hermes-services.conf` line 210 (inbox server block)

**Description:**
The CSP fallback map sets `script-src 'self'` (without `'unsafe-inline'`). Since the inbox page renders ALL its JavaScript as inline `<script>` blocks in the HTML template (lines 582-723 of server.py), nginx will apply this CSP to the FastAPI response (which sets no CSP header of its own), and the browser will **block all inline JavaScript**. The compose toggle, auto-refresh, Luke quick-post, cookie helpers — none of it will work when accessed through the nginx proxy.

The test at `test-inbox.sh` line 153 is **misleading** — it greps for `"unsafe-inline"` in the CSP header and passes because `style-src 'self' 'unsafe-inline'` contains it, but the test comment says "CSP allows inline scripts" — which it does NOT. Only inline styles are allowed.

**Suggested fix:** Change the CSP default map to include `'unsafe-inline'` in script-src, or refactor the JS to external files (`.js`) served from a separate path:

```
# Option A: Allow inline scripts (simple, current architecture)
script-src 'self' 'unsafe-inline';
# Option B: Use nonce or hash-based CSP with backend integration
# script-src 'self' 'nonce-<random>'  # requires server-side nonce injection
```

### S-02 [HIGH] — No input validation on message body (size/content)

**File:** `server.py` lines 112-147 (`_write_message`)

**Description:**
The `/send` endpoint accepts arbitrary form data. The body text is validated for nothing beyond being a form field. A 100MB body would be written to disk without truncation. HTML/script content is stored raw (only escaped at render time, which is correct XSS protection, but raw storage means file-based readers like `check-agent-messages.sh` work with unescaped content). No Content-Type validation either.

**Suggested fix:** Add size validation:
```python
if len(body) > 100_000:  # 100KB max
    raise HTTPException(status_code=413, detail="Message body too large")
```
Also cap `subject` length (currently truncated to 40 chars for filename but not validated in storage).

---

## RELIABILITY

### R-01 [HIGH] — Race condition in `_mark_read` (read-modify-write without locking)

**File:** `server.py` lines 150-183

**Description:**
`_mark_read` reads a message file, modifies the `read_by` field in memory, then writes it back. If two agents call `mark_read` concurrently (e.g., /read/{filename}?for=titus and /read/{filename}?for=joseph at the same time), one agent's read tracking will be silently lost because the second write overwrites the first. No file locking (fcntl/flock) is used.

This is the **per-agent read tracking** feature — it will miss entries under concurrent access.

**Suggested fix:** Use file locking around the read-modify-write:
```python
import fcntl
with open(path, 'r+') as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    text = f.read()
    # ... modify text ...
    f.seek(0)
    f.write(text)
    f.truncate()
    fcntl.flock(f, fcntl.LOCK_UN)
```

### R-02 [HIGH] — `_msg_path` returns a non-existent path as fallback

**File:** `server.py` lines 62-72

**Description:**
When neither `filename` nor `filename.md` exists in either `INBOX_DIR` or `PROCESSED_DIR`, the function returns `INBOX_DIR / filename` — a path that **does not exist**. Callers like `_mark_read` must separately check `.exists()`, which they do, but the API is misleading. If a future caller forgets the `.exists()` check, they'll silently operate on a non-existent path (creating empty files, etc.).

**Suggested fix:** Raise an explicit error or return `None`:
```python
def _msg_path(filename: str) -> Optional[Path]:
    for fname in [filename, filename + ".md"]:
        for d in [INBOX_DIR, PROCESSED_DIR]:
            p = d / fname
            if p.exists():
                return p
    return None  # or raise FileNotFoundError
```
And update callers to handle `None`.

### R-03 [MEDIUM] — File writes not atomically persisted (no fsync)

**File:** `server.py` line 146, line 178, line 183

**Description:**
`write_text()` does not call `fsync()`. If the OS crashes or the process is killed immediately after writing, partial writes may corrupt message files. For a debatable-inbox system this is low risk, but for any reliability requirements, file writes should be atomic.

**Suggested fix:** Write to a `.tmp` file, then `os.rename()` (atomic on same filesystem), or use `write_text()` followed by an explicit fsync on the file descriptor.

---

## UX

### UX-01 [MEDIUM] — No priority selector in compose form

**File:** `server.py` lines 537-564

**Description:**
The compose form only has `from`, `topic`, `subject`, and `body` fields. Priority (`normal`/`urgent`/`critical`) can only be set via the API. The renderer shows priority badges for urgent/critical (lines 416-429), but there's no UI affordance to set them. Users composing a critical alert through the web UI cannot flag it as such.

**Suggested fix:** Add a priority select to the compose form:
```html
<label for="priority">Priority</label>
<select id="priority" name="priority">
  <option value="normal">Normal</option>
  <option value="urgent">⚠ Urgent</option>
  <option value="critical">🔴 Critical</option>
</select>
```

### UX-02 [MEDIUM] — No feedback after marking read

**File:** `server.py` lines 754-758 (`/read/{filename}` endpoint)

**Description:**
`mark_read` redirects to "/" with a 303 and no flash message or success indicator. The user sees the page reload but gets no visual confirmation that the action succeeded (unless they notice the "NEW" badge disappeared). If the message was already read, the user has no idea.

**Suggested fix:** Add a `?read=true` query parameter to the redirect and show a brief success indicator, or use the existing `?sent=true` pattern:
```python
return RedirectResponse(url="/?read=true", status_code=303)
```

### UX-03 [LOW] — "Recently Processed" section may show empty for active topic

**File:** `server.py` lines 575-578

**Description:**
The processed section renders `_render_thread(..., topic_filter=topic)`. If no processed messages exist for the currently selected topic, it shows "None" even if there are processed messages in other topics. This makes the feature invisible for most users since they're likely switching topics.

**Suggested fix:** Show a count across all topics in the section header, or don't topic-filter the processed section.

---

## ARCHITECTURE

### A-01 [HIGH] — Duplicate frontmatter parsers across 3 files

**Files:**
- `server.py` lines 75-109 (`_parse_message`)
- `inbox-sensor.py` lines 56-66 (`parse_frontmatter`)
- `check-agent-messages.sh` lines 75-82 (sed/grep extraction)

**Description:**
The YAML frontmatter format is parsed in three completely independent implementations with different field handling. The `server.py` version has 9 fields, `inbox-sensor.py` has 4, and the shell script uses fragile `sed -n '/^from:/s/.*: *//p'` patterns that break if the frontmatter format changes (e.g., quoted values, trailing spaces). Adding a new field (e.g., `tags`) requires updating all three parsers.

**Suggested fix:** Either (a) centralize frontmatter parsing in a shared Python module imported by both server.py and inbox-sensor.py, and have check-agent-messages.sh use `python3 -c` for parsing, or (b) standardize on JSON message files instead of YAML frontmatter in markdown.

### A-02 [MEDIUM] — All CSS/JS embedded in Python f-strings

**File:** `server.py` lines 245-385 (CSS) and lines 582-723 (JS), both inside the `page = f"""..."""` string

**Description:**
The entire 140-line CSS stylesheet and 140-line JavaScript application live inside a Python multi-line f-string. This means:
- No syntax highlighting or linting for CSS/JS (the IDE treats it as a string)
- No CSS preprocessor or minifier can be used
- Changes to CSS/JS require editing a string inside a Python file
- The string has all `{` and `}` doubled to `{{`/`}}` for f-string escaping, reducing readability
- No separate caching or CDN for static assets

**Suggested fix:** Serve CSS/JS from static files:
- Move `STYLES` to `server.py`'s directory as `static/style.css`, serve via `Mount("/static", StaticFiles(...), name="static")`
- Move `<script>` block to `static/inbox.js`
- Reference as `<link rel="stylesheet" href="/static/style.css">`

### A-03 [MEDIUM] — `inbox-sensor.py` bypasses the API to read files directly

**File:** `src/scripts/inbox-sensor.py`

**Description:**
The sensor reads files directly from `$HOME/hermes-cortex-private/messages/inbox/` rather than using the `/api/inbox` endpoint. This means:
- It has its own duplicated frontmatter parsing (see A-01)
- It doesn't benefit from the `for_` per-agent filtering that the API provides
- It must hardcode the inbox directory path rather than discovering it from the server config
- If the storage format changes (e.g., to a database), the sensor breaks silently

**Suggested fix:** Have inbox-sensor.py call `http://127.0.0.1:8903/api/inbox` with `?for=moses&unread_only=true` instead of reading files directly. This eliminates the duplicate parser and keeps the storage format abstracted.

---

## PERFORMANCE

### P-01 [MEDIUM] — Full page reload on auto-refresh instead of lightweight fetch

**File:** `server.py` line 662

**Description:**
The auto-refresh feature calls `location.reload()` every 60 seconds. This is a full page reload — the browser re-parses all CSS, re-renders the entire DOM, and the server parses and renders every message file from disk. For 10+ concurrent auto-refreshing agents, this wastes CPU on the server.

**Suggested fix:** Implement a lightweight AJAX poll:
```javascript
fetch('/api/inbox?unread_only=true')
  .then(r => r.json())
  .then(data => {
    if (data.unread !== currentUnread) location.reload();
  });
```
This only reloads when new messages arrive.

### P-02 [LOW] — All message files parsed on every request (no caching)

**File:** `server.py` lines 186-196 (`_get_all_messages`)

**Description:**
Every request to `/` (the main page), `/health`, or `/api/inbox` reads and parses ALL `.md` files from disk. With 1000+ messages this becomes O(n) in file I/O per request. The processed dir is limited to 30 files, but the inbox is unbounded. No in-memory caching or file-watch-based invalidation.

**Suggested fix:** Add a simple cache with file-mtime-based invalidation:
```python
from functools import lru_cache
_cache: tuple = (None, 0.0)  # (messages, last_mtime_sum)

def _get_all_messages_cached():
    latest = max((p.stat().st_mtime for p in INBOX_DIR.glob("*.md")), default=0)
    if _cache[1] < latest or _cache[0] is None:
        _cache = (_get_all_messages(), latest)
    return _cache[0]
```

---

## MISSING FEATURES

### MF-01 [MEDIUM] — No search or filter by content

**Files:** `server.py` routes `/` and `/api/inbox`

**Description:**
There is no way to search message body or subject text. The only filtering is by topic and unread/urgent status. With dozens of messages, finding a specific conversation requires manual scanning.

**Suggested fix:** Add `?q=<search>` parameter to `/api/inbox` that filters by subject/body substring match.

### MF-02 [MEDIUM] — No pagination in API

**File:** `server.py` lines 772-813 (`/api/inbox`)

**Description:**
The `/api/inbox` endpoint returns ALL matching messages with no `limit`/`offset` parameters. An agent polling with `unread_only=true` gets the full batch every time. This is especially wasteful for the watch scripts that only need a count and IDs.

**Suggested fix:** Add query parameters:
```python
limit: int = Query(50, ge=1, le=500),
offset: int = Query(0, ge=0),
```
Return total counts alongside the current page.

### MF-03 [MEDIUM] — No message deletion or archival

**File:** `server.py`

**Description:**
Messages have only two lifecycle states: inbox (unread/read) and processed (moved by external scripts). There is no API endpoint or UI action to delete messages. Stale or irrelevant messages accumulate indefinitely.

**Suggested fix:** Add a `/delete/{filename}` endpoint and/or a `/archive/{filename}` that moves files to an archive directory.

### MF-04 [LOW] — No WebSocket/SSE for real-time updates

**File:** `server.py`

**Description:**
The only way to see new messages is page reload (manual or auto-refresh at 60s intervals). No push mechanism exists. This means up to 60 seconds of delay before seeing new messages even when the page is open.

**Suggested fix:** Add a lightweight SSE endpoint at `/api/events` that pushes message-count changes, or use Server-Sent Events so the page can update without polling.

### MF-05 [LOW] — No email/notification integration

**File:** `server.py`, all shell wrappers

**Description:**
When a critical-priority message arrives, there's no mechanism to push an out-of-band notification (email, SMS, webhook). The only detection mechanisms are agent poll scripts that run every 5-10 minutes. For genuinely time-sensitive "critical" priority messages, this is a gap.

**Suggested fix:** Add a webhook URL configuration and a background thread/process that POSTs critical-priority messages to the webhook.

### MF-06 [LOW] — No message edit/update endpoint

**File:** `server.py`

**Description:**
Messages are write-once. There's no way for an agent to update a message after sending it (e.g., to correct a typo or add context). The only workaround is to send a reply.

**Suggested fix:** Add a `PUT /edit/{filename}` endpoint that replaces the body/subject of a message, or a `PATCH /update/{filename}` for partial updates.

---

## SHELL WRAPPER & TEST ISSUES

### SW-01 [LOW] — `agent-inbox-check.sh` has no per-agent read tracking

**File:** `src/agent-inbox/agent-inbox-check.sh`

**Description:**
The `--mark-read` flag marks messages read using the legacy `status: read` path (via `/read/{filename}` with no `?for=`). It does not use per-agent read tracking via the `?for=` parameter. After marking, all other agents will also see this message as globally read.

**Suggested fix:** Pass the agent name from the config file:
```bash
AGENT="${AGENT_INBOX_USER:-unknown}"
# Then: ${URL}/read/${m['filename']}?for=${AGENT}
```

### SW-02 [LOW] — `agent-inbox-watch.sh` silently exits on missing auth

**File:** `~/.hermes/scripts/agent-inbox-watch.sh` lines 28-29

**Description:**
Lines 28-29 silently exit with code 0 when USER or PASS is empty. This means a misconfigured watch script produces zero output or diagnostic — it just doesn't work. The user has no way to know why the watch isn't polling.

**Suggested fix:** Output a warning to stderr when exiting due to missing config:
```bash
[ -z "$USER" ] && { echo "agent-inbox-watch: AGENT_INBOX_USER not set" >&2; exit 0; }
```

### SW-03 [LOW] — test-inbox.sh tests the API through both HTTPS (BASE) and HTTP (API) inconsistently

**File:** `src/agent-inbox/test-inbox.sh`

**Description:**
The test uses `BASE="https://127.0.0.1:13004"` for page loads and `API="http://127.0.0.1:8903"` for direct localhost calls. The /send test (line 91) hits the API directly over HTTP without auth, while the health check (line 78) also hits the API directly. This is correct for the architecture, but the test doesn't verify that /send works through nginx with auth, which is the actual production path for remote agents.

**Suggested fix:** Add a test that sends a message through nginx (`$BASE/send`) with auth credentials, and a test that verifies /send without auth is rejected when accessed through nginx.

---

## CLEAN / WELL-DESIGNED ASPECTS

Not everything is broken. Several things are done well:

1. **Security headers in nginx** — The `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy` headers are correctly set on the inbox server block.

2. **Direct-IP blocking** — The `$block_direct_ip` map prevents scanning by bare IP, which is a good anti-scanning measure.

3. **HTML escaping** — All user-supplied content is passed through `html.escape()` before rendering, preventing stored XSS.

4. **Rate limiting** — Two-tier rate limiting (general 20r/s, auth 5r/s) with connection limits is well-configured.

5. **Thread tree building** — `_build_thread_tree` correctly handles orphans and sorts replies chronologically. The thread model is well-designed for agent conversations.

6. **Per-agent read tracking** — The `read_by` comma-separated field and `?for=` parameter pattern is a pragmatic, file-based approach to per-agent read tracking without a database.

7. **Silent watchdog pattern** — `agent-inbox-watch.sh` and `agent-inbox-check.sh` both exit silently when there's nothing new, which is the correct pattern for cron-based watchdogs that save LLM tokens.

8. **Wrapper script architecture** — The per-agent wrapper scripts (agent-inbox-{name}.sh) generated from the registry is a clean, maintainable pattern that avoids config duplication.

---

## RECOMMENDED ORDER OF FIXES (by impact)

| Priority | ID | Why first |
|----------|----|-----------|
| 1 | **S-01** | CSP blocks ALL inline JS → the UI is effectively broken through nginx |
| 2 | **R-01** | File locking race → can silently lose per-agent read tracking data |
| 3 | **A-01** | Duplicate parsers → format changes break silently in 2/3 of codebase |
| 4 | **SW-01** | check.sh doesn't use per-agent read → watch agents mark messages globally read |
| 5 | **S-02** | Unbounded body size → DoS vector via disk fill |
| 6 | **UX-01** | No priority in compose → critical alerts can't be flagged through UI |
| 7 | **P-01** | Full page reload → wastes server CPU on auto-refresh |
| 8 | **R-02** | Misleading fallback path → future callers may operate on non-existent files |
| 9 | **A-02** | CSS/JS in strings → maintenance burden grows with every feature addition |
| 10 | Remaining | Lower impact items |

---

*Report generated by Hermes Agent codebase review. 19 issues found across 6 categories.*
