# CISAC IPI SOAP Integration Pattern

Porting the acme-alpha Ruby SOAP client (Savon + Nokogiri) to Python (httpx + ElementTree) for the CISAC IPI Interested Party API.

## Architecture

```
acme-works API (FastAPI) ──→ CISAC IPI System (SOAP over HTTPS)
GET /api/ipi/lookup?q=...       https://api.ipisystem.org/cxf/Change_v1?wsdl
  │                                    │ Basic Auth
  ├── local_lookup() ──→ members/publishers tables (fast path)
  └── lookup_party() ──→ SOAP getInterestedParty
```

## Key Patterns

### 1. Raw XML SOAP via httpx (no zeep)

Ruby uses Savon + WSDL loading. In Python, `zeep` is available but raw SOAP via httpx is simpler — the XML is small and predictable:

```python
import httpx, base64

def _make_soap_request(body_xml: str) -> str:
    endpoint = "https://apitest.ipisystem.org/cxf/Change_v1"
    auth = base64.b64encode(f"{user}:{pass}".encode()).decode()
    envelope = (
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        '<soap:Body>'
        f'{body_xml}'
        '</soap:Body>'
        '</soap:Envelope>'
    )
    headers = {
        "Content-Type": "text/xml;charset=UTF-8",
        "Authorization": f"Basic {auth}",
        "SOAPAction": "",
    }
    with httpx.Client(verify=False, timeout=30) as client:
        resp = client.post(endpoint, content=envelope, headers=headers)
        resp.raise_for_status()
        return resp.text
```

### 2. Namespace-agnostic XML parsing

The SOAP response has namespaces (`urn:ipisystem:api:v1.0:change`) but they're predictable. Use a helper that tries both namespace-aware and bare element paths:

```python
def _find(root, path):
    ns = {"ns1": "urn:ipisystem:api:v1.0:change"}
    result = root.find(path, ns)
    if result is None:
        result = root.find(path)
    return result
```

### 3. getInterestedParty request format

Ruby (Savon):
```ruby
client.call(:get_interested_party, xml: "<soap:Envelope...><ipBaseNr>#{ipb}</ipBaseNr>...</soap:Envelope>")
```

Python (httpx):
```python
body = '<getInterestedParty xmlns="urn:ipisystem:api:v1.0:change">' \
       f'<ipBaseNr>{ipb}</ipBaseNr>' \
       '</getInterestedParty>'
response_xml = _make_soap_request(body)
```

### 4. IPI Number formats

| Type | Format | Example |
|------|--------|---------|
| IPB (Base) | `I-\d{9}-\d` | `I-004744181-4` |
| IPN (Name) | `\d{14}` | `00026903421570` |
| Raw digits | 10 digits → IPB | `0047441814` → `I-004744181-4` |

Normalize before querying — extract digits, detect format, pad if needed.

### 5. Two-tier lookup (local first, then CISAC)

Check the local `members` and `publishers` tables by `ipi_base` / `ipi_name` before hitting the external SOAP API. This is faster and works offline.

```python
result = await db_session.execute(
    select(Member).where(or_(Member.ipi_base == ipb, Member.ipi_name == ipn)).limit(1)
)
```

## Response Fields

The `getInterestedParty` response contains:

- **baseData**: `ipBaseNr`, `ipType` (N=natural/L=legal), `dateOfBirthFoundation`, `sex`, `amendment/society`, `amendment/txTS`
- **status**: `statusCode`, `validFrom`, `validTo`
- **names[]**: each has `ipNameNr`, `nameType` (PA=primary, PP=pseudonym), `name`, `firstname`, `usage`

## client ↔ acme-works mapping

| client (Ruby) | acme-works (Python) |
|---|---|
| `IpiApiHelper` | `app/services/ipi_service.py` |
| `ipi_client_and_request` | `_make_soap_request()` |
| `ipi_get_interested_party` | `lookup_party()` |
| `ipi_interested_party_hash_from_xml_response` | `_parse_party_response()` |
| `Member.ipb` / `Member.ipn` | `Member.ipi_base` / `Member.ipi_name` |
| `ClientInterestedParty` (tblintrpty lookup) | `local_lookup()` on members/publishers |
