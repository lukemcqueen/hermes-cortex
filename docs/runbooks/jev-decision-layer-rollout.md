# Runbook: put the Jev decision layer on a host

For any agent on any fleet host. Jev takes the **cheap decisions** — which model a turn needs,
which skill to load, which search results to open — so the expensive model only does the thinking.
It is optional per host, and it is **off by default** on a fresh install.

Design + verified behaviour: `docs/design/jev-decision-layer.md`.
Swap proof: `docs/evidence/jev-swap-seam-2026-10-28/run.sh`.

## 0. Do I need to do anything?

Run the doctor and read one line:

```bash
python3 ops/scripts/manage/cortex-doctor.py 2>&1 | grep "Jev decision layer"
```

| What it says | What it means |
|---|---|
| `WARN — not installed on this host` | optional, nothing broken; install it if this host's tokens are worth it |
| `WARN — installed but no routing pools configured` | installed, but routing can never pick a model: run the installer |
| `PASS — installed · routing off · N pool(s)` | healthy, nothing switching. Enable shadow when you want data |
| `WARN/FAIL — <tier>/<spec> leads with <model> ($X vs $Y)` | **a pool leads with a model dearer than the one you run.** Reorder before switching routing on (FAIL = routing is already `on`, i.e. real money) |

## 1. Install or upgrade (one command, idempotent)

```bash
bash ops/scripts/manage/install-jev-layer.sh --check   # ALWAYS first: prints, changes nothing
bash ops/scripts/manage/install-jev-layer.sh           # install / upgrade, then verify
```

Re-running it **is** the upgrade path: it fetches the upstream repo, checks out the **pinned**
revision, runs the upstream installer, runs `jev doctor`, and writes cost-ordered pools if none
exist (`--force-pools` to reorder an existing set, `--commit <sha>` to move the pin).

The deployed copy is at `~/.hermes-cortex/scripts/manage/install-jev-layer.sh`, so a host that has
run `cortex-update.sh` can use it without the repo checkout.

What it changes, so nothing surprises you: plugins into `$HERMES_HOME/plugins/`, 13 skills into
`$HERMES_HOME/skills/jev/`, one script, a `jev` symlink in `~/.local/bin` and `$HERMES_HOME/bin`,
and **two lines in `$HERMES_HOME/config.yaml`** (it backs that file up first — diff against the
backup to confirm). No cron, no systemd unit. `install.py --uninstall` reverses it.

It never reads, asks for, or prints the API key. If `jev doctor` says the key is missing, that is
**the person's** step, in their own terminal: `jev setup-key`.

## 2. Restart, then shadow (operator step)

The plugin loads at gateway start, so until the gateway restarts nothing is being decided and
`$HERMES_HOME/logs/jev-decisions.jsonl` does not exist. After the restart, in a session:

```text
/jev                    status
/jev routing shadow     decide and log, switch nothing   <- start here
/jev notice on          show the one-line routing notice on routed replies
/jev routing on         switch models  (only after shadow data)
```

## 3. Verify (real evidence, not a green light)

```bash
ls -l "$HERMES_HOME/logs/jev-decisions.jsonl"     # rows appear as turns are routed
jev route --prompt "fix the failing test" --current "<provider>:<model>"   # one decision, now
```

`routed: false` with `reason: low confidence …` is the documented fail-open, not a fault: Jev
declines to gamble when it is unsure.

## 3b. Monitoring shadow (what you actually read)

Shadow switches nothing, so the log is the only evidence. Three surfaces:

```bash
python3 ops/scripts/manage/jev-shadow-report.py            # the summary + a verdict
python3 ops/scripts/manage/jev-shadow-report.py --json     # machine-readable
python3 ops/scripts/manage/jev-shadow-report.py --days 1
jev dashboard                                              # live page, loopback
```

The report reads `$HERMES_HOME/logs/jev-decisions.jsonl` (decisions only, never prompt
text) and prints rows, tiers, confidence distribution, `routed` vs `applied`, what it
*would* have switched to with the price delta, and a verdict. **Read the verdict, not the
counts:** a log full of `routed: false` on low confidence means the POOLS are not the
lever — Jev is not recognising those turns as asks, so moving models between pools
changes nothing and the fix is what the turn shows it. Measured on this host's first two
decisions: median confidence **0.075**, nothing would have switched.

For the money side, price the same tokens against a cheaper model — note that a `$0.00`
"actual" means unknown billing, not free, so read the *comparison* line:

```bash
jev spend --hermes-db "$HERMES_HOME/state.db" --compare openrouter:qwen/qwen3.7-flash
# 7 days, 49M tokens: $8.63 on our default vs $2.10 on qwen3.7-flash — the UPPER bound
# of a routing saving, since only the simple turns would move down.
```

`jev replay <turns.jsonl> --current <model>` prices logged turns through the policy, but
it needs a `prompt` field per turn and our decision log deliberately carries none — so
replay needs a separate turn export, not this log.

## 4. The cost rule (the reason the check exists)

Pools are **first fit wins**, so the ORDER is the money. `jev models suggest --write` bands by
price and on the first host it was installed on it led `medium/coding` with a model costing 6.5x
what we already run — switching routing on as-shipped would have **raised** spend. The installer
writes them cheapest-first for `simple`/`medium` and leaves `hard` as deliberate escalation; the
doctor check fails any pool that leads with a dearer model while routing is on.

Before trusting a price, re-read the catalog — it moves, and a stale snapshot once had us quoting
0.0525/M for a model that is 0.56/M:

```bash
jev models list --search <model-id>
```

## 5. Swapping the decision model (steadfaste / self-hosted von)

Not locked to TypeSafe. Any endpoint speaking the typed `/v1/systemone` wire format works:

```bash
TYPESAFE_BASE_URL=https://<steadfaste-host>/jev    # or http://127.0.0.1:<port> locally
TYPESAFE_MODEL=<model-id>
JEV_PROXY_API_KEY=<that gateway's key>             # the ONLY credential an override may receive
```

The real provider key never travels to an override, a dead endpoint fails open, and plaintext is
refused off loopback — all four properties are re-checkable with
`bash docs/evidence/jev-swap-seam-2026-10-28/run.sh` (6/6).

## 6. Do not

- Prefer `/jev routing shadow` in a session: it validates the word list and writes the shared
  state file. There is **no CLI for the routing switch** — `jev switches` covers the FEATURES
  (gate, lanes, retry, vision…) and deliberately excludes routing — so a host with no
  interactive session writes `$HERMES_HOME/jev/state.json` as exactly `{"routing": "shadow"}`:
  the same file, key and value the command writes. Never invent other keys, and re-read it
  with `_setting('routing', 'off')` to confirm the plugin sees it before trusting it.
- Do not enable `routing on` before a day of shadow data, and never with a pool whose head is
  dearer than the model you run.
- Do not copy another host's `routing.json` blind: pools are built from the models **that host**
  can call.
- Do not commit or paste a provider key. `jev doctor` reports presence and length only.
