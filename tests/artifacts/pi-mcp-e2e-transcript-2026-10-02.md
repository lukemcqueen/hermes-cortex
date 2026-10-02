# Pi MCP end-to-end transcript — 2026-10-02 (host: esther, Linux)

Evidence artifact for `ops/scripts/install/install-pi-mcp.sh`, recorded from a real
run against **pi 1.0.0** (the MCP-capable client), not a mock. The installer's
own regression test does not prove the *client* accepts the config; this does.

## Reproduce

```bash
# 1. a real Pi client with MCP support (>= 1.0). Scratch prefix — nothing global.
npm install --prefix /tmp/piver @earendil-works/pi-coding-agent@1.0.0

# 2. a temp HOME (the real ~/.pi/agent is untouched), with the deployed cortex tree linked
TD=/tmp/pihome
mkdir -p "$TD/.pi/agent" "$TD/.hermes-cortex" "$TD/.hermes"
ln -sfn ~/.hermes-cortex/scripts "$TD/.hermes-cortex/scripts"
ln -sfn ~/.hermes-cortex/tools   "$TD/.hermes-cortex/tools"
ln -sfn ~/.hermes/hermes-agent   "$TD/.hermes/hermes-agent"
printf 'AGENT_NAME=estherpitest\n' > "$TD/.hermes-cortex/agent.env"

# 3. install, then connect with the real client
HOME="$TD" PYTHON=~/.hermes/hermes-agent/venv/bin/python3 \
    bash ops/scripts/install/install-pi-mcp.sh
HOME="$TD" /tmp/piver/node_modules/.bin/pi mcp list --json
```

## Observed — step 3 (`pi mcp list --json`), verbatim

```json
{
  "servers": [
    {
      "name": "loop-governance", "scope": "global", "enabled": true, "exposure": "direct",
      "transport": "/tmp/pihome/.hermes/hermes-agent/venv/bin/python3 /tmp/pihome/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py",
      "state": "connected",
      "tools": ["rereview_change","begin_change","end_change","check_lock","cycle_query",
                "cycle_stats","config_show","config_set","feedback_accept","feedback_override",
                "cache_search","record_issue","advance_task_state","request_interruption",
                "resume_from_interrupt","request_completion","promote_issue_to_task"]
    },
    {
      "name": "tasks", "scope": "global", "enabled": true, "exposure": "direct",
      "state": "connected",
      "tools": ["task_add","task_list","task_pending","task_update","task_switch","task_save_end",
                "task_prune","task_claim","task_unclaim","task_list_claimable","task_board",
                "task_report","task_verify"]
    },
    {
      "name": "executor", "scope": "global", "enabled": true, "exposure": "direct",
      "state": "connected",
      "tools": ["executor_list","executor_probe","execution_request","execution_status",
                "execution_cancel","execution_collect"]
    },
    {
      "name": "agent-bus", "scope": "global", "enabled": true, "exposure": "direct",
      "state": "connected",
      "tools": ["inbox_send","inbox_read","inbox_watch","inbox_delete","inbox_list_agents",
                "inbox_get_agent","inbox_discover","inbox_send_task","inbox_get_task",
                "inbox_cancel_task"]
    }
  ],
  "errors": []
}
```

Result: 4 servers `connected`, 17 + 13 + 6 + 10 = **46 tools**, `errors: []`,
exit status 0. (The `transport` lines are abridged only in the temp-dir prefix.)

## Installer regression test

```bash
$ bash tests/test_pi_mcp_installer.sh
  PASS  run1: user keys preserved + 4 servers + derived AGENT_NAME + exposure
  PASS  run2: idempotent (same server set)
  PASS  --check exits 0
  PASS  --remove strips cortex only, keeps user's own
ALL PASS
```

Mutation check (proves the assertions bite): changing `"exposure": "direct"` to
`"codemode"` in the installer makes the same test report `1 FAILED`; restoring it
returns `ALL PASS`.
