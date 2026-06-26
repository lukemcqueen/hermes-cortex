# Breadcrumbs Component Pattern

A reusable `Breadcrumbs` component for Next.js App Router sub-pages that provides consistent hierarchical navigation.

## Component

Location: `components/Breadcrumbs.tsx`

```tsx
'use client';

import Link from 'next/link';
import { useLocale } from 'next-intl';

interface Crumb {
  label: string;
  href?: string;  // omit for current page (renders as plain text, no link)
}

interface BreadcrumbsProps {
  crumbs: Crumb[];
}
```

## Usage

```tsx
import Breadcrumbs from '../../../components/Breadcrumbs';

// Simple:
<Breadcrumbs crumbs={[
  { label: 'Dashboard', href: `/${locale}/dashboard` },
  { label: 'Breakdown' },
]} />

// Deep nesting:
<Breadcrumbs crumbs={[
  { label: 'Works', href: `/${locale}/works` },
  { label: work.title || work.work_code },
]} />
```

## Behavior

- Renders home icon (house SVG) as root crumb linking to `/${locale}`
- Chevrons between crumbs (`>` arrow)
- Last crumb (no href) renders as bold text — current page
- Non-last crumbs render as clickable links
- `aria-label="Breadcrumb"` for accessibility
- Client component (needs `'use client'`) due to `useLocale` hook

## Best Practices

- Every sub-page should have breadcrumbs: `dashboard/*`, `works/[id]`, `identity/*`, etc.
- The old "Back to X" single-link pattern should be supplemented by (not replaced with) breadcrumbs
- Remove the old `Link` back button if breadcrumbs already provide the same navigation
- Keep crumbs shallow — 3 levels max (Home > Section > Page)

## See also

- `engineering-approach/references/ux-gap-analysis-methodology.md` — UX audit methodology that identifies missing breadcrumbs
