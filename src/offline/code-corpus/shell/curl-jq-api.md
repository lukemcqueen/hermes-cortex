---
language: shell
tags: [net, api, cli]
title: curl & jq API Interaction
description: REST API calls with curl (GET, POST, headers, JSON body) and jq for filtering, selecting, transforming, and error handling.
source: pattern
---

```shell
#!/usr/bin/env bash
set -euo pipefail

# ── GET requests ──
# Simple GET
curl https://api.example.com/items

# GET with headers
curl -H "Authorization: Bearer $TOKEN" \
     -H "Accept: application/json" \
     https://api.example.com/items

# GET with query parameters
curl -G https://api.example.com/search \
     -d "q=search term" \
     -d "page=1" \
     -d "limit=20"

# ── POST requests ──
# POST with JSON body
curl -X POST https://api.example.com/items \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"name": "New Item", "value": 42}'

# POST from file (avoids shell quoting issues)
curl -X POST https://api.example.com/items \
     -H "Content-Type: application/json" \
     -d @payload.json

# ── PUT / PATCH / DELETE ──
curl -X PUT -H "Content-Type: application/json" \
     -d '{"name": "Updated"}' \
     https://api.example.com/items/1

curl -X DELETE https://api.example.com/items/1

# ── Download files ──
curl -o output.zip -L https://example.com/file.zip
curl -O https://example.com/file.zip              # preserves filename

# ── Error handling ──
# Fail on HTTP errors, follow redirects, silent mode
curl -sfSL https://api.example.com/items > response.json || {
    echo "API call failed" >&2
    exit 1
}

# ── jq: basic filtering ──
cat response.json | jq '.'                        # pretty-print
cat response.json | jq '.data'                    # extract key
cat response.json | jq '.items[]'                 # iterate array
cat response.json | jq '.items[0]'                # first element
cat response.json | jq '.items | length'          # count elements

# ── jq: select / filter ──
cat response.json | jq '.items[] | select(.status == "active")'
cat response.json | jq '.items[] | select(.price > 100)'
cat response.json | jq '.items[] | select(.name | test("^prefix"))'

# ── jq: transform output ──
cat response.json | jq '.items[] | {id, name, price}'
cat response.json | jq '[.items[] | {id, name}]'
cat response.json | jq -r '.items[].name'          # raw strings (no quotes)

# ── jq: error handling ──
cat response.json | jq -e '.data' > /dev/null 2>&1 || {
    echo "Response missing .data field" >&2
    exit 1
}

# ── Full pipeline: curl + jq ──
curl -sfSL "https://api.github.com/repos/user/repo/issues" |
    jq -r '.[] | select(.state == "open") | "\(.number) \(.title)"'

```
