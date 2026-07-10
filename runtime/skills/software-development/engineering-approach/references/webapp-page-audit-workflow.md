# Webapp Page Audit & Batch Build Workflow

Audit all sidebar/navigation links against actual route files, then batch-build missing pages following existing patterns. Use when the user asks to "fill in all missing pages" or "verify all pages work" for a Next.js webapp.

## Workflow

```
1. Full UX flow audit (not just nav links)
2. Document findings as audit doc
3. Slice gaps as story file with task IDs
4. Check API endpoints for each missing page
5. Build pages in parallel batches via delegate_task
6. Add API client functions if needed
7. Add i18n keys (en + ko)
8. Update nav/sidebar if needed
9. Create missing UI components
10. Run build → fix errors → verify
```

## Step 1: Full UX Flow Audit (Not Just Nav Links)

A nav-link-only audit misses UX gaps in auth flow, learning loops, loading/empty/error states, and page continuity. Audit ALL of these:

**Auth flow:**
- Login/Signup: form fields, validation, error display, forgot password link → works
- Email verification: banner after signup, resend button
- Password reset: flow from forgot → email → reset → success page
- Route guard: unauthenticated pages redirect correctly (login → /auth/login?redirect=...)
- Auth layout: branding, centered card, no bottom nav bleeding through

**Core learning loop (study → read → review → missions):**
- Dashboard: loads data, shows stats, quick actions work
- Study: content listing with filters, pagination, empty state for no results
- Content detail: bridge between study list and reading view (missing = broken flow)
- Reading view: tokens tappable, popover shows, save to review works, timed reading
- Review: due queue, session flow (flip → grade → next), empty state
- Missions: daily mission display, completion, history page

**Every page must have:**
- Loading state (skeleton matching layout shape, not spinner alone)
- Empty state (illustration + message + CTA action)
- Error state (message + retry button)
- Dark mode support
- i18n for all user-facing text

**Settings & Admin:**
- Profile edit: display name, email, language
- Preferences: daily card limit, difficulty, modalities
- Sessions: active session list, revoke, logout-all
- Admin dashboard: stats cards, quick links
- Admin CRUD pages: content, users, lexicon

## Step 2: Document Findings

Create an audit document at `docs/design/ux-audit-findings.md` with:
- ✅ / ❌ / 🔴 per finding
- Section headers per flow (Auth, Dashboard, Study, etc.)
- Each missing page listed with its route
- Priority implicit (P0 = breaks user flow, P1 = nice-to-have)

## Step 3: Slice Gaps as Story File

Create `docs/prd/stories/ux.md` with task IDs (e.g., TX-UX-01 through TX-UX-08):
- Each task: Route, estimate, description, implementation notes
- Dependencies table
- Group by priority

## Step 4: Check API Endpoint Support

Before building a page, verify what API endpoints exist:

```bash
# Check backend router for the resource
grep -r "@router\." apps/api/app/routers/<resource>.py | head -20
```

If the API has CRUD endpoints (`GET list`, `GET /{id}`, `POST`, `PATCH`, `DELETE`), build a full list page with search + pagination. If no API exists, build a placeholder/coming-soon page with meaningful content.

### Page Building Patterns

**For API-backed list pages:**
- Follow existing pattern: Suspense wrapper → Content component → AppLayout → Search + filter bar → Table with loading skeleton → Pagination
- Use existing API hooks or client functions
- Table pattern: clickable rows, pagination with `from–to of total`

**For utility pages (e.g., Import):**
- Check the backend API spec first (file upload, list history, get detail)
- Add API client functions to the API module
- Build with drag-and-drop upload area, status display, and history table

**For placeholder pages:**
- Use the app's layout wrapper
- Include Card components for visual structure
- Add meaningful placeholder content
- Do NOT leave empty white pages

## Step 5: Build Pages in Parallel Batches via delegate_task

Once all API support is confirmed, build missing pages in parallel batches (3 tasks per batch max):

**Batch 1 (highest impact):**
- Content detail page `/content/[id]` — bridge between study list and reading
- Mission history `/missions/history`
- Settings preferences `/settings/preferences`

**Batch 2:**
- Admin dashboard `/admin`
- Admin users `/admin/users`
- Settings sessions `/settings/sessions`

**Batch 3 (small items):**
- Email verification banner (component, not page)
- Password reset success page `/auth/reset-password/success`

Each delegate_task provides:
- Exact file path to create
- API endpoint to call (from Step 4)
- Interface/type definition for the response
- Loading/empty/error state patterns
- i18n namespace to use
- Existing page to follow as pattern reference

**Pitfalls to prevent in subagent contexts:**
- "Do NOT use `t` as a map iterator — the i18n function is already named `t`"
- "Import from `@/lib/api-client` not `@/lib/api`"
- "Use `next/navigation` for `useParams`, not `@/i18n/routing`"
- "Include i18n keys in BOTH `en.json` and `ko.json`"
- "Every page needs skeleton loading, empty state, error state, and dark mode"

## Step 6: Add API Client Functions If Needed

If the backend has endpoints the frontend doesn't call yet:

```typescript
// In src/lib/api.ts
export function uploadSomeFile(file: File): Promise<ResultType> {
  const formData = new FormData();
  formData.append('file', file);
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return fetch(`${API_BASE}/some/path`, {
    method: 'POST',
    headers,
    body: formData,
  }).then(/* handle 401, error, json response */);
}
```

For file uploads, use plain `fetch()` (not `fetchJSON`) because `FormData` sets its own `Content-Type` with boundary. The 401 redirect logic must be replicated manually.

## Step 7: Add i18n Keys

Add new i18n sections in both `messages/en.json` and `messages/ko.json`:

```
members: { title, description, search_placeholder, no_members, fields: { name, name_ko, ... } }
publishers: { title, description, search_placeholder, no_publishers, fields: { name, name_ko, ... } }
works.import: { title, description }
```

Also add `nav.members` and `nav.publishers` to the existing `nav` section if sidebar links are needed.

**Watch out for duplicate keys in JSON files.** If you patch a section in (e.g. `works.import`) but the `works` key already exists earlier in the file, you'll create a duplicate key that makes the JSON invalid. Always verify the JSON structure after editing — use `jq .` or run the build to catch this.

## Step 8: Update Sidebar or Bottom Nav

In `sidebar.tsx` (or `NavBar.tsx`), add new nav items:

```typescript
import { ..., Users, Building2 } from 'lucide-react';

const navItems = [
  // ...existing items...
  { href: '/members', label: t('nav.members'), icon: Users },
  { href: '/publishers', label: t('nav.publishers'), icon: Building2 },
];
```

Ensure new icons are added to the `lucide-react` import statement.

## Step 9: Missing UI Components

If the build fails with "Module not found: Can't resolve '@/components/ui/card'" or similar shadcn/ui component:

1. Check what components exist: `ls apps/web/src/components/ui/`
2. Create the missing component following the shadcn/ui pattern (forwardRef, cn() utility, className spreading)
3. Use the other existing components as a template (same import pattern, same ref forwarding)

## Step 10: Build Verification

```bash
cd apps/web && npm run build 2>&1
```

Expected output: all pages listed in build summary with their sizes. 0 errors, 0 warnings.
Check that every new route appears in the build output.

### Common Build Failures

| Error | Cause | Fix |
|---|---|---|
| `Module not found: Can't resolve '@/components/ui/card'` | Card component doesn't exist | Create `card.tsx` following shadcn pattern |
| `SearchParams` requires Suspense boundary | `useSearchParams()` without parent `<Suspense>` | Wrap content component in `<Suspense>` |
| `Unused import` lint error | Imported but unused symbol | Remove unused import |
