# macOS psql Transport — Container Exec Is Canonical (2026-08-21)

Session trace: Titus traced a macOS-only test-battery failure to a precise
line; Esther verified, widened, fixed, deployed, and fleet-verified. This
reference captures the durable pattern so the class stays fixed.

## The bug class

A Darwin branch that connects as `psql -h 127.0.0.1 -p 15432 -U <role> -d <db>`
with an **empty password** silently depends on `~/.pgpass` for auth. Any DB
without a pgpass entry — scratch/test DBs like `mycortex_test`, or a role
whose line is missing — makes psql prompt for a password and the script
hangs or fails.

Symptom pattern: the deployed CLI works (prod DB `mycortex` is in pgpass)
while the test battery (which points the same runner at a scratch DB) fails
with a password prompt — a "works in prod, fails in tests, macOS only"
signature. Not a schema bug, not a mycortex bug: a transport bug.

## The fix (canonical shape)

Both OSes use the same trust-auth container path; macOS Docker Desktop needs
no `sg docker` group:

```python
if platform.system() == "Darwin":
    # Same trust-auth container path as Linux — no pgpass dependency
    # (macOS Docker Desktop: no `sg docker` group needed).
    return [
        "docker", "exec", "-i", "mycortex-postgres",
        "psql", "-U", role, "-d", db_name,
        "-v", "ON_ERROR_STOP=1", "-t", "-A",
    ]
# Linux — container exec via sg docker group
return ["sg", "docker", "-c",
        f"docker exec -i mycortex-postgres psql -U {role} -d {db_name} -v ON_ERROR_STOP=1 -t -A"]
```

- Keep the single transport seam (`_psql_base(role, db_name) -> list[str]`).
- Role-parameterized in CLI/CRUD scripts; single-role in migrate.py
  (owner-run DDL).
- Removed Darwin dead weight: `MYCORTEX_CONFIG` (`~/.hermes-cortex/
  mycortex.conf` `database_url`), `urlparse`/`shutil.which("psql")` fallback,
  `os.environ.get("MYCORTEX_DB_URL")`, and the `json`/`os`/`shutil` imports
  that only the dead branch used.

## Sibling sweep — fix the class, not the ticket

The same latent Darwin branch sat in **8 files** (found via
`grep -rn '15432\|mycortex.conf' ops/`): mycortex/tasks/learnings
`migrate.py`, the `mycortex` CLI, `task-db.py`, `learning-ledger.py`,
`migrate-bus-todos.py`, `agent-mycortex-retention.py`. Each had its own
test battery that would fail the same way on macOS. One file fixed without
the sweep = next macOS test failure in a sibling.

## Verifying an OS branch without that OS (platform mock)

Exercise the Darwin branch on a Linux host against the REAL container:

```python
import platform, subprocess
from importlib.machinery import SourceFileLoader

orig = platform.system
platform.system = lambda: "Darwin"
try:
    mig = SourceFileLoader("mig", "/abs/path/migrate.py").load_module()
    argv = mig._psql_base("mycortex_test")   # shape assert here, INSIDE try
    p = subprocess.run(mig._psql_base("mycortex"),
                       input="SELECT 1;\n", capture_output=True, text=True)
    assert p.returncode == 0 and p.stdout.strip() == "1"
finally:
    platform.system = orig                    # restore AFTER the last assert
```

Pitfalls learned live:

- **`importlib.util.spec_from_file_location` returns None for files with no
  `.py` extension** (the extension-free `mycortex` CLI) — use
  `SourceFileLoader` for any file that might lack the suffix.
- **The `try/finally` restore trap**: if the asserts sit AFTER the `finally`,
  `platform.system` is already restored and the Darwin branch silently
  returns the Linux argv — the failure reads as "the mock didn't work" and
  costs a debug round. Keep every assert inside the `try`.
- Assert BOTH shapes (argv contents) AND behavior (running the argv against
  the live container), plus that the Linux branch is untouched
  (`_psql_base(...)[0] == "sg"` after restore).

## Verification evidence (2026-08-21)

- 8/8 `py_compile`; zero `15432`/`MYCORTEX_CONFIG` refs left.
- Darwin argv executed against live container: `SELECT 1` rc=0; CLI as
  `mycortex_reader_esther` rc=0.
- Batteries: mycortex 15/15, tasks 93/93, learnings 21/21.
- Adversarial A2/A4: 0 new findings vs HEAD (Mediums pre-existing).
- Deployed copies verified to carry the fix; deployed runner no-op rc=0.
