# FormData Upload Auth + Structured Error Handling

## FormData Upload — Auth Token

When uploading files via `fetch()` (not `fetchJSON()`), you MUST manually add the `Authorization` header. `fetchJSON` auto-injects the token; raw `fetch` does not.

**Required pattern:**

```typescript
const token = getStoredToken();
const headers: Record<string, string> = {};
if (token) headers['Authorization'] = `Bearer ${token}`;
const formData = new FormData();
formData.append('file', file);
return fetch(`${BASE_URL}/path`, { method: 'POST', headers, body: formData });
```

**Why raw fetch is unavoidable:** `fetchJSON` forces `Content-Type: application/json`. FormData uploads need the browser to auto-set `Content-Type: multipart/form-data; boundary=...`. Setting an explicit content type breaks the boundary parameter.

## Structured Error → `[object Object]`

When FastAPI returns structured error details (dict or list), the naive handler produces `[object Object]`:

```typescript
throw new Error(body.detail || `Upload failed: ${r.status}`);
// Error: [object Object]  ← body.detail is a dict
```

**Fix — stringify the detail before throwing:**

```typescript
const detail = body.detail;
const message = typeof detail === 'string' ? detail
  : Array.isArray(detail) ? detail.map((d: any) => d.msg || JSON.stringify(d)).join('; ')
  : typeof detail === 'object' && detail ? JSON.stringify(detail)
  : `Upload failed: ${r.status}`;
throw new Error(message);
```

Extract this into a shared `extractErrorMessage(body, fallback)` helper for all `fetch()` callers.
