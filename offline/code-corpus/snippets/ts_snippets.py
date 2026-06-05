"""TypeScript snippets — 15 entries covering core TS patterns."""

SNIPPETS = [
    # ═══════════════════════════════════════════════════════════
    #  1. Basic Types & Type Inference
    # ═══════════════════════════════════════════════════════════
    ("typescript/basic-types.md", "typescript", ["pattern", "util"],
     "Basic Types & Type Inference",
     "TypeScript primitives: string, number, boolean, array, tuple, any, unknown, never, void with inference.",
     "reference",
     """// Basic primitive types
let name: string = 'Alice';
let age: number = 30;
let isActive: boolean = true;

// Arrays and tuples
let scores: number[] = [85, 92, 78];
let pair: [string, number] = ['age', 30];

// any — opt out of type checking
let loose: any = 'could be anything';
loose = 42; // no error

// unknown — type-safe version of any
let input: unknown = JSON.parse('{"id":1}');
if (typeof input === 'object' && input !== null) {
  const obj = input as Record<string, unknown>;
  console.log(obj['id']);
}

// never — function never returns
function fail(msg: string): never {
  throw new Error(msg);
}

// void — function returns nothing
function log(msg: string): void {
  console.log(msg);
}

// Type inference — type is inferred automatically
let inferred = 'hello'; // inferred as string
// inferred = 42; // Error: Type 'number' not assignable to 'string'
"""),

    # ═══════════════════════════════════════════════════════════
    #  2. Interfaces & Type Aliases
    # ═══════════════════════════════════════════════════════════
    ("typescript/interfaces-type-aliases.md", "typescript", ["pattern", "util"],
     "Interfaces & Type Aliases",
     "Interface vs type, extends, intersection types, Pick/Omit/Partial with interfaces.",
     "reference",
     """// Interface — extends, mergeable
interface User {
  id: number;
  name: string;
  email: string;
}

interface Admin extends User {
  role: 'admin';
  permissions: string[];
}

// Type alias — intersection, computed properties
type Point = { x: number; y: number };
type NamedPoint = Point & { name: string };

const origin: NamedPoint = { x: 0, y: 0, name: 'origin' };

// Utility transformations on interfaces
type PartialUser = Partial<User>;
type UserNameAndEmail = Pick<User, 'name' | 'email'>;
type WithoutEmail = Omit<User, 'email'>;

// Readonly
const frozen: Readonly<User> = {
  id: 1, name: 'Alice', email: 'a@b.com',
};
// frozen.name = 'Bob'; // Error: readonly

// Interface vs type — use interface for public APIs, type for unions/computed
type Status = 'active' | 'inactive' | 'pending';
"""),

    # ═══════════════════════════════════════════════════════════
    #  3. Generics
    # ═══════════════════════════════════════════════════════════
    ("typescript/generics.md", "typescript", ["pattern", "util"],
     "Generics",
     "Generic functions, constraints, generic interfaces, and default type parameters.",
     "reference",
     """// Generic function
function identity<T>(arg: T): T {
  return arg;
}

const num = identity<number>(42);
const str = identity('hello'); // inferred

// Generic interface
interface Repository<T> {
  getById(id: string): T | undefined;
  getAll(): T[];
  create(item: T): void;
}

// Generic constraint with extends
function getProperty<T, K extends keyof T>(obj: T, key: K): T[K] {
  return obj[key];
}

const user = { id: 1, name: 'Alice' };
const userName = getProperty(user, 'name'); // string

// Default type parameter
function createArray<T = string>(length: number, value: T): T[] {
  return Array(length).fill(value);
}

const strings = createArray(3, 'x'); // string[]
const numbers = createArray<number>(3, 0); // number[]

// Generic class
class Stack<T> {
  private items: T[] = [];
  push(item: T): void { this.items.push(item); }
  pop(): T | undefined { return this.items.pop(); }
}

const numStack = new Stack<number>();
numStack.push(1);
"""),

    # ═══════════════════════════════════════════════════════════
    #  4. Enums & Union Types
    # ═══════════════════════════════════════════════════════════
    ("typescript/enums-unions.md", "typescript", ["pattern", "util"],
     "Enums & Union Types",
     "String enums, const enums, discriminated unions, and literal types.",
     "reference",
     """// String enum
enum Direction {
  Up = 'UP',
  Down = 'DOWN',
  Left = 'LEFT',
  Right = 'RIGHT',
}

function move(direction: Direction): void {
  console.log(`Moving ${direction}`);
}

move(Direction.Up);

// Const enum — no runtime overhead, inlined at compile time
const enum Colors {
  Red = '#FF0000',
  Green = '#00FF00',
  Blue = '#0000FF',
}

const red = Colors.Red;

// Literal union type
type Status = 'idle' | 'loading' | 'success' | 'error';

function handleStatus(s: Status): string {
  switch (s) {
    case 'idle': return 'Waiting...';
    case 'loading': return 'Loading...';
    case 'success': return 'Done!';
    case 'error': return 'Failed!';
  }
}

// Discriminated union — tagged with a literal type property
interface Circle { kind: 'circle'; radius: number; }
interface Square { kind: 'square'; sideLength: number; }
type Shape = Circle | Square;

function area(shape: Shape): number {
  if (shape.kind === 'circle') {
    return Math.PI * shape.radius ** 2;
  }
  return shape.sideLength ** 2;
}
"""),

    # ═══════════════════════════════════════════════════════════
    #  5. Type Guards & Narrowing
    # ═══════════════════════════════════════════════════════════
    ("typescript/type-guards.md", "typescript", ["pattern", "util"],
     "Type Guards & Narrowing",
     "typeof, instanceof, in, discriminated union narrowing, and type predicates.",
     "reference",
     """// typeof guard
function format(value: string | number): string {
  if (typeof value === 'string') {
    return value.toUpperCase();
  }
  return value.toFixed(2);
}

// instanceof guard
class APIError extends Error {
  constructor(public statusCode: number, message: string) {
    super(message);
  }
}

function handleError(err: Error | APIError): void {
  if (err instanceof APIError) {
    console.error(`API ${err.statusCode}: ${err.message}`);
  } else {
    console.error(err.message);
  }
}

// 'in' operator guard
interface Fish { swim(): void; }
interface Bird { fly(): void; }

function move(animal: Fish | Bird): void {
  if ('swim' in animal) {
    animal.swim();
  } else {
    animal.fly();
  }
}

// Type predicate — custom type guard function
function isFish(pet: Fish | Bird): pet is Fish {
  return (pet as Fish).swim !== undefined;
}

function feed(pet: Fish | Bird): void {
  if (isFish(pet)) {
    pet.swim(); // narrowed to Fish
  }
}
"""),

    # ═══════════════════════════════════════════════════════════
    #  6. Utility Types
    # ═══════════════════════════════════════════════════════════
    ("typescript/utility-types.md", "typescript", ["pattern", "util"],
     "Utility Types",
     "Partial, Required, Readonly, Record, Pick, Omit, Exclude, Extract, ReturnType, Parameters.",
     "reference",
     """interface User {
  id: number;
  name: string;
  email: string;
  role: 'admin' | 'user';
}

// Partial — all properties optional
const partial: Partial<User> = { name: 'Alice' };

// Required — all properties required (even optional ones)
type RequiredFields = Required<Partial<User>>;

// Readonly — no mutation allowed
const frozen: Readonly<User> = { id: 1, name: 'A', email: 'a@b.com', role: 'admin' };

// Record — dictionary with constrained keys
type Page = 'home' | 'about' | 'contact';
const routes: Record<Page, string> = {
  home: '/',
  about: '/about',
  contact: '/contact',
};

// Pick — select specific keys
const picked: Pick<User, 'id' | 'name'> = { id: 1, name: 'Alice' };

// Omit — exclude specific keys
const withoutRole: Omit<User, 'role'> = { id: 1, name: 'A', email: 'a@b.com' };

// Exclude — remove from union
type Roles = 'admin' | 'user' | 'guest';
type NonAdmin = Exclude<Roles, 'admin'>; // 'user' | 'guest'

// ReturnType — infer return type of a function
const createUser = (name: string): User => ({ id: 1, name, email: '', role: 'user' });
type NewUser = ReturnType<typeof createUser>;

// Parameters — infer parameter types
type CreateUserParams = Parameters<typeof createUser>; // [string]
"""),

    # ═══════════════════════════════════════════════════════════
    #  7. tsconfig.json Setup
    # ═══════════════════════════════════════════════════════════
    ("typescript/tsconfig-setup.md", "typescript", ["config", "util"],
     "tsconfig.json Setup",
     "Strict mode, path aliases, module resolution, target, and lib configuration.",
     "reference",
     """{
  "compilerOptions": {
    /* Strict mode — enables all strict checks */
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "strictFunctionTypes": true,
    "strictBindCallApply": true,
    "noUncheckedIndexedAccess": true,

    /* Module resolution */
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],

    /* Path aliases — must match bundler config too */
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"],
      "@utils/*": ["src/utils/*"]
    },

    /* Output */
    "outDir": "./dist",
    "rootDir": "./src",
    "sourceMap": true,
    "declaration": true,

    /* Interop */
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "skipLibCheck": true,
    "resolveJsonModule": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "**/*.test.ts"]
}
"""),

    # ═══════════════════════════════════════════════════════════
    #  8. React with TypeScript
    # ═══════════════════════════════════════════════════════════
    ("typescript/react-typescript.md", "typescript", ["web", "pattern"],
     "React with TypeScript",
     "FC, PropsWithChildren, typed useState/useEffect, event handlers, and refs.",
     "framework",
     """import React, { FC, PropsWithChildren, useState, useEffect, useRef, ChangeEvent } from 'react';

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
"""),

    # ═══════════════════════════════════════════════════════════
    #  9. Express with TypeScript
    # ═══════════════════════════════════════════════════════════
    ("typescript/express-typescript.md", "typescript", ["web", "api", "pattern"],
     "Express with TypeScript",
     "Typed Request/Response/NextFunction, typed middleware, and route handlers.",
     "framework",
     """import express, { Request, Response, NextFunction } from 'express';
import { ErrorRequestHandler } from 'express-serve-static-core';

const app = express();
app.use(express.json());

// Typed request body
interface CreateUserBody {
  name: string;
  email: string;
}

interface UserResponse {
  id: number;
  name: string;
  email: string;
}

app.post('/api/users', (req: Request<{}, {}, CreateUserBody>, res: Response<UserResponse>) => {
  const { name, email } = req.body;
  const user: UserResponse = { id: Date.now(), name, email };
  res.status(201).json(user);
});

// Typed route params
app.get('/api/users/:id', (req: Request<{ id: string }>, res: Response<UserResponse | { error: string }>) => {
  const id = parseInt(req.params.id, 10);
  if (id !== 1) {
    res.status(404).json({ error: 'Not found' });
    return;
  }
  res.json({ id, name: 'Alice', email: 'alice@example.com' });
});

// Typed error-handling middleware
const errorHandler: ErrorRequestHandler = (err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Internal server error' });
};
app.use(errorHandler);

// Typed middleware
const logger: express.RequestHandler = (req, res, next) => {
  console.log(`${req.method} ${req.path}`);
  next();
};
app.use(logger);

app.listen(3000);
"""),

    # ═══════════════════════════════════════════════════════════
    #  10. Zod Validation
    # ═══════════════════════════════════════════════════════════
    ("typescript/zod-validation.md", "typescript", ["pattern", "util", "api"],
     "Zod Validation",
     "Schema definition with z.object, parse/safeParse, inferred types from schemas.",
     "library",
     """import { z } from 'zod';

// Define schema
const UserSchema = z.object({
  id: z.number().int().positive(),
  name: z.string().min(1).max(100),
  email: z.string().email(),
  age: z.number().int().min(0).optional(),
  role: z.enum(['admin', 'user', 'guest']).default('user'),
});

// Infer TypeScript type from schema
type User = z.infer<typeof UserSchema>;

// Parse with validation — throws on failure
const rawData = { id: 1, name: 'Alice', email: 'alice@example.com', age: 30 };
const user: User = UserSchema.parse(rawData);

// Safe parse — returns result object, no throw
const result = UserSchema.safeParse({ id: -1, name: '', email: 'bad' });
if (!result.success) {
  console.error(result.error.format());
  // {
  //   id: { _errors: ['Number must be positive'] },
  //   name: { _errors: ['String must contain at least 1 character(s)'] },
  //   email: { _errors: ['Invalid email'] },
  // }
}

// Partial and pick from schemas
const PartialUserSchema = UserSchema.partial();
const UserNameSchema = UserSchema.pick({ name: true, email: true });
"""),

    # ═══════════════════════════════════════════════════════════
    #  11. Async/Await with Types
    # ═══════════════════════════════════════════════════════════
    ("typescript/async-await.md", "typescript", ["async", "pattern", "util"],
     "Async/Await with Types",
     "Typed Promise return values, async error handling, Promise.all typing.",
     "pattern",
     """interface ApiResponse<T> {
  data: T;
  status: number;
  message: string;
}

// Typed async function
async function fetchUser(id: number): Promise<ApiResponse<{ name: string; email: string }>> {
  const res = await fetch(`/api/users/${id}`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }
  return res.json();
}

// Typed error handling with async
async function getUser(id: number): Promise<string | null> {
  try {
    const response = await fetchUser(id);
    return response.data.name;
  } catch (err: unknown) {
    if (err instanceof Error) {
      console.error(`Failed to fetch user: ${err.message}`);
    }
    return null;
  }
}

// Promise.all with typed results
async function fetchMultiple(): Promise<[string, number]> {
  const [name, count] = await Promise.all([
    fetchUser(1).then(r => r.data.name),
    Promise.resolve(42),
  ]);
  return [name, count];
}

// Typed async generator
async function* generatePages(max: number): AsyncGenerator<number[], void, unknown> {
  for (let page = 1; page <= max; page++) {
    yield [page]; // simulated page data
  }
}

// Awaited helper — unwrap Promise type
type UserResponse = Awaited<ReturnType<typeof fetchUser>>;
"""),

    # ═══════════════════════════════════════════════════════════
    #  12. Classes & Access Modifiers
    # ═══════════════════════════════════════════════════════════
    ("typescript/classes-modifiers.md", "typescript", ["pattern", "util"],
     "Classes & Access Modifiers",
     "public/private/protected, readonly, abstract class, implements interface.",
     "reference",
     """// Interface for class contract
interface Drawable {
  draw(): void;
}

// Abstract class
abstract class Shape {
  constructor(protected readonly name: string) {}

  abstract area(): number;

  describe(): void {
    console.log(`Shape: ${this.name}, area: ${this.area()}`);
  }
}

// Class implementing interface and extending abstract class
class Circle extends Shape implements Drawable {
  // public (default), private, protected, readonly
  private _radius: number;

  constructor(name: string, radius: number) {
    super(name);
    this._radius = radius;
  }

  // Getter
  get radius(): number {
    return this._radius;
  }

  // Setter
  set radius(value: number) {
    if (value <= 0) throw new Error('Radius must be positive');
    this._radius = value;
  }

  // Abstract method implementation
  area(): number {
    return Math.PI * this._radius ** 2;
  }

  // Interface implementation
  draw(): void {
    console.log(`Drawing a circle with radius ${this._radius}`);
  }
}

const circle = new Circle('MyCircle', 5);
console.log(circle.area()); // ~78.54
circle.draw();
// circle._radius; // Error: private
// circle.name;    // Error: protected
"""),

    # ═══════════════════════════════════════════════════════════
    #  13. Declaration Files (.d.ts)
    # ═══════════════════════════════════════════════════════════
    ("typescript/declaration-files.md", "typescript", ["config", "util"],
     "Declaration Files (.d.ts)",
     "Global type declarations, module augmentation, ambient declarations for JS libs.",
     "reference",
     """// ── types/globals.d.ts ──
// Ambient global variable
declare const APP_VERSION: string;

// Global interface augmentation
interface Window {
  analytics?: {
    track(event: string, data?: Record<string, unknown>): void;
  };
}

// Ambient module declaration for untyped JS lib
declare module 'old-js-library' {
  export function doSomething(config: Record<string, unknown>): void;
  export const VERSION: string;
}

// ── types/env.d.ts ──
// Augment existing module
declare namespace NodeJS {
  interface ProcessEnv {
    NODE_ENV: 'development' | 'production' | 'test';
    API_KEY: string;
    DATABASE_URL: string;
  }
}

// ── types/images.d.ts ──
// Declare module for non-code imports
declare module '*.svg' {
  const content: string;
  export default content;
}

declare module '*.module.css' {
  const classes: { readonly [key: string]: string };
  export default classes;
}

// Usage throughout app:
// const key: string = process.env.API_KEY;
// if (APP_VERSION === '1.0.0') { ... }
// import config from 'old-js-library';
"""),

    # ═══════════════════════════════════════════════════════════
    #  14. Mapped & Conditional Types
    # ═══════════════════════════════════════════════════════════
    ("typescript/mapped-conditional.md", "typescript", ["pattern", "util"],
     "Mapped & Conditional Types",
     "keyof, in keyof, mapped type modifiers, conditional extends, infer keyword.",
     "reference",
     """// Mapped type — transform all properties
type Readonly<T> = {
  readonly [K in keyof T]: T[K];
};

type Optional<T> = {
  [K in keyof T]?: T[K];
};

// Mapped type with property filtering
type Getters<T> = {
  [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K];
};

interface Person {
  name: string;
  age: number;
}

// { getName: () => string; getAge: () => number }
type PersonGetters = Getters<Person>;

// Conditional type
type IsString<T> = T extends string ? true : false;
type A = IsString<'hello'>; // true
type B = IsString<42>;      // false

// Conditional with infer — extract unwrapped type
type UnwrapPromise<T> = T extends Promise<infer U> ? U : T;
type C = UnwrapPromise<Promise<string>>; // string
type D = UnwrapPromise<number>;          // number

// Recursive conditional — flatten array of arrays
type Flatten<T> = T extends Array<infer U> ? Flatten<U> : T;
type E = Flatten<number[][][]>; // number

// Conditional type with function arguments
type FirstArg<T> = T extends (arg: infer A, ...rest: unknown[]) => unknown ? A : never;
type F = FirstArg<(name: string, age: number) => void>; // string
"""),

    # ═══════════════════════════════════════════════════════════
    #  15. Node.js with TypeScript
    # ═══════════════════════════════════════════════════════════
    ("typescript/nodejs-typescript.md", "typescript", ["io", "file", "sys", "net", "config"],
     "Node.js with TypeScript",
     "Typed fs/path/http, @types packages, ESM vs CJS module configuration.",
     "pattern",
     """import fs from 'node:fs/promises';
import path from 'node:path';
import http, { IncomingMessage, ServerResponse } from 'node:http';

// Typed file read/write
interface Config {
  port: number;
  host: string;
  debug: boolean;
}

async function readConfig(filePath: string): Promise<Config> {
  const raw = await fs.readFile(filePath, 'utf-8');
  const config: Config = JSON.parse(raw);
  return config;
}

// Typed HTTP server
const server = http.createServer(
  async (req: IncomingMessage, res: ServerResponse) => {
    res.setHeader('Content-Type', 'application/json');

    if (req.url === '/api/health') {
      res.writeHead(200);
      res.end(JSON.stringify({ status: 'ok' }));
      return;
    }

    res.writeHead(404);
    res.end(JSON.stringify({ error: 'Not found' }));
  },
);

// ESM — package.json: "type": "module"
// import fs from 'node:fs/promises';  ✓
// CJS — package.json: no "type" or "type": "commonjs"
// import fs = require('node:fs');      ✓

// @types packages — always install dev dependencies
// npm install -D @types/node @types/express @types/react

// Path operations — typed and cross-platform
const dataDir = path.join(process.cwd(), 'data');
const logFile = path.resolve(dataDir, 'app.log');

server.listen(3000, () => {
  console.log(`Server running on port 3000`);
});
"""),
]
