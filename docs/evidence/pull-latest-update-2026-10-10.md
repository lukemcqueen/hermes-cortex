# Deploy evidence — pull-latest-update (cycle 4897)
## Cliff: cortex-update exit 1, sole cause = pre-existing psycopg/DB migration

    36:✓ Skipping mycortex-mem migration — memory.provider is 'unset' (not mycortex-mem)
    41:✗ fleet venv cannot import: psycopg  (~/.hermes-cortex/venv/bin/python3)
    797:✗ The host is NOT fully migrated. Re-run cortex-update.sh once the database is reachable.
    798:⚠   relock ran on a FAILED exit (rc=1) — enforcement files re-secured
    799:⚠   relock ran on a FAILED exit (rc=1) — enforcement files re-secured

## Deployed-file verification (repo source present at CORTEX_DEPLOY_HOME):
    loop-gov.py _stamp_repo_into_payload refs: 2
    enforcer _inject_session_context refs: 2
    cortex-update-mutex.py exists: yes
