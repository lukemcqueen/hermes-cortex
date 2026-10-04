---
name: credential-leak-response
version: 1.0.0
category: security
description: "Use when a credential leaks — verify live, scrub, rotate."
metadata:
  hermes:
    tags: [security, credentials, leak, rotation, secrets, incident-response]
    related_skills: [secure-credential-handling, pii-scrubbing, cortex-bus]
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

**Test the operation that CONSUMES the credential, not a listing/health endpoint.**
Provider catalog endpoints are usually public: an LLM provider's model list returns 200 for
a REVOKED key, and `/health` returns 200 for anything reachable. Probing those yields a
false green — "the key still works" — which sends you looking for the fault somewhere else
entirely (a reviewer auth error, a config resolution bug) while the credential is the
problem. Use an authenticated, billable/authorized operation (a completion call, a queue
read) and keep the deliberately-wrong control alongside it. State the probe you used when
reporting a credential's liveness; "verified live" from an unauthenticated endpoint is a
false claim, not a shortcut.

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
- **Every RESOLVER of the value, not just the file you edited.** A rotation is only closed
  when the running consumers actually resolve the NEW value, and resolvers disagree about
  where to look. Two traps, both silent: (1) a resolver that reads the process environment
  FIRST keeps serving the old value for the life of the process — the updated file has no
  effect until that process restarts, and a long-lived server (an MCP child, a daemon) can
  outlive the rotation by hours; (2) a resolver that searches SEVERAL files in a fixed order
  takes the FIRST match, so updating the file you found (or the last one in its order) leaves
  an older copy winning. Enumerate the resolver's order, verify the value it will actually
  pick — hash it and probe THAT against the consuming endpoint — and check the running
  process's environment separately from the file on disk. Report which source was stale,
  never the value.

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

### 7. The session transcript is an exposure channel — rotation is the only closure

Not every leak is in git. An edit tool's context/diff echo (or any tool output) can
put a live credential into the **session transcript and its persisted store**, where
no working-tree or history scrub can reach it. Scope it honestly, then rotate:

```bash
V=$(sed -n 's/^NAME=//p' .env | head -1)          # subshell: the value never appears
printf 'tracked: %s\n' "$(git grep -l -F "$V" -- . | wc -l)"      # 0 = no repo closure
printf 'history: %s\n' "$(git log --all -S"$V" --oneline | wc -l)"
grep -rl -F "$V" ~/.hermes/logs ~/.hermes/cron/output /tmp | wc -l  # persisted copies
curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $V" <gated-endpoint>  # 200
curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer INVALID-CONTROL" <same> # 401
```

If the repo/history counts are 0, there is nothing to rewrite — **report it, and
rotate**. Scrubbing the transcript does not un-expose a value the model already read;
the 401 control is what proves the old key is dead. Tell the user plainly which file
and channel leaked, and never re-embed the literal while investigating.

## Rotation mechanics by system

- **Bus (bearer tokens + nginx Basic auth):** `cortex-bus` skill →
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
- `cortex-bus` — bus-specific credential rotation playbook
