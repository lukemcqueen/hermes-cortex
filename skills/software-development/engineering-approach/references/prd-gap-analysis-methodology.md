# PRD Gap Analysis Methodology

Systematic approach to compare Product Requirements Document (PRD) features against actual codebase implementation to derive a prioritized story backlog.

## When to Use

- A PRD v2+ defines new architecture that differs from the current implementation
- Migrating from monolith to multi-service architecture (e.g., Next.js-only → FastAPI + Next.js dual-app)
- After a PRD update that changes tech stack, services, or data flow

## Workflow

### Phase 1: Enumerate PRD Requirements

Read the PRD and extract:

**Feature requirements (FR):** Each `FR-XXX-N` entry — product features the frontend must deliver
**Non-functional requirements (NFR):** Each `NFR-XXX-N` entry — quality attributes and constraints
**Architecture decisions:** ADRs, data flow diagrams, service boundaries

Output: two lists — all FRs and all NFRs with their ID, title, and priority.

### Phase 2: Scan Actual Codebase

Walk the filesystem to inventory what exists today. Cover:

- **App structure:** `apps/*` and `packages/*` directories
- **Pages/Routes:** `app/[locale]/*/page.tsx` (frontend), `routers/*.py` (backend), `app/api/*/route.ts` (Next.js API routes)
- **Models/Schema:** ORM models (SQLAlchemy, Drizzle), migration files
- **Config/Infra:** `docker-compose.yml`, `.env`, CI config, `Dockerfile`s
- **Services/Lib:** API clients, utility functions, external integrations

For each item, note:
1. What it does
2. Where it lives
3. Which PRD requirement it maps to (if any)
4. Whether it matches the PRD architecture or contradicts it

### Phase 3: Map Existing → Requirements

Create a gap matrix:

```
| PRD ID | Requirement            | Exists? | Location              | Gap Type     |
|--------|------------------------|---------|-----------------------|--------------|
| FR-DOC | Document listing       | ✅      | apps/web/.../route.ts | Architecture  |
| FR-AUTH | Admin login            | ✅      | middleware.ts + cookie | Architecture  |
| FR-MEMB | Membership wizard      | ❌      | —                      | Missing       |
| NFR-CI  | GitLab CI              | ❌      | —                      | Infrastructure|
```

**Gap types:**
- **Architecture** — exists but in wrong service/layer (e.g., API route in Next.js that should be in FastAPI)
- **Infrastructure** — missing CI/CD, monitoring, connection pooling, Docker services
- **Content** — feature doesn't exist yet at all
- **Version/Stack** — wrong dependency version (e.g., Redis 7 → Redis 8.6.3)
- **Naming** — outdated names (e.g., `client-client.ts` should be `works-client.ts`)

### Phase 4: Categorize into Epics

Group gaps into coherent epics ordered by dependency chain. Standard epic structure for architecture migrations:

| Epic | Theme | Rationale |
|------|-------|-----------|
| 1 | Foundation | New backend service, models, Docker — everything depends on this |
| 2 | Port API Routes | Move existing endpoints to new backend |
| 3 | Frontend Refactor | Update frontend to call new backend |
| 4 | Auth + Search | Session management, API client renaming |
| 5 | Infrastructure | CI/CD, monitoring, connection pooling, tests |
| 6 | New Features | Content gaps: wizards, licensing, CMS features |

Ordering rule: Epics 1-2 must land before 3. Infra (5) can run parallel to 2-4. New features (6) are independent but depend on 1 for backend.

### Phase 5: Write Stories

For each gap, write one or more stories using `sprint-task-file-generation.md` format. Key pattern differences:

**Architecture gaps** (migration stories):
```
Given the existing {old_location}
When it is ported to {new_location}
Then it behaves identically to the existing endpoint
And {new_location specific requirement}
```

**Missing features** (new-feature stories):
```
Given {context}
When {user action}
Then {expected result}
```

## Pitfalls

- Don't rely only on PRD reading — scan actual files. PRDs can be aspirational; code doesn't lie.
- Architecture gaps are often invisible from the PRD alone — you need to read the existing code directory tree and trace data flows.
- Naming gaps (e.g., `client-client.ts` for `acme-works`) are easy to miss but cause confusion long-term.
- `docker-compose.yml` is the single source of truth for architecture — compare it against PRD's architecture diagram.
- Rate-limit middleware, auth middleware, error handlers — these cross-cutting concerns exist in the old stack and must be replicated in the new one. Don't assume "it works already."
