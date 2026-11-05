# Resolving a Pi MCP server's interpreter — and the TLS dependency under it

An MCP entry names an interpreter (`"command"` in `~/.pi/agent/mcp.json`). It is the entry's
failure mode, not its arguments: the path can exist, start the server, and still die before any
tool runs. These are the rules for resolving it and for deciding whether a package in that
interpreter is load-bearing.

## Resolve by capability, never by a path that exists

```bash
bash ~/steadfaste-fleet/ops/scripts/lib/python-with-module.sh --print mcp
# exit 3 = NO interpreter on this host can import it
```

The resolver walks `PYTHON` → the declared fleet interpreter (`CORTEX_PYTHON`, else `CORTEX_PYTHON=`
from `~/.steadfaste-fleet/agent.env`) → `HERMES_VENV` → the fleet venv → the Hermes venv → PATH, and
picks the first candidate that actually IMPORTS the module. Use it instead of re-deriving a path:
seven scripts once each needed their own clean-env probe for the same question.

**Capability on the module you named is not capability on the server's real import set.** A server
that speaks HTTPS needs its HTTP client's CA source importable too, so an entry can be "resolved" by
the `mcp` probe and start DEAD on TLS. Probe the whole set the server needs in one command, and treat
a printed path as a claim to check — the file must exist:

```bash
PY=$(bash ~/steadfaste-fleet/ops/scripts/lib/python-with-module.sh --print mcp)
"$PY" -c "import mcp, certifi; print(certifi.where())"   # must print a real cacert.pem
```

## Is a package really required? Trace the IMPORT CHAIN, not the requirements list

A dependency is load-bearing only if something in THAT interpreter imports it. The import chain
answers it; the package name and the requirements file do not.

- **`requests` needs `certifi` at IMPORT time, with no fallback.** `requests/__init__.py` does
  `from . import packages, utils`; `utils.py` does `from . import certs` and then, at module level,
  `DEFAULT_CA_BUNDLE_PATH = certs.where()`; `certs.py` is literally `from certifi import where`.
  So without certifi you get `ModuleNotFoundError: certifi` — not a TLS error — and no env var can
  rescue it: `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` are read at request time, long after
  `certs.where()` has already run. Do not accept "the env overrides it" as a reason a package is
  disposable.
- **Upstream `httpx` requires certifi as well** (its own `requires_dist`), and its SSL path resolves
  `Path(certifi.where())`. The Python `mcp` SDK builds on httpx, so a certifi-less interpreter is a
  real failure for the SDK's users too — the CA source is not unique to requests.
- **`httpx2` (pydantic's fork) drops certifi for `truststore`**, so a venv installed on httpx2 has no
  certifi and is NOT broken by its absence. Check which client the host actually has before declaring
  certifi load-bearing in either direction. A venv is not "missing something" merely because another
  stack would want it.
- **pip's TLS is SELF-CONTAINED — never cite "pip will break" to keep a standalone certifi.** pip
  vendors its own certifi, requests, urllib3 and truststore under `pip/_vendor/` in every pip
  (`ls <prefix>/lib/python3.*/site-packages/pip/_vendor`), so uninstalling the standalone package
  cannot touch it. That reason is false and it propagates: it gets repeated as a premise.

## Reading a CA-bundle failure — the message names no library

`Could not find a suitable TLS CA certificate bundle, invalid path: <p>` is raised BYTE-IDENTICALLY
by **both** `requests` (`adapters.py`, in `cert_verify`) and `httpx` (`_config.py`,
`load_ssl_context_verify`). The text therefore identifies neither; grep every candidate before
naming one, or phrase the finding client-agnostically ("whichever client emitted it, certifi is the
CA source it needs").

What the message DOES establish: the CA source resolved to `<p>` and `<p>` was gone. That is
different from "the package is absent" — an absent package raises `ModuleNotFoundError` at import —
and it selects a different repair. A path pointing into an OLD, partly-removed venv means the package
was still importable and its DATA FILE had been deleted, so repointing the entry at an intact
interpreter (and confirming the bundle is where that interpreter says it is) is the fix, rather than
"install the package" alone. After a home-dir/venv migration, suspect any entry whose `command` still
names the pre-migration interpreter.

## Prove the entry works

```bash
pi mcp list | grep <server>     # connected, with its tools named
```

A `connected` line proves the process started. Call one tool for the capability you actually need
before reporting the server repaired, and prefer a host-optional foreign entry being ABSENT as a PASS
you do not tidy away.

## Bound your claim to the host you can see

A venv, an interpreter and an installed package set are PER HOST. You cannot inspect another host's
venv from yours, so a claim about what is installed THERE is unverifiable from here — say that plainly
instead of agreeing with it. Split every such verdict into: what you read yourself (the package's
source and metadata at the named version), what you inferred, and what you could not check.
