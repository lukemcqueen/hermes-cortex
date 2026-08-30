#!/usr/bin/env bash
# verify-ssl-pair.sh — TLS cert pair preflight probe.
# Usage: verify-ssl-pair.sh <fullchain.pem> <privkey.pem>
# Checks: cert parses, has subjectAltName, is NOT a CA cert (CA:TRUE), key parses,
# and key matches cert. Exit 0 = usable as a server cert pair; 1 = failures found.
# Live-verified 2026-08-30: caught a placeholder drop that was an intermediate CA
# cert (CN=YE1, CA:TRUE, no SAN, 3-yr validity) plus a headerless DER P-256 key
# that did not match the cert's P-384 key.
set -u
FC="${1:?usage: verify-ssl-pair.sh <fullchain.pem> <privkey.pem>}"
KEY="${2:?usage: verify-ssl-pair.sh <fullchain.pem> <privkey.pem>}"
fail=0

if ! openssl x509 -in "$FC" -noout -subject -dates >/dev/null 2>&1; then
  echo "FAIL: $FC is not a parseable X.509 certificate"
  fail=1
else
  openssl x509 -in "$FC" -noout -subject -issuer -dates
  echo "-- subjectAltName --"
  san="$(openssl x509 -in "$FC" -noout -ext subjectAltName 2>/dev/null | sed -n '2p')"
  if [ -z "${san:-}" ]; then
    echo "FAIL: no subjectAltName extension -> cannot serve any hostname"
    fail=1
  else
    echo "$san"
  fi
  echo "-- basic constraints --"
  if openssl x509 -in "$FC" -noout -text 2>/dev/null | grep -q 'CA:TRUE'; then
    echo "FAIL: Basic Constraints CA:TRUE -> this is a CA/intermediate cert, not a server leaf"
    fail=1
  else
    echo "OK: CA:FALSE (server leaf)"
  fi
fi

echo "-- private key --"
if ! openssl pkey -in "$KEY" -noout >/dev/null 2>&1; then
  echo "FAIL: cannot parse key (headerless DER missing PEM armor, or not a key at all)"
  fail=1
else
  openssl pkey -in "$KEY" -noout -text 2>/dev/null | head -1
fi

echo "-- key/cert match --"
k1="$(openssl x509 -in "$FC" -noout -pubkey 2>/dev/null | openssl pkey -pubin -outform DER 2>/dev/null | sha256sum | cut -d' ' -f1)"
k2="$(openssl pkey -in "$KEY" -pubout -outform DER 2>/dev/null | sha256sum | cut -d' ' -f1)"
if [ -n "$k1" ] && [ -n "$k2" ] && [ "$k1" = "$k2" ]; then
  echo "OK: key matches certificate ($k1)"
else
  echo "FAIL: key does not match certificate"
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "== VERDICT: usable server cert pair =="
else
  echo "== VERDICT: FAILURES FOUND =="
fi
exit "$fail"
