# Third-Party Licenses — Hermes Cortex

This document lists all third-party components referenced, installed, or used by
Hermes Cortex and describes their respective licenses. This is provided for
attribution and compliance purposes.

Hermes Cortex itself is **MIT License** (see [`LICENSE`](../LICENSE) in the
repository root).

---

## Docker Images

These images are referenced in `ops/install/deploy/docker-compose.langfuse.yml` and
`ops/offline/kiwix-docker-compose.yml`. They are pulled at runtime from their
respective registries and run as-is (no modifications, redistribution, or
embedding).

| Component | License | Source | Permissive? | Notes |
|-----------|---------|--------|-------------|-------|
| langfuse/langfuse | MIT | [GitHub](https://github.com/langfuse/langfuse) | ✅ Yes | Used via Docker; no redistribution of source. Include copyright notice if redistributing the image. |
| langfuse/langfuse-worker | MIT | [GitHub](https://github.com/langfuse/langfuse) | ✅ Yes | Same as langfuse; same image family. |
| clickhouse/clickhouse-server | Apache 2.0 | [GitHub](https://github.com/ClickHouse/ClickHouse) | ✅ Yes | Used via Docker. Apache 2.0 requires preservation of copyright/attribution notices in redistributed copies. |
| postgres:16-alpine | PostgreSQL License | [postgresql.org](https://www.postgresql.org/about/licence/) | ✅ Yes | Liberal OSI-approved license, similar to MIT/BSD. No attribution required for use (required if redistributing PostgreSQL itself). |
| redis:7-alpine | BSD 3-Clause | [redis.io](https://redis.io/legal/licenses/) | ✅ Yes | Redis ≤7.2 is BSD-3-Clause. The `:7-alpine` tag points to Redis 7.2.x. (Note: Redis 8.0+ uses RSALv2/SSPLv1 — not affected here.) |
| minio/minio | AGPL v3.0 | [GitHub](https://github.com/minio/minio) | ❌ Copyleft (strong) | AGPL v3 is a strong copyleft license. If modified and made available over a network, source must be provided to users. Hermes Cortex uses the official image unmodified as a backing store for Langfuse — no modifications are distributed. |
| ghcr.io/kiwix/kiwix-serve | GPL v3+ | [GitHub](https://github.com/kiwix/kiwix-tools) | ❌ Copyleft (strong) | Used unmodified via Docker to serve ZIM content. GPL v3 does not impose requirements on projects that merely invoke the program. |

---

## Software Installed by install.sh

These are installed on the host system (macOS, Linux, or Windows) by the
installer script or its sub-scripts.

| Component | License | Source | Permissive? | Notes |
|-----------|---------|--------|-------------|-------|
| Ollama | MIT | [GitHub](https://github.com/ollama/ollama) | ✅ Yes | Installed via brew/cURL. MIT — no special attribution requirements beyond standard MIT notice. |
| Hermes Agent | MIT | [GitHub](https://github.com/nousresearch/hermes-agent) | ✅ Yes | The host agent for this installer project. MIT-licensed. |
| Bun | MIT (core) + LGPL-2 (JavaScriptCore) | [GitHub](https://github.com/oven-sh/bun) | ✅ Yes (core) | Bun itself is MIT. It **statically links** JavaScriptCore (WebKit), which is LGPL-2. The LGPL applies only if you modify or re-distribute the Bun binary. Hermes Cortex simply installs and invokes it. |
| gbrain | MIT | [GitHub](https://github.com/garrytan/gbrain) | ✅ Yes | Installed via `bun install -g github:garrytan/gbrain`. |
| sqlite-vec (pip) | MIT / Apache 2.0 (dual) | [GitHub](https://github.com/asg017/sqlite-vec) | ✅ Yes | Dual-licensed; choose either. Used for vector search in web cache. |
| Flask (pip) | BSD 3-Clause | [GitHub](https://github.com/pallets/flask) | ✅ Yes | Used for the Cortex Dashboard. BSD-3 requires preservation of copyright notice in redistributions. |
| requests (pip) | Apache 2.0 | [GitHub](https://github.com/psf/requests) | ✅ Yes | Used in web cache and utility scripts. |
| nginx (Homebrew) | 2-Clause BSD | [nginx.org](https://nginx.org/LICENSE) | ✅ Yes | Used as a reverse proxy. The 2-Clause BSD license requires preservation of copyright notice in redistributions. |

---

## Python Packages (pip)

These are installed inside a virtual environment by `install.sh` (Step 11 —
Web Cache) or referenced in the Cortex Dashboard setup:

| Component | License | Notes |
|-----------|---------|-------|
| sqlite-vec | MIT / Apache 2.0 (dual) | See above |
| Flask | BSD 3-Clause | See above |
| requests | Apache 2.0 | See above |

---

## Offline Content Sources

These are **user-downloaded** resources for offline use. They are not
distributed with Hermes Cortex; the project provides tooling to download them
and serve them locally. Users are responsible for complying with their
respective licenses.

| Content | License | Source | Notes |
|---------|---------|--------|-------|
| Wikipedia ZIM files | CC BY-SA 4.0 + GFDL | [download.kiwix.org](https://download.kiwix.org/zim/) | Text is dual-licensed CC BY-SA 4.0 and GFDL. Media may have separate licenses. Attribution is required if redistributing or adapting the content. |
| WikiMed ZIM (medical Wikipedia) | CC BY-SA 4.0 + GFDL | [download.kiwix.org](https://download.kiwix.org/zim/) | Same licensing as Wikipedia. |
| Wikivoyage ZIM files | CC BY-SA 4.0 | [download.kiwix.org](https://download.kiwix.org/zim/) | Text is CC BY-SA 4.0. |
| Wiktionary ZIM files | CC BY-SA 4.0 + GFDL | [download.kiwix.org](https://download.kiwix.org/zim/) | Dual-licensed CC BY-SA 4.0 and GFDL. |
| Hesperian Health Guides PDFs | Custom Open Copyright Policy (Non-Commercial) | [hesperian.org](https://hesperian.org/) | Free PDF download for non-commercial use. Requires attribution. Commercial use, bulk printing (>100 copies), or redistribution in digital formats requires permission from Hesperian. |

---

## License Obligations Summary

For the MIT-licensed Hermes Cortex project, the primary obligations from
third-party components are:

1. **Apache 2.0** (ClickHouse, requests, sqlite-vec): Include the original
   copyright notice if any portion of these libraries' source code is
   redistributed. Mere use via Docker or pip does not trigger this.
2. **BSD 3-Clause / 2-Clause** (Flask, nginx): Same — attribution if
   redistributing source or binary.
3. **AGPL v3.0** (MinIO): This project uses the official MinIO Docker image
   **unmodified**. No AGPL obligations are triggered. If you modify the MinIO
   image and make it available on a network, you must provide source code to
   its users.
4. **GPL v3+** (kiwix-serve): The Docker image is used unmodified. GPL does
   not apply to software that merely invokes it.
5. **CC BY-SA 4.0** (Wikipedia/etc content): If you republish or adapt the
   content, you must attribute the original and share-alike under the same
   license. Using it for personal offline queries is unrestricted.
6. **LGPL-2** (JavaScriptCore via Bun): LGPL conditions apply if the Bun
   binary is modified or redistributed. Hermes Cortex installs Bun as-is.

None of these licenses impose obligations on the **source code** of Hermes
Cortex itself, which remains MIT-licensed.

---

## How to Add a New Component

When adding a new third-party dependency to Hermes Cortex:

1. Determine its license (check the project's GitHub/LICENSE, PyPI, or
   official site).
2. Classify it as permissive or copyleft.
3. Document it here with component name, license, source URL, and notes.
4. If the license requires NOTICE or attribution, add any required notices
   below.

---

*Generated: 2026-06-05*
*Hermes Cortex — MIT License (see [LICENSE](../LICENSE))*
