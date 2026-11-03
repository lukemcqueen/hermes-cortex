This skill is backed by the canonical deployment guide in the steadfaste-fleet repo:

- `steadfaste-fleet/deploy/README-langfuse-clickhouse.md` — Full deployment and troubleshooting guide
- `steadfaste-fleet/deploy/docker-compose.langfuse.yml` — Canonical Docker compose file
- `steadfaste-fleet/deploy/clickhouse-config.d/` — ClickHouse config files (log level, low-memory tuning, profile defaults)
- `steadfaste-fleet/ops/scripts/cortex-setup-langfuse.sh` — Automated setup script (secrets generation, API key insertion)

The deploy README covers:
- File structure and where configs mount
- chmod 644 requirement for ClickHouse configs
- ClickHouse 25.5 SIGSEGV crash bug details
- Full first-time setup (secrets, configs, stack startup)
- Hermes API key generation and plugin wiring
- Common issues and fixes

Always pull latest from steadfaste-fleet before referencing these files:
```bash
cd ~/steadfaste-fleet && git pull
```