# UX Gap Analysis Methodology (hc-elicit / hc-party)

A structured 5-phase methodology for auditing existing web applications to identify UX gaps, user workflow issues, data placement problems, and ease-of-use improvements. Designed for complex enterprise apps (ACME royalty systems) with 20+ pages and 25+ API routers.

**Trigger:** User says "hc-elicit and hc-party", "UX gap analysis", "UX audit", "review the UI", "review the UX", "are there missing pages", "make the workflow efficient".

## Phase 1: Page & Route Inventory

First, discover the full surface area of the app — both frontend pages and backend API routes.

### Frontend pages
```bash
find apps/web/src/app -name "page.tsx" | sort
```

This reveals every route. Group them by sidebar section (from NavBar.tsx) to see which pages are linked vs orphaned.

### API routers
```bash
find apps/api/routers -name "*.py" | sort
```

Cross-reference against frontend pages to detect:
- **Unused API routes** (no frontend page consumes them) — these may be unfinished features
- **Missing API routes** (page exists but no backend endpoint) — these may be purely frontend stubs

### Navigation structure
Read `NavBar.tsx` (or equivalent) to understand the sidebar sections, link keys, and icon paths:
- Every `sections[]` entry maps to a navigation group
- Every `{ href, key, icon }` maps to a link
- `iconPaths` reveals all supported icons (SVG path data)
- Check `messages/en.json` `"Nav"` section for label keys

### Key questions:
- Are there pages NOT in the nav bar? → These are orphan pages
- Are there nav entries for pages that don't exist? → Dead links
- Are section groupings intuitive? → Data vs Finance vs Operations vs Admin

## Phase 2: User Flow Mapping

Trace the journey a user takes through the app. For each role (creator, staff ops, admin), map the expected page sequence.

### For each page:
1. **Entry points**: How does a user get here? (nav bar, link from another page, direct URL, redirect after action)
2. **Exit points**: Where can a user go from here? (back links, breadcrumbs, action buttons, tab switches)
3. **Breadcrumbs**: Does the page have them? If not, it's an orphan.

### Common gaps to flag:
- **Orphan pages**: Pages reachable only by direct URL or fragile single back-link
- **Missing cross-page links**: E.g., ingestion→works, distribution→reconciliation, dashboard→payments
- **Broken navigation**: "Back to Dashboard" that navigates away from where the user came from
- **No breadcrumbs**: Sub-pages need a breadcrumb trail showing the full path from root
- **Dead-end flows**: User completes an action and lands on a page with no next step

### Tools:
- Use `Breadcrumbs` component (`components/Breadcrumbs.tsx`) with `crumbs={[{label, href?}]}` array
- Add breadcrumbs to every sub-page: `dashboard/*`, `works/[id]`, `identity/*`, etc.

## Phase 3: Data Placement Audit

Evaluate whether the right data lives in the right place.

### For each page:
1. **What data does it display?** (Read the page component and the API response type)
2. **Where does the data come from?** (Which API router serves it?)
3. **Should it be somewhere else?** (A staff page showing creator-only data, or vice versa)

### Common problems:
- **Data trapped in wrong page**: Admin data only accessible from a creator-facing page with no staff equivalent
- **Missing drill-down**: Summary numbers on homepage but no way to see the individual items
- **No link to related data**: E.g., work detail page doesn't show distribution amounts, ingestion job doesn't link to imported works
- **Cross-system data missing**: Epic 6.5 identity verification API exists but no frontend page for it

### Fix pattern:
- Add nav links for pages that exist but are hidden
- Add cross-reference links between related pages (ingestion→works, distribution→reconciliation)
- Build frontend pages for orphaned APIs

## Phase 4: Ease-of-Use Assessment

Evaluate tooltips, empty states, loading patterns, error handling, terminology consistency, and terminology.

### Tooltip audit
For each page, scan for complex concepts that need explanation:

| Concept | Tooltip Content |
|---------|----------------|
| ISWC | International Standard Musical Work Code — unique identifier for musical works |
| ACK status | CWR Acknowledgement — partner PRO confirms receipt of work registration |
| Status lifecycles | "Calculated → Reviewed → Approved → Confirmed → Settled" each step needs a brief explanation |
| Approval tiers | Auto (under threshold) / Single (1 approver) / Dual (2 approvers required) |
| Variance types | Bank fees, timing differences, unexplained — what each means for reconciliation |
| Accrued vs Paid | Accrued = calculated but not yet disbursed; Paid = settled in your account |

Use existing tooltip component pattern (e.g., `DeductionHelpTooltip`) for consistency.

### Empty state audit
Every list/data page must handle 4 states:
1. **Loading** — skeleton or spinner
2. **Error** — red banner with retry button
3. **Empty** — friendly message + call-to-action (CTA)
4. **Data** — the normal view

For empty states, include:
- A clear message explaining *why* it's empty
- A CTA linking to the relevant action page ("Register your first work", "Upload usage data", etc.)
- An icon or illustration (optional but helpful)
- Use the `EmptyState` component from `components/EmptyState.tsx` (see `engineering-approach/references/empty-state-component-pattern.md`)

### Tooltip component
- Use the `InfoTooltip` component from `components/InfoTooltip.tsx` for complex field tooltips (see `engineering-approach/references/info-tooltip-component-pattern.md`)

### Admin override UIs
For admin review/override pages (identity verification, corrections, approvals):
- Fetch pending items with `useQuery` and auto-refetch interval
- Display each item in a card with status badge, user info, and failure reason
- Inline override form with dual-approval fields (Approver 1 + Approver 2)
- Cancel button to collapse the form
- Inline success/error feedback (never `alert()`)
- See `admin/identity/page.tsx` in acme-royalty for a complete example

### Loading/Error pattern audit
Inconsistent patterns across pages degrade UX. Audit:
- Does every page use `useQuery` (React Query) or `useEffect` + `setState`? Mixing is confusing.
- Skeleton loaders vs text "Loading..." — skeletons are better
- `alert()` vs inline error banners — never use `alert()`
- Retry buttons on error states

### Status terminology audit
Status values should be:
- **Consistent** across pages (same status word → same meaning)
- **Shared** from a single source (not defined inline per-page)
- **Colored** consistently (green=success, yellow=in-progress, red=error/failed, gray=inactive)

**Fix pattern:** Extract all status label maps into `lib/status-labels.ts`:
```typescript
export const STATUS_COLORS = { completed: 'bg-green...', failed: 'bg-red...', ... };
export const STATUS_LABELS = { calculated: 'Calculated', reviewed: 'Under Review', ... };
```

## Phase 5: Report & Prioritization

Structure the findings in a unified report with priority tiers.

### Priority tiers

| Tier | Criteria | Expected Effort |
|------|----------|-----------------|
| **P0** | Navigation/UX blocker — a page is unreachable, or a critical action has no UI | <1hr each |
| **P1** | Significant UX gap — missing tooltips, empty states, cross-page links degrade daily use | 1-4hr each |
| **P2** | Polish — terminology inconsistency, loading patterns, missing features | 2-8hr each |

### Report template
```
# UX Gap Analysis: {app name}

## 1. Page Inventory & Navigation Map

{Table of all pages, organized by sidebar section, with current status}

## 2. User Workflow Gaps

{Items with P0/P1/P2 labels}

## 3. Data Placement Audit

{Items with P0/P1/P2 labels}

## 4. Ease-of-Use Findings

{Tooltips, empty states, loading patterns, terminology}

## 5. Prioritized Fix Plan

| # | Tier | Fix | Effort | Pages |
```

### Verification after fixes
After implementing any fix from this analysis:
```bash
npx vitest run --reporter=verbose   # frontend tests — must not regress
POSTGRES_PORT=13111 uv run pytest tests/...  # backend tests if API changes
```

## Example output

See `docs/reviews/ux-gap-analysis.md` in acme-royalty for a completed example (June 2026) covering 24 pages and 25 API routers with 17 findings across P0-P2.

### ACME Works variant: batch build after gap analysis

This session (June 2026) produced a variation: the gap analysis was immediately followed by batch-building all identified gaps and running E2E tests against the built pages. The process was:

1. Run hc-elicit + hc-party (page inventory → gap matrix → prioritized slices)
2. Create slice docs + update SLICES-INDEX
3. Build all P0 items in parallel via subagents
4. Run Next.js build to verify compilation
5. Build Docker image + restart stack
6. Run E2E tests against Docker stack
7. Fix any bugs found by tests (SelectItem value=\"\" React 19 crash, API path mismatches)
8. Iterate: fix tests → rebuild → re-run until clean
9. Mark slice complete and move to next slice

The key difference from the standard methodology: **build first, test second, fix third** — not analyze → document → hand off. The priority slices were built in the same session as the analysis.

See `docs/research/hc-elicit-ux-gap-analysis-2026-06-05.md` in acme-works for the actual output.

## See also

- `engineering-approach/references/frontend-code-review-methodology.md` — code-level review (focused on component quality, not UX)
- `engineering-approach/references/architecture-review-methodology.md` — architecture-level trade-off review (hc-party)
- `engineering-approach/references/breadcrumbs-component-pattern.md` — Breadcrumbs component usage
- `engineering-approach/references/info-tooltip-component-pattern.md` — InfoTooltip component for complex field explanations
- `engineering-approach/references/empty-state-component-pattern.md` — EmptyState component for pages with no data
