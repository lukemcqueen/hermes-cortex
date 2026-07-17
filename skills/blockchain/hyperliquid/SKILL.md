--- Full content (truncated) ---
---
name: hyperliquid
description: Hyperliquid market data, account history, trade review.
version: 0.1.0
author: Hugo Sequier (Hugo-SEQUIER), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Hyperliquid, Blockchain, Crypto, Trading, Perpetuals, Spot, DeFi]
    related_skills: []
---

# Hyperliquid Skill

Query Hyperliquid market and account data through the public `/info` endpoint.
Read-only — no API key, no signing, no order placement.

12 commands: `dexs`, `markets`, `spots`, `candles`, `funding`, `l2`, `state`,
`spot-balances`, `fills`, `orders`, `review`, `export`. Stdlib only
(`urllib`, `json`, `argparse`).

---

## When to Use

- User asks for Hyperliquid perp or spot market data, candles, funding, or L2 book
- User wants to inspect a wallet's perp positions, spot balances, fills, or orders
- User wants a post-trade review combining recent fills with market context
- User wants to inspect builder-deployed perp dexs or HIP-3 markets
- Us
... [truncated]
--- End skill ---