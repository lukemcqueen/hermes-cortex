# OpenRouter model catalogue — surveying price, speed, provider reliability

Use when answering "what is the best / cheapest model right now", choosing a cron
pin or a fallback route, or checking whether a free tier still exists. Prices,
model ids and availability move weekly — **never answer from memory; query.**

## The public API (authoritative for price, context, tool support)

```
GET https://openrouter.ai/api/v1/models                  # catalogue, no key needed
GET https://openrouter.ai/api/v1/models/<id>/endpoints   # per-provider detail
```

- `pricing.prompt` / `pricing.completion` are **USD per token** — multiply by
  1e6 for the $/M figure everyone quotes.
- **Do NOT percent-encode the `/` in a model id.** `urllib.parse.quote(id)` with
  its default `safe='/'` works; a hand-written `%2F` returns **404**.
- `supported_parameters` containing `"tools"` is the tool-calling flag. Check it
  before recommending a model for agent work.
- Ids ending `:batch` are the async route (~half price); `:free` ids are the
  zero-cost tier (0 in / 0 out).
- **Filter negative prices.** Rows priced `-1000000` are dynamic routers (auto /
  pareto / fusion) with no fixed price; they sort to the top of any naive
  "cheapest" list and mean nothing.
- **The API does NOT expose speed.** `throughput_last_30m` and
  `latency_last_30m` exist as keys but are **null** on every endpoint sampled,
  and the frontend stats paths (`/api/frontend/models`,
  `/api/frontend/stats/endpoint`) 404. Only `uptime_last_1d` populates — so the
  API can prove a provider is *up*, never that it is fast.
- `uptime_last_1d` is **already a percentage** (e.g. `99.97`) — do not multiply
  by 100. And cheap endpoints are not reliable endpoints: the same model showed
  one provider at 99.97% and another at 84.77%.

## Model ids are spelled several ways — match by regex, then assert existence

The same family appears as `z-ai/glm-5.3`, `z-ai/glm-5.3-flash`,
`...-flashx`, plus `:batch` variants. Search the catalogue by regex on the id
rather than guessing an exact id, and **assert the model you recommend actually
EXISTS in the live list** — a model that benchmarks well but is not listed
cannot be pinned.

## Speed comes from an external source

llm-stats.com's leaderboard carries score + subscores + price + output price +
speed + latency. It is **JS-rendered**: a direct fetch returns a few KB of shell,
so read it with the browser tool and pull the table out of the DOM
(`[...document.querySelectorAll('tr')].map(tr => [...tr.querySelectorAll('td,th')].map(td => td.innerText.trim()))`).
The landing page mounts ~15 rows; the full view is `/leaderboards/llm-leaderboard`.

- Its SPEED column is **characters/second, not tokens/second.** Report the unit
  as given; never silently convert.
- These are third-party measurements of the **model**, not of the OpenRouter
  *route*. State that distinction when quoting them.

## Answering the question well

Split the answer into **best performing** (top of the score board) and **cheapest
competent** (apply a score floor — it is not cheap if it cannot do the job), and
give in/out $/M, context, speed, and the source with its unit. Name the value
outlier explicitly (highest score per dollar): that is usually the actual
recommendation, and it is rarely the top-ranked or the absolute cheapest model.

## Free-tier pins rot — check the tier before trusting a pin

A cron pinned to a free provider keeps its pin while the provider disappears, and
the run then falls through to a paid fallback while still reporting `ok` (see the
free-tier pitfall in SKILL.md). Before recommending or keeping a free pin,
enumerate today's free models from the live catalogue (`pricing.prompt == 0 and
pricing.completion == 0`) with context size and tool support, and prefer a
**resolvable pair** (cheap paid primary + a distinct fallback) or an aggregate
free route over a single named free model.

## Web extraction

`web_extract` needs a real extraction backend. With `web.extract_backend` set to
a search-only backend (ddgs) every call fails with `search-only backend and
cannot extract URL content`. Either set a real backend (firecrawl / tavily / exa
/ parallel) or fetch directly — urllib for JSON APIs and static HTML, the browser
for JS-rendered pages.
