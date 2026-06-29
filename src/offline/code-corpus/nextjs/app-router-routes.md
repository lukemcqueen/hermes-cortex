---
language: typescript
tags: [nextjs, react, ssr, app-router]
title: Next.js App Router — Route Handlers
description: API route handlers in App Router with typed request/response patterns, middleware, and edge runtime.
source: pattern
---

```typescript
// app/api/users/route.ts — GET, POST handlers
import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const page = searchParams.get('page') ?? '1'
  const users = await db.users.findMany({ skip: (+page - 1) * 20, take: 20 })
  return NextResponse.json(users)
}

export async function POST(request: NextRequest) {
  const body = await request.json()
  const user = await db.users.create({ data: body })
  return NextResponse.json(user, { status: 201 })
}

// app/api/users/[id]/route.ts — dynamic segment
export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const user = await db.users.findUnique({ where: { id: params.id } })
  if (!user) return NextResponse.json({ error: 'Not found' }, { status: 404 })
  return NextResponse.json(user)
}

// app/api/route.ts — edge runtime
export const runtime = 'edge'
export async function GET(request: NextRequest) {
  return NextResponse.json({ message: 'Edge function' })
}
```
