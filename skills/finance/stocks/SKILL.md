--- Full content (truncated) ---
---
name: stocks
description: Stock quotes, history, search, compare, crypto via Yahoo.
version: 0.1.0
author: Mibay (Mibayy), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Stocks, Finance, Market, Crypto, Investing]
    category: finance
    related_skills: [dcf-model, comps-analysis, lbo-model]
---

# Stocks Skill

Read-only market data via Yahoo Finance. Five commands: `quote`, `search`,
`history`, `compare`, `crypto`. Python stdlib only — no API key, no pip
installs. Yahoo's endpoint is unofficial and may rate-limit or change.

## When to Use

- User asks for a current stock price (AAPL, TSLA, MSFT, ...)
- User wants to look up a ticker by company name
- User wants OHLCV history or performance over a date range
- User wants to compare several tickers side by side
- User asks for a crypto price (BTC, ETH, SOL, ...)

## Prerequisites

Python 3.8+ stdlib only. Optional: set `ALPHA_VANTAGE_KEY` to enrich
`market_cap`, `pe_ratio`, and 52-wee
... [truncated]
--- End skill ---