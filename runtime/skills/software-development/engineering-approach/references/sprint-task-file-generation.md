# Sprint Task File Generation

**Context:** acme-royalty project — converting Epic definitions into individual sprint task files.

## Workflow

Given an `epics.md` file with Epic → Story definitions, generate one markdown file per story at `docs/tasks/sprint-{epic_id}-{story_num}.md`.

## File Format

### Frontmatter (YAML)

```yaml
---
story_id: '{epic_id}.{story_num}'
story_key: '{epic_id}-{story_num}-kebab-case-title'
epic_id: '{epic_id}'
status: 'pending'
date: '{YYYY-MM-DD}'
user_name: 'Luke'
workflow_type: 'create-story'
---
```

- `story_key`: kebab-case derived from the story title, e.g. `3-1-tiered-approval-gate`
- `status`: `'pending'` for new stories, `'complete'` for done ones
- `user_name`: `'Luke'` (current user convention)

### Title & Epic reference

```markdown
# Story {X.Y}: {Title}

**Epic:** {X} — {Epic Name}
```

### Body

Two story types with different AC patterns:

### New-Feature Stories

User story in "As a… / I want… / So that…" Gherkin format, with acceptance criteria as Given/When/Then blocks:

```markdown
## User Story

> As a {role},
> I want {capability},
> So that {benefit}.

**Acceptance Criteria:**

**Given** {context}
**When** {action}
**Then** {expected result}
**And** {additional result}
```

- Use concrete names from the personas (Min-su, Ji-yeon, Eun-ji, etc.) where relevant
- Each AC block is a scenario, not a checkbox list
- Write acceptance criteria with enough detail that they're testable

## Batch Creation Pattern

For 10+ files, batch writes in parallel groups of 8-12 using `write_file` calls. Each file is independent so they don't need sequencing. Verify with `ls | wc -l` and a grep on `status:` after all writes.

## File naming convention

```
docs/tasks/sprint-{epic_id}-{story_num}.md
```

- Epic 2, Story 8 → `sprint-2-8.md`
- Epic 11, Story 4 → `sprint-11-4.md`

## Pitfalls

- Don't prefix with `00` or zero-pad story numbers (actual files use `sprint-2-8.md`, not `sprint-02-08.md`)
- Include `---` YAML delimiters — omitting them produces invalid frontmatter
- The `story_key` must be globally unique across all stories, not just within the epic
- Use `'pending'` (lowercase, quoted) — YAML treats unquoted `pending` as a bare word which is fine but quoted is consistent with existing files
- When converting epics.md content, preserve the original intent but expand bullet points into proper Gherkin Given/When/Then

### Migration/Porting Stories

When the story ports existing functionality to a new stack (e.g., Next.js API route → FastAPI endpoint), use a behaviour-preservation pattern instead of a user-scenario:

```
# Story {X.Y}: {Title}

**Epic:** {X} — {Epic Name}

## User Story

> As a developer,
> I want {existing feature} ported from {old_location} to {new_location},
> So that {benefit of the new architecture}.

## Acceptance Criteria

**Given** the existing {old_location} {behaviour summary}
**When** it is reimplemented at {new_location}
**Then** it behaves identically for the caller (same input fields, same response shape, same error codes)
**And** {new-location-specific requirements like rate limiting, auth, caching}

**Given** {new_location} is deployed
**When** {old_location} is removed
**Then** all callers have been updated to use {new_location}
**And** the frontend build succeeds with no dangling imports

**Given** {error scenario specific to new stack}
**When** {error condition}
**Then** {expected graceful behaviour}
```

Key differences from new-feature stories:
- Focus on **behaviour parity** — the AC proves nothing broke, not that something new is built
- Include a **removal criterion** — old code must be deletable after migration
- Include **error scenarios** specific to the new stack (e.g., "proxy target unreachable" for search proxy port)
- Rate limits, auth requirements, and caching that existed in the old route must be explicitly called out in the AC
