---
language: typescript
tags: [nextjs, react, ssr, server-components]
title: Next.js Server & Client Components
description: Server Components for data fetching, Client Components for interactivity, and the 'use client' boundary.
source: pattern
---

```typescript
// app/users/page.tsx — Server Component (default)
// Fetches data directly, no client JS, no 'use client' directive
async function getUsers() {
  const res = await fetch('https://api.example.com/users')
  return res.json()
}

export default async function UsersPage() {
  const users = await getUsers()

  return (
    <ul>
      {users.map(user => (
        <li key={user.id}>{user.name} — {user.email}</li>
      ))}
    </ul>
  )
}

// app/users/[id]/page.tsx — Server Component with params
export default async function UserPage({ params }: { params: { id: string } }) {
  const user = await fetch(`https://api.example.com/users/${params.id}`, {
    next: { revalidate: 60 }  // ISR: revalidate every 60s
  }).then(r => r.json())

  return <div>{user.name}</div>
}

// ── Client Component boundary ──
// app/users/ClientTable.tsx
'use client'

import { useState } from 'react'

export function ClientTable({ users }: { users: any[] }) {
  const [sortBy, setSortBy] = useState<'name' | 'email'>('name')
  const sorted = [...users].sort((a, b) => a[sortBy].localeCompare(b[sortBy]))

  return (
    <div>
      <button onClick={() => setSortBy('name')}>Sort by name</button>
      <button onClick={() => setSortBy('email')}>Sort by email</button>
      <table>{/* render sorted rows */}</table>
    </div>
  )
}
```
