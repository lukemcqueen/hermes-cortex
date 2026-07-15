# ACME License i18n Pattern — React Context (no next-intl)

acme-license uses a **React Context-based** i18n system instead of next-intl.
Locale is stored in user settings + localStorage, not the URL path.
This allows 3+ languages without URL restructuring.

## Architecture

```
src/lib/i18n/
├── translations/
│   ├── ko.json          # All Korean strings (~150 keys)
│   └── en.json          # Same keys in English
├── translations.ts      # TranslationKey type constants (for autocomplete)
├── context.tsx           # LanguageProvider + useTranslation() hook
└── index.ts             # Re-exports
```

## Key Components

| Component | File | Role |
|---|---|---|
| `LanguageProvider` | `context.tsx` | Wraps app, loads locale from localStorage, provides context |
| `useTranslation()` | `context.tsx` | Returns `{ t, locale, setLocale, isReady }` |
| `LanguageSwitcher` | `components/LanguageSwitcher.tsx` | Fixed top-right dropdown, 한국어 / English |
| `t(key, params?)` | `context.tsx` | Resolves dot-notation keys, supports `{param}` interpolation |

## Usage

```tsx
'use client';
import { useTranslation } from '@/lib/i18n';

export default function MyPage() {
  const { t, locale, setLocale } = useTranslation();
  return (
    <div>
      <h1>{t('license.search.title')}</h1>
      <p>{t('license.search.found', { count: results.length })}</p>
    </div>
  );
}
```

## Adding a New Translation Key

1. Add the key to `translations.ts` as a typed constant if new pages need it
2. Add Korean text in `translations/ko.json`
3. Add matching English text in `translations/en.json`
4. Tests verify all keys match between ko.json and en.json
5. The `t()` function falls back: English → Korean → raw key

## State Persistence

- **Primary**: `localStorage('acme-locale')` — persists across sessions
- **Secondary**: User model `language` column in PostgreSQL — set via DB (available when auth token resolves the user)
- **Priority**: localStorage override > user setting > default 'ko'

The `User` model (in `app/models/user.py`) has a `language` column (`String(10)`, default `'ko'`). When a user logs in, their language preference is loaded from the DB into the session. The localStorage setting still serves as a session-level override.

## Test Patterns

Wrap test components with LanguageProvider:

```tsx
import { render, screen } from '@testing-library/react';
import { LanguageProvider } from '@/lib/i18n';

it('renders in Korean', () => {
  render(<LanguageProvider><MyComponent /></LanguageProvider>);
  expect(screen.getByText('한국어 텍스트')).toBeDefined();
});
```

Or mock the hook for unit tests:

```tsx
vi.mock('@/lib/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    locale: 'ko',
    setLocale: vi.fn(),
    isReady: true,
  }),
}));
```

## Pitfalls

1. **Server components can't use `useTranslation()`** — it's a client hook. Metadata, titles, and SEO tags must use hardcoded bilingual strings in layout.tsx (or `generateMetadata` with a locale param later).
2. **All pages must be `'use client'`** — the `t()` function is only available client-side. This is acceptable for acme-license as all pages have interactivity (search, forms, wizard steps).
3. **Keys must stay in sync between languages** — the i18n test (`tests/i18n.test.tsx`) enforces this. Always add to both files. Missing keys produce fallback cascade not errors.
4. **Dynamic content needs interpolation** — use `t('key', {count})` syntax, not string concatenation. The template uses `{param}` double-brace syntax in JSON strings.
5. **Hardcoded Korean/English text in page components is the #1 regression risk** — after any page update, grep for Korean Hangul range `[\uAC00-\uD7AF]` in tsx files. Only `layout.tsx` metadata should have them.

## Porting from next-intl to React Context

If a project migrates from next-intl (acme-royalty pattern) to React Context:
- Remove `next-intl` dependency and routing config
- Remove URL `[locale]/` prefix from all routes (helps SEO)
- Replace `useTranslations()` with `useTranslation()` and `t('ns.key')` (flat keys, not namespace-scoped)
- Add `'use client'` to all pages that use translation
- Create `LanguageProvider` and wrap root layout
