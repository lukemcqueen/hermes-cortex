# PII deny-list digests

The enforcer's PII gate (`plugins/governance-enforcer/__init__.py`) blocks
writes that carry personal identifiers into the shared surface. It has to know
which strings to look for — but this repository is public, and a readable
deny-list is itself an index of the identifiers it protects: it tells every
reader exactly which strings to search for. The terms are therefore stored as
**SHA-256 digests**, and the gate hashes candidate substrings of the content
instead of matching literals.

## Format

```python
_PII_SENSITIVE_DIGESTS = frozenset(
    base64.b64decode(v) for v in (
        "<base64 of the raw 32-byte SHA-256>",   # length N
        ...
    )
)
_PII_SENSITIVE_LENGTHS = (7, 10, 11, 17)   # the distinct lengths above
```

`_PII_SENSITIVE_LENGTHS` bounds the scan: the gate slides a window of each
listed length over the content, hashes the window, and checks membership. A
term embedded inside a longer token (a URL owner segment, for example) is
therefore still found, exactly as literal matching found it.

Base64 of the raw digest rather than hex: it is shorter, and — unlike a hex
digest — it cannot contain a seven-digit run that this module's own phone
pattern would flag when the file is written through the gate it implements.

## Adding or changing an entry

1. Take the identifier, **lowercased** (matching is case-insensitive).
2. `python3 -c "import hashlib,base64; print(base64.b64encode(hashlib.sha256(b'<term>').digest()).decode())"`
3. Add the value to `_PII_SENSITIVE_DIGESTS` with its length in a trailing
   comment, and add the length to `_PII_SENSITIVE_LENGTHS` if it is new.

Never write the plaintext term into the repository — including in a commit
message, a test fixture, or this document.

## Verifying an entry still fires

Build the probe in a scratch directory, never in the repo, because the probe
has to hold the plaintext:

```python
import importlib.util
spec = importlib.util.spec_from_file_location(
    "enf", "plugins/governance-enforcer/__init__.py")
enf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enf)
args = {"path": "/home/<user>/hermes-cortex/docs/x.md",
        "content": "Built by <term> in Seoul"}
print(enf._check_pii_content_gate("write_file", args) is not None)   # expect True
```

## The URL-allowance class

One entry — the surname — is allowed inside the repo's own public GitHub URL,
because the README and the install one-liners must be able to link it. That is
`_PII_SENSITIVE_URL_ALLOWED`, and the allowance is checked only for digests in
that set. The URL is matched by `_PII_REPO_URL_RE` with a **generic** owner
segment, so the handle is not restated here either.

## What this does and does not buy

It removes the machine-readable list of identifiers from the public repo: a
reader no longer learns which strings are protected, and a scraper cannot lift
the list. It is **not** a secrecy guarantee — SHA-256 over a short,
low-entropy string is brute-forceable, and a reader who guesses a candidate can
confirm it in milliseconds. Treat it as removing the index, not the exposure.

The surname itself stays public by design: it is the owner segment of this
repository's own GitHub URL, which appears throughout the README and docs.

## Test coverage

`tests/test_enforcer_pii_gate.py` cannot build the real terms, so it tests:

- the matching mechanism end to end with **synthetic** digests injected through
  the module's own attributes (blocked in prose, allowed inside the repo URL);
- the **real** surname entry end to end using a value already public in this
  repo — the owner handle parsed out of `README.md`'s own GitHub URL;
- the unchanged email / phone / private-host classes, directly.

It also asserts the enforcer source contains no identifier component, which is
the regression guard for this whole design.
