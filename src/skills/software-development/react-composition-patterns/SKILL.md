---
name: react-composition-patterns
description: "React composition patterns that scale — compound components, state lifting, context interfaces, and avoiding boolean prop proliferation. Includes React 19 API changes. Use when refactoring components with many boolean props or building flexible component libraries."
version: 1.0.0
author: Titus (incorporating vercel-labs/agent-skills)
metadata:
  tags: [react, composition, patterns, component-architecture, vercel]
  source: https://github.com/vercel-labs/agent-skills
---

# React Composition Patterns — Vercel Engineering

**Source:** Vercel Labs agent-skills (MIT). Composition patterns for building flexible, maintainable React components. Avoid boolean prop proliferation by using compound components, lifting state, and composing internals.

## When to Apply

- Refactoring components with many boolean props
- Building reusable component libraries
- Designing flexible component APIs
- Reviewing component architecture
- Working with compound components or context providers
- Code review feedback on component interfaces

## Rule Categories (by priority)

| Priority | Category | Impact | Prefix |
|----------|----------|--------|--------|
| 1 | Component Architecture | HIGH | `architecture-` |
| 2 | State Management | MEDIUM | `state-` |
| 3 | Implementation Patterns | MEDIUM | `patterns-` |
| 4 | React 19 APIs | MEDIUM | `react19-` |

---

## 1. Component Architecture (HIGH)

### architecture-avoid-boolean-props
Don't add boolean props to customize behavior — use composition instead.

```tsx
// INCORRECT — boolean prop proliferation
interface CardProps {
  title: string
  content: string
  showFooter?: boolean
  showHeader?: boolean
  isCompact?: boolean
  isBordered?: boolean
  isElevated?: boolean
}

// CORRECT — compound components let consumers compose exactly what they need
<Card>
  <Card.Header>
    <Card.Title>Title</Card.Title>
    <Card.Actions>
      <Button>Edit</Button>
    </Card.Actions>
  </Card.Header>
  <Card.Body>
    <p>Content</p>
  </Card.Body>
  <Card.Footer>
    <small>Last updated: today</small>
  </Card.Footer>
</Card>
```

**When you reach 3+ boolean props on a component, it's time to extract compound components.**

### architecture-compound-components
Structure complex components with shared context. The parent creates context, children read from it:

```tsx
const CardContext = createContext<{ variant: 'default' | 'compact' } | null>(null)

function Card({ variant = 'default', children }: CardProps) {
  return (
    <CardContext.Provider value={{ variant }}>
      <div className={`card card--${variant}`}>{children}</div>
    </CardContext.Provider>
  )
}

Card.Header = function CardHeader({ children }: { children: ReactNode }) {
  return <header className="card__header">{children}</header>
}

Card.Title = function CardTitle({ children }: { children: ReactNode }) {
  const ctx = useContext(CardContext)
  const size = ctx?.variant === 'compact' ? 'text-sm' : 'text-lg'
  return <h3 className={size}>{children}</h3>
}
```

---

## 2. State Management (MEDIUM)

### state-decouple-implementation
The Provider is the only place that knows how state is managed. Consumers don't care if it's useState, useReducer, or Zustand:

```tsx
const ThemeContext = createContext<ThemeContextValue | null>(null)

function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<'light' | 'dark'>('light')
  // Consumers never know this is useState — could swap to useReducer
  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}
```

### state-context-interface
Define a generic interface with `state`, `actions`, and `meta` for dependency injection:

```typescript
interface Store<T, A, M = {}> {
  state: T
  actions: A
  meta?: M
}

interface NotificationStore extends Store<
  NotificationState,          // state
  { add: (n: Notification) => void; dismiss: (id: string) => void },  // actions
  { count: number }           // meta
> {}
```

### state-lift-state
Move state into provider components for sibling access. If two sibling components share state, the common parent should host it:

```tsx
function Sidebar() {
  const { setActiveSection } = useSectionContext()
  return <button onClick={() => setActiveSection('profile')}>Profile</button>
}

function MainPanel() {
  const { activeSection } = useSectionContext()
  return <div>{renderSection(activeSection)}</div>
}
```

---

## 3. Implementation Patterns (MEDIUM)

### patterns-explicit-variants
Create explicit variant components instead of boolean modes:

```tsx
// INCORRECT — mode prop
<Button mode="primary" />
<Button mode="secondary" />
<Button mode="danger" />

// CORRECT — explicit variant components
<PrimaryButton />
<SecondaryButton />
<DangerButton />
```

Each variant wraps the shared base with pre-applied styles/props:
```tsx
function PrimaryButton(props: ButtonProps) {
  return <BaseButton variant="primary" {...props} />
}
```

### patterns-children-over-render-props
Use `children` for composition instead of render props:

```tsx
// INCORRECT — renderX props
<List
  renderItem={(item) => <li>{item.name}</li>}
  renderEmpty={() => <p>No items</p>}
/>

// CORRECT — children composition
<List>
  <List.Items>
    {items.map(item => <List.Item key={item.id}>{item.name}</List.Item>)}
  </List.Items>
  {items.length === 0 && <List.Empty>No items</List.Empty>}
</List>
```

---

## 4. React 19 APIs (MEDIUM)

**⚠️ React 19+ only.** Skip this section if using React 18 or earlier.

### react19-no-forwardref
Don't use `forwardRef` in React 19 — ref is now a regular prop:

```tsx
// INCORRECT — React 19 still works but unnecessary
const MyInput = forwardRef<HTMLInputElement, Props>((props, ref) => (
  <input ref={ref} {...props} />
))

// CORRECT — ref is just a prop
function MyInput({ ref, ...props }: Props & { ref?: Ref<HTMLInputElement> }) {
  return <input ref={ref} {...props} />
}
```

### react19-use-over-usecontext
Use `use()` instead of `useContext()` — it works with promises too:
```tsx
import { use } from 'react'

function Card() {
  // Instead of useContext(CardContext)
  const ctx = use(CardContext)
  return <div>{ctx.title}</div>
}

// Also works with promises (integrates with Suspense)
function Comments({ commentsPromise }: { commentsPromise: Promise<Comment[]> }) {
  const comments = use(commentsPromise)  // Suspends until resolved
  return <ul>{comments.map(c => <li key={c.id}>{c.text}</li>)}</ul>
}
```

---

## Verification

After refactoring, check:
1. Count boolean props on each component — target ≤2 per component
2. Compound components have clear, documented sub-components
3. State providers are at the right level in the tree (not too high, not duplicated)
4. Consumers don't import implementation details from state providers