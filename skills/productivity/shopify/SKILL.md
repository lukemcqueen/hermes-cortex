---
name: shopify
version: 1.0.0
description: "Shopify Admin & Storefront GraphQL APIs via curl. Products, orders, customers, inventory, metafields."
---

## When to Use
Use when reading or querying Shopify store data (products, orders, customers, inventory, metafields) via the Admin or Storefront GraphQL APIs using curl — no SDK needed. For order mutations or app development, prefer the official libraries.

## Workflow
1. **Get credentials.** Admin: a private/custom app admin API access token sent as `X-Shopify-Access-Token`. Storefront: a storefront access token sent as `X-Shopify-Storefront-Access-Token` (safe to expose client-side).
2. **Pick the endpoint.** Admin: `https://{store}.myshopify.com/admin/api/2026-01/graphql.json`. Storefront: `https://{store}.myshopify.com/api/2026-01/graphql.json`.
3. **Query.** Use `curl -s -X POST` with a JSON body containing `query` and optional `variables`.

### Admin — products with variants
```bash
curl -s -X POST "https://{store}.myshopify.com/admin/api/2026-01/graphql.json" \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Access-Token: $SHOPIFY_ADMIN_TOKEN" \
  -d '{
    "query": "query { products(first: 10) { edges { node { id title handle status variants(first: 5) { edges { node { id title sku price } } } } } } }"
  }'
```

### Admin — recent orders
```bash
curl -s -X POST "https://{store}.myshopify.com/admin/api/2026-01/graphql.json" \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Access-Token: $SHOPIFY_ADMIN_TOKEN" \
  -d '{
    "query": "query { orders(first: 10, sortKey: CREATED_AT, reverse: true) { edges { node { id name createdAt totalPriceSet { shopMoney { amount currencyCode } } } } } }"
  }'
```

### Admin — customers
```bash
curl -s -X POST "https://{store}.myshopify.com/admin/api/2026-01/graphql.json" \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Access-Token: $SHOPIFY_ADMIN_TOKEN" \
  -d '{"query": "query { customers(first: 10) { edges { node { id email firstName lastName ordersCount } } } }"}'
```

### Admin — inventory locations then levels
```bash
curl -s -X POST "https://{store}.myshopify.com/admin/api/2026-01/graphql.json" \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Access-Token: $SHOPIFY_ADMIN_TOKEN" \
  -d '{"query": "query { locations(first: 10) { edges { node { id name } } } }"}'
```
Then query `inventoryLevels(locationId: "LOCATION_ID") { nodes { available } }` for stock per variant.

### Admin — metafields on a product
```bash
curl -s -X POST "https://{store}.myshopify.com/admin/api/2026-01/graphql.json" \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Access-Token: $SHOPIFY_ADMIN_TOKEN" \
  -d '{
    "query": "query { product(id: \"gid://shopify/Product/PRODUCT_ID\") { metafields(first: 10) { edges { node { namespace key value type } } } } }"
  }'
```

### Storefront — products (public, client-safe)
```bash
curl -s -X POST "https://{store}.myshopify.com/api/2026-01/graphql.json" \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Storefront-Access-Token: $SHOPIFY_STOREFRONT_TOKEN" \
  -d '{"query": "query { products(first: 10) { edges { node { id title handle availableForSale } } } }"}'
```

### Pagination (cursor)
Shopify returns `pageInfo { hasNextPage endCursor }`; pass the cursor to the next request:
```bash
curl -s -X POST "https://{store}.myshopify.com/admin/api/2026-01/graphql.json" \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Access-Token: $SHOPIFY_ADMIN_TOKEN" \
  -d '{
    "query": "query { products(first: 10, after: \"CURSOR\") { edges { node { id title } } pageInfo { hasNextPage endCursor } } }"
  }'
```

## Pitfalls
- Admin API rate limit: 2 requests/second (burst 40). Storefront: 4 requests/second (burst 60). Monitor the `X-Shopify-Shop-Api-Call-Limit` response header; back off with jitter on 429s.
- IDs are opaque GIDs (`gid://shopify/Product/123`) — always pass them as strings and URL-encode them inside query variables.
- Product `status` is DRAFT/ACTIVE/ARCHIVED; use the `query:` argument to filter list queries.
- The Storefront API only exposes published, sales-channel-visible data — don't use it for admin reads.
- Never hardcode tokens in scripts — use env vars (e.g. `$SHOPIFY_ADMIN_TOKEN`); keep them out of logs and reports.
- The `2026-01` version segment is pinned — Shopify deprecates API versions, so update it on a schedule.

## Verification
- Confirm the response has no `errors` key; if present, fix the query before trusting data.
- Sanity-check counts: products returned vs. expected catalog size; order timestamps within the expected window.
- For storefront calls, verify the query works with the public token only (no admin auth).
- During bulk loops, watch the rate-limit header stays under limits.
