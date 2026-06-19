# Docker Build Caching Performance

## Next.js .next/cache — Cache Mount

Without a cache mount, `.next/cache` is ephemeral — Webpack's incremental compilation cache is thrown away after every Docker build.

**Fix:** Add `--mount=type=cache,target=/app/.next/cache` to the `pnpm build` RUN instruction:

```dockerfile
RUN --mount=type=cache,target=/app/.next/cache \
    pnpm build
```

**Impact:** First build ~7 min (full Webpack compile). Subsequent builds ~10-30s (incremental).

## pnpm Store — Cache Mount

Without a cache mount, the pnpm store (`~/.local/share/pnpm/store`) is thrown away after every Docker build. Every build re-downloads all packages from the npm registry.

**Fix:** Add `--mount=type=cache,target=/root/.local/share/pnpm/store` to both `pnpm fetch` and `pnpm install`:

```dockerfile
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm fetch --frozen-lockfile
...
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile --prod --prefer-offline
```

**Impact:** Without mount: 170-450s. With mount (after first build): ~0s.

## pnpm --no-dev → --prod

`--no-dev` is NOT a valid pnpm flag. It is silently ignored, so ALL devDependencies (playwright, vitest, testing-library, postcss, tailwindcss, typescript — 15 packages) get installed in the production image. This bloats the image and slows the build.

**Fix:** Use `--prod` which is pnpm's correct flag for production-only installs.

**Verification:**
```bash
docker run --rm <image> ls node_modules | grep -E 'playwright|vitest|testing-library'
# Should return nothing
```

## Pre-test Rebuild Ritual

Always follow before asking the user to test:

1. `./run build` — rebuild images from current code
2. `./run down` — tear down old containers (+ stale state)
3. `./run up` — start fresh containers from new images
4. Re-seed demo data if the DB needs it
