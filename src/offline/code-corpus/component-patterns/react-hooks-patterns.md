---
language: typescript
tags: [react, hooks, patterns, custom]
title: React Custom Hooks Patterns
description: useLocalStorage, useDebounce, useMediaQuery, useIntersectionObserver, hook composition
source: pattern
---

## useLocalStorage

```typescript
import { useState, useCallback } from 'react';

function useLocalStorage<T>(
  key: string,
  initialValue: T,
): [T, (value: T | ((prev: T) => T)) => void, () => void] {
  const [storedValue, setStoredValue] = useState<T>(() => {
    try {
      const item = window.localStorage.getItem(key);
      return item ? (JSON.parse(item) as T) : initialValue;
    } catch {
      console.warn(`Failed to read localStorage key "${key}"`);
      return initialValue;
    }
  });

  const setValue = useCallback(
    (value: T | ((prev: T) => T)) => {
      setStoredValue((prev) => {
        const nextValue = value instanceof Function ? value(prev) : value;
        try {
          window.localStorage.setItem(key, JSON.stringify(nextValue));
        } catch {
          console.warn(`Failed to write localStorage key "${key}"`);
        }
        return nextValue;
      });
    },
    [key],
  );

  const removeValue = useCallback(() => {
    try {
      window.localStorage.removeItem(key);
      setStoredValue(initialValue);
    } catch {
      console.warn(`Failed to remove localStorage key "${key}"`);
    }
  }, [key, initialValue]);

  return [storedValue, setValue, removeValue];
}

// Usage
function ThemeToggle() {
  const [theme, setTheme] = useLocalStorage<'light' | 'dark'>('theme', 'light');
  return (
    <button onClick={() => setTheme((t) => (t === 'light' ? 'dark' : 'light'))}>
      Current: {theme}
    </button>
  );
}
```

## useDebounce

```typescript
import { useState, useEffect } from 'react';

function useDebounce<T>(value: T, delayMs: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debouncedValue;
}

// Usage
function SearchInput() {
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    if (debouncedQuery) {
      fetch(`/api/search?q=${encodeURIComponent(debouncedQuery)}`);
    }
  }, [debouncedQuery]);

  return (
    <input
      type="text"
      value={query}
      onChange={(e) => setQuery(e.target.value)}
      placeholder="Search..."
    />
  );
}
```

## useMediaQuery

```typescript
import { useState, useEffect } from 'react';

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      return window.matchMedia(query).matches;
    }
    return false;
  });

  useEffect(() => {
    const mql = window.matchMedia(query);
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);

    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [query]);

  return matches;
}

// Usage with breakpoint constants
const BREAKPOINTS = {
  sm: '(min-width: 640px)',
  md: '(min-width: 768px)',
  lg: '(min-width: 1024px)',
  xl: '(min-width: 1280px)',
  dark: '(prefers-color-scheme: dark)',
  reducedMotion: '(prefers-reduced-motion: reduce)',
} as const;

function ResponsiveSidebar() {
  const isDesktop = useMediaQuery(BREAKPOINTS.lg);
  const prefersDark = useMediaQuery(BREAKPOINTS.dark);
  const prefersReducedMotion = useMediaQuery(BREAKPOINTS.reducedMotion);

  if (!isDesktop) return <nav className="drawer">Mobile nav</nav>;
  return (
    <nav
      className={`sidebar ${prefersDark ? 'dark' : ''}`}
      style={{ transition: prefersReducedMotion ? 'none' : undefined }}
    >
      Desktop sidebar
    </nav>
  );
}
```

## useIntersectionObserver

```typescript
import { useRef, useState, useEffect, useCallback } from 'react';

interface UseIntersectionObserverOptions {
  threshold?: number | number[];
  root?: Element | null;
  rootMargin?: string;
  triggerOnce?: boolean;
}

function useIntersectionObserver(
  options: UseIntersectionObserverOptions = {},
): [React.RefObject<Element | null>, boolean, IntersectionObserverEntry | null] {
  const { threshold = 0, root = null, rootMargin = '0px', triggerOnce = false } = options;
  const ref = useRef<Element>(null);
  const [isIntersecting, setIsIntersecting] = useState(false);
  const [entry, setEntry] = useState<IntersectionObserverEntry | null>(null);

  const handleIntersection = useCallback(
    (entries: IntersectionObserverEntry[], observer: IntersectionObserver) => {
      const [intersectionEntry] = entries;
      setEntry(intersectionEntry);
      setIsIntersecting(intersectionEntry.isIntersecting);

      if (triggerOnce && intersectionEntry.isIntersecting) {
        observer.unobserve(intersectionEntry.target);
      }
    },
    [triggerOnce],
  );

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const observer = new IntersectionObserver(handleIntersection, {
      threshold,
      root,
      rootMargin,
    });

    observer.observe(node);
    return () => observer.disconnect();
  }, [threshold, root, rootMargin, handleIntersection]);

  return [ref, isIntersecting, entry];
}

// Usage
function LazyImage({ src, alt }: { src: string; alt: string }) {
  const [ref, isVisible] = useIntersectionObserver({ triggerOnce: true, rootMargin: '200px' });

  return (
    <div ref={ref} style={{ minHeight: 200, background: '#f0f0f0' }}>
      {isVisible ? (
        <img src={src} alt={alt} loading="lazy" style={{ width: '100%', height: 'auto' }} />
      ) : (
        <div className="placeholder" />
      )}
    </div>
  );
}
```

## Custom Hook Composition

```typescript
import { useState, useEffect, useCallback } from 'react';

/* ---------- Composing multiple hooks together ---------- */

interface PaginationResult<T> {
  data: T[];
  isLoading: boolean;
  error: Error | null;
  page: number;
  totalPages: number;
  goToPage: (page: number) => void;
  nextPage: () => void;
  prevPage: () => void;
}

function usePaginatedFetch<T>(
  baseUrl: string,
  pageSize: number = 20,
): PaginationResult<T> {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<T[]>([]);
  const [totalPages, setTotalPages] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchPage = useCallback(async (pageNum: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const url = `${baseUrl}?page=${pageNum}&pageSize=${pageSize}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json.items ?? json.data ?? json);
      setTotalPages(json.totalPages ?? json.total_pages ?? 1);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setIsLoading(false);
    }
  }, [baseUrl, pageSize]);

  useEffect(() => {
    fetchPage(page);
  }, [page, fetchPage]);

  const goToPage = useCallback((p: number) => setPage(Math.max(1, Math.min(p, totalPages))), [totalPages]);
  const nextPage = useCallback(() => goToPage(page + 1), [page, goToPage]);
  const prevPage = useCallback(() => goToPage(page - 1), [page, goToPage]);

  return { data, isLoading, error, page, totalPages, goToPage, nextPage, prevPage };
}

/* ---------- Composable form hook ---------- */

interface FieldState<T> {
  value: T;
  error: string | null;
  touched: boolean;
  onChange: (value: T) => void;
  onBlur: () => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

function useField<T>(initialValue: T, validate?: (value: T) => string | null): FieldState<T> {
  const [value, setValue] = useState<T>(initialValue);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  const onChange = useCallback(
    (newValue: T) => {
      setValue(newValue);
      if (touched && validate) {
        setError(validate(newValue));
      }
    },
    [touched, validate],
  );

  const onBlur = useCallback(() => {
    setTouched(true);
    if (validate) setError(validate(value));
  }, [validate, value]);

  const reset = useCallback(() => {
    setValue(initialValue);
    setError(null);
    setTouched(false);
  }, [initialValue]);

  return { value, error, touched, onChange, onBlur, setError, reset };
}

// Usage of composed hooks
function ArticleList() {
  const { data, isLoading, error, page, totalPages, nextPage, prevPage } =
    usePaginatedFetch<{ id: number; title: string }>('/api/articles', 10);

  const searchField = useField('', (v) => (v.length < 2 ? 'Min 2 characters' : null));

  useEffect(() => {
    if (searchField.value) {
      // debounced search from composed hooks
    }
  }, [searchField.value]);

  if (error) return <div>Error: {error.message}</div>;
  return (
    <div>
      <input
        placeholder="Search articles..."
        value={searchField.value}
        onChange={(e) => searchField.onChange(e.target.value)}
        onBlur={searchField.onBlur}
      />
      {searchField.error && <span className="error">{searchField.error}</span>}

      {isLoading ? (
        <p>Loading...</p>
      ) : (
        <ul>
          {data.map((article) => (
            <li key={article.id}>{article.title}</li>
          ))}
        </ul>
      )}

      <div>
        <button onClick={prevPage} disabled={page <= 1}>Previous</button>
        <span> Page {page} of {totalPages} </span>
        <button onClick={nextPage} disabled={page >= totalPages}>Next</button>
      </div>
    </div>
  );
}
```