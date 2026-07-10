---
language: typescript
tags: [react, components, composition, patterns]
title: React Component Composition Patterns
description: Compound components, slots, render props, children prop, context + composition
source: pattern
---

## Children Prop (Basic Composition)

```typescript
import { ReactNode } from 'react';

interface CardProps {
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}

function Card({ title, children, footer }: CardProps) {
  return (
    <div className="rounded-lg border p-4 shadow-sm">
      <h2 className="mb-2 text-lg font-semibold">{title}</h2>
      <div className="mb-4">{children}</div>
      {footer && <div className="border-t pt-2 text-sm text-gray-500">{footer}</div>}
    </div>
  );
}

// Usage
<Card title="Getting Started" footer={<span>Updated 2h ago</span>}>
  <p>This is the card body content passed as children.</p>
</Card>
```

## Compound Components

```typescript
import {
  createContext,
  useContext,
  useState,
  ReactNode,
  cloneElement,
  ReactElement,
} from 'react';

/* ---------- Context-based compound component ---------- */
interface ToggleContextValue {
  on: boolean;
  toggle: () => void;
}

const ToggleContext = createContext<ToggleContextValue | null>(null);

function useToggleContext(): ToggleContextValue {
  const ctx = useContext(ToggleContext);
  if (!ctx) throw new Error('Toggle sub-components must be used inside <Toggle>');
  return ctx;
}

/* Root */
interface ToggleProps {
  children: ReactNode;
  defaultOn?: boolean;
  onChange?: (value: boolean) => void;
}

function Toggle({ children, defaultOn = false, onChange }: ToggleProps) {
  const [on, setOn] = useState(defaultOn);
  const toggle = () =>
    setOn((prev) => {
      const next = !prev;
      onChange?.(next);
      return next;
    });

  return (
    <ToggleContext.Provider value={{ on, toggle }}>
      <div className="toggle-root">{children}</div>
    </ToggleContext.Provider>
  );
}

/* Sub-components */
function ToggleOn({ children }: { children: ReactNode }) {
  const { on } = useToggleContext();
  return on ? <>{children}</> : null;
}

function ToggleOff({ children }: { children: ReactNode }) {
  const { on } = useToggleContext();
  return on ? null : <>{children}</>;
}

function ToggleButton({ children }: { children?: ReactNode }) {
  const { on, toggle } = useToggleContext();
  return (
    <button onClick={toggle} aria-pressed={on} className="toggle-btn">
      {children ?? (on ? 'ON' : 'OFF')}
    </button>
  );
}

// Attach sub-components as static properties
Toggle.On = ToggleOn;
Toggle.Off = ToggleOff;
Toggle.Button = ToggleButton;

// Usage
<Toggle defaultOn onChange={(v) => console.log('toggled', v)}>
  <Toggle.Button />
  <Toggle.On>Visible when ON</Toggle.On>
  <Toggle.Off>Visible when OFF</Toggle.Off>
</Toggle>
```

## Render Props

```typescript
import { useState, ReactNode } from 'react';

interface MouseTrackerRenderProps {
  x: number;
  y: number;
}

interface MouseTrackerProps {
  children: (props: MouseTrackerRenderProps) => ReactNode;
}

function MouseTracker({ children }: MouseTrackerProps) {
  const [position, setPosition] = useState({ x: 0, y: 0 });

  return (
    <div
      onMouseMove={(e) => setPosition({ x: e.clientX, y: e.clientY })}
      style={{ width: '100%', height: '400px', border: '1px solid #ccc' }}
    >
      {children(position)}
    </div>
  );
}

// Usage
<MouseTracker>
  {({ x, y }) => (
    <p>
      Mouse position: {x}, {y}
    </p>
  )}
</MouseTracker>
```

## Slots Pattern

```typescript
import { ReactNode, isValidElement, Children } from 'react';

interface SlotProps {
  name: string;
  children: ReactNode;
}

function Slot({ children }: SlotProps) {
  return <>{children}</>;
}

interface LayoutProps {
  children: ReactNode;
}

function Layout({ children }: LayoutProps) {
  // Extract named slots from children
  const slots: Record<string, ReactNode> = {};
  const rest: ReactNode[] = [];

  Children.forEach(children, (child) => {
    if (isValidElement(child) && child.type === Slot) {
      slots[(child.props as SlotProps).name] = (child.props as SlotProps).children;
    } else {
      rest.push(child);
    }
  });

  return (
    <div className="layout">
      <header className="layout-header">{slots.header}</header>
      <aside className="layout-sidebar">{slots.sidebar}</aside>
      <main className="layout-main">{rest}</main>
      <footer className="layout-footer">{slots.footer}</footer>
    </div>
  );
}

Layout.Slot = Slot;

// Usage
<Layout>
  <Layout.Slot name="header">
    <h1>Page Title</h1>
  </Layout.Slot>
  <Layout.Slot name="sidebar">
    <nav>Navigation</nav>
  </Layout.Slot>
  <p>Default content rendered in the main area.</p>
  <Layout.Slot name="footer">
    <small>&copy; 2026</small>
  </Layout.Slot>
</Layout>
```

## Context + Composition (Provider Pattern)

```typescript
import { createContext, useContext, useState, ReactNode, useCallback } from 'react';

/* ---------- Auth context with composed hooks ---------- */
interface User {
  id: string;
  name: string;
  email: string;
}

interface AuthContextValue {
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error('Login failed');
    const data: User = await res.json();
    setUser(data);
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    fetch('/api/auth/logout', { method: 'POST' });
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, logout, isAuthenticated: user !== null }}>
      {children}
    </AuthContext.Provider>
  );
}

/* Custom hook for consuming the context */
function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}

// Usage
function UserMenu() {
  const { user, logout, isAuthenticated } = useAuth();
  if (!isAuthenticated) return <a href="/login">Sign in</a>;
  return (
    <div>
      <span>{user!.name}</span>
      <button onClick={logout}>Sign out</button>
    </div>
  );
}

export { AuthProvider, useAuth };
```