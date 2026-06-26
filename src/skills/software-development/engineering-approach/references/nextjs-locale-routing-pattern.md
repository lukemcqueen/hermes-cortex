# Next.js Locale Routing (acme-works)

Pattern for adding locale prefix (`/ko/`, `/en/`) to all Next.js App Router pages.

## Architecture

```
Before: /works          /creators         /audit
After:  /ko/works       /ko/creators      /ko/audit
        /en/works       /en/creators      /en/audit
```

## Files to create/modify

### 1. Middleware — `src/middleware.ts`

```ts
const LOCALES = ['ko', 'en'] as const;
const DEFAULT_LOCALE = 'ko';

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (pathname.startsWith('/_next') || pathname.startsWith('/api')) return NextResponse.next();
  if (pathname === '/') { request.nextUrl.pathname = `/${DEFAULT_LOCALE}`; return NextResponse.redirect(request.nextUrl); }

  const first = pathname.split('/')[1];
  if (LOCALES.includes(first as any)) return NextResponse.next();

  request.nextUrl.pathname = `/${DEFAULT_LOCALE}${pathname}`;
  return NextResponse.redirect(request.nextUrl);
}
```

### 2. Locale layout — `src/app/[locale]/layout.tsx`

Server component that owns `<html lang={locale}>`. Also imports Inter font and globals.css:

```tsx
export default async function LocaleLayout({ children, params }: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <html lang={locale} className="dark"><body>...</body></html>;
}
```

The root `app/layout.tsx` becomes a pass-through (`return children`) since the locale layout handles everything.

### 3. Locale sync client — `src/app/[locale]/locale-layout-client.tsx`

Syncs the URL locale into `localStorage` so the i18n provider stays consistent:

```tsx
export function LocaleLayoutClient({ locale, children }: { locale: 'ko' | 'en'; children: ReactNode }) {
  useEffect(() => { localStorage.setItem('acme-locale', locale); }, [locale]);
  return <>{children}</>;
}
```

### 4. Current locale hook — `src/lib/use-locale.ts`

```ts
export function useCurrentLocale(): 'ko' | 'en' {
  const pathname = usePathname();
  const first = pathname.split('/')[1];
  return first === 'en' ? 'en' : 'ko';
}
```

### 5. Locale-aware router — `src/lib/use-locale-router.ts`

Wraps `useRouter().push`/`replace` to auto-prepend locale:

```ts
export function useLocaleRouter() {
  const router = useRouter();
  const locale = useCurrentLocale();
  const push = useCallback((path: string, options?: any) => {
    const prefixed = path.startsWith('/') && !path.startsWith(`/${locale}/`)
      ? `/${locale}${path}` : path;
    router.push(prefixed, options);
  }, [router, locale]);
  return { ...router, push };
}
```

### 6. Locale-aware Link — `src/components/ui/locale-link.tsx`

```tsx
export const LocaleLink = React.forwardRef<HTMLAnchorElement, LinkProps & React.ComponentPropsWithoutRef<'a'>>(
  ({ href, ...props }, ref) => {
    const locale = useCurrentLocale();
    const localizedHref = typeof href === 'string' && !href.startsWith(`/${locale}/`)
      ? `/${locale}${href}` : href;
    return <Link ref={ref} href={localizedHref} {...props} />;
  }
);
```

## Page migration

Move all page files and their subdirectories into `app/[locale]/`:

```bash
mkdir -p '[locale]'
for d in audit contracts creators documents help import login members publisher publishers reports review settings works; do
  mv "$d" '[locale]/'"$d"
done
mv page.tsx '[locale]/page.tsx'
```

## Updating internal links

Every page that does `router.push('/works')` needs to use `useLocaleRouter()` instead of `useRouter()`:

```tsx
// Before
import { useRouter } from 'next/navigation';
const router = useRouter();
router.push('/works');

// After
import { useLocaleRouter } from '@/lib/use-locale-router';
const router = useLocaleRouter();
router.push('/works'); // auto-prefixed to /ko/works
```

The sidebar uses `useCurrentLocale()` + `useMemo` to build locale-prefixed hrefs.

## Test adaptation

When pages move under `[locale]/`:

1. **Import path** — `import Page from '@/app/[locale]/audit/page'` not `'@/app/audit/page'`
2. **usePathname mock** — return `/ko/audit` not `/audit`
3. **Auth mock** — `useRouter` in auth mock can stay unchanged since the wrapper handles it
