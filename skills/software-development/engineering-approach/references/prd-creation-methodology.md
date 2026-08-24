# PRD Creation Methodology (hc-elicit pattern)

Structured product requirements document creation for complex features. Maps to the hc-elicit phase of AgentKore's `/plan` command.

## When to Use

- New product, website, or major feature requiring formal stakeholder alignment
- Parallel agent execution needs clearly bounded work packages
- External dependencies (APIs, services) need documented contracts
- Competitive/regulatory landscape needs analysis

**Not for**: simple tasks, small UI changes, bug fixes, internal refactors. Use fast-bmad (concise task list) instead.

### Domain-Specific Research

Before creating a PRD in the copyright society / PRO domain, consult `references/pro-metadata-systems-research-methodology.md` for:

- PRO catalog system architecture benchmarking (what to measure, where to look)
- Korean cross-lingual matching challenges (romanization variance, Konglish, encoding issues, ISRC collisions, artist disambiguation)
- Research-to-PRD pipeline (how to feed research into PRD patches and architecture review)
- Cautionary tales with specific PRO examples (PRS 40% ISRC error, GEMA migration corruption)

## Process

### Step 1: Investigate & Research

- **Review existing system** — codebase, database schema, live site, API contracts
- **Competitive benchmarking** — identify 6–12 comparable products/services. Extract feature matrix. Key dimensions: public search, member portal, document library, licensing, i18n, APIs, accessibility
- **Stakeholder context** — read READMEs, config files, and any existing docs in `docs/` tree

### Step 2: Define Scope

- **Personas** — 4–6 archetypal users. Each: name, role, goal, tech level
- **User stories** — 8–12 key stories covering all personas (for projects with 50+ FRs, organize stories per domain in separate files at `docs/prd/stories/{domain}.md` instead)
- **Goals & constraints** — business goals, tech constraints, regulatory requirements

### Step 3: Feature Inventory (the core)

Each feature gets a unique ID, MoSCoW priority, dependencies, and description:

| ID Pattern | Domain | Example |
|------------|--------|---------|
| FR-HOME-01 | Homepage | Hero section with animated background |
| FR-SRCH-01 | Search | Quick search bar with typeahead |
| FR-DOC-01 | Documents | Document library list |
| FR-NAV-01 | Navigation | Responsive sticky nav bar |
| FR-AUTH-01 | Authentication | Login page |
| FR-ADM-01 | Admin | Document CRUD |
| FR-SYS-01 | System | Health check endpoint |

MoSCoW rules:
- **M** — Must Have (MVP: the product doesn't work without it)
- **S** — Should Have (v1.1: important but not blocking launch)
- **C** — Could Have (v1.2+: nice to have, low effort first)
- **W** — Won't Have (v2: needs separate planning)

### Step 4: Non-Functional Requirements

Parallel to step 3, cover:

| Category | Typical Sections |
|----------|-----------------|
| Performance | TTFB, LCP, bundle size, API p95 response time |
| Security | CSP, HSTS, rate limiting, DDoS, headers, input validation |
| Reliability | Uptime SLA, error rate, RTO/RPO, graceful degradation |
| Scalability | Concurrent users, throughput targets, data volume |
| Maintainability | Monorepo structure, TypeScript strict, test coverage, CI/CD |
| SEO | Structured data, sitemap, semantic HTML, OG tags |
| Legal/Regulatory | GDPR, local privacy laws, WCAG accessibility, ToS |

### Step 5: Architecture & System Design

- **Architecture diagram** — ASCII or SVG showing all services, direction of data flow
- **Tech stack table** — framework, language, ORM, caching, auth, deployment per layer
- **Directory structure** — full tree for the project showing where every file lives
- **Integration architecture** — per external service: endpoints, auth method, caching strategy
- **Data contracts** — schema definitions (SQL or Drizzle/Prisma format)

## Implementation Phases

Organise into phases with parallel tracks where possible.

Each phase is a set of parallel tracks. Each track is a self-contained task document that can be handed to a subagent.

### Parallel Track Document Format

After the PRD is finalized, decompose each phase into **parallel track documents** — one markdown file per track at `docs/tasks/TRACK-<letter>-<slug>.md`. Each track must be self-contained so a subagent can execute it independently with no context beyond the file:

```
docs/tasks/
├── TRACK-A-search-page.md              # Full search experience
├── TRACK-B-documents-public-page.md    # Document library
├── TRACK-C1-documents-api.md           # Server queries + endpoints
├── TRACK-C2-admin-infrastructure.md    # Login, layout, auth
├── TRACK-C3-document-admin-crud.md     # Admin document CRUD
└── TRACK-D-about-news-contact.md       # Content pages
```

Each track document must include:

| Section | Content |
|---------|---------|
| **FR References** | The FR-IDs this track implements (from PRD §Feature Requirements) |
| **Files to create/modify** | Exact file paths relative to project root |
| **Acceptance criteria** | Checkbox list (12–35 items) ordered by priority |
| **Data flow** | How data moves between components, API, and database |
| **UI guidance** | Colors, layout references, component hierarchy |
| **Edge cases** | 8–12 documented edge cases per track |
| **Dependencies** | What other tracks this waits on (exact: "Track C1 must be completed first" vs "parallel safe — can start with mock data") |
| **Verification commands** | Exact shell commands to run for verification |

### Dependencies & Ordering

Map dependencies explicitly so subagents can be dispatched in batches:

```
Phase 1 Start
├── Track A  ───────────────┐  (no deps → batch 1)
├── Track D  ───────────────┤
├── Track C1 │──────────────┘
├── Track C2 ───────────────┘  (no deps → batch 1 or 2)
├── Track B ── wait for C1     (batch 2, or parallel-safe if mock data used)
└── Track C3 ── wait for C1+C2 (batch 3 only)
```

Batches:
- **Batch 1** — launch all no-dep tracks together via `delegate_task(tasks=[...])`
- **Batch 2** — launch tracks that need C1 foundation but can stub
- **Batch 3** — launch tracks needing both C1 and C2

### Estimation

Each task references the FR-ID it implements. Estimate effort in hours per track (e.g., "6–8h") and provide it in the document title or header.

### Step 7: Open Questions & Trade-offs

Document unresolved decisions with:
- Question number, exact question, who needs to decide, impact
- Design trade-offs table: Option A vs Option B vs Chosen (with rationale)

### Step 8: References

Feature comparison matrix vs competitors. Links to codebase READMEs, key source files, related skills.

## FR ID Format Rules

```
{FR|NFR}-{DOMAIN}-{NN}
```

- Domain is 2–4 uppercase letters (HOME, SRCH, DOC, NAV, LIC, ABT, NEWS, CONT, AUTH, ADM, SYS, PERF, SEC, REL, SCAL, MNT, SEO, LEG)
- Number is zero-padded to 2 digits
- Dependencies reference other FR-IDs

## Pitfalls

- **Over-engineering**: 150+ FRs is fine for a large project. For a simple page, cap at 20. Know when to stop.
- **Competitive research rabbit hole**: limit to 10–12 competitors. More is diminishing returns.
- **Scope creep in phases**: if a Phase 1 track has more than 6 tasks, split the track.
- **Missing data contracts**: every external API endpoint must have method, URL, params, response shape, and auth. If unknown, flag as "TBD — check source code" in the FR.
- **FR/NFR orphaned references**: every FR referenced in phases must exist in the feature inventory. Remove orphans.
- **Overly aggressive rate limits**: 100 req/min general limit breaks on 4 page loads with assets. Distinguish asset vs API limits.
- **Missing graceful degradation**: every external dependency should have a "when X is down" fallback defined.

## Template Structure

```
docs/prd/<project>-<version>-prd.md
```

Sections in order:
1. Executive Summary
2. Strategic Context
3. Personas & User Stories
4. Feature Requirements (FR table)
5. Non-Functional Requirements (NFR table)
6. Architecture & System Design
7. Data Model & API Integration
8. Security & Compliance
9. Localization & i18n Strategy
10. Visual Design Guidelines
11. Implementation Phases
12. Architecture Decisions (or Open Questions & Trade-offs)
13. References & Benchmarking
14. Appendices (Glossary, Go-Live Checklist)

## Updating an Existing PRD (Major Revision)

When a major architecture decision changes the PRD (e.g. new backend framework, CI/CD platform, monitoring service, integration targets), use this systematic update pattern:

1. **Identify all relevant sections** — read the full PRD once to understand what's affected
2. **Search for every occurrence** of the old term (`client`, `Sentry`, `GitHub Actions`, `Redis 7`, `PostgreSQL 16`, etc.)
3. **Fix broken diagrams** — after text replacements, verify ASCII architecture diagrams are still aligned
4. **Update metadata** — increment version number, add revision note
5. **Check cross-references** — ADRs, phases, glossary, launch checklist, and acceptance criteria all need the same treatment
6. **Verify ToC** — section headers may have changed

Common PRD update operations (example from acme-website v1.0 → v2.1):
- Architecture: Next.js-only → FastAPI + Next.js dual-app
- CI/CD: GitHub Actions → GitLab CI
- Monitoring: Sentry → Highlight.io
- Integration targets: acme-alpha (Rails) → acme-works (FastAPI)
- Stack versions: PG 16 → 18.3-trixie, Redis 7 → 8.6.3-alpine
- ORM: Drizzle-only → SQLAlchemy (backend) + Drizzle (frontend reads)

For each change, the levers are:
- **Feature tables**: update dependencies column (e.g. "client API" → "acme-works API")
- **NFR table**: update platform-specific entries (CI/CD, monitoring)
- **Architecture diagram**: redraw with new service names and connections
- **Directory structure**: add/remove service directories
- **API route table**: update route descriptions and endpoint URLs
- **Implementation phases**: add/remove tasks for new scaffolding, adjust estimates
- **ADRs**: add new ADRs for significant decisions, update existing ones
- **Glossary**: add new terms, update renamed ones
- **Launch checklist**: update verification items to match new architecture

## Related

- `references/architecture-review-methodology.md` — the hc-party review to run AFTER this PRD is drafted
