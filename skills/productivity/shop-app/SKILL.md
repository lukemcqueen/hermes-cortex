--- Full content (truncated) ---
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

All endpoints return **plain-text markdown** (including errors, whi
... [truncated]
--- End skill ---