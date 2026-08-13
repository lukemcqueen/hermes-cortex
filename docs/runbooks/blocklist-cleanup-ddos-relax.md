# Runbook: Blocklist Cleanup & DDoS Relaxation — Implement on Each Host

**Date:** 2026-08-08 · **Author:** Esther · **Status:** Implemented on Esther, pending fleet
**Why:** Legitimate users on Kustos/Gisu/Joseph were being blocked — Luke got
kicked off after refreshing a dashboard a few times in a minute.

---

## TL;DR — the four changes

| # | Change | Commit | Agent action |
|---|--------|--------|--------------|
| 1 | DDoS rate-limit bursts relaxed (rates kept) | `dc8d47f2` | Manually apply nginx templates (anti-tamper — agents CANNOT) |
| 2 | Scanner adds ONLY fail2ban-confirmed abusers | `1bb98896` | `cortex-update.sh` deploys the new scanner |
| 3 | Scanner never re-adds allow-listed IPs | `95933111` | `cortex-update.sh` deploys |
| 4 | Evidence-based blocklist classifier (new tool) | `95933111` | Run on Joseph (primary discovery host) |

**Template changes are MANUAL-only** (Luke 2026-08-08: all templates are
manually installed to prevent agent tampering). Only `blocked_ips.add` is
agent-writable. Do NOT attempt to edit nginx templates from an agent.

---

## 1. DDoS burst relaxation (nginx templates — MANUAL)

**Problem:** `limit_req zone=auth rate=5r/s burst=10 nodelay` + `limit_conn 10`.
A dashboard is an SPA: one refresh fires 15-30 parallel requests, blowing the
burst; `nodelay` converts excess to instant 503 = "kicked off."

**Changed in repo templates** (`ops/install/deploy/nginx/`):

| Knob | Before | After |
|------|--------|-------|
| `zone=general` burst | 40 | **150** |
| `zone=auth` burst | 10 | **40** |
| health burst | 10 | **40** |
| `limit_conn conn_limit` | 10 | **50** |
| **Sustained rates** | 20r/s, 5r/s | **unchanged** (this is the DDoS catch) |

**To apply on a host (manual, needs root):**
```bash
sudo cp ~/hermes-cortex/ops/install/deploy/nginx/hermes-zone-defs.conf /etc/nginx/hermes-zone-defs.conf
sudo cp /tmp/hermes-services-processed.conf /etc/nginx/sites-available/hermes-services.conf
# or re-run cortex-update.sh to regenerate, then:
sudo nginx -t && sudo nginx -s reload
```
`nodelay` is kept deliberately — excess past the (larger) burst still 503s,
so true floods are still shed instantly. Only the burst tolerance changed.

---

## 2. Scanner: only true abusers (AUTO — deploys via cortex-update)

**Problem:** the old scanner added ANY IP with ≥10 req/60min — no
discrimination. One legit dashboard refresh = 15-30 requests = tripped it.
99.9% of the 19K-entry list is volume-only suspects, never fail2ban-banned.

**New behavior** (`ops/scripts/manage/nginx-security-scanner.sh`):
- Volume-threshold path **removed entirely**
- **fail2ban bans are the sole auto-source** (real attack evidence)
- Reads rotated fail2ban logs (`.log.1`, `.gz`) so history isn't missed
- Allow-list guard: reads `/etc/nginx/allow-ips-manual.conf` (exact + CIDR)
  and skips allow-listed IPs before appending

**Agent action:** none beyond normal `cortex-update.sh`. Verify after deploy:
```bash
grep -c "volume" ~/.hermes-cortex/scripts/nginx-security-scanner.sh  # expect 0 hits on old code
grep -c "_is_allowed_ip" ~/.hermes-cortex/scripts/nginx-security-scanner.sh  # expect 1
```

---

## 3. Allow-list guard (AUTO — in the same scanner)

The scanner now respects `/etc/nginx/allow-ips-manual.conf`. This file is the
**manual, agent-tamper-proof** surface — agents may READ it but never edit it.
Legit office/VPN/user IPs belong there (human-managed).

Confirmed office IPs removed from `blocked_ips.add` source (commit `95933111`):
`222.111.179.67`, `115.21.71.146`, `115.21.71.147`, `52.47.194.69`.

---

## 4. Evidence-based classifier (NEW TOOL — run on Joseph)

**Purpose:** answer "which of the 19K blocked IPs are real abusers vs
volume false-positives?" WITHOUT deleting the bad ones.

**New script:** `ops/scripts/manage/classify-blocked-ips.sh`
(registered in cortex-update.sh, deploys to `~/.hermes-cortex/scripts/`)

**Run on the host with the fail2ban ban evidence — Joseph is primary
discovery, Gisu/Kustos second/third** (Luke 2026-08-08):
```bash
bash ~/.hermes-cortex/scripts/classify-blocked-ips.sh
```

**Output (review-only — NEVER edits or deploys anything):**
- `blocked_ips.confirmed` — fail2ban-banned IPs (STRONG evidence, KEEP)
- `blocked_ips.review` — volume-only suspects (WEAK evidence, review/remove)
- Console summary: strong/stale/weak/allow-listed counts

**Classification tiers:**
| Tier | Evidence | Verdict |
|------|----------|---------|
| STRONG | fail2ban ban in log history | KEEP |
| STALE | banned then unbanned (IP recycled) | review later |
| WEAK | volume-only, never banned | removal candidates |
| ALLOWED | in allow-ips-manual.conf | excluded (never blocked) |

**Result on Esther:** 19,176/19,190 entries (99.9%) are WEAK — volume-only.
Real classification must run on Joseph (that's where the bans are).

**After review, removing confirmed-false-positives:**
```bash
# 1. Confirm the IP is truly legit (user report, office range, etc.)
# 2. Add to /etc/nginx/allow-ips-manual.conf (manual, human action):
#      allow X.X.X.X;   # reason
# 3. Remove from blocked_ips.add source:
grep -vE '^(X\.X\.X\.X)$' blocked_ips.add > /tmp/b && mv /tmp/b blocked_ips.add
# 4. Commit + push (agent can do this — blocked_ips.add is agent-writable)
# 5. The deploy-time generator strips allow-listed IPs automatically
```

**Safety net:** fail2ban stays armed. Any IP removed from the static list
that is actually attacking gets re-banned automatically within minutes. The
static list should hold only confirmed abusers; fail2ban handles the rest.

---

## Agent implementation checklist (per host)

- [ ] `git pull origin main` + `cortex-update.sh` (deploys scanner + classifier)
- [ ] Verify scanner no longer has volume path (grep above)
- [ ] Run `classify-blocked-ips.sh` — review output, do NOT auto-delete
- [ ] NEVER edit nginx templates or allow-ips-manual.conf (manual domain)
- [ ] Only `blocked_ips.add` is agent-writable — and only for confirmed abusers

---

## Execution log — 2026-08-13 fleet prune (Esther)

**Trigger:** Luke — "prune the blocked IPs; it was set too aggressively, too
many good IPs captured."

**Keep-set (git-evidence technique):** `git diff 95933111..HEAD --
ops/install/deploy/nginx/blocked_ips.add` added-lines = every IP the fleet
pipeline added since the 08-08 pollution fix. Those are fail2ban-confirmed
bans from moses/joseph/kustos/gisu (the pipeline's only post-fix source).
Result: 19,983 → 836 IPs (-96.5%), then +8 from the local scanner's
rotated-log history the same day → 844. This beats the classifier-on-Joseph
approach when you need the answer now and SSH isn't set up: the git history
IS the fail2ban evidence.

**Also fixed (root cause):** the pipeline's Step 2 (direct fail2ban log
collection) had no allow-list guard — the scanner had one since 08-08, the
pipeline didn't. It re-added allow-listed office IPs (222.111.179.67,
115.21.71.146/147) on 08-10..08-12. Guard mirrored into
`agent-nginx-threat-pipeline.sh` (commit 8b8e8089). Without this, every
transient fail2ban ban of a legit IP re-pollutes the source forever.

**Fleet deploy:** UPDATE_REQUEST (pull + cortex-update) then
EXEC deploy-blocked-ips.sh to joseph/kustos/gisu/moses — each host must pull
the pruned source BEFORE regenerating its live conf, or it re-deploys the old
19K list.

## Rollback

- Scanner revert: restore old scanner from git, cortex-update.
- Burst changes: re-apply old values manually (templates are manual anyway).
- The blocklist itself is never destroyed — cleanup only ever removes
  allow-listed or weak-evidence IPs, and fail2ban re-bans real threats.
