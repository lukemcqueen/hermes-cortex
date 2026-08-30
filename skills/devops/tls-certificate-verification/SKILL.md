---
name: tls-certificate-verification
description: "Verify TLS cert/key pairs before trusting a deploy."
version: 1.0.0
category: devops
platforms: [linux, macos]
---

# TLS Certificate Verification

Use when a cert/key pair must be installed, swapped, or verified on any server
(nginx, reverse proxy, gateway, agent bus, dashboard) — especially after a
user places cert files and says "check".

## Core rule: `nginx -t` passing ≠ cert valid

A hand-made placeholder loads fine and passes config tests while every TLS
client rejects it. Always probe the actual files (and after reload, the
actually-served chain) before declaring HTTPS done.

## 1. Identity probe — placeholder red flags

```bash
C=/path/to/cert-dir
openssl x509 -in $C/fullchain.pem -noout -subject -issuer -dates
openssl x509 -in $C/fullchain.pem -noout -ext subjectAltName
openssl x509 -in $C/fullchain.pem -noout -text | grep -E 'Basic Constraints|Public-Key'
```

Any of these means the "cert" is unusable as a server cert:
- `CA:TRUE` (server certs need CA:FALSE) — a downloaded intermediate CA
  passed off as a server cert; an AIA URI pointing at an intermediate
  download endpoint (e.g. `http://<short>.i.lencr.org/`) confirms it
- Missing `subjectAltName` / "No extensions in certificate" — SAN is
  required for hostname authentication
- Validity NOT ~90 days (real Let's Encrypt leafs are 90 days; 1-3 years =
  placeholder/CA/self-signed)
- Subject CN that is a CA short name (e.g. `CN=YE1`) instead of a domain
  (multi-domain LE certs carry the customer domain as CN, e.g.
  `CN=ecobiomaterials.com`)

## 2. Key-match proof (hash compare)

```bash
K1=$(openssl x509 -in $C/fullchain.pem -noout -pubkey | openssl pkey -pubin -outform DER | sha256sum | cut -d' ' -f1)
K2=$(openssl pkey -in $C/privkey.pem -pubout -outform DER | sha256sum | cut -d' ' -f1)
[ "$K1" = "$K2" ] && echo MATCH || echo NO-MATCH
```

- K2 = `e3b0c44298fc...` (sha256 of empty input) → key file unparseable
- Curve mismatch (P-256 key vs P-384 cert; compare the `Public-Key:` lines)
  → mismatched regardless of re-encoding
- Key file starting `MIGH`/`MII` (ASN.1 DER, no `-----BEGIN` armor) → nginx
  fails with `PEM_read_bio_PrivateKey() failed`; re-armoring won't fix a
  curve mismatch, so replace with the real pair

## 3. Chain trust — what a public client actually checks (definitive)

```bash
echo | timeout 8 openssl s_client -connect 127.0.0.1:PORT -servername YOUR_DOMAIN \
  -CAfile /etc/ssl/certs/ca-bundle.crt -verify_return_error -showcerts 2>&1 | \
  grep -E 'Verification|Verify return code|subject='
```

`Verification: OK (0)` + exit 0 = served chain validates end-to-end against
the trust store. `error 20` = chain incomplete (missing intermediates). This
is the only test that proves a REAL cert; pass the domain clients will
actually use (SANs must cover it — check `.env`-derived URLs, not just the
file path's domain).

## 4. Reload worker race — one stale probe is NOT a deploy problem

Right after `nginx -s reload`, graceful shutdown keeps OLD workers draining
while new ones serve — consecutive handshakes can return different certs.
Probe 2-3x with ~2s gaps and confirm a single generation of workers
(`ps -ef | grep nginx`) before concluding anything. This bites hard when you
swap certs then immediately test.

## 5. Through-proxy layer semantics (backend not deployed yet)

```bash
curl -sk  -o /dev/null -w '%{http_code}\n' https://127.0.0.1:PORT/health        # 401 (no creds) = auth challenge works
curl -sk -u user:pass -o /dev/null -w '%{http_code}\n' https://127.0.0.1:PORT/health  # 502 (right creds) = auth passed + proxy wired
curl -sk -o /dev/null -w '%{http_code}\n' https://LAN_IP:PORT/health           # 000 = direct-IP block (444) works
```

502 with correct creds is PROOF the proxy is wired to the upstream — the
backend simply isn't listening yet. 502 ≠ broken config. 200 only once the
service runs.

## 6. htpasswd generation when `htpasswd` is absent

Arch and other minimal hosts lack apache-tools. Generate nginx-compatible
apr1 hashes with openssl (salt truncates to 8 chars — use exactly 8):

```bash
HASH=$(openssl passwd -apr1 -salt <8-char> '<password>')
echo "user:$HASH" > /tmp/hermes-htpasswd    # stage readable, then deploy via tight sudoers cp rule
```

Verify round-trip by regenerating the hash and diffing against the stored one
before relying on it.

## NEVER substitute certs without approval (user correction 2026-08-30)

When the provided certs are unusable: report the evidence and ASK where the
real ones are — do NOT generate/install a self-signed or placeholder
substitute on your own. The user may hold the real certs (multi-domain LE
cert under a different CN). Staging a clearly-labeled throwaway pair in /tmp
as an option the user can approve is acceptable; installing it is the user's
call. Fabricating substitute certs when real ones exist was a live
correction in session. Report which checks failed (SAN/item 1), key mismatch
(item 2), and whether the domain(s) in `.env`/client configs are covered by
the eventual real cert.

## Pitfalls recap

| Symptom | Cause |
|---------|-------|
| `nginx -t` emerg `open() ... No such file or directory` | broken sites-enabled symlink (ln target missing a suffix, e.g. `hermes-services` vs `.conf`) — `readlink -f` then `ln -sfn` |
| `PEM_read_bio_PrivateKey() failed` | headerless DER key or wrong-curve key |
| First probe shows old cert after reload | worker drain race — re-probe 2-3x |
| Cert loads but browser/curl rejects | placeholder: CA:TRUE leaf, no SAN, non-LE validity |
| Every request 500s | missing auth_basic_user_file |
