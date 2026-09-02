# Fine-Grained GitHub PATs — Format + Capability Gaps

Verified against api.github.com on 2026-09-01 while creating a public repo
with a fine-grained token (prefix `github_pat_`).

## Credential-line format (~/.git-credentials)

A fine-grained PAT must live in the git credential store as:

```
https://x-access-token:<PAT>@github.com
```

The PAT goes in the PASSWORD field; the username is literally
`x-access-token`. Two malformed shapes seen in the wild:

- `https://github_pat_...:<something>@github.com` — PAT in the USERNAME
  field (works with some clients, not the canonical shape).
- A bare token with no `user:pass@host` structure at all — git cannot
  parse it; `git ls-remote` on a PUBLIC repo still "works" (anonymous
  read succeeds), so a false green hides the broken credential.

**Truncation smell:** a token that ENDS in literal `...` or is ~13 chars
is a TRUNCATED/placeholder value, not a scoped token. The real fix is a
fresh token, not more GitHub scope toggling — the on-disk value is
incomplete and can never authenticate. (2026-09-01: a restored
credential file had the PAT physically cut to `github_pat_11AAD...`;
"expanding scope to all repos" cannot repair a truncated value.)

## Capability gaps (auth ≠ capability)

A token that authenticates (`GET /user` → 200) and lists repos
(`GET /user/repos` → 200) may STILL be unable to write:

| Operation | Fine-grained permission needed | Failure when missing |
|---|---|---|
| `GET /user`, list repos | read (any) | — |
| **Create repo** `POST /user/repos` | `Administration: Read and write` | 403 `Resource not accessible by personal access token` |
| Push to a repo | `Contents: Read and write` | 403 on push |

Key facts:

- **Expanding "repository access" to all repos does NOT grant create or
  push.** Repository permissions are separate toggles under the token;
  Administration and Contents are distinct.
- The response header `X-Accepted-GitHub-Permissions:
  allows_permissionless_access=true` reveals a READ-ONLY token. Check it
  when a write 403s before re-generating.
- `gh repo create` and the REST API share the same permission model — no
  path around it.

## Fastest unblock: browser-created empty repo

When the token can push but not create (Contents ✓, Administration ✗):

1. User creates the repo at github.com/new (Public, **no** README/
   license/.gitignore so the local push lands clean).
2. `git remote add origin https://github.com/<user>/<repo>.git`
3. Push with the existing token — no Administration needed.

API-creation is only worth pursuing when the token already has
Administration: write (then `POST /user/repos` with `name`, `private`,
`description`).

## Detection recipe

```python
import re, json, urllib.request
line = open('/home/<user>/.git-credentials').read().strip().split('\n')[0]
tok = re.search(r'(github_pat_[A-Za-z0-9_]+)', line)
if not tok: print("no github_pat token"); exit()
token = tok.group(1)
if '...' in token or len(token) < 40:
    print("TRUNCATED/placeholder token — get a fresh one")
req = urllib.request.Request("https://api.github.com/user",
    headers={"Authorization": f"Bearer {token}"})
# 200 → authenticates; then test POST /user/repos for create capability
```
