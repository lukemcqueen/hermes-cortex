---
language: typescript
tags: [web, pattern]
title: React with TypeScript
description: FC, PropsWithChildren, typed useState/useEffect, event handlers, and refs.
source: framework
---

```typescript
import React, { FC, PropsWithChildren, useState, useEffect, useRef, ChangeEvent } from 'react';

// Functional component with typed props
interface GreetingProps {
  name: string;
  age?: number;
}

const Greeting: FC<GreetingProps> = ({ name, age }) => (
  <div>Hello {name}{age != null && ` (${age})`}</div>
);

// Component with children
const Card: FC<PropsWithChildren<{ title: string }>> = ({ title, children }) => (
  <div className="card">
    <h2>{title}</h2>
    {children}
  </div>
);

// Typed useState — type inferred from initial value
const Counter: FC = () => {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(c => c + 1)}>{count}</button>;
};

// Typed useEffect with cleanup
const useDocumentTitle = (title: string): void => {
  useEffect(() => {
    const prev = document.title;
    document.title = title;
    return () => { document.title = prev; };
  }, [title]);
};

// Typed event handler
const Input: FC = () => {
  const [value, setValue] = useState('');
  const handleChange = (e: ChangeEvent<HTMLInputElement>): void => {
    setValue(e.target.value);
  };
  return <input value={value} onChange={handleChange} />;
};

// Typed ref
const AutoFocus: FC = () => {
  const inputRef = useRef<HTMLInputElement>(null!);
  useEffect(() => { inputRef.current?.focus(); }, []);
  return <input ref={inputRef} />;
};

```
