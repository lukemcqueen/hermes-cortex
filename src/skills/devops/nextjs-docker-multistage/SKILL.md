---
name: nextjs-docker-multistage
description: "Next.js Docker multi-stage builds with standalone output — minimal runtime images, no node_modules in production"
version: 1.0.0
author: Titus
metadata:
  tags: [nextjs, docker, multi-stage, standalone, best-practices]
---

# Next.js Docker Multi-Stage Build (Standalone Output)

## When to Use

- Creating or updating a Dockerfile for a standalone Next.js app (not a monorepo package)
- Reviewing a Dockerfile that copies `node_modules` into the runtime image
- Debugging large image sizes (>500MB) for a Next.js production container
- **For pnpm workspace monorepo builds**, use `pnpm-monorepo-docker` instead (standalone output path differs)

## The Problem

Naive Dockerfiles copy `node_modules` directly into the final image:

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY . .
RUN npm install && npm run build

FROM node:22-alpine
WORKDIR /app
COPY --from=build /app/node_modules ./node_modules   # ← bloated, fragile
COPY --from=build /app/.next ./.next
CMD ["npm", "start"]
```

Issues:
- **Image bloat** — `node_modules` includes dev deps (TypeScript, ESLint, vitest, etc.)
- **OS-native binaries** — `sharp`, `@swc/core` are built for the host arch, not the container's target arch
- **Security surface** — every transitive dep is an extra CVE vector
- **Startup overhead** — Node.js has to resolve modules from thousands of files

## The Fix: Standalone Output

Next.js `output: 'standalone'` traces all runtime dependencies into `.next/standalone/` — producing a self-contained bundle with only the code actually needed at runtime.

**Two approaches for the Dockerfile build stage:**

- **Multi-stage `deps` + `build` + `runtime`** (below) — uses `pnpm fetch` to populate the pnpm store in a deps layer, then `pnpm install --offline` to rebuild symlinks in build. Good for large monorepos where lockfile rarely changes. See `pnpm-monorepo-docker` §8 for symlink caveats.
- **Single-stage `build` + `runtime`** — simpler, runs `pnpm install --frozen-lockfile --prod` directly. Layer caching still works because `package.json` and `pnpm-lock.yaml` change less often than source. Preferred for standalone apps where the extra `deps` stage adds complexity. See the Alternative box at the end of Step 2.

**`--prod` vs `--no-dev`:** `--no-dev` is NOT a valid pnpm flag. It is silently ignored, causing ALL devDependencies to be installed. But `--prod` strips devDeps, which may be needed for the build (tailwindcss, postcss, typescript). **Strategy:**
- **Multi-stage builds** (with a `deps` stage): Omit `--prod` in the build stage. Use `pnpm install --offline --frozen-lockfile` so devDeps are available for `next build`. The standalone runtime excludes them.
- **Single-stage builds**: Use `pnpm install --frozen-lockfile --prod` but move build tools (tailwindcss, postcss, typescript) from devDependencies to dependencies in package.json.

### Step 1: Enable standalone in next.config

```ts
// next.config.ts
const nextConfig: NextConfig = {
  output: 'standalone',
  // ... other config
};
```

### Step 2: Multi-stage Dockerfile

```dockerfile
# ── Deps: install all dependencies ──
FROM node:22-alpine AS deps
RUN corepack enable && corepack prepare pnpm@10 --activate
WORKDIR /app
COPY pnpm-lock.yaml package.json ./
RUN pnpm fetch --frozen-lockfile

# ── Build: compile the app ──
FROM node:22-alpine AS build
RUN corepack enable && corepack prepare pnpm@10 --activate
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY pnpm-lock.yaml package.json ./
# NOTE: No --prod flag — devDeps (tailwindcss, postcss, typescript) are
# needed for next build. Standalone output traces only runtime deps,
# so devDeps do not leak into the runtime image.
RUN pnpm install --offline --frozen-lockfile
COPY . .
RUN pnpm build

# ── Runtime: standalone only ──
FROM node:22-alpine AS runtime
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs
WORKDIR /app

# Copy standalone bundle (self-contained, no node_modules needed)
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
# Copy static assets (served by Next.js directly)
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
# Copy public assets
COPY --from=build --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000
ENV PORT=3000
CMD ["node", "server.js"]
```

**No ARG NEXT_PUBLIC_API_URL needed** when using Next.js rewrites. See "Rewrites Alternative" below.

The runtime image contains ONLY:
- `server.js` + traced runtime code (~5-20MB)
- `.next/static/` (compiled chunks, ~200KB-2MB)
- `public/` (static assets)
- No `node_modules/`, no dev tools, no source files

**Alternative — single-stage build (simpler, no `deps` stage):**

```dockerfile
FROM node:22-alpine AS build
RUN corepack enable && corepack prepare pnpm@10 --activate
WORKDIR /app

# Layer 1: deps (cached until package.json or lockfile changes)
COPY package.json pnpm-lock.yaml .npmrc ./
RUN pnpm install --frozen-lockfile --prod

# Layer 2: source (invalidates on any file change)
COPY . .
RUN pnpm build

FROM node:22-alpine AS runtime
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs
WORKDIR /app

COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=build --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000
ENV PORT=3000
CMD ["node", "server.js"]
```

Docker layer caching still separates deps from source: Layer 1 caches on `package.json`/`lockfile` content; Layer 2 on remaining source. This is simpler than the `deps` + `build` two-stage approach and avoids `pnpm fetch` symlink issues entirely.

### Step 3: Build the image

```bash
docker build --build-arg NEXT_PUBLIC_API_URL=http://api:8000 -t myapp-web .
```

## Alternative: Eliminate ARG with Next.js Rewrites

Instead of baking `NEXT_PUBLIC_API_URL` into the client bundle at build time (which requires a build arg and causes cross-origin API calls), use Next.js rewrites to proxy API requests through the same origin:

### Step A: API_BASE uses relative path

```ts
// lib/api/index.ts
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";
```

When `NEXT_PUBLIC_API_URL` is unset (no build arg), the client calls `/api/auth/login` (same-origin). When set (legacy config), it still works.

### Step B: Add rewrites in next.config.ts

```ts
// next.config.ts
async rewrites() {
  return [
    {
      source: "/api/:path*",
      destination: `${process.env.API_INTERNAL_URL || "http://localhost:13202"}/api/:path*`,
    },
  ];
}
```

At runtime, `API_INTERNAL_URL` tells the Next.js server where to forward API requests. In Docker Compose, set it to the internal service hostname.

### Step C: Docker Compose sets API_INTERNAL_URL (not NEXT_PUBLIC_API_URL)

```yaml
# docker-compose.yml
web:
  environment:
    API_INTERNAL_URL: http://api:8000   # Docker internal DNS
```

### Step D: Add API_INTERNAL_URL as a Dockerfile build arg

**CRITICAL: `next.config.ts` `async rewrites()` is evaluated at BUILD time, not runtime.** The rewrite destination is baked into the `required-server-files.json` during `next build`.

This means `process.env.API_INTERNAL_URL` in `next.config.ts` reads the build-time value, not the runtime container environment. You MUST pass it as a Dockerfile `ARG`:

```dockerfile
FROM node:22-alpine AS build
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL
```

For docker-compose, add it to the web service's `environment:` — it passes through to the build context:

```yaml
web:
  environment:
    API_INTERNAL_URL: ${API_INTERNAL_URL:-http://api:8000}
```

If the ARG is missing, the rewrite destination falls back to `"http://localhost:13202"` — which only works when the web server is on the host network, NOT inside Docker's internal network.

### Combined example (Dockerfile + next.config + compose):

**`next.config.ts`**:
```ts
async rewrites() {
  return [
    {
      source: "/api/:path*",
      destination: `${process.env.API_INTERNAL_URL || "http://localhost:13202"}/api/:path*`,
    },
  ];
}
```

**`Dockerfile`**:
```dockerfile
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL
```

**`docker-compose.yml`**:
```yaml
web:
  environment:
    API_INTERNAL_URL: ${API_INTERNAL_URL:-http://api:8000}
```

### Benefits

- **No CORS** — all requests are same-origin through the web server
- **No build-time coupling** — the Docker image is independent of the API URL
- **nginx compatibility** — if nginx is in front, it catches `/api/` before Next.js rewrites fire (no double-proxying)
- **Cleaner separation** — build config (what the image needs at build) vs runtime config (where the backend lives)

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Cannot find module 'next'` at runtime | Standalone not enabled, or COPY path wrong | Verify `output: 'standalone'` in next.config; check COPY destination |
| `Error: ENOENT: no such file or directory` | Monorepo: standalone output is nested | Copy from `.next/standalone/apps/web/` not `.next/standalone/` |
| Image still >300MB | Static assets or public/ are too large | Audit `public/` for binary files; use CDN for large assets |
| New page routes return 404 in Docker, but host `next build` lists them | Standalone tracer's `.next/server/` directory (contains new route trees) is NOT copied into the runtime image | The multi-stage Dockerfile's `COPY --from=build /app/.next/standalone ./.next` copies the standalone bundle, and `COPY --from=build /app/.next/static ./.next/static` copies static chunks. But the tracer's **`.next/server/`** directory — which contains the server chunks for newly added route directories (admin/, shares/, publisher/submit/, etc.) — is not copied unless explicitly added. **Fix:** Add `COPY --from=build /app/.next/server ./.next/server` after the standalone and static copies in the runtime stage. This is deterministic — `--no-cache` rebuild alone does NOT fix it because the tracer output is correct in the build stage; the missing step is the COPY directive. |
| `pnpm build` fails with `No projects matched` | Wrong filter name in monorepo | Check exact package name from package.json |
| `sharp` fails to load | Native binary mismatch | Ensure native deps are built in the same arch as runtime (Alpine uses musl) |
| `node: not found` | Alpine image mismatch | Use `node:22-alpine` consistently across all stages |
| `COPY public ./public fails` | No `public/` directory exists | Remove the COPY line or create the directory. Many Next.js apps have no static public assets. |
| `pnpm approve-builds` hangs at build time | `approve-builds` is interactive (requires TTY); Docker build has no TTY | Never call `pnpm approve-builds` in a Dockerfile. Instead, configure `only-built-dependencies[]` in `.npmrc` at the project root. |
| `Node.js 18+ module not found` at runtime with standalone output | Standalone tracing via `@vercel/nft` incorrectly marks modules as not used | Set `experimental.outputFileTracingIncludes` in `next.config.ts` to force-include missing modules |
| **`.dockerignore` excludes root `node_modules/` but NOT nested ones — 489MB build context** | `.dockerignore` pattern `node_modules/` only matches root-level. Nested dirs like `web/node_modules/` (352MB) are still sent to the Docker daemon. Context transfer stalls at 30+ seconds; build may time out. | Use `**/node_modules/` to exclude ALL nested `node_modules` dirs. Verify with `docker buildx build --progress=plain` — context transfer should be <5MB for a Next.js project. |
| **Docker build hangs after `docker system prune` (cold cache)** | `pnpm install` re-downloads 46+ packages, then `next build` compiles from scratch. | **Fallback:** Build standalone locally, then create a minimal Docker image. |
| **Tailwind CSS not applied** | `postcss.config.ts` is silently ignored by Next.js 15. Must be `.mjs` or `.js`. CSS contains raw @tailwind directives, no utility classes. | Rename to `postcss.config.mjs`, delete old `.ts`. |
| **pnpm install --prod strips tailwindcss** | If tailwindcss, postcss, autoprefixer are in devDependencies, --prod skips them. | Move to dependencies in package.json, update lockfile. |

### Next.js 16 TypeScript Strictness — Build-Only Failures

> **Build caching reference:** See `references/docker-build-caching.md` for cache mount patterns (`.next/cache`, pnpm store), the `--no-dev` → `--prod` fix, and the pre-test rebuild ritual.

Next.js 16's Turbopack compiler is stricter about JSX types than v15. These errors may not appear in `tsc` or local dev but will fail `next build` (and therefore Docker builds):

| Error | Pattern | Fix |
|-------|---------|-----|
| `Type 'unknown' is not assignable to type 'ReactNode'` | `{state.data && <Component />}` where `data: unknown \| null` | Use `{!!state.data && <Component />}` — the `!!` coerces `unknown` to `boolean` which is valid JSX |
| `Property 'defaultOpen' does not exist on type '...HTMLDetailsElement...'` | `<details defaultOpen={bool}>` — React 19 added `defaultOpen` but TS types may not include it yet | Use `open={bool}` instead (controlled), or add `@ts-expect-error` |
| `Inferred workspace root may not be correct` | pnpm monorepo + Turbopack can't auto-detect workspace root in Docker | Set `outputFileTracingRoot: path.resolve(__dirname, "../../")` at the **top level** of `next.config.ts` (NOT under `experimental`). Also add `transpilePackages: ["<package-name>"]` |
| `Object literal may only specify known properties, but 'outputFileTracingRoot' does not exist in type 'NextConfig'` | LSP thinks it belongs under `experimental` — but the Zod schema validates it at top level | Ignore the LSP diagnostic; the compiler accepts it. If it doesn't, wrap in `experimental: { outputFileTracingRoot: ... }` |

**Verification after build fix:**
```bash
# Run build locally first (fast iteration)
cd apps/web && pnpm build 2>&1 | tail -5

# Then rebuild Docker
docker compose build --no-cache web

# Verify routes in container
docker compose exec web find /app/apps/web/.next/server/app -name "page.js" 2>/dev/null | sort | head -30
```

## Official Vercel Patterns

The [official Next.js Docker example](https://github.com/vercel/next.js/tree/canary/examples/with-docker) provides additional production patterns.

### ARG NODE_VERSION for Easier Maintenance

Parameterize the Node.js version so it can be updated in one place:

```dockerfile
ARG NODE_VERSION=24.13.0-slim

FROM node:${NODE_VERSION} AS dependencies
WORKDIR /app
COPY package.json yarn.lock* package-lock.json* pnpm-lock.yaml* .npmrc* ./
RUN --mount=type=cache,target=/root/.npm \
    --mount=type=cache,target=/usr/local/share/.cache/yarn \
    --mount=type=cache,target=/root/.local/share/pnpm/store \
    if [ -f package-lock.json ]; then \
      npm ci --no-audit --no-fund; \
    elif [ -f yarn.lock ]; then \
      corepack enable yarn && yarn install --frozen-lockfile --production=false; \
    elif [ -f pnpm-lock.yaml ]; then \
      corepack enable pnpm && pnpm install --frozen-lockfile; \
    fi

FROM node:${NODE_VERSION} AS builder
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN if [ -f package-lock.json ]; then \
      npm run build; \
    elif [ -f yarn.lock ]; then \
      corepack enable yarn && yarn build; \
    elif [ -f pnpm-lock.yaml ]; then \
      corepack enable pnpm && pnpm build; \
    fi

FROM node:${NODE_VERSION} AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
COPY --from=builder --chown=node:node /app/public ./public
RUN mkdir .next && chown node:node .next
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
```

The `ARG` pattern supports npm, yarn, AND pnpm in a single Dockerfile — useful when the project's package manager could vary.

### slim vs alpine

| Base | Size | Libc | Compatibility |
|------|------|------|---------------|
| `slim` (glibc) | ~226MB | glibc | Best npm package compatibility |
| `alpine` (musl) | ~126MB | musl | May break native deps (sharp, @swc/core) |

**Use slim when:** compatibility matters more than 100MB savings. Most production deployments should use slim.  
**Use alpine when:** image size is critical AND you've verified all native dependencies work with musl.

### Bun Runtime Alternative

For projects using Bun instead of Node.js:

```dockerfile
FROM oven/bun:1 AS dependencies
WORKDIR /app
COPY package.json bun.lock* ./
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --no-save --frozen-lockfile

FROM oven/bun:1 AS builder
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
ENV NODE_ENV=production
RUN bun run build

FROM oven/bun:1 AS runner
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME="0.0.0.0"
COPY --from=builder --chown=bun:bun /app/public ./public
RUN mkdir .next && chown bun:bun .next
COPY --from=builder --chown=bun:bun /app/.next/standalone ./
COPY --from=builder --chown=bun:bun /app/.next/static ./.next/static
USER bun
EXPOSE 3000
CMD ["bun", "server.js"]
```

### Production .dockerignore

The official example includes AI/ML metadata in `.dockerignore` — exclude `.cursor/`, AGENTS.md, `.kiro`, `.claude`, and other tooling files that bloat build context:

```dockerignore
# Dependencies
node_modules/
.pnpm-store/
npm-debug.log*

# Build outputs
.next/
out/
dist/
build/
.vercel/

# AI/ML tool metadata and configs
.cursor/
.cursorrules
.copilot/
.gemini/
.anthropic/
.kiro
.claude
AGENTS.md
.agents/

# Tests
coverage/
__tests__/
*.test.*
*.spec.*

# Dev
.git/
.vscode/
.env*
Dockerfile*
.dockerignore
compose.yml

# Docs
*.md
docs/

# CI
.github/
.gitlab-ci.yml

# OS junk
.DS_Store
Thumbs.db
```

The full example: https://github.com/vercel/next.js/blob/canary/examples/with-docker/.dockerignore

## Related Skills

- `pnpm-monorepo-docker` — for pnpm **workspace monorepo** Docker builds. The standalone output path differs (nested under `apps/web/`). Load when building a monorepo package, not a standalone app.
- `react-best-practices` — 70+ React/Next.js performance optimization rules from Vercel Engineering

## Verification

After building, verify the runtime image:

```bash
# Check image size
docker images myapp-web

# Verify no node_modules
docker run --rm myapp-web ls /app/node_modules 2>&1 || echo "No node_modules — correct"

# Health check
docker run -d -p 3000:3000 myapp-web
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000

# Check process
docker exec <container> ps aux | grep node
```
