---
language: typescript
tags: [errors, debugging, javascript, troubleshooting]
title: Common JavaScript / TypeScript Errors
description: Frequent JS/TS errors — Cannot read property of undefined, CORS, Unexpected token, webpack/vite build failures, null is not an object, React hook rules — with messages, causes, and fixes
source: pattern
---

```typescript
// ---------------------------------------------------------------------------
// 1. Cannot read properties of undefined / Cannot read property 'x' of undefined
// ---------------------------------------------------------------------------
// Error message (browser):
//   TypeError: Cannot read properties of undefined (reading 'name')
//   Cannot read property 'name' of undefined
//
// Error message (Node):
//   TypeError: Cannot read property 'x' of undefined
//
// Cause:
//   - Accessing a property on an object that is undefined
//   - API response is not what you expected (null/undefined instead of object)
//   - React: accessing state before it's initialized
//
// Fixes:

// Fix 1: Optional chaining (?.) — returns undefined instead of throwing
interface User {
  name?: string;
  address?: { city?: string };
}
const user: User | undefined = undefined;
console.log(user?.name);              // undefined (no error)
console.log(user?.address?.city);     // undefined (no error)

// Fix 2: Default value with nullish coalescing (??)
const city = user?.address?.city ?? "Unknown";

// Fix 3: Guard with early return
function greet(user: User | undefined) {
  if (!user) return "Hello, guest";
  return `Hello, ${user.name ?? "friend"}`;
}

// Fix 4: Check API response shape
// fetch("/api/user")
//   .then(res => res.json())
//   .then(data => {
//     if (data?.user?.name) {
//       setName(data.user.name);
//     }
//   });

// ---------------------------------------------------------------------------
// 2. CORS errors
// ---------------------------------------------------------------------------
// Error message:
//   Access to fetch at 'https://api.example.com/data' from origin
//   'http://localhost:3000' has been blocked by CORS policy:
//   No 'Access-Control-Allow-Origin' header is present
//
// Cause:
//   - Browser enforces same-origin policy — frontend (localhost:3000) trying to
//     call an API on a different domain/port/protocol
//   - Server doesn't include CORS headers in the response
//
// Fixes:

// Fix 1: Configure CORS on the server (Express example)
// npm install cors
// import cors from "cors";
// app.use(cors({ origin: "http://localhost:3000" }));

// Fix 2: Use a proxy in development (Vite)
// In vite.config.ts:
// export default defineConfig({
//   server: {
//     proxy: {
//       "/api": {
//         target: "https://api.example.com",
//         changeOrigin: true,
//       },
//     },
//   },
// });

// Fix 3: CORS browser extension (dev only — never for production)

// Fix 4: Use JSONP (legacy, GET-only workaround)
// <script src="https://api.example.com/data?callback=handleData"></script>

// Fix 5: For simple requests, add the header server-side
// Access-Control-Allow-Origin: http://localhost:3000
// or
// Access-Control-Allow-Origin: *  (not recommended for production)

// ---------------------------------------------------------------------------
// 3. Unexpected token / SyntaxError
// ---------------------------------------------------------------------------
// Error message:
//   SyntaxError: Unexpected token ';'
//   SyntaxError: Unexpected token 'export'
//   Unexpected token '<'  (in React apps — serving index.html as JS)
//
// Cause:
//   - Missing comma, bracket, or parenthesis
//   - Using ES module syntax in CommonJS file (or vice versa)
//   - Webpack/Vite not configured for JSX or TypeScript
//   - Server returns HTML (404 page) instead of JS bundle
//
// Fixes:

// Fix 1: Check for missing commas / brackets in objects
// ❌ Missing comma
// const obj = { a: 1 b: 2 };
// ✅
const obj = { a: 1, b: 2 };

// Fix 2: Fix module system mismatch
// package.json "type": "module" + require() → use import
// package.json "type": "commonjs" + import → use require
// Or rename .mjs / .cjs to override

// Fix 3: Ensure JSX/TSX is configured
// tsconfig.json — "jsx": "react-jsx"
// vite.config.ts — @vitejs/plugin-react

// Fix 4: Check that the build output exists and is the right file
// Verify dist/ folder, check webpack output path

// ---------------------------------------------------------------------------
// 4. Webpack / Vite build failures
// ---------------------------------------------------------------------------
// Error message:
//   Module not found: Error: Can't resolve 'react-icons/fi'
//   Module build failed: SyntaxError: Unexpected token (in JSX file)
//   [vite] Internal server error: Failed to resolve import "xxx"
//
// Cause:
//   - Missing dependency
//   - Missing loader/plugin for the file type (JSX, TypeScript, CSS modules, etc.)
//   - Case-sensitive import on case-insensitive filesystem (macOS dev → Linux CI)
//   - Path alias not configured
//
// Fixes:

// Fix 1: Install missing dependency
// npm install react-icons

// Fix 2: Configure loaders (Webpack)
// module: {
//   rules: [
//     { test: /\.tsx?$/, use: "ts-loader", exclude: /node_modules/ },
//     { test: /\.css$/, use: ["style-loader", "css-loader"] },
//   ],
// }

// Fix 3: Configure aliases
// Webpack:
// resolve: { alias: { "@": path.resolve(__dirname, "src") } }
// Vite:
// resolve: { alias: { "@": "/src" } }

// Fix 4: Check case sensitivity — macOS is case-insensitive, Linux is not
// ❌ import Button from "./components/button";   // File is Button.tsx
// ✅ import Button from "./components/Button";

// Fix 5: Clear cache
// rm -rf node_modules/.cache && npm run build

// ---------------------------------------------------------------------------
// 5. null is not an object / null is not an object (evaluating '...')
// ---------------------------------------------------------------------------
// Error message:
//   TypeError: null is not an object (evaluating 'document.getElementById')
//   TypeError: null is not an object
//
// Cause:
//   - DOM element doesn't exist when script runs
//   - Script tag runs before the DOM is loaded
//   - document.querySelector returns null when no element matches
//
// Fixes:

// Fix 1: Wait for DOM to be ready
document.addEventListener("DOMContentLoaded", () => {
  const el = document.getElementById("my-element");
  if (el) {
    el.textContent = "Loaded!";
  }
});

// Fix 2: Use optional chaining
const text = document.getElementById("my-element")?.textContent ?? "default";

// Fix 3: Move the <script> tag to the bottom of <body>
// <body>
//   <div id="app"></div>
//   <script src="app.js"></script>
// </body>

// Fix 4: Use defer attribute on script tag
// <script src="app.js" defer></script>

// ---------------------------------------------------------------------------
// 6. React Hook rules violations
// ---------------------------------------------------------------------------
// Error messages:
//   React Hook "useState" is called conditionally.
//   React Hook "useEffect" may be executed more than once.
//   React has detected a change in the order of Hooks...
//
// Cause:
//   - Calling hooks inside if/for/while blocks or after early returns
//   - Calling hooks inside callbacks or event handlers
//   - Hooks called in a different order between renders
//
// Fixes:

// ❌ Wrong — hook inside condition
// function MyComponent({ enabled }: { enabled: boolean }) {
//   if (enabled) {
//     const [data, setData] = useState(null);  // ERROR
//   }
// }

// ✅ Correct — hooks always at top level
function MyComponent({ enabled }: { enabled: boolean }) {
  const [data, setData] = useState(null);   // Always called

  useEffect(() => {
    if (enabled) {
      fetchData().then(setData);
    }
  }, [enabled]);

  return <div>{data}</div>;
}

// ❌ Wrong — hook inside callback
// const handleClick = () => {
//   const [count, setCount] = useState(0);  // ERROR
// };

// ✅ Correct — hooks at component top level
function Counter() {
  const [count, setCount] = useState(0);
  const handleClick = () => setCount(c => c + 1);
  return <button onClick={handleClick}>{count}</button>;
}

// ❌ Wrong — early return before hooks
// function User({ id }: { id?: string }) {
//   if (!id) return null;
//   const [user, setUser] = useState(null);  // ERROR
// }

// ✅ Correct — hooks before early return
function User({ id }: { id?: string }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (id) fetch(`/api/users/${id}`).then(res => res.json()).then(setUser);
    setLoading(false);
  }, [id]);

  if (!id) return <p>No user selected</p>;
  if (loading) return <p>Loading...</p>;
  return <p>{user?.name}</p>;
}
```