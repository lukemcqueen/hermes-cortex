# Next.js 15 Standalone + Docker + Tailwind v4 Patterns

Patterns used in the acme-website project (Next.js 15 monorepo, no FastAPI backend). Differs from acme-royalty which uses FastAPI + Next.js.

## Next.js Config for Standalone Output

```typescript
// next.config.ts
import type { NextConfig } from 'next';
import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');

const config: NextConfig = {
  output: 'standalone',                          // MUST be set — creates .next/standalone/
  poweredByHeader: false,
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ['lucide-react', '@radix-ui/react-icons'],
  },
  serverExternalPackages: ['pino', 'pino-pretty'], // packages that shouldn't be bundled
  async rewrites() {
    return [
      {
        source: '/api/search/:path*',
        destination: `${process.env.CLIENT_API_URL || 'http://localhost:3001'}/api/:path*`,
      },
    ];
  },
};

export default withNextIntl(config);
```

## Dockerfile (Multi-stage, Standalone)

```dockerfile
FROM node:20-alpine AS base
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate

FROM base AS deps
WORKDIR /app
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY apps/web/package.json ./apps/web/package.json
COPY packages/shared/package.json ./packages/shared/package.json
RUN pnpm install --frozen-lockfile

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules
COPY --from=deps /app/packages/shared/node_modules ./packages/shared/node_modules
COPY . .
RUN pnpm build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME="0.0.0.0"

# Runtime env defaults — override via docker compose environment or .env
ENV PORT=3000
ENV WEB_URL=http://localhost:3000
ENV DATABASE_URL=postgres://acme:***@postgres:5432/acme_website
ENV REDIS_URL=redis://redis:6379
ENV CLIENT_API_URL=http://host.docker.internal:3001
ENV AUTH_SECRET=change-me
ENV MINIO_ROOT_USER=acme_admin
ENV MINIO_ROOT_PASSWORD=acme_secret_minio

COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /app/apps/web/public ./apps/web/public

EXPOSE 3000
CMD ["node", "apps/web/server.js"]
```

### Key points

- `output: 'standalone'` makes Next.js produce `.next/standalone/` which includes a server.js that bundles the framework code — no `next start` needed
- The standalone output is at `.next/standalone/` — the COPY in the runner stage copies this to `/app/` root
- Static assets need separate COPY: `.next/static` to `/app/apps/web/.next/static` and `public/` to `/app/apps/web/public`
- `ENV` defaults ensure the container boots without an `.env` file — production deployments override these
- Build-time `DATABASE_URL` is only needed if DrizzleKit generates at build time; for most Next.js build targets it's not required
- `corepack enable` must run before `pnpm` on fresh node images

### 🔥 CRITICAL: NEXT_PUBLIC_* vars must be build args, not runtime env

**Symptom:** `NEXT_PUBLIC_API_URL=http://api:8000` set in docker-compose `environment:` does NOT affect the Next.js API proxy. Rewrites still hit `http://localhost:8000` (the default fallback in code). The web container returns "Internal Server Error" on every API route.

**Root cause:** `NEXT_PUBLIC_*` env vars in Next.js are **embedded at build time** (during `next build`). The Next.js bundler inlines their values into the JavaScript bundle. Setting them in docker-compose `environment:` only affects the **runtime** container — the JS bundle was already compiled with the old fallback value.

**Dockerfile fix:** Accept the var as a build arg and set it in the builder stage:

```dockerfile
FROM base AS builder
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL:-http://api:8000}
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
...
RUN pnpm build
```

**docker-compose fix:** Pass the arg via `build.args`:

```yaml
services:
  web:
    build:
      context: .
      dockerfile: apps/web/Dockerfile
      args:
        NEXT_PUBLIC_API_URL: "http://api:8000"
    environment:
      NEXT_PUBLIC_API_URL: "http://api:8000"   # runtime fallback for good measure
```

**Docker service naming inside compose:** Inside the Docker network, services are reachable by their compose service name, not `localhost`. If the API service is named `api`, the URL must be `http://api:8000` (with the container's internal port, not the host-mapped port). Using `http://localhost:${API_PORT}` (e.g. `http://localhost:13000`) from inside the web container fails because nothing listens on port 13000 inside that container.

### Dual-URL pattern: NEXT_PUBLIC_API_URL vs API_INTERNAL_URL

When a Docker compose maps the API to a non-standard host port (e.g. `127.0.0.1:15678:8000`), two different URLs are needed:

| Context | URL | Why |
|---------|-----|-----|
| **Client-side JS** (`NEXT_PUBLIC_API_URL`, build arg) | `http://localhost:15678` | Browser runs on the host — must use the **host-mapped** port |
| **Server-side fetch** (`API_INTERNAL_URL`, runtime env) | `http://api:8000` | Server runs inside Docker — uses the **internal** service name and container port |

```typescript
// api.ts — client-side API client
function getBaseUrl(): string {
  if (typeof window === "undefined") {
    return process.env.API_INTERNAL_URL || "http://localhost:8000";  // server-side: Docker network
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"; // client-side: host port
}
```

**The fallback `http://localhost:8000` must match an actual host-accessible port.** If the compose only exposes `127.0.0.1:15678:8000`, the fallback to port 8000 silently fails on client-side fetches. Either:
- Add a second port mapping (`8000:8000`) for backward compatibility, OR
- Pass the correct URL as a build arg (proper fix), OR
- Use a forward proxy (nginx, macOS pf) to redirect 8000→15678 (band-aid)

**The fix (proper):** See the NEXT_PUBLIC build-arg pattern above.

### 🚨 CRITICAL: NODE_ENV breaks `next build`

**Symptom:** Build fails with `Error: <Html> should not be imported outside of pages/_document.` during prerendering of "/404".

**Root cause:** Next.js 15's `next build` **must** run with `NODE_ENV=production` (explicitly or implicitly). If `.env` or the shell sets `NODE_ENV=development`, the build breaks — the Pages Router `Document` component validation check fires and blocks prerendering of error pages.

**Fix:** Always override to production when building:

```bash
NODE_ENV=production npx next build
```

**In `./run` scripts** that source `.env` (which may contain `NODE_ENV=development` for dev workflows), wrap the build command explicitly:

```bash
cmd_rebuild() {
    ...
    NODE_ENV=production pnpm build
}
```

**In Docker multi-stage builds**, the `builder` stage inherits the host shell's env vars by default. If the host has `NODE_ENV=development`, the Docker build also fails. The Dockerfile's `RUN pnpm build` does **not** inherit from Docker Compose `environment:` — only from `docker build` context. If you see this error in CI/`docker compose build`, pass `--build-arg` or annotate the Dockerfile:

```dockerfile
FROM base AS builder
ARG NODE_ENV=production
ENV NODE_ENV=$NODE_ENV
...
RUN pnpm build
```

The `docker-compose.yml` `environment:` section only affects the **runtime** container, not the build stage.

**Verification:** After build succeeds, the route table should show `○ /_not-found  999 B` (static) rather than a build crash.

## docker-compose.yml — .env Variable Pattern

```yaml
services:
  web:
    build:
      context: .
      dockerfile: apps/web/Dockerfile
    ports:
      - "${WEB_PORT:-3000}:3000"
    env_file:
      - .env
    environment:
      - WEB_URL=${WEB_URL:-http://localhost:3000}
      - DATABASE_URL=postgres://${POSTGRES_USER}:***@postgres:5432/${POSTGRES_DB:-acme_website}
      - REDIS_URL=redis://redis:6379

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-acme}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-acme_website}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
```

Rules:
- **Always** use `${VAR:-default}` pattern so `docker compose up` works without `.env`
- `.env` file is mounted via `env_file:` — Docker Compose auto-loads it
- Services talk over internal Docker network (hostname = service name, e.g. `postgres` not `localhost`)
- Host ports exposed for local tooling (`psql`, `redis-cli`, `curl`)

## Tailwind CSS: v4 vs v3

### ⚠ Critical: Tailwind v4 silently fails in Next.js 15

**Symptom:** CSS file builds to ~1.3KB with only 20 base/theme selectors. `@tailwind utilities` placeholder appears literally in output. All utility classes (`h-5`, `w-5`, `flex-col`, `grid`, `gap-8`, `text-xl`, `bg-gradient-to-br`, `rounded-lg`, `shadow-md`, etc.) are **completely absent**. Icons render at 300×150 (default SVG size), text has no formatting, layout breaks.

**Root cause:** The `@tailwindcss/postcss` v4 PostCSS plugin processes `@import "tailwindcss"` (theme variables + base layer) but **skips source file scanning** in Next.js 15's build pipeline. It never calls the JIT engine that generates utility classes from your component source files.

**Fix: Roll back to Tailwind v3.** The v3 pipeline (`tailwindcss@^3.4` + `postcss.config.js` with `tailwindcss` plugin + `tailwind.config.ts`) reliably scans `content` paths and generates all requested utilities.

### Approach comparison

| Aspect | Tailwind v4 | Tailwind v3 (recommended for Next.js 15) |
|--------|-------------|------------------------------------------|
| CSS syntax | `@import "tailwindcss"` | `@tailwind base/components/utilities` |
| Theme config | `@theme { ... }` in CSS | `tailwind.config.ts` → `theme.extend` |
| PostCSS plugin | `@tailwindcss/postcss` | `tailwindcss` + `autoprefixer` |
| Source scanning | Auto (but fails in Next.js 15) | Explicit `content: ['./src/**/*.{ts,tsx}']` |
| Config file | None needed | `tailwind.config.ts` (required) |
| Utility generation | 0 classes (Next.js 15 bug) | All classes from content paths |
| JIT mode | Built-in | Built-in (v3.2+) |
| Works reliably | ❌ in this project | ✅ |

### v3 setup instructions

#### 1. `package.json` dependencies

```json
{
  "dependencies": {
    "tailwindcss": "^3.4.0",
    "autoprefixer": "^10.4.0"
  }
}
```

Remove `@tailwindcss/postcss` if present — it's v4 only.

#### 2. `postcss.config.js` (ESM — project has `"type": "module"`)

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

**Important:** Use `.js` extension, not `.ts`. A `.ts` PostCSS config is silently ignored by Next.js. The file must use ESM `export default` because package.json has `"type": "module"`.

#### 3. `tailwind.config.ts`

```typescript
import type { Config } from 'tailwindcss';

export default {
  content: ['./src/**/*.{ts,tsx,js,jsx,mdx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
        },
        // ... custom colors
      },
    },
  },
  plugins: [],
} satisfies Config;
```

Note: The `satisfies Config` is an alternative to `as Config` for better type checking.

#### 4. `globals.css`

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  * {
    border-color: var(--color-neutral-200, #e5e7eb);
  }
  body {
    background: var(--color-white, #ffffff);
    color: var(--color-neutral-900, #111827);
  }
}
```

#### 5. Verify

After `next build`, check the CSS output:

```bash
wc -c .next/static/css/*.css
# Should be 50KB+ with hundreds of utility class selectors
ls -l .next/static/chunks/*.css | awk '{print $5, $9}'
# Verify classes exist:
grep -c '\.h-5' .next/static/css/*.css  # → many matches
grep -c '\.flex-col' .next/static/css/*.css
```

### Tailwind v4 (for reference — may work in future Next.js versions)

The original v4 setup is described below for reference, but **do not use it in this project's current Next.js 15 + Docker pipeline** without verifying utility generation:

```css
@import "tailwindcss";
@plugin "@tailwindcss/typography";

@theme {
  --color-white: #ffffff;
  --color-primary-50: #eef2ff;
  /* ... */
}
```

```typescript
// postcss.config.ts
export default {
  plugins: {
    '@tailwindcss/postcss': {},
  },
};
```

### v4 pitfalls (for reference)

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| `var(--color-white)` not in theme | Body background transparent | Add `--color-white: #ffffff` to `@theme` |
| No `@import "tailwindcss"` | Zero Tailwind styles render | Replace v3 `@tailwind` directives with `@import` |
| Using `@tailwind base/components/utilities` v3 syntax | Nothing renders | Use `@import "tailwindcss"` only |
| `backdrop-blur` doesn't render | Glass effect missing | Add `supports-[backdrop-filter]:bg-white/80` |
| **v4 PostCSS plugin in Next.js 15** | **No utility classes generated** | **Roll back to v3 (see above)** |
| Missing PostCSS plugin | No Tailwind classes work | Ensure `@tailwindcss/postcss` is installed |

## Dev Server Lifecycle

```bash
# Start in background (returns immediately)
cd apps/web && pnpm dev

# Verify it's up
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/en
# → 200

# Kill when done
lsof -ti :3000 | xargs kill -9

# Verify port is free
lsof -ti :3000 || echo "free"
```

## Next.js 15.5+ typedRoutes Breaking Change

### `experimental.typedRoutes` moved to top-level

In Next.js 15.5+, `typedRoutes` was promoted from `experimental` to a top-level config key. If it stays nested under `experimental`, the build still runs but a deprecation warning appears. **However**, if any `<Link href>` value doesn't match an actual route file path, the build **errors out** with:

```
Type error: '/en/admin/news' is not an existing route.
```

**Config fix:**

```typescript
// ❌ DEPRECATED (Next.js <15.5)
const config: NextConfig = {
  experimental: {
    typedRoutes: true,
  },
};

// ✅ CORRECT (Next.js 15.5+)
const config: NextConfig = {
  typedRoutes: true,   // ← top-level, outside experimental
};
```

### Strict typedRoutes + dynamic sidebar links

When `typedRoutes: true` is set, every `<Link href>` must be a compile-time known literal matching an existing route. This conflicts with data-driven sidebar patterns where `href` comes from an array:

```tsx
// ❌ COMPILE ERROR — dynamic string not statically checkable
sections.map(s => s.links.map(link =>
  <Link href={link.href}>{link.key}</Link>
));
```

**Fix: Use `as Route` cast from `next/navigation`:**

```typescript
import { Route } from 'next';

// In the sidebar component:
<Link href={link.href as Route}>
  {link.key}
</Link>
```

This tells the type checker to trust the runtime value. Use sparingly — it bypasses the safety typedRoutes provides.

### Non-existent routes crash the build

With `typedRoutes: true`, **any** `<Link href>` pointing to a non-existent route file fails the build. Common culprits:

- Hardcoded locale-prefixed paths like `/en/admin/news` when the route is actually at `/[locale]/admin/documents`
- Nav items added before their page components exist
- Old paths from a previous version that were renamed

**Pattern:** Never hardcode `/en/...` — use `/{locale}/...` via dynamic locale from `useParams()` or the `next-intl` `<Link>` (which auto-prefixes).

If a nav item references a page that doesn't exist yet, either:
1. Remove the nav item until the page exists, OR
2. Use `as Route` cast with a comment noting it's a planned route

## next-intl v4 — Comprehensive Setup (Next.js 15 App Router)

### Plugin wiring in next.config.ts

```typescript
import type { NextConfig } from 'next';
import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');

const config: NextConfig = {
  output: 'standalone',
};

export default withNextIntl(config);
```

The plugin path is relative to project root, not `src/`.

### Routing definition (src/i18n/routing.ts)

```typescript
import { defineRouting } from 'next-intl/routing';
import { createNavigation } from 'next-intl/navigation';

export const routing = defineRouting({
  locales: ['ko', 'en'],
  defaultLocale: 'ko',
  localePrefix: 'always',          // URL always includes locale: /ko/page, /en/page
});

export const { Link, redirect, usePathname, useRouter, getPathname } =
  createNavigation(routing);
```

Key decisions:
- `localePrefix: 'always'` — explicit locale in every URL (best for SSG + SEO)
- `defaultLocale: 'ko'` — Korean market primary
- Export `Link, redirect, usePathname, useRouter` — these wrap Next.js equivalents with locale awareness
- Add 3+ languages later by extending the `locales` array and adding message files

### Request config (src/i18n/request.ts)

```typescript
import { getRequestConfig } from 'next-intl/server';
import { routing } from './routing';

export default getRequestConfig(async ({ requestLocale }) => {
  let locale = await requestLocale;
  if (!locale || !routing.locales.includes(locale as 'ko' | 'en')) {
    locale = routing.defaultLocale;
  }
  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
```

The `messages/` directory is at project root level (outside `src/`). Path `../../messages/` navigates up from `src/i18n/` to project root.

### Translation file structure (messages/{locale}.json)

Single JSON file per locale, namespaced by section:

```json
{
  "common": { "appName": "...", "save": "...", "cancel": "..." },
  "nav": { "dashboard": "...", "productions": "..." },
  "auth": { "login": "...", "email": "...", "password": "..." },
  "home": { "title": "...", "getStarted": "..." },
  "productions": { ... },
  "episodes": { ... },
  "cueSheets": { ... },
  "validation": { ... },
  "export": { ... },
  "settings": { ... },
  "errors": { ... },
  "wizard": { ... }
}
```

11+ sections covering common UI, nav, auth pages, domain pages, validation, export, settings, errors, and wizards. Access via `useTranslations('nav')`, `useTranslations('auth')`, etc.

### Root layout (src/app/[locale]/layout.tsx)

```tsx
import { NextIntlClientProvider } from 'next-intl';
import { getMessages } from 'next-intl/server';
import { notFound } from 'next/navigation';
import { routing } from '@/src/i18n/routing';

type Props = { children: React.ReactNode; params: Promise<{ locale: string }> };

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({ children, params }: Props) {
  const { locale } = await params;
  if (!routing.locales.includes(locale as 'ko' | 'en')) notFound();

  const messages = await getMessages();
  return (
    <NextIntlClientProvider messages={messages}>
      {children}
    </NextIntlClientProvider>
  );
}
```

Key elements:
- `generateStaticParams` — returns all locales for SSG prerendering
- `routing.locales.includes(...)` guard — rejects unknown locales with 404
- `NextIntlClientProvider` — makes messages available to all client components
- `getMessages()` — server-side message loading

### Root page redirection (src/app/page.tsx)

```tsx
import { redirect } from 'next/navigation';
export default function RootPage() { redirect('/ko'); }
```

Root `/` always redirects to the default locale so locale-prefixed URLs are canonical.

### LanguageSwitcher component (src/components/LanguageSwitcher.tsx)

```tsx
'use client';
import { usePathname, useRouter } from '@/src/i18n/routing';
import { useLocale, useTranslations } from 'next-intl';
import { useParams } from 'next/navigation';

export default function LanguageSwitcher() {
  const t = useTranslations('nav');
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const params = useParams();

  const switchLocale = (newLocale: string) => {
    router.replace({ pathname, params } as any, { locale: newLocale });
  };

  return (
    <select value={locale} onChange={(e) => switchLocale(e.target.value)} aria-label={t('language')}>
      <option value="ko">{t('korean')}</option>
      <option value="en">{t('english')}</option>
    </select>
  );
}
```

Key patterns:
- Import `usePathname` and `useRouter` from `@/src/i18n/routing` (not `next/navigation`) for locale-awareness
- `router.replace({ pathname, params }, { locale })` — switches locale without full reload
- `as any` type cast for params object (next-intl v4 types are complex)
- All display text via `useTranslations('nav')`

### Client component usage

```tsx
'use client';
import { useTranslations } from 'next-intl';
export function MyComponent() {
  const t = useTranslations('productions');
  return <h1>{t('title')}</h1>;
}
```

### Server component usage

```tsx
import { getTranslations } from 'next-intl/server';
export default async function ServerPage() {
  const t = await getTranslations('home');
  return <h1>{t('title')}</h1>;
}
```

### i18n nav links

Use the locale-aware `Link` from `@/src/i18n/routing`:

```tsx
import { Link } from '@/src/i18n/routing';
<Link href="/productions">{t('productions')}</Link>  // auto-includes locale prefix
```

Do NOT hardcode locale prefixes — the routing Link is locale-aware.

### Adding new translation keys

1. Add key/value to `messages/ko.json` under appropriate section
2. Add key/value to `messages/en.json` under the same section path
3. Use in components via `useTranslations('section')` or `getTranslations('section')`
4. Verify build: `pnpm run build` (catches missing keys at compile time)

### Pitfalls

- **Missing keys crash the build** — next-intl validates that all referenced keys exist. Always add keys to BOTH locale files simultaneously.
- **`as any` type cast on router.params** — next-intl v4's `router.replace()` type is complex. `as any` is the pragmatic workaround for the LanguageSwitcher.
- **Translation files at project root** — next-intl loads messages via dynamic `import()` at runtime. Path must resolve correctly from project root. `request.ts` uses `../../messages/` to navigate up from `src/i18n/`.
- **`generateStaticParams` is required for SSG** — without it, `[locale]` routes are ISR (rendered on first request). Always define in `[locale]/layout.tsx`.
- **Korean-first UI** — default locale is `ko`, all new pages default to Korean. English is secondary.

## Related

- `references/fullstack-feature-workflow.md` — full-stack feature workflow (acme-royalty FastAPI + Next.js)
- `references/env-example-conventions.md` — .env.example style guide
