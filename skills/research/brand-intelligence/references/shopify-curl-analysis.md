# Shopify Store Analysis via curl

Technique used to research KAESA (kaesa.co) — a Shopify-based sustainable handbag brand — when browser tools were unavailable.

## Context
- Browser (`agent-browser` binary) not installed on the machine
- `web_extract` backend was DuckDuckGo (search-only, no URL extraction)
- No browser engine available to render JS-heavy Shopify pages

## Approach

### Step 1: Fetch raw HTML
```bash
curl -sL --max-time 15 \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36' \
  https://kaesa.co/
```

### Step 2: Extract metadata from `<head>`
Grep for key tags:
- `<title>` — brand name
- `<meta name="description">` — brand tagline
- `<meta property="og:description">` — social description
- `<meta property="og:image">` — hero product image
- `<link rel="alternate" hreflang="...">` — markets served

### Step 3: Extract Shopify config from inline scripts
The Shopify global object in `<script>` blocks reveals:
| Field | What it reveals |
|-------|----------------|
| `Shopify.shop` | Subdomain handle (`kaesa-kaesa.myshopify.com`) |
| `Shopify.currency` | Currency and rate (USD) |
| `Shopify.theme` | Theme name and version (`Kaesa-dev/master`, Dawn v2.1.0) |
| `Shopify.locale` | Default locale |
| `Shopify.country` | Default ship-to country |

### Step 4: Extract brand design tokens from CSS
Inline `:root` custom properties:
```css
--kaesa-black: #202122;
--kaesa-white: #F9F9F9;
--kaesa-silver: #C2CCD4;
--kaesa-grey: #ababab;
--kaesa-red: #b00000;
--color-product-card: #F0F2F4;
```

Font families from Google Fonts imports and `@font-face`:
- Lato (body + headings)
- NewYork (display/custom font)

### Step 5: Identify third-party integrations
Scan `<script>` src URLs:
- Mailchimp (`chimpstatic.com/mcjs-connected/js/users/...`)
- Instafeed (`instafeed.nfcube.com`) — Instagram feed
- PageFly — page builder
- hCaptcha

### Step 6: Check for bilingual/multi-market setup
```html
<link rel="alternate" hreflang="x-default" href="https://kaesa.co/">
<link rel="alternate" hreflang="en" href="https://kaesa.co/">
<link rel="alternate" hreflang="ko" href="https://kaesa.co/ko">
```
Confirms English + Korean markets, a sign of Korean-founder brand.

## What to do when pages return 404
`/pages/about` returned 404 for KAESA — this is normal for Shopify stores using section-based homepages. Don't conclude "no about page exists"; instead search for the brand story in the homepage meta and OG tags.

## Result Summary
From this analysis, the brand profile was:
- **Name**: KAESA
- **Category**: Sustainable handbags & accessories
- **Tagline**: "Sustainable handbags & accessories that balance beautiful aesthetics with function"
- **Platform**: Shopify, Dawn theme v2.1.0, custom "Kaesa-dev/master" theme
- **Languages**: English + Korean
- **Currency**: USD
- **Design**: Minimal, Lato + NewYork fonts, black/silver/white palette
- **Integrations**: Mailchimp newsletter, Instagram feed, PageFly builder
- **Location insight**: Korean founder in Seoul (KST UTC+9 offset)
