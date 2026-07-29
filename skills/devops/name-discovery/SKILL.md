---
name: name-discovery
description: "Use when checking if a software/tool name is available for use — searches GitHub, web, and registries for conflicts, evaluates severity, and generates alternatives."
version: 1.0.0
author: Hermes Cortex
license: MIT
metadata:
  hermes:
    tags: [naming, brand, discovery, research, naming-conventions]
    related_skills: [spike]
---

# Name Discovery

Systematically check if a software name is available for a new project, CLI tool, or brand — and find alternatives if it's not.

## When to Use

- User asks "check if [name] is available"
- User asks "find a good name for [project/tool]"  
- You need to name a new component, repo, or tool and want to avoid namespace collisions
- A proposed name has obvious conflicts and you need to generate alternatives

**Don't use for:** internal variable/function naming, repo slug naming for private repos, or codenames that will never be public-facing.

## Methodology

### Phase 1: Check the primary name

Run these checks **in parallel** (batch independent searches):

1. **GitHub search** — `web_search(query="<name> github")`
   - Look for: orgs (`github.com/<name>`), major repos (`github.com/X/<name>`), topics
   - Assess stars, activity, and recency

2. **Web search** — `web_search(query="<name> software tool OR CLI OR framework")`
   - Look for: actual projects, products, or companies using the name
   - Ignore: dictionary-word uses unrelated to software (e.g. "motif" in biology, "ballast" in shipping)

3. **Package registries** — `web_search(query="<name> pypi")`, `web_search(query="<name> npm")`
   - Check if the name is published on PyPI, npm, or other relevant registries

4. **Domain check (if relevant)** — `web_search(query="<name>.ai OR <name>.dev OR <name>.io")`
   - For public-facing tools, domain availability matters

### Phase 2: Evaluate conflict severity

| Severity | Criteria | Verdict |
|----------|----------|---------|
| **Major** | Same space (AI agent infra, orchestration, developer tools) + active project | ❌ Unusable |
| **Moderate** | Different space but well-known name (e.g. Hyundai Sonata) or adjacent space | ⚠️ High confusion risk |
| **Minor** | Different space, obscure/small project, or antiquated (e.g. 90s Unix toolkit) | ⚡ Usable with caveat |
| **Clean** | No significant conflicts found in any registry | ✅ Fully available |

### Phase 3: Generate alternatives (when primary is taken)

When the primary name fails, generate alternatives anchored to the **concept space**:

1. Identify the core concept: what does the tool *do*? (orchestrate, know, guide, connect, stabilize)
2. Generate 5-10 candidates from these angles:
   - **Root language** — Latin/Greek roots of the concept (nexum, cantus, sensus, ballast)
   - **Metaphor** — analogous real-world objects (lighthouse, keystone, anchor, compass)
   - **Composite** — blend two concept words (cortex+text = cortext, source+sorcerer = sorcer)
   - **Musical** — if the concept has rhythmic/timing elements (motif, cadence, etude, fugue)
   - **Shortened** — truncate/extend the original (cortex → cortx, orchestrator → orchex)
3. Run Phase 1 on each candidate
4. Present top candidates ranked by availability + conceptual fit

### Phase 4: Deliver the recommendation

Format the output as a ranked table:

| Name | Availability | Fit | Notes |
|------|-------------|-----|-------|
| ✅ **ballast** | Clean | Strong (stability) | Best option — no conflicts |
| ⚠️ **motif** | Minor conflict | Strong (pattern) | Old Unix GUI toolkit, different space |
| ❌ **cortx** | Major conflict | Strong | Seagate + AI assistant at cortx.me |

Include your top pick with reasoning.

## Common Pitfalls

1. **Confusing "exists" with "conflict."** A biology paper called "Motif" is not a software conflict. A 3.3k-star GitHub project in your exact space (agent orchestration) is. Always assess *what space* the existing project is in.

2. **Stopping after one search.** A name may be clean on GitHub but taken on PyPI, or vice versa. Check multiple registries.

3. **Overlooking adjacent spaces.** "cortx" conflicts aren't just Seagate's object store — there's also a self-hosted AI assistant at cortx.me doing something eerily similar. Check the user's actual niche.

4. **Generating weak alternatives.** "Just add a suffix" (cortx-cli, cortx-tool) doesn't solve the problem — the base name still collides. Generate conceptually distinct options.

5. **Missing the obvious domain check.** If the `.ai` or `.dev` domain is parked by a squatter or used by a different project, flag it.

6. **Recommending a name without conceptual fit.** A clean name is worthless if it doesn't evoke what the tool does. Assess fit alongside availability.

7. **Spending too many rounds.** If the first 3-4 candidates all fail, you're in a crowded naming space. Present the best of what you found and recommend the user pick rather than searching 20 more.
