---
name: credential-leak-response
version: 1.0.0
category: security
description: "Use when a credential leaks — verify live, scrub, rotate."
metadata:
  hermes:
    tags: [security, credentials, leak, rotation, secrets, incident-response]
    related_skills: [secure-credential-handling, pii-scrubbing, agent-bus]
---

# Credential Leak Response

## Trigger

- A live-looking credential (password, Bearer token, API key) is found in a repo, doc, config, or public file
- A security review or the secret-leak-detector flags a real credential
- Asked to "rotate" or "scrub" a credential
- An incident: leaked credential may have been exploited

## Doctrine (learned 2026-08-03 — live moses Basic-auth password + bus tokens in a public repo for 12 days)

### 1. Verify "live" with a baseline — or the test proves nothing

Test the credential against an **auth-gated** endpoint (e.g. `/api/pgmq/queues`,
NOT `/health`, which may or may not be gated), and always run a deliberately
wrong credential as control:

```bash
curl -sk -o /dev/null -w "%{http_code}" --basic -u "moses:LEAKED_VALUE" https://host:13004/api/pgmq/queues   # 200 = live
curl -sk -o /dev/null -w "%{http_code}" --basic -u "moses:WRONG_CONTROL" https://host:13004/api/pgmq/queues  # 401 = baseline
```

A 200 without the 401 baseline proves nothing. For bearer tokens, test against
the DIRECT localhost bus port — Bearer through nginx is ignored (nginx demands
Basic and sets X-Forwarded-User), so a token that "401s" through nginx can
still be LIVE locally.

### 2. Identify the owner by hash, not label

A token's owner is the DB row whose hash matches — never the account name in
the config/doc that carried it. (The "esther" setup guide actually held
**moses'** bus token; esther's `.env` was seeded with it, so it authenticated
as moses with full queue privileges.) Hash + lookup, then rotate the MAPPED row:

```bash
python3 -c "import hashlib; print(hashlib.pbkdf2_hmac('sha256', b'<token>', b'<salt>', <iters>).hex())"
# → SELECT agent_name FROM <tokens_table> WHERE token_hash='<hash>' AND is_active=true;
```

Use the system's own hash function (check the auth module) — don't guess the
algorithm/salt.

### 3. Scrubbing the working tree ≠ closure

The value remains in **git history** (`git show <old-commit>:<file>`), and the
credential may still be **live server-side**. Two closures:
- **History:** rewrite with `git-filter-repo` (see `pii-scrubbing` skill Phase 4) — needs user authorization, force-push coordination
- **Running system:** rotate the credential itself (generate new → update all consumer configs → update the auth store → verify old dies)

Do whichever the user authorizes. Scrubbing alone only stops NEW exposure.

### 4. Don't re-embed the literal while scrubbing

In comments/examples describe it ("a 16-char hex password") — never repeat the
value. (Almost re-embedded the leaked password in the detector's own history
comment while scrubbing.)

### 5. Grep the whole tree, not just the file you found

One value was in 6 files across 6 commits. `git grep -l <string>` finds every
current copy; `git log -S <string>` finds the commits that introduced it (dates
matter for exposure windows).

### 6. Warn-only detectors never block — and warnings get ignored

The pre-commit `secret-leak-detector.sh` was warn-only (exit 0) from creation,
which let the live credential through every commit for 12 days. Since
2026-08-03 it **blocks** (exit 1) real-looking inline creds
(`curl -u "user:<12+ alnum>"`); placeholders (`your-password`, `$(cat file)`,
short demos) stay warn-only. If a commit is blocked: replace the literal — do
NOT `--no-verify`. When the detector report prints "N potential leaks",
REVIEW every line before pushing; don't tail-past the report.

## Rotation mechanics by system

- **Bus (bearer tokens + nginx Basic auth):** `agent-bus` skill →
  `references/credential-rotation.md` — token rotation steps, bearer-vs-Basic
  exposure model, htpasswd rotation blockers (sudo password required,
  Docker userns remapping kills container-root writes, postgres images run as
  `USER postgres` → `--user root`, gateway parser rejects ssh+heredoc → scp the
  script), concurrent-session git safety.

## Pitfalls

- Testing "live" against an open endpoint → false "dead" or false "live" claim. Always baseline.
- Rotating the wrong row because the token was labeled with the wrong account → verify by hash first.
- Stopping at the working-tree scrub → history + live service still exposed. Rotate.
- `--no-verify` to push a blocked commit → bypasses the enforcement the leak taught you to build.
- Half-applying a rotation (config updated, auth store not) → breaks consumers; update consumer configs BEFORE the auth store, verify old→401 new→200.

## Related

- `secure-credential-handling` (user-owned) — behavioral rules for not leaking secrets into command strings in the first place
- `pii-scrubbing` (user-owned) — full repo PII inventory + git-filter-repo history rewrite
- `agent-bus` — bus-specific credential rotation playbook
