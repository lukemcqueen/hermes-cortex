# Continuous Skill Suggestion — Design for "During-Edits" Skill Loading

**Status:** Design document (not implemented)
**Author:** Moses
**Date:** 2026-07-29

## Problem

The `.skills-loaded` marker ensures agents load always-section skills at session/task
start. But it's a **one-time gate**. Once open, there's nothing structural that reminds
agents to load task-specific skills discovered *during* a complex edit session.

### Behavioral Gap

An agent deep in a task will:
- Edit a Dockerfile without loading `docker-management`
- Touch a cron definition without loading `cron-job-management` or `cron-format-standard`
- Write an nginx config without loading `nginx-security-pipeline`
- Debug a test failure without loading `root-cause-debugging`
- Create a new script without loading `shell-scripting` or `project-run-scripts`
- Modify a failing cron without loading `cron-quality-gate` or `auto-remediation`

The system prompt says "scan the skills below; if one matches, load it." But when an
agent is 30 tool calls deep in a session with the skills already listed in the prompt,
the list becomes noise — every skill is visible but none are *salient* to the current
file being edited.

## Design Goal

A **structural, non-blocking suggestion system** that fires on write operations and
tells the agent "this file has a matching skill — consider loading it."

### Constraints

1. **Structural** — enforced by the enforcer plugin or MCP server, not agent willpower
2. **Non-blocking** — suggestion only, never blocks work
3. **Low-overhead** — simple regex/glob pattern match, no embeddings or LLM calls
4. **No latency** — must not add measurable delay to tool calls
5. **Maintainable** — agents add new path-to-skill mappings without plugin code changes

## Architecture

### Components

```
skill-path-map.yaml              ← Agent-maintained mapping file
       │
       ▼
hermes plugin: post_tool_call    ← Enforcer: matches file path → returns hint in result
       │
       ▼
Loop gov MCP server: end_change  ← Reads trace file, returns aggregate suggestions
```

### Data Flow

```
1. Agent calls patch("nginx.conf", old=..., new=...)
2. Enforcer pre_tool_call_hook validates lock → allows
3. Enforcer post_tool_call_hook:
   a. Matches file path against skill-path-map.yaml → "nginx.conf" → [nginx-security-pipeline]
   b. Appends hint to tool result: "📎 Relevant skill: skill_view('nginx-security-pipeline')"
   or
   c. Appends to session touch-trace file for end_change aggregation
4. Agent sees hint, optionally loads the skill
5. On end_change, aggregate suggestions from touch-trace return as summary
```

### Mapping File Format

Path: `~/.hermes-cortex/skill-path-map.yaml`

```yaml
# Glob pattern → [skill-names]
# First match wins within a line; lines evaluated top-to-bottom
docker*:
  - docker-management
  - env-aware-compose-wrapper
  - deployed-component-verification
nginx*:
  - nginx-security-pipeline
  - nginx-web-app-deployment
cron*:
  - cron-job-management
  - cron-format-standard
  - cron-request-protocol
  - cron-quality-gate
fail2ban*:
  - nginx-security-pipeline
  - sync-allow-ips-to-fail2ban
cortex-update*:
  - hermes-cortex-maintenance
  - fleet-management
  - hermes-cortex-setup
install*:
  - hermes-cortex-setup
  - package-security
sudoers*:
  - sudoers-audit
pre-commit*:
  - ci-cd-pipeline
docker-compose*:
  - env-aware-compose-wrapper
systemd*:
  - hermes-s6-container-supervision
  - prevent-crash-looping
telegram*:
  - telegram-delivery-diagnostics
test*:
  - test-driven-development
  - test-seed-uniqueness
ops/scripts/manage/*:
  - server-administration
  - shell-scripting
docs/*.md:
  - documentation-auditing
```

Patterns use Python `fnmatch`. First-match-wins within a pattern group; all matching
patterns fire (union of skill names). Agents update the map as they discover
associations.

## Implementation Options

### Option A — Enforcer post_tool_call hinting (Best, if post_tool_call hooks exist)

Requires Hermes to support `post_tool_call` hooks. The enforcer:

1. Runs after every allowed tool call
2. Extracts file path from tool arguments
3. Matches against `skill-path-map.yaml`
4. Returns a hint dict: `{"hint": "📎 Relevant skill: skill_view('docker-management')"}`
5. Hermes appends this to the tool result the agent sees

**Pro:** Immediate — agent sees the hint on the same turn as the write
**Con:** Requires Hermes plugin API to support post_tool_call with result modification

### Option B — Trace file + end_change aggregation (Works with pre_tool_call only)

The enforcer writes a JSONL trace file during the session. The `end_change` MCP tool
reads it and returns suggestions.

1. Enforcer `pre_tool_call_hook`:
   ```python
   if hermes_session_id and _is_write_tool(tool_name, args):
       file_path = _extract_path(tool_name, args)
       if file_path:
           _append_trace(hermes_session_id, file_path)
   ```
2. `end_change` in loop-gov-mcp.py:
   ```python
   traces = _read_traces(session_id)
   paths = {t["file"] for t in traces}
   suggestions = _get_skill_suggestions(paths)
   if suggestions:
       result += "\n\n📌 Skills for files you edited:\n" + "\n".join(f"   skill_view('{s}')" for s in suggestions)
   ```

**Pro:** Works with existing Hermes plugin API
**Con:** Suggestion arrives at end_change, not in the moment

### Option C — Combined approach (Recommended)

Phase 1: Option B (trace file + end_change) as the initial implementation — it works
with today's Hermes plugin API.

Phase 2: Option A (post_tool_call hinting) if/when the API supports it — move from
"end-of-cycle summary" to "in-the-moment nudge."

## Implementation Details

### Phase 1: Touch-trace writer in enforcer

Add to `pre_tool_call_hook`, after the lock check but before `return None`:

```python
# Track touched files for skill suggestion
if hermes_session_id and SKILLS_MARKER.exists():
    file_path = _extract_tool_path(tool_name, args)
    if file_path:
        _append_touch_trace(hermes_session_id, file_path)
```

Supporting functions:

```python
import json, datetime
from pathlib import Path

def _extract_tool_path(tool_name: str, args: dict) -> str | None:
    """Extract the primary file path from a write tool call."""
    if tool_name == "write_file":
        return args.get("path")
    if tool_name == "patch":
        return args.get("path")
    if tool_name == "terminal":
        cmd = args.get("command", "")
        # Extract destination from redirects
        m = re.search(r'(?:>|>>)\s*(\S+)', cmd)
        if m:
            return m.group(1)
        # Extract the last path-like argument (heuristic)
        parts = cmd.split()
        for part in reversed(parts):
            if part.startswith("/") or part.startswith("~") or part.startswith("."):
                return part
    if tool_name in ("skill_manage",):
        return args.get("name")  # skill name, not file
    return None

def _append_touch_trace(session_id: str, file_path: str) -> None:
    """Append a touch trace entry for skill suggestion."""
    trace_dir = Path.home() / ".hermes-cortex" / "state"
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_file = trace_dir / f".touched-{session_id}.jsonl"
    entry = {
        "ts": datetime.datetime.now().isoformat(),
        "file": file_path,
    }
    with open(trace_file, "a") as f:
        f.write(json.dumps(entry) + "\n")
```

### Phase 2: Suggestion in end_change

In `loop-gov-mcp.py`, after the lock release and marker cleanup:

```python
# Suggest skills for touched files
skill_hint = _get_skill_suggestions(session_id)
if skill_hint:
    extra += skill_hint
```

Supporting function:

```python
import json, fnmatch, yaml
from pathlib import Path

SKILL_PATH_MAP = Path.home() / ".hermes-cortex" / "skill-path-map.yaml"

def _get_skill_suggestions(session_id: str) -> str:
    """Return aggregated skill suggestions from touch trace."""
    trace_file = Path.home() / ".hermes-cortex" / "state" / f".touched-{session_id}.jsonl"
    if not trace_file.exists() or not SKILL_PATH_MAP.exists():
        return ""
    
    # Read touched paths
    touched = set()
    with open(trace_file) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    fp = entry.get("file", "")
                    if fp:
                        touched.add(fp)
                except json.JSONDecodeError:
                    pass
    
    if not touched:
        return ""
    
    # Load mapping
    with open(SKILL_PATH_MAP) as f:
        mapping = yaml.safe_load(f)
    
    # Match and deduplicate
    matched_skills = set()
    for path in touched:
        for pattern, skills in mapping.items():
            if fnmatch.fnmatch(path, pattern):
                matched_skills.update(skills)
    
    if not matched_skills:
        return ""
    
    lines = ["\n\n📌 Skills you may find useful for files you edited:"]
    for s in sorted(matched_skills):
        lines.append(f"   skill_view('{s}')")
    return "\n".join(lines)
```

### Phase 3: Trace cleanup

```python
def _cleanup_traces(session_id: str) -> None:
    """Remove trace file for a session."""
    trace_file = Path.home() / ".hermes-cortex" / "state" / f".touched-{session_id}.jsonl"
    if trace_file.exists():
        trace_file.unlink(missing_ok=True)
```

Call `_cleanup_traces(session_id)` at:
- End of `end_change` (after reading the trace)
- Session start (clean stale traces)

## Open Questions

1. **Hermes post_tool_call API** — Does Hermes support it? If yes, Phase 1 can be
   enriched from "write trace" to "return hint in result."

2. **Terminal path extraction** — Terminal commands carry file paths implicitly
   (`cp src dest`, `sed -i 's/x/y/' file`). Heuristic extraction may miss or
   misidentify paths. Conservative approach: only extract from explicit redirect
   (`>`, `>>`) and from `write_file`/`patch` (which have named path arguments).

3. **Mapping maintenance** — Who updates `skill-path-map.yaml`? Agents should update
   it when they discover "I was editing X and should have loaded skill Y." The map
   should be in the repo so all agents benefit.

4. **False positive rate** — Broad patterns like `*.py` match everything. The default
   map should be conservative (specific paths, not extensions). Agents broaden as
   needed.

5. **Suggestion frequency** — Every `end_change` or only when new patterns are
   discovered? Suggested: show at most once per session for each skill, then suppress
   repeats.

6. **Session-to-session persistence of suggestions** — If an agent misses a suggestion
   at end_change but the next task reuses the same session (no new begin_change),
   should the suggestion persist? Probably not — clean up at end_change.

## Migration Path

1. Create `~/.hermes-cortex/skill-path-map.yaml` with initial mappings (from above)
2. Deploy updated enforcer with `_append_touch_trace` in pre_tool_call_hook
3. Deploy updated loop-gov-mcp.py with `_get_skill_suggestions` in end_change
4. Add `_cleanup_traces` to session start and end_change
5. Agents discover and extend mappings over time

## See Also

- `plugins/governance-enforcer/__init__.py` — Governance enforcer (add here)
- `mcp-servers/loop-gov-mcp.py` — Loop governance MCP server (extend end_change)
- `AGENTS.md#rule-6` — "Prove existing can't handle it before creating new"
- `docs/loop-governance-reference.md` — Loop governance reference
