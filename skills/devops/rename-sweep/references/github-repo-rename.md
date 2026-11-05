# GitHub Repo Rename — Backward Compatibility

Renaming a public GitHub repo (and rewiring local references) is a distinct
sweep: the working tree, its origin remote, and every build/install artifact
that embeds the repo URL or its archive ARE the surface.

## Order

1. Make remote-URL GUARDS accept OLD + NEW (both), owner-agnostic, BEFORE the
   rename — one governance lock per repo but many deployed copies; a guard that
   accepts a single URL breaks the half of the fleet that has not changed yet.
2. Rename (see credential note), THEN land any reference pointing at the NEW
   name. A documented URL must never name a repo that does not exist yet.
3. Sweep references; set the local origin remote; verify the old URL still works.

## Credential: a push-capable fine-grained PAT often cannot rename

A token that PUSHES fine (git push rc=0) and READS the repo (admin data = 200)
can still get `403 Resource not accessible by personal access token` on the
rename PATCH. Renaming is a Repository-level Administration WRITE on a
fine-grained PAT, and it often stays ineffective even after the permission is
added. Reliable paths instead of fighting the scope:

- the operator renames in the GitHub UI (Settings → General → Danger Zone →
  Rename) — zero credential friction; the push token needs no admin at all; or
- a CLASSIC token with the `repo` scope (rename works).

Verify identity after: `GET /repos/<o>/<new>` returns the SAME `id` (same repo,
not a fresh one), and the old web/API URL is a 301 redirect.

## Guards: owner-agnostic match + reject the known-dead legacy org

Do not hardcode both owner URLs into a guard — that re-writes the handle and
breaks on the next rename. Match on `github.com` plus the repo-name SUFFIX
(`.../hermes-cortex.git` OR `.../steadfaste-fleet.git`), and reject the
known-dead legacy org explicitly (`/fleet-operator/` NOT in the URL). An
owner-agnostic match otherwise silently broadens acceptance to the dead org,
which the prior exact-URL guard used to reject; keeping the rejection preserves
its scope. (The guard here also happens to avoid writing a deny-listed handle.)

## Archive tarball member names follow the CURRENT repo name

GitHub names an archive root after the repo as it is NOW:
`.../<new>/archive/refs/heads/main.tar.gz` extracts to `<new>-main/` — not the
old name. Any `tar ... --strip-components=N '<old>-main/...'` or path-built
extraction breaks the moment the repo is renamed. Grep for the ARCHIVE MEMBER
name as well as the URL when sweeping. A close-review gate caught exactly this
(URL updated, tar member still `old-main/`, extraction pulled nothing).

## Old-URL verification battery — every surface, not just the webpage

- web + API: 301 redirect (or reachable through it)
- `git ls-remote https://github.com/<o>/<old>.git HEAD` → rc=0 (existing clones keep fetching)
- `raw.githubusercontent.com/<o>/<old>/...` → serves (old install one-liners)
- shields.io badge path → 200

## Writing repo-URL references into a PII-gated shared surface

The enforcer deny-lists the owner's surname but EXEMPTS it inside the repo's
own URL. The exemption requires the FULL `https://` scheme (or `git@github.com:`)
— a bare `github.com/<o>/<repo>` with no scheme is REFUSED. The exemption's
lookahead accepts only `/`, end-of-string, whitespace, or `,()).;` immediately
after the repo name — so a string ending in a closing quote
(`...repo.git"`) is REFUSED; give the line a trailing space, `/`, or a `)`.
Patch URL lines WHOLE with the scheme; a token patch starting at
`raw.githubusercontent.com` (no scheme) is refused.

Enforcement is cached in the process: editing the enforcer source does NOT
change a running gateway's gate (it compiled the regex at import), and the
running gate reads the DEPLOYED copy. Make the allowlist change, `cortex-update.sh`
to propagate it, then test a representative write — not before the deploy.

The close-review self-adversarial gate judges CLAIMS in comments too: a
docstring asserting a history the diff does not show is filed as FABRICATION.
Write only what the diff proves. Where an owner-agnostic match narrows or
broadens a guard's scope, say exactly that in the comment — the reviewer reads
the diff and will refute an invented "the old guard used to do X" that the
removed lines never did.
