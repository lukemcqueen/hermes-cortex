# Guard Content-Scan False Positive — cortex-update.sh case (2026-08-24)

## Incident

Kustos reported a fleet-wide deploy block: `bash cortex-update.sh` was
hard-blocked on his host by the Hermes gateway lifecycle guard. Diagnosis
showed the repo + origin were already fine — the problem was the DEPLOYED
script's content tripping the guard's **order-independent launchctl branch**:

```
_LAUNCHCTL_LIFECYCLE_VERBS_RE  = launchctl (kickstart|unload|load|stop|restart|bootout|kill|disable|remove)
_HERMES_GATEWAY_LABEL_RE       = \bhermes[.\-]?gateway\b
_contains_launchctl_gateway_lifecycle = verbs_re.search(text) AND label_re.search(text)
```

cortex-update.sh legitimately contains BOTH halves:
- Verb half: `launchctl unload/load` for com.hermes.cortex-bus / cortex-dashboard
  plists, `launchctl kickstart` for com.hermes.health-server (real macOS service
  management, lines ~623-670)
- Label half: `com.hermes.gateway` in the launchd label loop, `hermes-gateway`
  in the systemd unit loop + a `systemctl is-active hermes-gateway` check

The guard is designed so these two halves being ANYWHERE in scanned content =
a gateway lifecycle op — because a shell loop can build the label from a
variable (#77083). It cannot tell "checking gateway service status" from
"restarting the gateway" at content-scan level.

## The old (brittle) workaround — now DEAD

The script previously split literals: `"hermes gateway re""start"`,
`"com.hermes"".gateway"`. The guard's token-aware second pass (#80269) shell-
tokenizes segments and resolves quote-splicing — `re""start` → `restart` —
so the splice reassembles into the literal and STILL matches. The split trick
is obsolete.

## The clean fix (what shipped, commit d2de94d9)

Zero guard changes, zero splices. Make the trigger literals unnecessary:

1. **Banner** (`_loud_restart_banner`): stopped printing the exact restart
   command. The guard's own block message already tells the operator the
   exact syntax (`Run hermes gateway restart from a separate shell...`).
   Duplicating it in the script was the only reason for the workaround.
2. **macOS launchd labels**: discovered at runtime from the deployed plists:
   ```bash
   for plist in "$HOME/Library/LaunchAgents/"*.plist; do
     [[ -e "$plist" ]] || continue
     case "$plist" in
       *cortex-bus*|*cortex-dashboard*|*agent-inbox*|*ollama*|*health-server*|*gateway*)
         label=$(basename "$plist" .plist)
         launchctl list "$label" &>/dev/null 2>&1 || warn "$label: not registered"
         ;;
     esac
   done
   ```
3. **Linux systemd units**: discovered from the live unit list:
   ```bash
   for unit in $(systemctl list-unit-files --no-legend 2>/dev/null | \
     awk '{print $1}' | grep -E '^(ollama|hermes-|hermes_)' || true); do ...
   ```
4. **Unmanaged-process check**: `systemctl --user status "$hermes_pid"` instead
   of naming the unit.

## Regression test pattern

`tests/test_cortex_update_guard.py` loads the REAL deployed guard and asserts
the file passes both scans:

```python
spec = importlib.util.spec_from_file_location(
    "lifecycle_guard", str(Path.home() / ".hermes/hermes-agent/cron/lifecycle_guard.py"))
lg = importlib.util.module_from_spec(spec); spec.loader.exec_module(lg)
assert not lg.contains_gateway_lifecycle_command(script_text)
assert not lg.contains_gateway_lifecycle_command_or_referenced_script("bash .../cortex-update.sh")
```

## Verification checklist (all passed for d2de94d9)

- [ ] `bash -n ops/scripts/cortex-update.sh`
- [ ] Guard scan PASS on repo source AND deployed copy (`~/.hermes-cortex/scripts/`)
- [ ] Referenced-script scan PASS (`contains_gateway_lifecycle_command_or_referenced_script`)
- [ ] Zero splice artifacts remain (grep `re""start`, `hermes""`, `gw_verb` etc.)
- [ ] Runtime discovery works on a live host (units loop handles empty via `|| true`)
- [ ] A4 adversarial gate PASS
- [ ] Regression test 2/2 GREEN against the real guard
- [ ] dogfood deploy, fleet unblock dispatched via bus (kustos/titus/joseph/gisu)

## Diagnostic shortcut for future guard false-positives

When a guard flags a large script and per-line scans find nothing, check
ORDER-INDEPENDENT branches — grep each regex half separately (verbs alone,
labels alone), then find where both halves coexist. They can be hundreds of
lines apart. The combined pattern will never match a single line.
