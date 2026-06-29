---
title: API → Database → Frontend Flow
description: Full request lifecycle from FastAPI endpoint querying PostgreSQL to React frontend fetching and displaying data with loading, error, and empty states.
language: typescript
tags: [glue-code, fullstack, api, database, frontend]
---

# API → Database → Frontend Flow

## Overview

This snippet traces the complete lifecycle of a data request from the user's click in a React frontend, through a FastAPI backend that queries PostgreSQL, and back to the rendered UI with proper loading, error, and empty states.

---

## Backend: FastAPI + PostgreSQL

### Database Setup

```sql
-- 0001_create_tasks_table.sql
CREATE TABLE tasks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title       TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'in_progress', 'done', 'cancelled')),
    priority    INT NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created_at ON tasks(created_at DESC);

-- Seed data
INSERT INTO tasks (title, description, status, priority) VALUES
    ('Set up CI/CD pipeline', 'Configure GitHub Actions for automated testing', 'in_progress', 1),
    ('Write API docs', 'Document all endpoints with OpenAPI', 'pending', 2);
```

### FastAPI Endpoints

```python
# backend/app.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import asyncpg
import uuid
from datetime import datetime
from typing import Optional

app = FastAPI(title="Task Manager API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connection pool (set up on startup)
pool: asyncpg.Pool | None = None

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(
        dsn="postgresql://postgres:postgres@localhost:5432/taskdb",
        min_size=2,
        max_size=10,
    )

@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()

# --- Models ---

class TaskOut(BaseModel):
    id: str
    title: str
    description: str | None = None
    status: str
    priority: int
    created_at: datetime
    updated_at: datetime

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    priority: int = Field(default=3, ge=1, le=5)

class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: int | None = None

# --- Endpoints ---

@app.get("/api/tasks", response_model=list[TaskOut])
async def list_tasks(
    status: str | None = Query(None),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Fetch tasks with optional status filter, pagination."""
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch(
                """
                SELECT * FROM tasks
                WHERE status = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                status, limit, offset,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT * FROM tasks
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit, offset,
            )

        count = await conn.fetchval(
            "SELECT COUNT(*) FROM tasks" +
            (" WHERE status = $1" if status else ""),
            *([status] if status else []),
        )

    return {
        "items": [dict(row) for row in rows],
        "total": count,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return dict(row)


@app.post("/api/tasks", response_model=TaskOut, status_code=201)
async def create_task(task: TaskCreate):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO tasks (title, description, priority)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            task.title, task.description, task.priority,
        )
        return dict(row)


@app.patch("/api/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: uuid.UUID, task: TaskUpdate):
    # Build dynamic SET clause from provided fields
    updates = task.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates))
    set_clause += ", updated_at = NOW()"

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE tasks SET {set_clause}
            WHERE id = $1
            RETURNING *
            """,
            task_id, *updates.values(),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return dict(row)


@app.delete("/api/tasks/{task_id}", status_code=204)
async def delete_task(task_id: uuid.UUID):
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Task not found")
```

---

## Frontend: React + TypeScript

### Type Definitions

```typescript
// src/types.ts
export interface Task {
  id: string;
  title: string;
  description: string | null;
  status: 'pending' | 'in_progress' | 'done' | 'cancelled';
  priority: number;
  created_at: string;
  updated_at: string;
}

export interface TaskListResponse {
  items: Task[];
  total: number;
  limit: number;
  offset: number;
}
```

### API Client

```typescript
// src/api/tasks.ts
import type { Task, TaskListResponse } from '../types';

const API_BASE = 'http://localhost:8000/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });

  if (!response.ok) {
    const errorBody = await response.text().catch(() => '');
    throw new ApiError(
      `HTTP ${response.status}: ${response.statusText}`,
      response.status,
      errorBody,
    );
  }

  if (response.status === 204) return undefined as T;
  return response.json();
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export const tasksApi = {
  list: (params?: { status?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return fetchJson<TaskListResponse>(
      `${API_BASE}/tasks${query ? `?${query}` : ''}`,
    );
  },

  get: (id: string) => fetchJson<Task>(`${API_BASE}/tasks/${id}`),

  create: (data: { title: string; description?: string; priority?: number }) =>
    fetchJson<Task>(`${API_BASE}/tasks`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (
    id: string,
    data: { title?: string; status?: string; priority?: number },
  ) =>
    fetchJson<Task>(`${API_BASE}/tasks/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    fetchJson<void>(`${API_BASE}/tasks/${id}`, { method: 'DELETE' }),
};
```

### Custom Hook for Data Fetching

```typescript
// src/hooks/useTasks.ts
import { useState, useEffect, useCallback } from 'react';
import { tasksApi, ApiError } from '../api/tasks';
import type { Task } from '../types';

interface UseTasksResult {
  tasks: Task[];
  total: number;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useTasks(statusFilter?: string): UseTasksResult {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await tasksApi.list({
        status: statusFilter,
        limit: 100,
      });
      setTasks(response.items);
      setTotal(response.total);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Network error — please check your connection');
      }
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  return { tasks, total, loading, error, refetch: fetchTasks };
}
```

### Task List Component

```tsx
// src/components/TaskList.tsx
import React, { useState } from 'react';
import { useTasks } from '../hooks/useTasks';
import type { Task } from '../types';

export function TaskList() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const { tasks, total, loading, error, refetch } = useTasks(statusFilter);

  return (
    <div className="task-list-container">
      {/* Header */}
      <div className="task-list-header">
        <h1>Tasks ({total})</h1>
        <div className="filters">
          <select
            value={statusFilter ?? ''}
            onChange={(e) => setStatusFilter(e.target.value || undefined)}
          >
            <option value="">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="in_progress">In Progress</option>
            <option value="done">Done</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <button onClick={refetch} disabled={loading}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="loading-state" role="status">
          <div className="spinner" aria-hidden="true" />
          <p>Loading tasks...</p>
        </div>
      )}

      {/* Error State */}
      {!loading && error && (
        <div className="error-state" role="alert">
          <h2>Failed to load tasks</h2>
          <p>{error}</p>
          <button onClick={refetch}>Try Again</button>
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && tasks.length === 0 && (
        <div className="empty-state">
          <p>No tasks found.</p>
          {statusFilter ? (
            <p>Try clearing the status filter.</p>
          ) : (
            <p>Create your first task to get started!</p>
          )}
        </div>
      )}

      {/* Data State */}
      {!loading && !error && tasks.length > 0 && (
        <div className="task-grid">
          {tasks.map((task) => (
            <TaskCard key={task.id} task={task} onUpdated={refetch} />
          ))}
        </div>
      )}
    </div>
  );
}

// --- Task Card Component ---

interface TaskCardProps {
  task: Task;
  onUpdated: () => void;
}

function TaskCard({ task, onUpdated }: TaskCardProps) {
  const statusColors: Record<string, string> = {
    pending: '#f59e0b',
    in_progress: '#3b82f6',
    done: '#10b981',
    cancelled: '#6b7280',
  };

  const [updating, setUpdating] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);

  const handleStatusChange = async (newStatus: string) => {
    setUpdating(true);
    setUpdateError(null);
    try {
      await import('../api/tasks').then((m) =>
        m.tasksApi.update(task.id, { status: newStatus }),
      );
      onUpdated();
    } catch (err) {
      setUpdateError('Failed to update status');
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div className="task-card">
      <div className="task-card-header">
        <h3>{task.title}</h3>
        <span
          className="priority-badge"
          data-priority={task.priority}
        >
          P{task.priority}
        </span>
      </div>

      {task.description && (
        <p className="task-description">{task.description}</p>
      )}

      <div className="task-meta">
        <span
          className="status-badge"
          style={{ backgroundColor: statusColors[task.status] }}
        >
          {task.status.replace('_', ' ')}
        </span>
        <span className="task-date">
          {new Date(task.created_at).toLocaleDateString()}
        </span>
      </div>

      <div className="task-actions">
        <select
          value={task.status}
          onChange={(e) => handleStatusChange(e.target.value)}
          disabled={updating}
        >
          <option value="pending">Pending</option>
          <option value="in_progress">In Progress</option>
          <option value="done">Done</option>
          <option value="cancelled">Cancelled</option>
        </select>
        {updating && <span className="updating-indicator">Updating...</span>}
        {updateError && (
          <span className="update-error">{updateError}</span>
        )}
      </div>
    </div>
  );
}
```

---

## Request Lifecycle (Click to Render)

```
User clicks "Refresh"
    │
    ▼
React: useTasks() hook fires
    │  — sets loading=true, error=null
    ▼
React: fetch("http://localhost:8000/api/tasks")
    │  — HTTP GET request
    ▼
FastAPI: GET /api/tasks handler
    │  — validates query params (status, limit, offset)
    ▼
FastAPI: pool.acquire() → acquires connection from pool
    │  — asyncpg connection from pool
    ▼
PostgreSQL: SELECT * FROM tasks ORDER BY created_at DESC LIMIT 50
    │  — query executes, returns rows
    ▼
FastAPI: serializes rows → list[TaskOut] (Pydantic)
    │  — returns JSON response with 200 OK
    ▼
React: response.json() → TaskListResponse
    │  — sets tasks, total, loading=false
    ▼
React: re-renders TaskList
    │  — maps tasks → TaskCard components
    ▼
Browser: paints updated DOM
```

### CSS (Basic Styling)

```css
/* src/styles/task-list.css */
.task-list-container {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
  font-family: system-ui, -apple-system, sans-serif;
}

.task-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
}

.task-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  background: white;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.loading-state, .error-state, .empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #6b7280;
}

.error-state { color: #ef4444; }

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e5e7eb;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 12px;
}

@keyframes spin { to { transform: rotate(360deg); } }

.priority-badge[data-priority="1"] { background: #ef4444; }
.priority-badge[data-priority="2"] { background: #f97316; }
.priority-badge[data-priority="3"] { background: #eab308; }
.priority-badge[data-priority="4"] { background: #22c55e; }
.priority-badge[data-priority="5"] { background: #6b7280; }

.priority-badge {
  color: white;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}
```

---

## Key Takeaways

- **FastAPI + asyncpg** gives non-blocking database access with connection pooling.
- **React custom hooks** (`useTasks`) encapsulate fetch/loading/error logic cleanly.
- **Every state is handled**: loading (spinner), error (message + retry), empty (guidance text), and data.
- **Full lifecycle**: user click → HTTP request → server validation → DB query → serialization → JSON response → React state update → re-render.
- **Optimistic updates** (like status change dropdown) can further improve UX by updating locally before the server confirms.
