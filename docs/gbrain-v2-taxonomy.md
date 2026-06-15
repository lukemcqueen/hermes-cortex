# gbrain-base-v2 — Canonical Taxonomy

Since v0.41.22, new gbrain brains default to **gbrain-base-v2**, a 15-type
DRY/MECE taxonomy that replaces the original 24-type gbrain-base layout.

## The 15 canonical types

| # | Type | Purpose |
|---|------|---------|
| 1 | `person` | Individuals — contacts, collaborators, historical figures |
| 2 | `company` | Organizations, startups, enterprises, institutions |
| 3 | `media` | Articles, videos, podcasts, publications |
| 4 | `tweet` | Individual posts from X/Twitter |
| 5 | `social-digest` | Multi-post social media roundups |
| 6 | `analysis` | Analytical writing — research notes, deep dives |
| 7 | `atom` | Atomic notes — single facts, ideas, quotes |
| 8 | `concept` | Abstract ideas, frameworks, mental models |
| 9 | `source` | Provenance records — where information came from |
| 10 | `deal` | Business deals, investments, transactions |
| 11 | `email` | Email messages |
| 12 | `slack` | Slack/chat messages |
| 13 | `writing` | Drafts, essays, long-form output |
| 14 | `project` | Project tracking, milestones, status |
| 15 | `note` | Catch-all for anything that doesn't fit above |

Subtypes, format, and origin metadata should be pushed to
**frontmatter fields** rather than encoded in the page type.

## Why it matters

- **Fewer types** (24 → 15) means less fragmentation
- **Frontmatter-driven** — subtypes in YAML, not in the type system
- **Aligns with downstream tooling** — all new gbrain features target this taxonomy
- **New brains default to it** since v0.41.22 — existing brains can upgrade

## Upgrading an existing brain from gbrain-base

```bash
cd ~/gbrain
gbrain onboard --check --explain
gbrain jobs submit unify-types --allow-protected \
  --params '{"target_pack":"gbrain-base-v2"}'
gbrain jobs work --concurrency 1
```

This collapses the old 24-type system into the 15 canonical types,
preserving original types in `frontmatter.legacy_type`. Reversible
for 72h via soft-delete TTL.

## Verifying

```bash
gbrain doctor | grep "Active pack"
# Expected: gbrain-base-v2@1.0.0+...
```