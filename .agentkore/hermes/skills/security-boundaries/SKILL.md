---
name: security-boundaries
description: What Hermes must never delegate or expose to OpenCode subagents.
---

# Security Boundaries

## Never delegate to OpenCode
- `.env` file operations
- Key/certificate management
- Secrets or credential handling
- Direct production data access
- Session token operations
- `.git/credentials` or SSH key management

## Never expose in task context
- API keys, tokens, passwords
- Environment variable values
- Private keys, certificates
- Session tokens or auth cookies
- Personal user data

## Safe for delegation
- Code changes in `src/`, project directories
- Test writing and execution (`./run test`)
- Git operations (except `git push` without approval)
- Documentation updates
- Config changes (non-secret)

## Isolation
- Subagents get isolated terminal sessions
- No access to Hermes skills, memory, or cron
- No access to messaging platforms
- 180s timeout per subagent invocation
- No nested delegation
