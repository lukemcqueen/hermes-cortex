---
name: lesson-aware-agent
version: 1.0.0
category: software-development
description: "Universal lesson-aware injection pattern. Makes every agent action memory-aware: search lessons before acting, save lessons after fixing. Works across all skills, not just change-test-loop."
author: Hermes Cortex
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [memory, lessons, compounding, agent-pattern, universal]
    related_skills: [change-test-loop, save-lesson, offline-knowledge, agent-contract]
---

# Lesson-Aware Agent — Memory That Compounds

## The Core Insight

**The most expensive fix is the one you've already made.** Lesson-aware agents prevent re-discovery by searching personal memory before every non-trivial action. Every fix compounds — 10 lessons saves an hour, 100 lessons saves a day, 1,000 lessons transforms how you develop.

## Universal Protocol

This skill defines **one pattern that applies everywhere** — not just change-test-loop, but PR review, debugging, refactoring, even answering questions:

### Before Every Action

```python
# Step 0: Is this a non-trivial action that might have a known solution?
# If yes → search lessons
if is_non_trivial(problem):
    result = json.loads(terminal(
        "offline_knowledge lesson search " + shlex.quote(problem) + " --limit 3"
    )["output"])
    
    if result.get("count", 0) > 0:
        lesson = result["results"][0]
        # Apply known fix
        # INCREMENT success_count: terminal("bash ~/.hermes/scripts/lesson-hit.sh --search '" + lesson["title"] + "'")
        # Rebuild index: terminal("offline_knowledge lesson index")
        # Report time saved
```

### After Every Fix

```python
# Was this non-trivial? Would I want to remember this?
if should_save(problem, solution):
    terminal(f"""offline_knowledge lesson create \\
      --title {shlex.quote(title)} \\
      --problem {shlex.quote(problem)} \\
      --cause {shlex.quote(cause)} \\
      --solution {shlex.quote(solution)} \\
      --language {lang} \\
      --tags {" ".join(["tag"] if tag else [])}""")
    terminal("offline_knowledge lesson index")
```

## When to Load This Skill

Load `lesson-aware-agent` whenever you begin a session that involves:

- **Any code change** (bug fix, feature, refactor)
- **Debugging** (error investigation, root cause analysis)
- **PR review** (check if similar issues have been fixed before)
- **Answering a technical question** (check lessons for relevant experience)
- **Starting a new project** (check lessons for domain-specific pitfalls)

**Combined with change-test-loop:** The `change-test-loop` skill v2.0+ already includes this pattern natively (LEARN → RED → GREEN → REFACTOR). Load both for full coverage.

**Combined with save-lesson:** The `save-lesson` skill covers the manual save workflow. This skill adds the universal "check before, save after" around everything.

**Combined with agent-contract:** Add these rules to your agent-contract for always-on enforcement:

```yaml
# In agent-contract or AGENTS.md:
rules:
  - "Before debugging any error: search the lesson database first"
  - "After fixing any non-trivial bug: save as a lesson"
  - "Report lesson matches and time saved in session summary"
```

## The Compound Score

Track the compounding effect to see tangible value:

| Metric | Formula | Today (example) |
|--------|---------|-----------------|
| **Lessons saved** | total_lessons | 134 |
| **Times applied** | sum(success_count) | 187 |
| **Time saved (est.)** | times_applied × 15min | 46.75 hours |
| **Coverage** | lessons per language/framework | 12 languages |
| **Hit rate** | LEARN matches / total actions | ~40% |

## Integration Points

### With root-cause-debugging

Before any debugging session:
1. **LEARN** — search lessons for the error message
2. If found → apply fix, skip debug
3. If not → debug as normal, save as lesson

### With pr-review

During code review:
1. Check if any proposed fix pattern has a matching lesson
2. Reference the lesson in review comments
3. If review discovers a fix pattern, save as lesson

### With agent-flow (workflow router)

When the router classifies an incoming request:
1. If the request mentions an error or bug → search lessons before routing
2. If a lesson matches → short-circuit to direct fix

## Dependencies

- `offline-knowledge` (provides the lesson search/index/create CLI)
- `nomic-embed-text:v1.5` (Ollama model for semantic embeddings)
- `save-lesson` (manual save workflow, already integrated)

## Design Principles

1. **Zero friction** — lesson search should take <1 second and never block progress
2. **Always relevant** — only surface lessons with similarity ≥ 0.55; lower = noise
3. **Compound by default** — every fix automatically feeds back into the system
4. **Measurable** — track hit rates, time saved, coverage expansion
5. **Transparent** — user sees "Applied known fix from lesson 'X' (saved 20min)" so they know the system is working
