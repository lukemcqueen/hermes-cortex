---
language: typescript
tags: [nextjs, middleware, auth, edge]
title: Next.js Middleware
description: Edge middleware for authentication, redirects, rewrite, and request/response modification.
source: pattern
---

```typescript
// middleware.ts at project root
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  const token = request.cookies.get('session')?.value
  const isAuthPage = request.nextUrl.pathname.startsWith('/login')
  const isApiRoute = request.nextUrl.pathname.startsWith('/api/')

  // Redirect to login if unauthenticated
  if (!token && !isAuthPage && !isApiRoute) {
    const login = new URL('/login', request.url)
    login.searchParams.set('from', request.nextUrl.pathname)
    return NextResponse.redirect(login)
  }

  // Add security headers
  const response = NextResponse.next()
  response.headers.set('X-Frame-Options', 'DENY')
  response.headers.set('X-Content-Type-Options', 'nosniff')

  return response
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico).*)',  // all routes except static
  ],
}
```
