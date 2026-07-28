"""
Config — paths, constants, and dynamic registries for cortex-doctor.

All path resolution, external service definitions, footprint manifests,
and source-parsing logic lives here.
"""

import os
import re
import sys
from pathlib import Path

# ── Base paths ──────────────────────────────────────────────────
HOME = Path.home()
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform == "linux"
HERMES_HOME = Path(os.environ.get("HERMES_HOME", HOME / ".hermes"))
CORTEX_HOME = Path(os.environ.get("HERMES_CORTEX_HOME", HOME / ".hermes-cortex"))
JOBS_FILE = HERMES_HOME / "cron" / "jobs.json"
CORTEX_ENV = HOME / "hermes-cortex" / ".env"
LEGACY_MODELS_ENV = HERMES_HOME / "models.env"
CONFIG_FILE = HERMES_HOME / "config.yaml"

# ── Cortex repo discovery ───────────────────────────────────────
CORTEX_REPO = Path(os.environ.get("CORTEX_REPO", ""))
if not CORTEX_REPO.is_dir() or not (CORTEX_REPO / "AGENTS.md").exists():
    for candidate in [HOME / "hermes-cortex", HOME / "src" / "hermes-cortex"]:
        if candidate.is_dir() and (candidate / "AGENTS.md").exists():
            CORTEX_REPO = candidate
            break

SCRIPTS_SRC = CORTEX_REPO / "ops" / "scripts"
INSTALL_CRONS = SCRIPTS_SRC / "install-crons.sh"
CORTEX_UPDATE = SCRIPTS_SRC / "cortex-update.sh"
INSTALL_ORCH_CRONS = SCRIPTS_SRC / "install" / "install-orch-crons.sh"
INSTALL_SCRIPT = CORTEX_REPO / "ops" / "install" / "install.sh"
INSTALL_OLLAMA = SCRIPTS_SRC / "install" / "install-ollama.sh"
INSTALL_SCORE_HOOK = SCRIPTS_SRC / "install" / "install-score-hook.sh"
SYMLINK_AUDIT = SCRIPTS_SRC / "manage" / "symlink-audit.sh"
MCP_SERVERS_DIR = CORTEX_REPO / "mcp-servers"

# ── Passthrough ─────────────────────────────────────────────────
CURL = os.environ.get("CURL_BIN", "curl")

# ── Agent role detection ─────────────────────────────────────────
# Roles: orchestrator, server, dev
# Detection: AGENT_TYPE env var → IS_ORCHESTRATOR env var → hostname → fallback
_agent_type = os.environ.get("AGENT_TYPE", "").lower().strip()
if _agent_type in ("orchestrator", "server", "dev"):
    AGENT_ROLE = _agent_type
elif os.environ.get("IS_ORCHESTRATOR", "").lower() in ("true", "1", "yes"):
    AGENT_ROLE = "orchestrator"
else:
    _hostname = os.uname().nodename.split(".")[0]
    AGENT_ROLE = "orchestrator" if _hostname in ("moses", "esther") else "server"

# ── External base URL resolution ────────────────────────────────
def resolve_external_base() -> str:
    """Determine the external base URL for service health checks."""
    base = os.environ.get("CORTEX_DOCTOR_BASE", "")
    if base:
        return base.rstrip("/")

    # Also check .env file (sourced by cortex-update.sh but not always in env)
    _env_file = CORTEX_HOME / ".env"
    try:
        for _line in _env_file.read_text().splitlines():
            _line = _line.strip()
            if _line.startswith("CORTEX_DOCTOR_BASE="):
                _val = _line.split("=", 1)[1].strip().strip('"').strip("'")
                if _val:
                    return _val.rstrip("/")
    except (FileNotFoundError, OSError):
        pass

    for env_key in ("CORTEX_BUS_URL", "CORTEX_BUS_FALLBACK_URL"):
        url = os.environ.get(env_key, "")
        if url:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.scheme and parsed.hostname:
                return f"{parsed.scheme}://{parsed.hostname}"

    bus_conf = CORTEX_HOME / "cortex-bus.conf"
    if bus_conf.exists():
        try:
            for line in bus_conf.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = (x.strip().strip("'\"").strip() for x in line.split("=", 1))
                v = re.sub(r"\s+#.*$", "", v).strip()
                if k in ("CORTEX_BUS_URL", "CORTEX_BUS_FALLBACK_URL") and v:
                    from urllib.parse import urlparse
                    parsed = urlparse(v)
                    if parsed.scheme and parsed.hostname:
                        return f"{parsed.scheme}://{parsed.hostname}"
        except OSError:
            pass

    return "https://localhost"


EXTERNAL_BASE = resolve_external_base()

# ── Port prefix ─────────────────────────────────────────────────
_PORT_PREFIX_ENV = CORTEX_HOME / ".env"
_PORT_PREFIX = "13"
try:
    for _line in _PORT_PREFIX_ENV.read_text().split("\n"):
        _line = _line.strip()
        if _line.startswith("CORTEX_NGINX_PORT_PREFIX="):
            _val = _line.split("=", 1)[1].strip().strip('"').strip("'")
            if _val:
                _PORT_PREFIX = _val
except (FileNotFoundError, OSError, IndexError):
    pass

# ── Gbrain non-orch allowlist ────────────────────────────────────
# Set GBRAIN_ALLOW_NON_ORCH=true in .env to suppress the non-orch guard
# for gbrain-autopilot on machines that legitimately need brain sync
# without being an orchestrator (e.g. cisnet02).
GBRAIN_ALLOW_NON_ORCH = os.environ.get("GBRAIN_ALLOW_NON_ORCH", "").lower() in ("true", "1", "yes")
if not GBRAIN_ALLOW_NON_ORCH:
    try:
        for _line in _PORT_PREFIX_ENV.read_text().split("\n"):
            _line = _line.strip()
            if _line.startswith("GBRAIN_ALLOW_NON_ORCH="):
                _val = _line.split("=", 1)[1].strip().strip('"').strip("'")
                if _val.lower() in ("true", "1", "yes"):
                    GBRAIN_ALLOW_NON_ORCH = True
                    break
    except (FileNotFoundError, OSError):
        pass

# ── Expected MCP servers ────────────────────────────────────────
EXPECTED_MCP_SERVERS = {
    "agent-bus": "agent-bus-mcp.py",
    "loop-governance": "loop-gov-mcp.py",
}

# ── External services ───────────────────────────────────────────
EXTERNAL_SERVICES = [
    ("Dashboard", f"{EXTERNAL_BASE}:{_PORT_PREFIX}001/", "401"),
    ("Langfuse", f"{EXTERNAL_BASE}:{_PORT_PREFIX}002/", "401"),
    ("Agent Bus", f"{EXTERNAL_BASE}:{_PORT_PREFIX}004/health", "401"),
]

# ── Core install footprint ──────────────────────────────────────
CORE_FOOTPRINT = [
    (".hermes", "d", "Hermes config directory"),
    (".hermes/cron", "d", "Cron jobs directory"),
    (".hermes/skills", "d", "Skills directory"),
    (".hermes/config.yaml", "f", "Hermes configuration"),
    (".hermes-cortex", "d", "Cortex home directory"),
    (".hermes-cortex/scripts", "d", "Deployed scripts"),
    (".hermes-cortex/sessions", "d", "Session archive"),
    (".hermes-cortex/hooks", "d", "Shared hooks directory"),
    (".hermes-cortex/state", "d", "State directory"),
    (".hermes-cortex/memory", "d", "Agent memory directory"),
    (".local/bin/hermes", "f", "Hermes CLI binary"),
    ("brain", "d", "Knowledge brain root"),
    ("brain/lessons", "d", "Lessons directory"),
]

# ── Bus alert config paths ──────────────────────────────────────
REPO_OWNERS_PATH = CORTEX_HOME / "config" / "repo-owners.yaml"
REPO_OWNERS_TEMPLATE = CORTEX_REPO / "docs" / "templates" / "repo-owners.yaml"
BUS_CONFIG_PATHS = [
    HOME / ".hermes-cortex" / "cortex-bus.conf",
]


# ── Dynamic registries (parsed from source) ─────────────────────

def parse_expected_crons():
    """Read expected cron names from install-crons.sh's create_cron calls,
    conditionally including orchestrator-only crons based on AGENT_ROLE.

    The source of truth for 'which crons should exist' is the set of create_cron calls,
    NOT the uninstall array (which tracks names for cleanup purposes, including legacy
    crons that no longer have create_cron entries).

    Agent role logic:
    - orchestrator: universal crons + orch crons (full fleet set)
    - server / dev: universal crons only (orch crons excluded)
    """
    text = _read_file(INSTALL_CRONS)
    if not text:
        return []
    names = re.findall(r'^create_cron\s+"([^"]+)"', text, re.MULTILINE)
    orch_crons = set(parse_orch_crons())

    if AGENT_ROLE == "orchestrator":
        # Orchestrator expects ALL crons: universal (from install-crons.sh) + orch crons
        result = [n for n in names if n != "system-heartbeat"]
        result.extend(sorted(orch_crons))
        return result
    else:
        # Server / dev: universal crons only, exclude any that are orch-only
        return [n for n in names if n != "system-heartbeat" and n not in orch_crons]


def parse_orch_crons():
    """Read orchestrator-only cron names from install-orch-crons.sh."""
    text = _read_file(INSTALL_ORCH_CRONS)
    if not text:
        return []
    m = re.search(r'for job in \\\n(.*?); do', text, re.DOTALL)
    if not m:
        return []
    block = m.group(1)
    return re.findall(r'"([^"]+)"', block)


def find_script_consumers():
    """Scan cortex scripts for .env variable names."""
    scripts_dir = SCRIPTS_SRC
    if not scripts_dir.is_dir():
        return {}
    known_vars = ["JUDGE_MODEL", "EMBEDDING_MODEL", "CODING_MODEL", "CREATIVE_MODEL", "DEFAULT_MODEL"]
    consumers = {v: [] for v in known_vars}
    for script in sorted(scripts_dir.iterdir()):
        if not script.is_file():
            continue
        text = script.read_text(errors="replace")
        for var in known_vars:
            if var in text:
                consumers[var].append(script.name)
    return consumers


def _read_file(path):
    """Internal helper — read file content, return empty string on error."""
    try:
        return Path(path).read_text()
    except (FileNotFoundError, OSError):
        return ""
