# MCP registration runbook — "my loop-governance tools are missing"

A server can be *registered* and still expose nothing. Registrations are read at
**startup**, so a repaired entry does not appear until the client/gateway restarts.

## Check, in this order (read-only)

```bash
<fleet python> ~/hermes-cortex/ops/scripts/manage/mcp_wiring.py   # paths + interpreter per server
hermes mcp list                                                  # what THIS host registers
hermes mcp test <name>                                           # starts it; does it connect?
```

The auditor prints per server: `PASS` (paths exist, fleet venv), `WARN` (bare
interpreter, or a command inside the Hermes venv), `FAIL` (a registered path does
not exist). Exit 0 clean, 1 broken entry, 3 = COULD NOT VERIFY.

## Fix by branch

| What the check says | Fix |
|---|---|
| entry missing | `hermes mcp add <name> --command ~/.hermes-cortex/venv/bin/python3 --args ~/hermes-cortex/mcp-servers/<script>` |
| a registered path does NOT exist | deploy it: `bash ~/hermes-cortex/ops/scripts/cortex-update.sh`, re-check |
| the fleet venv cannot import `mcp` | `~/.hermes-cortex/venv/bin/python3 ~/.hermes-cortex/scripts/fix-cortex-venv.py` |
| command is the Hermes venv or bare `python3` | `hermes mcp remove <name> && hermes mcp add <name> --command …` (there is no `hermes mcp update`) |

## Re-registering against a different interpreter (the fleet-venv migration)

`hermes mcp add` is INTERACTIVE: it lists the server's tools and asks
`Enable all N tools? [Y/n/select]`. With stdin closed — `< /dev/null`, a cron, any
non-TTY runner — it reads EOF, prints `Cancelled.`, and writes NOTHING, while the
`remove` before it has already succeeded. Run a remove/add pair non-interactively
and you strip every server you touch: `mcp_servers:` comes back empty and both
commands exit 0. So:

```bash
cp -a ~/.hermes/config.yaml ~/.hermes/cache/scratch/config.yaml.bak-$(date +%Y%m%d_%H%M%S)
for s in agent-bus loop-governance tasks executor; do
  printf 'y\n' | hermes mcp add "$s" --command ~/.hermes-cortex/venv/bin/python3 --args "$DEPLOYED_PATH_FOR_$s"
done
sed -n '/^mcp_servers:/,/^[a-z_]*:/p' ~/.hermes/config.yaml   # read the block back
python3 ~/hermes-cortex/ops/scripts/manage/mcp_wiring.py      # then the audit, not the rc
```

- **Keep the ARGS as the deployed script paths** (`~/.hermes-cortex/scripts/<name>.py`,
  `~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py`): that is what the fleet's own
  installer registers (`ops/scripts/install/install-pi-mcp.sh`) and it keeps the deploy
  boundary — pointing a server at the repo working tree makes an uncommitted edit live.
  Change the `command` only.
- **Prove the new interpreter can run the server BEFORE swapping it**: `timeout 15 <venv>/bin/python3 <server> < /dev/null` should exit 0 on stdin EOF (a stdio server that
  imports cleanly does). A server that hangs or traces back is not a candidate.
- **A live gateway keeps the OLD registration until it restarts** (and agents cannot
  restart it): the edit is correct and pending, not broken. Say which half is loaded.
- **Read the config diff key by key, not as text.** The CLI rewrites the file, so
  unrelated keys can move or vanish (an empty mapping like `cron: {}` is dropped); compare
  parsed YAML and confirm only the intended values changed.

## Rules learned the hard way

- **Audit paths, not names.** A name-in-config-text check once passed while the
  entry was keyed `agent-bus` and the expectation said `cortex-bus` — which
  matched the *filename* in the args.
- **A bare command name is a PATH lookup, not a relative path.** Treating
  `command: python3` as a path reports "python3 does not exist"; resolve it with
  `which` and warn that it should be the fleet venv.
- **One authoritative verdict.** Two checks judging the same line while
  disagreeing (one passing any `venv`+`python3`, the other warning it is the
  Hermes venv) is worse than one; keep the presence line informational and let a
  single line judge the interpreter.
- **Never print a fix command you have not run.** Verify subcommands with
  `hermes mcp --help` before shipping fix text or docs that tell an operator or
  another agent to run it.
- **`--fix`-style automation must key on the real registered name**, or it adds a
  SECOND, differently-named server for the same script.
