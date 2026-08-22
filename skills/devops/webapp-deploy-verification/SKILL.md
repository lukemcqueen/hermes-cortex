---
name: webapp-deploy-verification
version: 1.0.0
description: "Verify deployed web app routes render and links resolve."
author: Hermes Cortex
metadata:
  hermes:
    tags: [web, deploy, verification, e2e, routes, links, nextjs, docker]
    related_skills: [deploy-load-verification, integration-audit, dogfood]
---

# Web App Deploy Verification — Prove It, Don't Assume

## When to Use

- After rebuilding/restarting a web container — before telling the user it's live.
- When a user reports a page "still broken" after you fixed it.
- After adding routes, links, nav/footer changes, or i18n/localization work.
- Any time you need to claim "the site works" with evidence.

## Core Principle

Git commit ≠ running deployment. A committed file is not a serving page. The
**only** proof a web app works is exercising the URL another user would hit and
observing the real response. Three axes are independently verifiable — check all
three:

1. **Routes render** (each URL returns 200 and no JS errors)
2. **Links resolve** (every href on every page actually returns 200 when followed)
3. **Container health is real** (the healthcheck passes; it isn't lying)

## Technique 1 — HTTP Route Crawl

Enumerate the route tree from the app dir, then curl each one over the deployed
path (never the dev server):

```python
import requests
BASE = "http://127.0.0.1:PORT"            # the deployed/proxied origin
routes = ["/", "/about", "/about/x", ...] # from find apps/web/src/app -name page.tsx
for r in routes:
    resp = requests.get(BASE + r, allow_redirects=False, timeout=20)
    # treat 3xx as "follow, then check final"; 4xx/5xx = broken
```

**Gotchas from the field:**
- A route can 404 with a **layout wrapper but no page** (e.g. `/admin` was
  layout-only → 404; same for a bare `/questions` where only `[slug]` exists).
  Flag these separately — no link targets them, but they 404 on direct visit.
- Capture the `<title>` from each 200 body to confirm you got the right page, not
  a generic error page that still returns 200.
- Auth-gated routes (admin/dashboard) render 200 with the login shell even
  anonymous — that's expected; check the title tag, not just the status.

## Technique 2 — E2E Link Verification (THE critical one)

**Read hrefs, then FOLLOW them. Reading href text alone proves nothing.** The
expensive failure this session: an i18n header prepended `/${locale}` (= `/en/`)
to every nav/footer href, but the locale was a **runtime preference
(localStorage/navigator), NOT a URL route** — no `[locale]` dir, no middleware, no
i18n rewrite existed. Every nav/footer link 404'd when clicked, while:
- the page rendered fine,
- every link *label* was correct (Home, About, ...),
- and checking href *text* looked perfectly healthy.

Only following each link surfaced it. **The technique:**

```
for each route:
    visit it in a real browser, collect every internal <a href>
dedupe the global link set
then HTTP-GET every unique link and assert 200
```

Also intersect the **collected link graph** against the **actual route tree** —
a nav pointing `/warriors` when the page is `/warrior` (or `/rest` vs `/breath`)
is a dead link neither a route crawl nor a label check will catch.

Synthetic DOM events (dispatchEvent/mouseover) do NOT trigger CSS `:hover` —
to verify a hover dropdown use a real pointer move, or check the menu nodes exist
in the DOM with correct hrefs and trust the CSS rule.

## Technique 3 — Container Health Reality Check

A compose healthcheck failing does NOT mean the service is down — it means the
*probe* can't reach the service. **unhealthy ≠ down.** See the container
pitfalls below; the two classic traps are a server bound to the container IP
(not loopback) and `localhost` fanning out to IPv6 `[::1]` first.

## Container Healthcheck Pitfalls (Next.js standalone)

- **Server binds container IP, not loopback.** Next standalone `server.js` binds
  to `HOSTNAME`, which Docker resolves to e.g. `172.26.0.6:3000`. A healthcheck
  `wget http://localhost:3000/` inside is refused while the published `-p` port
  works fine from the host (DNAT targets the container IP).
- **`localhost` → IPv6 `[::1]` first.** Even after an all-interface bind, a probe
  of the *hostname* `localhost` resolves to `[::1]` and gets refused on the
  IPv4-only listener. Probe the literal `http://127.0.0.1:PORT/`, never the
  `localhost` hostname.
- **Fix:** force `HOSTNAME: "0.0.0.0"` in the compose `environment:` (or `ENV
  HOSTNAME=0.0.0.0` in the runner stage) AND probe the explicit IPv4 address in
  the healthcheck. Verify inside:
  `docker exec <c> netstat -tlnp | grep :PORT` → `0.0.0.0:PORT` LISTEN, then
  `wget -q --spider http://127.0.0.1:PORT/; echo $?` → 0.

## Script

- `scripts/webapp-http-crawl.py` — ready-to-run HTTP route crawl + link check:
  pass `--base <url>` and `--routes file-or-list`; reports OK/BAD per URL.

## Verification Checklist

- [ ] Every route in the app dir returns 200 over the deployed origin
- [ ] Every internal `<a href>` collected from the live pages returns 200
- [ ] Link graph intersected with route tree — no dead/bare targets
- [ ] `<title>` tag present and correct on the served HTML (empty title = missing metadata export)
- [ ] Container healthcheck reads `healthy` (not a false `unhealthy` while serving)
- [ ] Hard-refresh note given to user for stale browser cache on icon/favicon changes
