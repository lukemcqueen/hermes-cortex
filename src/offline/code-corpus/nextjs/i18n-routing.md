---
language: typescript
tags: [nextjs, localization, i18n, routing]
title: Next.js i18n Routing
description: Internationalization with Next.js App Router — localized routes, interceptors, and locale detection.
source: pattern
---

```typescript
// middleware.ts — locale detection & redirect
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const LOCALES = ['en', 'ko', 'ja'] as const
const DEFAULT_LOCALE = 'en'

function getLocale(request: NextRequest): string {
  // Check cookie first
  const cookie = request.cookies.get('NEXT_LOCALE')?.value
  if (cookie && LOCALES.includes(cookie as any)) return cookie

  // Check Accept-Language header
  const acceptLang = request.headers.get('accept-language')?.split(',')[0]?.slice(0, 2)
  if (acceptLang && LOCALES.includes(acceptLang as any)) return acceptLang

  return DEFAULT_LOCALE
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  const pathLocale = LOCALES.find(loc => pathname.startsWith(`/${loc}/`) || pathname === `/${loc}`)

  if (!pathLocale) {
    const locale = getLocale(request)
    request.nextUrl.pathname = `/${locale}${pathname}`
    return NextResponse.redirect(request.nextUrl)
  }
}

// app/[lang]/page.tsx — localized page
export default async function Page({ params }: { params: { lang: string } }) {
  return <h1>{params.lang === 'ko' ? '안녕하세요' : 'Hello'}</h1>
}
```
