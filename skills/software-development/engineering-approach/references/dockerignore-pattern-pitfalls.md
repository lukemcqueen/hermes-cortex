# .dockerignore Pattern Pitfalls

Docker sends the **entire build context** to the daemon. What you exclude matters.

## The `node_modules/` Trap

A `.dockerignore` pattern like `node_modules/` only matches the **root-level** directory. Nested `node_modules/` (e.g. `web/node_modules/`) are **not** excluded.

**Wrong (root-only match):**
```
node_modules/
```
Result: `web/node_modules/` (352MB typical) ships with every build — 489MB context → 34s transfer.

**Right (recursive match):**
```
node_modules/
**/node_modules/
```
Or just `**/node_modules/` alone. Context drops to ~2MB, build completes in seconds.

## Why This Happens

Docker's `.dockerignore` glob patterns follow filepath.Match rules: `node_modules/` matches exactly `./node_modules/`, not `./web/node_modules/`. The `**/` prefix enables recursive matching.

## When It Bites

- **Monorepos** with nested `apps/*/node_modules/` or `packages/*/node_modules/`
- Any project where `node_modules` lives in a subdirectory, not the root
- After `docker system prune` clears the build cache (first cold build hits full context transfer)

## Recommended Minimal `.dockerignore`

```
node_modules/
**/node_modules/
.next/
.venv/
**/__pycache__/
*.pyc
.git/
*.log
.env
.env.*local
.secrets/
.hermes/
memory/
```

## Verification

To check what's actually being sent:
```bash
docker buildx build --load --progress=plain ... 2>&1 | grep "transferring context"
# Look for the MB number — should be < 10MB for most projects
```

## Standalone Image Build (When Docker Builds Hang)

When the Docker daemon's pnpm build step is slow or hangs, build locally and construct a minimal image from Next.js standalone output:

```bash
# 1. Build locally with correct env
cd web && NEXT_PUBLIC_API_URL=http://localhost:15678 pnpm build

# 2. Create minimal Dockerfile
cat > /tmp/Dockerfile.web << 'EOF'
FROM node:22-alpine
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
WORKDIR /app
COPY --chown=nextjs:nodejs . .
USER nextjs
ENV PORT=3000
EXPOSE 3000
CMD ["node", "server.js"]
EOF

# 3. Build from the standalone output directory
docker buildx build --load -t client-web-app-web -f /tmp/Dockerfile.web web/.next/standalone

# 4. Recreate container
docker compose up -d --force-recreate web
```

The standalone output includes `node_modules/next`, `node_modules/react`, and `node_modules/typescript` — everything the runtime needs. No pnpm install or Next.js build inside Docker.