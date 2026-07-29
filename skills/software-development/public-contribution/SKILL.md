---
name: public-contribution
description: "After any improvement, bug fix, workflow discovery, or lesson — pause and evaluate whether the insight is public-worthy for the Hermes Cortex OSS community. If yes, genericize and contribute."
version: 1.0.0
author: Hermes Cortex
license: MIT
metadata:
  hermes:
    tags: [meta, oss, contribution, community, sharing]
    related_skills: [save-lesson, hermes-agent-skill-authoring, soul-authoring]
---

# Public Contribution — Sharing Every Improvement

## Philosophy

> *"We are sharers and helpers. All improvements we discover must be instantly usable by those using Hermes Cortex."*

Every bug fix, workflow refinement, config improvement, or discovered pattern is an asset — not just for you, but for everyone running Hermes Cortex. Before closing any improvement, pause and ask:

**"How can this be used to help those using Hermes Cortex?"**

If the answer is anything other than "it can't" (which is rare), the next question is:

**"What would it take to make this publishable?"**

## Decision Tree

```
Did an improvement, fix, or lesson just happen?
│
├── Is it PII-specific (server paths, domains, personal data)?
│   ├── YES → Can it be genericized?
│   │   ├── YES → Do the genericization → contribute
│   │   └── NO  → Keep private (lesson in brain/moses)
│   │
│   └── NO  → Is it already in the public repo?
│       ├── NO  → Is it a:
|       │   ├── Skill? → Copy to skills/ in public repo
│       │   ├── Config template? → Update deploy/nginx/*.conf or docs/
│       │   ├── Testament to how a problem was solved? → docs/ or README
│       │   ├── New concept? → Create skill + update manifest
│       │   └── Something else? → docs/ or ask
│       │
│       └── YES → Does the existing version need updating?
│           ├── YES → Patch the existing file
│           └── NO  → Done
│
└── Update SKILLS-MANIFEST.md if anything changed
```

## Genericization Patterns

When moving something from private → public, apply these transforms:

| Private | Public |
|---------|--------|
| `your-domain.com` | `$DOMAIN` or `your-domain.com` |
| `/Users/luke/...` | `/path/to/app` or `$HOME/...` |
| `com.hermes.timely` | `com.hermes.APPNAME` (generic pattern) |
| `luke` / `amy` | generic user names or `user` |
| Port `13003` | `EXTERNAL_PORT` |
| Specific dates | Omit or use relative dates |
| Private API keys/secrets | `$ENV_VAR` placeholders |

## Standard Scope Check

Before contributing, ask:

1. **Does this apply to at least 80% of Hermes Cortex users?**
   - If yes → contribute as-is or with minimal genericization
   - If no → Is it useful as an *example* or *template* for others to adapt?
     - Yes → contribute with clear "adapt this to your setup" notes
     - No → keep private

2. **Would a new Hermes user benefit from knowing this?**
   - Yes → contribute
   - No → reconsider whether it belongs in docs vs a skill

3. **Is this a one-off fix or a repeatable pattern?**
   - One-off → lessons index only (brain/moses)
   - Repeatable pattern → skill + public repo

## Inventory of Contribution Targets

| Target Location | What Goes There | When |
|----------------|----------------|------|
| `skills/software-development/` | Reusable workflows, meta-skills | After any repeatable insight |
| `skills/devops/` | Deployment, infrastructure, nginx | After config/system improvement |
| `deploy/nginx/hermes-services.conf` | Reverse proxy templates | After nginx config evolution |
| `docs/templates/SOUL.md` | Agent identity template | After SOUL.md improvement |
| `docs/templates/SKILL.md` | Skill format template | After skill format evolves |
| `docs/templates/USER.seed.md` | User profile template | After user profile pattern change |
| `SKILLS-MANIFEST.md` | Skill registry | After skill add/update/merge |
| `README.md` | Project docs | After major capability addition |

## Workflow

### Step 1: Recognize the opportunity

After any of these events, pause and run through the decision tree:
- Bug fix
- User correction
- Installation or deployment
- Workflow discovery
- Config improvement
- Lesson captured in `~/brain/moses/lessons/`

### Step 2: Evaluate scope

Run through the **Standard Scope Check** (above).

### Step 3: Genericize

For each file being contributed, apply the **Genericization Patterns** table.

### Step 4: Write to public repo

```bash
# For a new skill:
# Write to hermes-cortex/skills/<category>/<skill-name>/SKILL.md

# For an existing file:
# Patch or replace the file in hermes-cortex/

# For a new template:
# Write to hermes-cortex/docs/templates/
```

### Step 5: Update manifest

If you added or modified a skill, update `docs/SKILLS-MANIFEST.md`:
- Add the new row to the appropriate category table
- Keep alphabetical order within the table
- Include: Skill name, version, concise purpose, load instruction

### Step 6: Commit and push

```bash
cd "${CORTEX_REPO:-$HOME/hermes-cortex}" && git add -A && git commit -m "feat: contribution description"
git push
```

## PITFALLS

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Leaving PII in public files | Domain names, user paths exposed | Run the genericization transforms before committing |
| Forgetting the manifest | Skill exists but isn't discoverable | Always update SKILLS-MANIFEST.md |
| Contributing too narrowly | Skill only solves one user's specific problem | Name and scope at the workflow level |
| Skipping the "would this help others?" pause | Improvement stays private forever | Make the pause a habit — it's in your SOUL.md now |
| Over-engineering for "public" | Adding features nobody asked for | Contribute the fix as-is with generic paths, no gold-plating |

## Verification Checklist

- [ ] Decision tree run — this *is* public-worthy
- [ ] Genericization applied — no PII, paths, domains, secrets
- [ ] Written to correct location in hermes-cortex/
- [ ] SKILLS-MANIFEST.md updated if applicable
- [ ] `git status` clean before push
- [ ] Lesson also noted in `~/brain/moses/lessons/` (private, for your own reference)
