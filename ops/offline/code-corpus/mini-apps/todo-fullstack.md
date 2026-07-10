---
title: Full-Stack TODO App
description: Full-stack TODO app with FastAPI backend, SQLite/PostgreSQL, React frontend, and Docker Compose. Demonstrates CRUD endpoints, React hooks, CORS config, and containerized deployment.
language: typescript
tags: [todo, fullstack, fastapi, react, docker]
---

# Full-Stack TODO App

A complete full-stack TODO application with a FastAPI backend, React TypeScript frontend, and Docker Compose for orchestration. Supports both SQLite (dev) and PostgreSQL (prod).

## Project Structure

```
todo-app/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── database.py
│   │   └── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── TodoList.tsx
│   │   ├── TodoItem.tsx
│   │   ├── TodoForm.tsx
│   │   ├── api.ts
│   │   └── types.ts
│   ├── package.json
│   ├── tsconfig.json
│   └── Dockerfile
└── docker-compose.yml
```

## Backend

### `backend/app/database.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./todo.db"  # SQLite for dev
)

# If PostgreSQL URL is provided, use it
if DATABASE_URL.startswith("postgres"):
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### `backend/app/models.py`

```python
from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from app.database import Base


class Todo(Base):
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, default="")
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

### `backend/app/schemas.py`

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class TodoCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = ""
    completed: Optional[bool] = False


class TodoUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    completed: Optional[bool] = None


class TodoResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    completed: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TodoListResponse(BaseModel):
    items: list[TodoResponse]
    total: int
    skip: int
    limit: int
```

### `backend/app/main.py`

```python
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional

from app.database import engine, Base, get_db
from app.models import Todo
from app.schemas import TodoCreate, TodoUpdate, TodoResponse, TodoListResponse

Base.metadata.create_all(bind=engine)

app = FastAPI(title="TODO API", version="1.0.0")

# CORS — allow React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://frontend:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/todos", response_model=TodoListResponse)
def list_todos(
    skip: int = 0,
    limit: int = 50,
    completed: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Todo)
    if completed is not None:
        query = query.filter(Todo.completed == completed)
    total = query.count()
    items = query.order_by(Todo.created_at.desc()).offset(skip).limit(limit).all()
    return TodoListResponse(items=items, total=total, skip=skip, limit=limit)


@app.get("/api/todos/{todo_id}", response_model=TodoResponse)
def get_todo(todo_id: int, db: Session = Depends(get_db)):
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="TODO not found")
    return todo


@app.post("/api/todos", response_model=TodoResponse, status_code=status.HTTP_201_CREATED)
def create_todo(data: TodoCreate, db: Session = Depends(get_db)):
    todo = Todo(title=data.title, description=data.description, completed=data.completed)
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo


@app.put("/api/todos/{todo_id}", response_model=TodoResponse)
def update_todo(todo_id: int, data: TodoUpdate, db: Session = Depends(get_db)):
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="TODO not found")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(todo, key, value)
    db.commit()
    db.refresh(todo)
    return todo


@app.delete("/api/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(todo_id: int, db: Session = Depends(get_db)):
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="TODO not found")
    db.delete(todo)
    db.commit()
    return None
```

### `backend/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy==2.0.35
pydantic==2.9.0
psycopg2-binary==2.9.9
```

### `backend/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Frontend

### `frontend/src/types.ts`

```typescript
export interface Todo {
  id: number;
  title: string;
  description?: string;
  completed: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface TodoListResponse {
  items: Todo[];
  total: number;
  skip: number;
  limit: number;
}

export interface TodoCreate {
  title: string;
  description?: string;
  completed?: boolean;
}

export interface TodoUpdate {
  title?: string;
  description?: string;
  completed?: boolean;
}
```

### `frontend/src/api.ts`

```typescript
import { Todo, TodoCreate, TodoUpdate, TodoListResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`HTTP ${res.status}: ${err}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  list: (params?: { skip?: number; limit?: number; completed?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.skip !== undefined) q.set("skip", String(params.skip));
    if (params?.limit !== undefined) q.set("limit", String(params.limit));
    if (params?.completed !== undefined) q.set("completed", String(params.completed));
    return request<TodoListResponse>(`/api/todos?${q}`);
  },

  get: (id: number) => request<Todo>(`/api/todos/${id}`),

  create: (data: TodoCreate) =>
    request<Todo>("/api/todos", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: number, data: TodoUpdate) =>
    request<Todo>(`/api/todos/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    request<void>(`/api/todos/${id}`, { method: "DELETE" }),
};
```

### `frontend/src/TodoForm.tsx`

```typescript
import React, { useState } from "react";

interface Props {
  onAdd: (title: string, description?: string) => Promise<void>;
}

export function TodoForm({ onAdd }: Props) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setLoading(true);
    try {
      await onAdd(title.trim(), description.trim() || undefined);
      setTitle("");
      setDescription("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ marginBottom: "1rem" }}>
      <input
        type="text"
        placeholder="What needs to be done?"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        disabled={loading}
        required
      />
      <input
        type="text"
        placeholder="Description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        disabled={loading}
      />
      <button type="submit" disabled={loading || !title.trim()}>
        {loading ? "Adding..." : "Add Todo"}
      </button>
    </form>
  );
}
```

### `frontend/src/TodoItem.tsx`

```typescript
import React, { useState } from "react";
import { Todo } from "./types";

interface Props {
  todo: Todo;
  onToggle: (id: number, completed: boolean) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
  onUpdate: (id: number, title: string) => Promise<void>;
}

export function TodoItem({ todo, onToggle, onDelete, onUpdate }: Props) {
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(todo.title);

  const handleSave = async () => {
    if (editTitle.trim() && editTitle !== todo.title) {
      await onUpdate(todo.id, editTitle.trim());
    }
    setEditing(false);
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 0" }}>
      <input
        type="checkbox"
        checked={todo.completed}
        onChange={() => onToggle(todo.id, !todo.completed)}
      />
      {editing ? (
        <input
          type="text"
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          onBlur={handleSave}
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
          autoFocus
        />
      ) : (
        <span
          onDoubleClick={() => setEditing(true)}
          style={{
            textDecoration: todo.completed ? "line-through" : "none",
            flex: 1,
            cursor: "pointer",
          }}
        >
          {todo.title}
        </span>
      )}
      <button onClick={() => onDelete(todo.id)} aria-label="Delete">
        ✕
      </button>
    </div>
  );
}
```

### `frontend/src/TodoList.tsx`

```typescript
import React, { useEffect, useState, useCallback } from "react";
import { Todo, TodoCreate, TodoUpdate } from "./types";
import { api } from "./api";
import { TodoForm } from "./TodoForm";
import { TodoItem } from "./TodoItem";

export function TodoList() {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTodos = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.list({ limit: 100 });
      setTodos(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch todos");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTodos();
  }, [fetchTodos]);

  const handleAdd = async (title: string, description?: string) => {
    const newTodo = await api.create({ title, description });
    setTodos((prev) => [newTodo, ...prev]);
  };

  const handleToggle = async (id: number, completed: boolean) => {
    const updated = await api.update(id, { completed });
    setTodos((prev) => prev.map((t) => (t.id === id ? updated : t)));
  };

  const handleDelete = async (id: number) => {
    await api.delete(id);
    setTodos((prev) => prev.filter((t) => t.id !== id));
  };

  const handleUpdate = async (id: number, title: string) => {
    const updated = await api.update(id, { title });
    setTodos((prev) => prev.map((t) => (t.id === id ? updated : t)));
  };

  if (loading) return <div>Loading todos...</div>;
  if (error) return <div style={{ color: "red" }}>Error: {error}</div>;

  return (
    <div>
      <h1>TODO App</h1>
      <TodoForm onAdd={handleAdd} />
      {todos.length === 0 ? (
        <p>No todos yet. Add one above!</p>
      ) : (
        todos.map((todo) => (
          <TodoItem
            key={todo.id}
            todo={todo}
            onToggle={handleToggle}
            onDelete={handleDelete}
            onUpdate={handleUpdate}
          />
        ))
      )}
    </div>
  );
}
```

### `frontend/src/App.tsx`

```typescript
import React from "react";
import { TodoList } from "./TodoList";

function App() {
  return (
    <div style={{ maxWidth: "600px", margin: "2rem auto", padding: "0 1rem" }}>
      <TodoList />
    </div>
  );
}

export default App;
```

### `frontend/package.json`

```json
{
  "name": "todo-frontend",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0"
  }
}
```

### `frontend/Dockerfile`

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

### `frontend/nginx.conf`

```nginx
server {
    listen 3000;
    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
}
```

## Docker Compose

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: todo
      POSTGRES_PASSWORD: todo
      POSTGRES_DB: todo
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U todo"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://todo:todo@db:5432/todo
    depends_on:
      db:
        condition: service_healthy

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      VITE_API_URL: http://localhost:8000
    depends_on:
      - backend

volumes:
  pgdata:
```

## Running

```bash
# Development (SQLite)
cd todo-app/backend
pip install -r requirements.txt
uvicorn app.main:app --reload

cd todo-app/frontend
npm install
npm run dev

# Production (Docker Compose with PostgreSQL)
cd todo-app
docker compose up --build
```

## API Endpoints

| Method | Path               | Description       |
| ------ | ------------------ | ----------------- |
| GET    | /api/todos         | List todos (paginated) |
| GET    | /api/todos/:id     | Get single todo   |
| POST   | /api/todos         | Create todo       |
| PUT    | /api/todos/:id     | Update todo       |
| DELETE | /api/todos/:id     | Delete todo       |
| GET    | /health            | Health check      |

## Key Patterns Demonstrated

- **FastAPI CRUD endpoints** with Pydantic schemas (Create/Update/Response)
- **SQLAlchemy ORM** with dual SQLite/PostgreSQL support via env var
- **CORS middleware** configured for multiple React dev ports
- **React hooks** (`useState`, `useEffect`, `useCallback`) for state management
- **API client layer** with typed request helpers
- **Docker Compose** with multi-service orchestration and health checks
- **Optimistic UI updates** via local state after API calls