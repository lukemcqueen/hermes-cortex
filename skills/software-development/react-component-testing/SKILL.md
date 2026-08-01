---
name: react-component-testing
description: "React component testing patterns — mocking UI libraries (recharts), React Query, MSW with direct fetch, file upload flows, browser API stubs that don't break jsdom/React, vitest hoisting, and state-vs-data pitfalls."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [react, testing, vitest, recharts, react-query, msw, jsdom, browser-apis, file-upload, fetch]
    related_skills: [test-driven-development, react-best-practices]
---

# React Component Testing Patterns

## Overview

Testing React components that use third-party chart libraries (recharts), data-fetching (React Query), and internal state requires specific mocking strategies because these libraries don't render properly in jsdom. This skill captures proven patterns and common pitfalls, distilled from real test suites that fought every one of these battles.

## When to Use

- Testing components that render recharts or other SVG-based chart libraries
- Testing components using `useQuery` from React Query
- Testing components with MSW-intercepted `fetch` calls
- Testing file upload flows
- Testing components that touch browser APIs (ResizeObserver, matchMedia, scrollTo, IntersectionObserver)
- Any vitest + jsdom setup hitting "not implemented" errors
- Debugging flaky component tests

## Core Principles

### 1. Test behavior, not implementation

Assert on what the user sees and does — rendered text, roles, calls to
handlers — not on internal function calls or DOM structure. If a test must
reach into internals, that's a signal the component is over-coupling.

### 2. One mock layer, not three

Mock the **boundary** — the network (MSW), the third-party library (recharts),
the browser API (ResizeObserver). Don't mock your own API modules AND the
fetch layer AND the component's props. Choose the outermost layer that keeps
the test deterministic.

### 3. retry: false everywhere in tests

React Query retries failed queries by default. In tests, a transient failure
becomes a 3× retry loop that makes `waitFor` flaky or hangs:

```tsx
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});
```

## Pattern 1 — Mocking recharts

recharts uses ResizeObserver + SVG rendering that breaks in jsdom. Mock the
library itself. This is the ONLY reliable way — trying to make recharts
render in jsdom is a rabbit hole:

```tsx
// __mocks__/recharts.tsx
export const ResponsiveContainer = ({ children }: any) => <div>{children}</div>;
export const BarChart = ({ children }: any) => <div data-testid="bar-chart">{children}</div>;
export const Bar = () => <div />;
export const XAxis = () => <div />;
export const YAxis = () => <div />;
export const Tooltip = () => <div />;
export const CartesianGrid = () => <div />;
export const Legend = () => <div />;
```

```tsx
// in the test
vi.mock("recharts");
```

Assert on the wrapper testid, not SVG internals:

```tsx
expect(screen.getByTestId("bar-chart")).toBeInTheDocument();
expect(screen.getByTestId("bar-chart")).toHaveTextContent("Expected Label");
```

### If the chart must show real data

Render the data through the mock's children — pass the same data props and
assert the mock receives them:

```tsx
const { container } = render(<BarChart data={mockData} />);
// The mock renders children; assert labels appear
```

## Pattern 2 — React Query

### Wrapper

```tsx
function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}
```

### Async data resolution

```tsx
await waitFor(() => {
  expect(screen.getByText("Loaded data")).toBeInTheDocument();
});
```

### Loading state

```tsx
// Initial render shows loading
expect(screen.getByTestId("loading")).toBeInTheDocument();
// After resolution
await waitFor(() => expect(screen.queryByTestId("loading")).not.toBeInTheDocument());
```

### Error state

```tsx
server.use(
  http.get("/api/items", () => HttpResponse.json({ message: "boom" }, { status: 500 }))
);
await waitFor(() => expect(screen.getByText(/error/i)).toBeInTheDocument());
```

### Invalidation after mutation

```tsx
await userEvent.click(screen.getByRole("button", { name: /save/i }));
await waitFor(() => expect(mockFn).toHaveBeenCalled());
```

## Pattern 3 — MSW with direct fetch

MSW intercepts at the network boundary, so your components exercise their
REAL fetch/axios code — no mocking of your own API layer:

```ts
// mocks/server.ts
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

export const server = setupServer(
  http.get("/api/items", () => HttpResponse.json([{ id: 1, name: "alpha" }])),
  http.post("/api/items", async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json({ id: 2, ...body }, { status: 201 });
  })
);
```

```ts
// vitest.setup.ts
import { server } from "./mocks/server";

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

### Per-test overrides

```tsx
server.use(
  http.get("/api/items", () => HttpResponse.json([], { status: 200 }))
);
```

### Why MSW over module mocks

- Your API module's real code runs — URL building, error mapping, response
  parsing all get tested.
- No drift between "what the mock returns" and "what the API really returns".
- Adding a new endpoint to a component test is a one-line handler, not a
  new module mock.

## Pattern 4 — File upload flows

```tsx
import userEvent from "@testing-library/user-event";

it("shows the uploaded file name", async () => {
  const file = new File(["name,value\n1,2"], "data.csv", { type: "text/csv" });
  const input = screen.getByLabelText(/upload/i) as HTMLInputElement;

  await userEvent.upload(input, file);

  expect(screen.getByText("data.csv")).toBeInTheDocument();
});
```

### Multiple files

```tsx
const files = [
  new File(["a"], "a.csv", { type: "text/csv" }),
  new File(["b"], "b.csv", { type: "text/csv" }),
];
await userEvent.upload(input, files);
```

### Drag-and-drop

```tsx
const dropzone = screen.getByTestId("dropzone");
await userEvent.upload(dropzone, file);
```

## Pattern 5 — Browser API stubs

jsdom doesn't implement ResizeObserver, matchMedia, scrollTo,
IntersectionObserver, or URL.createObjectURL. Stub them in a setup file —
minimally, so you don't mask real behavior:

```ts
// vitest.setup.ts
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
global.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

Object.defineProperty(window, "scrollTo", {
  writable: true,
  value: () => {},
});
```

### URL.createObjectURL / revokeObjectURL

Used by file-preview components. jsdom has neither:

```ts
global.URL.createObjectURL = vi.fn(() => "blob:mock-url");
global.URL.revokeObjectURL = vi.fn();
```

## Pattern 6 — vitest hoisting

`vi.mock` calls are hoisted above imports. You CANNOT reference variables
declared after the imports inside the factory — the reference is undefined
at hoist time. Use `vi.hoisted`:

```tsx
const { mockFn } = vi.hoisted(() => ({ mockFn: vi.fn() }));

vi.mock("../api", () => ({ fetchData: mockFn }));
```

Without `vi.hoisted`, the classic error is `ReferenceError: Cannot access
'mockFn' before initialization`.

### Mocking a hook module

```tsx
const { useUser } = vi.hoisted(() => ({ useUser: vi.fn() }));

vi.mock("../hooks/use-user", () => ({ useUser }));

useUser.mockReturnValue({ id: 1, name: "Ada" });
```

## State-vs-Data Pitfall

A component re-renders for **state changes** (interaction) AND **data
changes** (query refetch). When a test fails, classify first:

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Text updates after click, but fetch mock never called | State path only — the click doesn't refetch | Assert on state-driven render; the test is correct as written |
| Data renders but interaction assertions fail | The interaction triggers a refetch that resets state | Mock the refetch (return cached data), assert state after |
| `waitFor` times out | retry: true, or the query never resolves | retry: false; check the MSW handler matches the URL |
| Flaky across runs | Shared module state / no cleanup | Reset handlers + clear QueryClient between tests |

**Never conflate the two:** a passing interaction test with a broken fetch
mock tells you nothing about data rendering. Write separate tests for
state-driven and data-driven behavior.

## Async Utils — waitFor vs findBy

- `screen.findByText()` — waits for an element; prefer over
  `waitFor(() => screen.getByText())` when asserting existence.
- `waitFor` — use when the condition isn't a single element (e.g., a mock
  was called, a count changed).

```tsx
// Prefer
expect(await screen.findByText("Loaded")).toBeInTheDocument();

// Over
await waitFor(() => expect(screen.getByText("Loaded")).toBeInTheDocument());
```

## Pitfalls Checklist

- ❌ **Full recharts render** — SVG in jsdom is not layout; always mock the library
- ❌ **`retry: true` in tests** — failed queries retry and make `waitFor` flaky
- ❌ **No cleanup between tests** — stale DOM/query cache leaks across tests
- ❌ **Mocking your own API module instead of MSW** — locks in implementation details
- ❌ **`vi.mock` factory referencing outer variables** — use `vi.hoisted`
- ❌ **Asserting on SVG internals** — brittle; assert on testids/text
- ❌ **Not resetting MSW handlers** — per-test overrides leak into later tests
- ❌ **`userEvent` not awaited** — unawaited userEvent causes act warnings and flakiness
- ❌ **Testing library not installed** — `@testing-library/react` + `@testing-library/jest-dom` + `@testing-library/user-event` are required; `user-event` needs a setup entry

## Verification

```bash
# Run the component test suite
pnpm vitest run --reporter=verbose

# Confirm zero failures and zero act() warnings
# Act warnings hide real bugs — don't suppress them with console.error mocks
```

## Related
- `test-driven-development` — RED-GREEN-REFACTOR discipline
- `react-best-practices` — performance/quality rules
- `react-composition-patterns` — component structure that makes testing easier
- `storybook-setup` — Storybook for component documentation
- `change-test-loop` — small changes, verified
