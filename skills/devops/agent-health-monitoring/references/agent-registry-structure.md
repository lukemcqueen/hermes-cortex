# Agent Registry Structure

The `agent-registry.json` file at `~/hermes-cortex/ops/services/agent-registry.json` defines every agent's identity, reachability, and health polling configuration. A public `.example` version is committed to the repo with placeholders.

## Key structural rules

### 1. Use external health URLs

Health endpoints must point to the externally-reachable nginx SSL port, not an internal service address. This ensures the orchestrator tests the same path a human or peer agent would use.

```json
// ✅ Correct — external nginx SSL URL
"health_url": "https://your-domain.com:13007/health"

// ❌ Wrong — internal service address (bypasses nginx, false positive)
"health_url": "http://127.0.0.1:8905/health"
```

Rationale: polling against 127.0.0.1 proves only that the service is running locally. Polling against the external URL proves the full path works: DNS → nginx → TLS → proxy → backend.

### 2. Prefer hostname over host

Use `hostname` (worker role label like `"worker-1"`) for most agents. Only use `host` (DNS name) for the orchestrator. This keeps server locations out of the public file.

```json
// ✅ Correct — hostname for non-orchestrator agents
"gisu": {
  "hostname": "worker-1",
  "health_url": "https://your-gisu-host:13007/health"
}

// ✅ Correct — host + hostname for the orchestrator
"moses": {
  "host": "your-domain.com",
  "hostname": "orchestrator-1",
  "health_url": "https://your-domain.com:13007/health"
}
```

### 3. Include platform field

Server agents get `"platform": "linux"`. Client agents (macOS dev machines) get `"platform": "macOS"`. This helps the orchestrator decide probing strategy.

### 4. Descriptions carry port info

The `description` field documents which port range the agent uses, replacing the old separate `port_range` field:

```json
"description": "Moses — orchestrator server, ports 13001-13007"
```

### 5. The .example file must mirror the real file's structure

When the real `agent-registry.json` changes structure (new fields added, fields removed, naming conventions updated), update `src/agent-registry.json.example` to match. The example uses placeholder URLs (`your-domain.com`, `your-gisu-host`, `your-kustos-host`) but must have identical structure so that:

- New agents copy the example and fill in real values
- The orchestrator poller sees the same expected fields
- Documentation referencing the structure stays accurate

### 6. health_method controls polling strategy

| Method | Used for | What Moses does |
|--------|----------|----------------|
| `"http"` | Server agents with reachable health endpoints | HTTP GET to `health_url` |
| `"inbox"` | Client-only agents (no inbound access) | Reads inbox for health push messages |

### 7. health_vector_map must match SERVICE_MAP

The `health_vector_map` array in the registry must match the exact order of service checks in the deployed health endpoint's `SERVICE_MAP`. If the agent runs `health-server.py` with a 9-element compact format, the `health_vector_map` must enumerate those 9 checks in the same order. A mismatch causes the orchestrator to mislabel every health vector index.
