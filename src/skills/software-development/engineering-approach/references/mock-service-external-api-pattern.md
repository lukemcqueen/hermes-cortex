# Mock Service Pattern for External API Dependencies

## Pattern

Wrap every external API service in a class that attempts the real API call but falls back to mock data when the integration is not available (development, testing, or connectivity failure).

```python
class SomeExternalService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=15)
        self._debug = settings.DEBUG
        self._api_key = settings.SOME_API_KEY

    async def search(self, query: str) -> list[dict]:
        if self._debug and not self._api_key:
            return self._mock_search(query)   # ← dev fallback

        try:
            resp = await self.client.get(f"{self.settings.ENDPOINT}/search", params={"q": query})
            resp.raise_for_status()
            return resp.json()["results"]
        except (httpx.HTTPError, ConnectionError) as e:
            if self._debug:
                return self._mock_search(query)  # ← connection failure fallback
            raise RuntimeError("External API unreachable") from e

    def _mock_search(self, query: str) -> list[dict]:
        return [{"id": "mock-001", "title": f"Sample: {query}", ...}]
```

## When to Use

- **Stripe/Payment gateways** — empty `STRIPE_SECRET_KEY` → return mock checkout URL
- **Works/Metadata APIs** — connection failure → return Korean sample data
- **PDF generation (WeasyPrint)** — import guard → return JSON placeholder
- **Email/SMS services** — dev mode → log to console instead of send
- **Any external HTTP API** where the project needs to function in dev without the dependency

## Condition Flags

Common patterns for triggering mock mode:

| Flag | How | When |
|---|---|---|
| `DEBUG=True` env var | `settings.DEBUG` | Broad dev mode — enable all mocks |
| Empty API key | `not self._api_key` | Specific service not configured |
| `try/except` on connection | `except httpx.HTTPError` | Service down, fall back gracefully |
| Import guard | `try: import weasyprint; except ImportError:` | Optional dependency not installed |

## Pitfalls

- **Mock data can mask real integration bugs.** Test against the real API before production deployment. Add a CI stage that runs with real credentials.
- **Don't mix mock and real data in the same response.** If search returns 3 real results and 1 mock result, downstream code will try to process the mock as real data and produce nonsense. All-or-nothing per request.
- **Mock data must be structurally identical to real data.** Verify by running the same assertion against both mock and real responses. Missing fields or different types cause silent downstream failures.
- **Wrap the `try/except` around the entire API call** — not just the HTTP request. Connection setup, DNS resolution, SSL handshake all throw `httpx.HTTPError`.
- **Use `ConnectionError` as a broader fallback** — DNS failures raise `ConnectionError`, not `httpx.HTTPError`. Catch both for robust fallback.
