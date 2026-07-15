# Music Licensing Portal: Home Page = Song Search

## Principle

For a music licensing portal (acme-license), the home page is song search — not a generic landing page with hero text, feature cards, and CTAs. Licenses are tied to musical works, so the first thing a user sees should be a search bar to find songs.

## Pattern

```
┌─────────────────────────────────────────────────┐
│  ACME Licensing Portal (accent color)          │
│  Search for a song to license...  [ Search ]     │
│                                                   │
│  ┌───────────────────────────────────────────┐    │
│  │ 봄날 · Spring Day    BTS    [LICENSABLE] ₩45,000│
│  ├───────────────────────────────────────────┤    │
│  │ Dynamite              BTS    [LICENSABLE] ₩45,000│
│  ├───────────────────────────────────────────┤    │
│  │ ...                                        │    │
│  └───────────────────────────────────────────┘    │
│                                                   │
│  [ Browse Types ] [ My Licenses ] [ Admin ]       │
└─────────────────────────────────────────────────┘
```

## Implementation Details

### What to remove from the home page
- Generic hero section (marketing text, feature cards, "welcome to the portal")
- License type cards (Software/Patent/Content/Partner — irrelevant for music)
- Search CTA section (search IS the hero, not a separate CTA)
- Generic quick links (Guide, FAQ — replace with domain-specific links)

### What the home page needs
- **Hero section** with ACME brand + prominent search input (auto-focused)
- **Search results** section showing song cards from `GET /api/v1/works/search?title=...`
- **Quick links row** with domain-appropriate destinations: Browse Types, My Licenses, Admin
- **Footer** with copyright

### API integration
- Frontend calls `//localhost:{API_PORT}/api/v1/works/search?title={query}` directly
- Backend endpoint uses `WorksSearchService` which proxies to acme-works at `{ACME_WORKS_ENDPOINT}/api/works/search` with mock fallback
- Response shape: `{ items: WorkSearchItem[], total: number, page: number }`
- WorkSearchItem fields: `id`, `title_ko`, `title_en`, `artists`, `isrc`, `licensable`, `estimated_price`

### Song card result
Each result card shows:
- Title (ko primary, en secondary in lighter text)
- Artist name
- ISRC (optional, mono font)
- Licensable badge (green "Licensable" / red "Not Licensable")
- Estimated price (₩ format)

Clicking a song navigates to `/license/youtube?workId={id}` to start the licensing wizard with that song pre-selected.

### Search behavior
- Debounce not needed — user presses Enter or clicks Search
- Loading state shows spinner text
- Empty state shows "No results found" with hint: "Try a different search term, or search by ISRC"
- Error state shows inline error message
- API error does NOT crash the page — caught in try/catch

### i18n keys
Keep home.hero.title, home.hero.title_accent, home.hero.subtitle, home.hero.description
Replace all other `home.*` keys with:
- home.search.placeholder — Korean: "곡 제목을 검색하세요..."
- home.search.aria_label — Korean: "음악 검색"
- home.search.button — "검색" / "Search"
- home.search.button_loading — "검색 중..." / "Searching..."
- home.search.loading — "검색 중..." / "Searching..."
- home.search.error — error message text
- home.search.no_results — "검색 결과가 없습니다."
- home.search.no_results_hint — hint for try different search
- home.search.results_heading — "검색 결과 ({count})"
- home.search.licensable — "라이선스 가능" / "Licensable"
- home.search.unlicensable — "라이선스 불가" / "Not Licensable"
- home.quick_links.browse — "라이선스 유형 보기" / "Browse License Types"
- home.quick_links.dashboard — "내 라이선스" / "My Licenses"
- home.quick_links.admin — "관리자 대시보드" / "Admin Dashboard"

### Inline styles approach
Use `<style>` tag in the page component (client component approach) rather than a separate CSS module — keeps the page self-contained. Name classes semantically (`.hero`, `.search-input-row`, `.song-card`, `.badge-green`, `.badge-red`).

## When to use this pattern
- Building a new licensing portal UI for music works
- Replacing a generic landing page with a domain-specific search-first experience
- Any app where search is the primary action users come for (music, video, content licensing)
