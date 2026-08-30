---
name: tls-cert-preflight
description: "Use when validating TLS certs before deploying an endpoint."
category: devops
triggers:
  - certs were handed over or dropped in and need verification
  - nginx -t fails with cannot load certificate / PEM_read_bio_PrivateKey
  - TLS clients reject a deployed endpoint
  - verifying Let's Encrypt or self-signed cert material before a restart
---

# TLS Cert Pair Preflight

"A cert file exists at the configured path" is NOT a working cert. Placeholder and broken drops are
common — hand-copied intermediates, headerless DER keys, mismatched key/cert. Validate the pair
BEFORE `nginx -t` / reload / restart: an endpoint that starts and silently rejects every TLS handshake
wastes a whole debug cycle.

## Quick probe

```bash
bash ~/.hermes/skills/devops/tls-cert-preflight/scripts/verify-ssl-pair.sh <fullchain.pem> <privkey.pem>
```

Exit 0 = usable server pair; 1 = failures found, each named. Reproduce the checks by hand with:

- parse + metadata:        `openssl x509 -in fullchain.pem -noout -subject -issuer -dates`
- SAN present:             `openssl x509 -in fullchain.pem -noout -ext subjectAltName`
                           (empty or "No extensions" = dead — modern clients reject)
- NOT a CA cert:           `openssl x509 -in fullchain.pem -noout -text | grep CA:TRUE`
                           (a CA/intermediate cert can never serve a hostname)
- key parses:              `openssl pkey -in privkey.pem -noout`
                           (fails on headerless DER: a ~100-200-byte file with no `-----BEGIN` line)
- key matches cert:        compare DER SHA256 of cert pubkey vs key pubkey (see script)

## Fingerprints of a broken/placeholder cert drop (live-verified 2026-08-30)

| Symptom | Meaning |
|---|---|
| `Basic Constraints: CA:TRUE` + no SAN | PEM is an intermediate/CA cert (e.g. CN=YE1 / "Root YE" test chain), not a server leaf |
| ~3-year validity | Real Let's Encrypt leaves = 90 days; multi-year = hand-made/copied placeholder |
| nginx -t: `cannot load certificate key ... PEM_read_bio_PrivateKey() failed` | key is headerless DER (missing PEM armor) — re-armor or replace |
| key parses but different curve/size than cert (e.g. P-256 key beside P-384 cert) | mismatched pair — replace both files |
| No `/etc/letsencrypt/renewal/<domain>.conf`, no `archive/`, live files owned by a user | certbot never issued it; cert is not managed or renewable |

## When nginx is involved

- Run the probe BEFORE `nginx -t`. A pair issue shows up as either `cannot load certificate key`
  (unarmored/mismatched key) or as a config that tests clean but serves a broken handshake.
- The full nginx deployment flow (upstream config, single-listener rule, multi-layer testing, htpasswd)
  lives in the `nginx-web-app-deployment` skill.

## Staging while real certs are pending

Keep the proxy layer testable via `curl -k` with a SAN-correct self-signed pair:

```bash
openssl req -x509 -newkey rsa:2048 -keyout privkey.pem -out fullchain.pem -days 90 -nodes \
  -subj "/CN=DOMAIN" -addext "subjectAltName=DNS:DOMAIN,DNS:localhost"
```

Verify with the probe, swap into the live dir, restart. Real certs drop in later with just a reload.

## Pitfalls

- **DNS reality beats assumptions**: before deciding which domain a cert must cover, resolve it. In the
  2026-08-30 case both realgospelmessage.com AND .org resolved to the same public IP, and the service
  `.env` pointed at .org while the user referenced .com certs — check the actual URL the client uses.
- **certbot sudoers rules ≠ certbot installed**: NOPASSWD rules can exist for a binary that isn't
  there (`command not found`). Policy presence is not binary presence.
- **Ownership smell**: live-dir files owned by an unprivileged user, no `cert.pem`/`chain.pem`/
  `privkey.pem` quartet → hand-placed, not certbot-managed.
- **Check before asking**: all of the above are observable with openssl/getent/ls — verify first,
  then ask the user only for the real cert material or a root path to place it.
