# Sidebar Navigation Architecture (acme-royalty)

The app uses a vertical sidebar instead of a horizontal nav bar. Layout is flex row:

```
<div class="flex min-h-screen">
  <NavBar />    {/* fixed w-60 sidebar */}
  <main />      {/* flex-1 content area */}
</div>
```

## Component Structure

| File | Role |
|---|---|
| `app/[locale]/NavBar.tsx` | Sidebar component (the name `NavBar` is kept for import compatibility) |
| `app/[locale]/layout.tsx` | Flex layout wrapper |
| `app/[locale]/__tests__/NavBar.test.tsx` | Tests |

## Responsive Behavior

| Breakpoint | Sidebar State |
|---|---|
| `md+` (≥768px) | Fixed left sidebar, w-60 (240px), sticky top, border-right. In document flow via flex. |
| `<md` (<768px) | Hidden by default. Hamburger button in top bar toggles slide-in overlay. Backdrop click closes. |

## Categorized Sections

Links are grouped into 4 sections defined as a data structure in the component:

```typescript
const sections = [
  { labelKey: 'sectionData', links: [
    { href: '/works', key: 'works' },
    { href: '/conflicts', key: 'conflicts' },
    { href: '/cross-references', key: 'crossRefs' },
  ]},
  { labelKey: 'sectionFinance', links: [
    { href: '/dashboard', key: 'dashboard' },
    { href: '/dashboard/breakdown', key: 'breakdown', sub: 'breakdown' },
    { href: '/forecast', key: 'forecast' },
  ]},
  { labelKey: 'sectionOps', links: [
    { href: '/ingestion', key: 'ingestion' },
    { href: '/validation-queue', key: 'validation' },
    { href: '/reconciliation', key: 'reconciliation' },
    { href: '/societies', key: 'societies' },
    { href: '/treaty-rates', key: 'treatyRates' },
    { href: '/distributions', key: 'distributions' },
  ]},
  { labelKey: 'sectionAdmin', links: [
    { href: '/admin/users', key: 'users' },
    { href: '/audit-log', key: 'auditLog' },
    { href: '/migration-audit', key: 'migrationAudit' },
  ]},
];
```

### i18n Keys (Nav namespace)

| Key | EN | KO |
|---|---|---|
| `sectionData` | Data | 데이터 |
| `sectionFinance` | Finance | 재무 |
| `sectionOps` | Operations | 운영 |
| `sectionAdmin` | Admin | 관리 |
| `distributions` | Distributions | 분배 |
| `migrationAudit` | Migration Audit | 마이그레이션 감사 |

## Active Link Detection

Uses path segments from `usePathname()`:

```typescript
const pathname = usePathname();
const segments = pathname.split('/').filter(Boolean);
const locale = segments[0] || 'en';
const base = segments[1] || '';

function isActive(href: string, segments: string[], base: string): boolean {
  if (href === '/dashboard/breakdown') return segments[2] === 'breakdown';
  if (href === '/admin/users') return base === 'admin';
  return base === href.split('/')[1];
}
```

## Adding a New Link

1. Add the link to the appropriate `sections` array in `NavBar.tsx`
2. Add i18n key in `messages/en.json` and `messages/ko.json` under the `Nav` namespace
3. Active detection is automatic via `isActive()` as long as `href` is the route's first path segment

## Login Page

When on the login page (`base === 'login'`), the sidebar is replaced with a minimal bar:

```tsx
if (isLoginPage) {
  return (
    <div className="flex items-center justify-end border-b border-gray-200 bg-white px-4 py-3">
      <LocaleSwitcher />
    </div>
  );
}
```

## Collapsible Mode (Icon Rail)

The sidebar has a toggle button at the bottom (hidden on mobile) that collapses it to a 64px (w-16) icon rail:

**Expanded (w-60):**
```
┌──────────────────────┐
│ ACME               │
│                      │
│ DATA                 │
│   Works              │
│   Conflicts          │
│   ...                │
│                      │
│  ──────────          │
│  [Locale]            │
│  Alice  [Logout]     │
│  ◀ collapse          │  ← toggle button
└──────────────────────┘
```

**Collapsed (w-16):**
```
┌──────┐
│ K    │
│      │
│  📄  │  ← icons only
│  ⚠   │
│  🔗  │
│      │
│      │
│  ◀   │  ← rotated chevron
└──────┘
```

### Implementation

```typescript
const [collapsed, setCollapsed] = useState(() => {
  // Persisted to localStorage so state survives page reloads
  if (typeof window !== 'undefined') {
    return localStorage.getItem('acme_sidebar_collapsed') === 'true';
  }
  return false;
});

const toggleCollapse = () => {
  setCollapsed(prev => {
    const next = !prev;
    localStorage.setItem('acme_sidebar_collapsed', String(next));
    return next;
  });
};

// Sidebar width varies by state:
`${collapsed ? 'w-16' : 'w-60'}`
```

When collapsed:
- Brand shows "K" instead of "ACME"
- Section headers (`<p>`) are hidden
- Link text is hidden; only the `<LinkIcon>` SVG renders
- Each link gets `title={t(link.key)}` for hover tooltip
- Collapse chevron rotates 180° (visually expands inward)
- Login/logout buttons become icon-only (door arrow SVG icons)
- LocaleSwitcher hidden

### Icon System

Each nav link defines an `icon` key matching the relevant SVG path in a static `iconPaths` map:

```typescript
const iconPaths: Record<string, string> = {
  works: 'M4 4h16v2H4zm0 5h14v2H4zm0 5h10v2H4z',
  conflicts: 'M12 2L2 18h20zM12 8v4m0 2v1',
  // ... one SVG path per nav item
};

function LinkIcon({ name, className }: { name: string; className?: string }) {
  const path = iconPaths[name];
  if (!path) return null;
  return (
    <svg className={className || 'h-5 w-5 shrink-0'} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth={2}
      strokeLinecap="round" strokeLinejoin="round">
      <path d={path} />
    </svg>
  );
}
```

Each section link object now includes `icon`:

```typescript
{ href: '/works', key: 'works', icon: 'works' },
```

The toggle button sits at the very bottom of the footer:

```tsx
<button onClick={toggleCollapse}
  className="hidden md:flex items-center justify-center rounded-md p-1.5
    text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors mx-auto"
  title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
  <svg className={`h-4 w-4 transition-transform duration-200
    ${collapsed ? 'rotate-180' : ''}`} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={2}>
    <path d="M15 18l-6-6 6-6" />
  </svg>
</button>
```

### Collapsing Behaviour Rules

| Aspect | Expanded (w-60) | Collapsed (w-16) |
|---|---|---|
| Brand text | "ACME" | "K" |
| Section headers | Visible | Hidden |
| Link labels | Show text + icon | Icon only |
| Link hover tooltip | Not needed | `title={t(link.key)}` |
| Locale switcher | Shown | Hidden |
| Login/Logout text | Full label (`t('login')`) | Icon-only (door arrow) |
| Toggle chevron | Points left (◀) | Points right (▶) |
| Mobile (<md) | Always full overlay | N/A — collapsed only on desktop |

### Test Adaptation

The brand test must account for both "ACME" (expanded) and "K" (collapsed) being present:

```typescript
it('renders the ACME brand link', () => {
  render(<NavBar />);
  const brands = screen.getAllByText('ACME');
  expect(brands.length).toBeGreaterThanOrEqual(1);
  expect(brands[0]?.getAttribute('href')).toBe('/ko');
});
```

Active link styling changed from `text-blue-600 border-b-blue-600` (horizontal nav) to `bg-blue-50 font-medium text-blue-700` (sidebar):

```typescript
expect(worksLink.className).toContain('text-blue-700');
expect(worksLink.className).toContain('font-semibold'); // or font-medium
```

## Auth Integration

The sidebar footer shows:
- **Authenticated**: user name + Logout button
- **Unauthenticated**: full-width Login link (calls `useAuth()`)

The Login link is only in the sidebar footer — it is NOT a nav link in any section.

## Test Mocks

### NavBar tests

```tsx
vi.mock('../../../components/AuthProvider', () => ({
  useAuth: () => ({
    user: null,
    loading: false,
    logout: vi.fn(),
    login: vi.fn(),
    getAccessToken: () => null,
    isAuthenticated: false,
  }),
}));
```

### Layout tests

```tsx
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock('../NavBar', () => ({
  default: () => <nav data-testid="navbar">NavBar</nav>,
}));
```
