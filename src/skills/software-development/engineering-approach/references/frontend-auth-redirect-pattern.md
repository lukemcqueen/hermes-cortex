# Frontend Auth Redirect Pattern (Next.js / acme-royalty)

When auto-logged out (session expired) and the user refreshes or navigates, they should always be sent to `/login?redirect=<encoded_current_path>`, and after logging in they should go back to that referring page.

## Four touchpoints to implement

### 1. AuthProvider — session restore failure (mount-time check)

In `AuthProvider.tsx`:
- Import `usePathname` from `next/navigation`
- Build a helper: `loginUrlWithRedirect()` returning `` `/login?redirect=${encodeURIComponent(pathname)}` ``
- On catch in the `/auth/me` validation promise: call `router.push(loginUrlWithRedirect())` instead of hardcoded `/login`

```typescript
const pathname = usePathname();

function loginUrlWithRedirect(): string {
  const encoded = encodeURIComponent(pathname);
  return `/login?redirect=${encoded}`;
}

// in the .catch() of the /auth/me fetch:
.catch(() => {
  clearAuth();
  router.push(loginUrlWithRedirect());
})
```

### 2. AuthProvider — logout

Same helper, same change in the `logout` callback. Add `pathname` to the dependency array:

```typescript
router.push(loginUrlWithRedirect());
}, [router, pathname]);
```

### 3. AuthGuard — page-level guard

In `AuthGuard.tsx`:
- Import `usePathname` from `next/navigation`
- Build the redirect URL inline in the `useEffect` that redirects unauthenticated users
- Add `pathname` to dependency array

```typescript
useEffect(() => {
  if (!loading && !isAuthenticated) {
    const encoded = encodeURIComponent(pathname);
    router.push(`/login?redirect=${encoded}`);
  }
}, [loading, isAuthenticated, router, pathname]);
```

### 4. fetchJSON (api.ts) — 401 after refresh failure

In `api.ts` (a plain utility, not a React component):
- Use `window.location.pathname + window.location.search` to capture the current URL
- Use `window.location.href` for a hard redirect (no router available)

```typescript
clearAuth();
if (typeof window !== 'undefined') {
  const currentPath = window.location.pathname + window.location.search;
  const encoded = encodeURIComponent(currentPath);
  window.location.href = `/login?redirect=${encoded}`;
}
throw new Error('Session expired');
```

### 5. Login page — consume redirect param

In `login/page.tsx`:
- Import `useSearchParams` from `next/navigation`
- On successful login, read `searchParams.get('redirect')` and push there

```typescript
const searchParams = useSearchParams();

const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault();
  // ... login call ...
  const redirect = searchParams.get('redirect');
  router.push(redirect || '/');
};
```

## Test implications

Any test that renders a component using `usePathname` (AuthProvider, AuthGuard, or any page wrapped in layout) must mock `usePathname` in `next/navigation`:

```typescript
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/en',
}));
```

Any test rendering the login page must mock `useSearchParams`:

```typescript
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => ({ get: mockSearchParamsGet }),
}));
```

## Why not Server Components

Auth state lives in `localStorage` (browser-only) and the redirect check needs to happen client-side. All four touchpoints are `'use client'` components or browser-only utilities. The login page itself is a client component.
