---
name: skill-vetting
version: 1.0.0
description: "Vet skills for safety, external dependencies, and self-contained operation before installing. Scan scripts, check for external API calls, verify stdlib-only imports, and reject skills that require external services. Use when installing any skill from a registry, hub, or third-party repo."
triggers:
  - "vet skill"
  - "skill review"
  - "skill safety check"
---

# Skill Vetting

Vet any skill before it enters the fleet — from the Skills Hub, a community
repo, a peer agent's report, or a PR. A bad skill ships to every agent that
loads it.

## When to Use

- Installing any skill from a registry, hub, or third-party repo
- Evaluating a fleet-submitted skill (orch-skill-lifecycle Phase 2)
- Approving a `skill_manage(action='create')` for the shared repo

## Vet Checklist — run before install

### 1. Safety scan

- Read the FULL SKILL.md — never install on the description alone.
- **Stub body is a hard REJECT**: if the body is a compression/pruning
  placeholder (frontmatter intact, body replaced by a placeholder marker
  such as "content unavailable"), the content was lost — flag it for
  restore, never upstream or install it.
- Scan `scripts/` for: shell injection, `rm -rf`, `curl … | bash`,
  `eval`, base64-decode pipelines, `sudo` without a passwordless check.
- Look for credential exfiltration: hardcoded API keys, pastebin /
  webhook.site endpoints, env vars read then echoed.

### 2. External dependencies

- Scripts must be **stdlib-only** unless the dependency is declared and
  justified. A `pip install` inside a skill = REJECT unless the skill is
  explicitly a setup/installer skill.
- Runtime network I/O (external API calls) = WARN: the skill must declare
  the endpoint, auth model, and failure mode.
- Required external services (Docker daemon, SaaS, remote DB) = REJECT
  for generic skills; only host-specific skills may assume host services.

### 3. Self-containment

- No absolute paths that only exist on the author's host (`/home/<user>`).
  Use `$HOME` / `Path.home()`.
- No reliance on another skill's private files unless declared via
  `related_skills`.
- Works from any cwd, or declares its `workdir`.

### 4. Fleet/repo fit

- Name follows convention (lowercase, hyphens, max 64 chars).
- Frontmatter has `name` + `description` with the trigger self-contained
  in the first ~57 chars.
- **No PII**: real domains, emails, or client names → placeholders
  (`your-domain.com`, `client-alpha`).

### 5. local-* priority (fleet evaluation only)

A `local-*` prefix declares host-scope: the skill was created on one host
for that host's problems. It is NOT a quality mark against the skill —
but upstreaming priority is LOW. Fleet evaluation (orch-skill-evaluate):
- Default stance: **DEFER** — rarely generalizes beyond the authoring host.
- Reconsider only when the skill clearly solves a generic problem (no
  host-specific paths, services, or workflows) AND would benefit other
  agents — then evaluate it as a normal candidate, renamed without the
  `local-` prefix.
- Never reject a `local-*` skill for being local — collect still reports
  it and the author may promote it later. Defer, don't discard.

## Decision Table

| Finding | Decision |
|---------|----------|
| Stub / missing body | **REJECT** — flag for restore |
| Injection / exfiltration pattern | **REJECT** — do not install |
| Undeclared external service / runtime API | **REJECT** or WARN |
| Stdlib-only, self-contained, no PII | **APPROVE** |
| Minor issues (path, PII, naming) | APPROVE after fix, note the fix |

## Verification after approval

1. `skill_view(name)` — body loads, fences balanced
2. `bash -n` / `py_compile` on any scripts
3. `secret-leak-detector.sh` clean before committing to the repo
4. Doctor `Skills manifest` checks pass after deploy
