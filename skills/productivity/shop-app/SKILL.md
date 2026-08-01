---
name: shop-app
description: "Shop.app: product search, order tracking, returns, reorder."
version: 0.0.28
author: community
license: MIT
platforms: [linux, macos, windows]
prerequisites:
  commands: [curl]
metadata:
  hermes:
    tags: [Shopping, E-commerce, Shop.app, Products, Orders, Returns]
    related_skills: [shopify, maps]
    homepage: https://shop.app
    upstream: https://shop.app/SKILL.md
---

# Shop.app — Personal Shopping Assistant

Use this skill when the user wants to **search products across stores, compare prices, find similar items, track an order, manage a return, or re-order a past purchase** through Shop.app's agent API.

No auth required for product search. Auth (device-authorization flow) is required for any per-user operation: orders, tracking, returns, reorder. Store tokens **only in your working memory for the current session** — never write them to disk, never ask the user to paste them.

All endpoints return **plain-text markdown** (including errors, which are human-readable). Treat the response body as the answer — parse it for display.

## Product Search (no auth)

```bash
curl -s "https://shop.app/api/agent/search?q=<query>"
```

Returns markdown with matching products: title, store, price, and a direct
link. Use it to:
- Compare prices across stores
- Find similar/related items
- Check availability

## Per-User Operations (auth required)

### Device-authorization flow

1. Request a device code:
   ```bash
   curl -s -X POST "https://shop.app/api/agent/auth/device"
   ```
2. Show the user the verification URL + code and ask them to authorize.
3. Poll for the token until the user completes authorization:
   ```bash
   curl -s -X POST "https://shop.app/api/agent/auth/token" -d '{"device_code":"<code>"}'
   ```
4. Keep the resulting token **in session memory only**.

### Track an order

```bash
curl -s -H "Authorization: Bearer <token>" "https://shop.app/api/agent/orders/<order-id>"
```

### Start a return

```bash
curl -s -X POST -H "Authorization: Bearer <token>" \
  "https://shop.app/api/agent/orders/<order-id>/return" -d '{"items":["<item-id>"]}'
```

### Reorder

```bash
curl -s -X POST -H "Authorization: Bearer <token>" \
  "https://shop.app/api/agent/orders/<order-id>/reorder"
```

## Security Rules

- **Never persist tokens** — session memory only; forget them when the session ends.
- **Never ask the user to paste a token into chat** — use the device flow so
  they authorize on Shop.app's own page.
- **Never print the full token in tool output** — reference it by variable.

## Related
- `shopify` — Shopify store admin API (seller side)
- `maps` — store location lookups
