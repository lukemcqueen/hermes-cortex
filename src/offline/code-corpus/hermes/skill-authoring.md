---
language: yaml
tags: [hermes, agent, config, setup]
title: Authoring SKILL.md Files
description: How to write SKILL.md files — frontmatter, sections, file structure, and best practices
source: pattern
---

# Authoring SKILL.md Files

Skills are Markdown files that teach Hermes how to act in specific domains. They
live in skill directories and are loaded at startup.

## File Name Convention

```
SKILL.md                    # Root skill descriptor (meta)
<domain>/SKILL.md           # Domain skill
<domain>/<subdomain>.md     # Sub-skills
```

Examples:

```
~/.hermes/skills/
├── SKILL.md                # Skill catalog root
├── hermes-agent/
│   ├── SKILL.md            # Hermes Agent skill descriptor
│   ├── configuration.md    # Sub-skill on config
│   ├── tool-use.md         # Sub-skill on tool usage
│   └── troubleshooting.md
├── software-development/
│   ├── SKILL.md
│   ├── python/
│   │   ├── SKILL.md
│   │   ├── testing.md
│   │   └── packaging.md
│   └── go/
│       ├── SKILL.md
│       └── modules.md
└── devops/
    ├── SKILL.md
    ├── docker.md
    └── kubernetes.md
```

## YAML Frontmatter

Every SKILL.md file must start with YAML frontmatter:

```yaml
---
# Required
name: go-development          # Unique skill identifier
description: >               # One-line summary
  Go language development patterns, tooling, and best practices
version: 1.0.0

# Recommended
author: nous-research
tags:
  - go
  - golang
  - backend
  - development
depends_on:                  # Skills loaded before this one
  - software-development

# Optional metadata
priority: normal             # normal | high | low
icon: 🐹                     # Emoji icon for UI display
max_tokens: 4096             # Truncation limit for this skill
---
```

## Section Structure

Use a consistent heading hierarchy. Agents parse these headings to locate
relevant guidance.

```markdown
# Skill Title

Brief overview — one or two paragraphs. State what this skill teaches and when
to apply it. Agents read this to decide if the skill applies to the current
task.

## Principles

Core rules and non-negotiable behaviors. Keep these short and actionable.

- Always use explicit error handling; never panic in library code.
- Favor composition over inheritance.
- Format all code with `gofumpt` before committing.

## Patterns

Pragmatic recipes with code examples. Use fenced code blocks with language
tags.

### Pattern: HTTP Handler with Middleware

```go
func loggingMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        log.Printf("%s %s", r.Method, r.URL.Path)
        next.ServeHTTP(w, r)
    })
}
```

### Pattern: Table-Driven Tests

```go
func TestAdd(t *testing.T) {
    tests := []struct {
        name string
        a, b int
        want int
    }{
        {"positive", 1, 2, 3},
        {"negative", -1, -2, -3},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            if got := Add(tt.a, tt.b); got != tt.want {
                t.Errorf("Add() = %d, want %d", got, tt.want)
            }
        })
    }
}
```

## Tools

Describe tool configurations relevant to this skill. Reference specific commands
and expected output.

```
hermes tool: terminal
commands:
  - go build ./...
  - go test -race ./...
  - go vet ./...

hermes tool: session_search
query: "Go module path conventions"
```

## References

Links to external documentation, specification pages, or related skills.

- [Go Documentation](https://go.dev/doc/)
- [Effective Go](https://go.dev/doc/effective_go)
- [Go Modules Reference](https://go.dev/ref/mod)

## Anti-Patterns

Common mistakes this skill should help avoid.

- **Ignoring errors**: `rows.Close()` returns an error that should be logged.
- **Global state**: Package-level variables make testing impossible.
- **Over-abstracting**: One-off interfaces with a single implementation.
```

## Best Practices

### 1. Keep Skills Focused

Each skill should cover one domain. If a skill grows beyond ~200 lines, split it.

```
good:  go-testing.md         # Testing in Go
bad:   go-everything.md      # Every Go pattern ever
```

### 2. Use Active Voice

Write as instructions to the agent, not descriptive prose.

> ✓ "Use `context.Context` as the first parameter in every RPC function."
> ✗ "The context package provides a way to carry deadlines and cancellation
>    signals across API boundaries."

### 3. Favor Examples Over Explanations

A working code block is worth ten paragraphs of prose.

### 4. Tag Code Blocks

Always specify the language for syntax highlighting and tool extraction.

````markdown
```go
// good — tagged
```

```
// bad — untagged
```
````

### 5. Provide Fallbacks

When a pattern requires a specific tool or library, mention alternatives.

```yaml
# Frontmatter fallback hint
fallbacks:
  logging: [zerolog, zap, logrus]
  routing: [chi, gorilla/mux, http.ServeMux]
```

## Validation

Check your skill files with:

```bash
hermes validate skills                     # validate all skills
hermes validate skills --path ./myskill.md # single file
hermes validate skills --strict            # fail on warnings
