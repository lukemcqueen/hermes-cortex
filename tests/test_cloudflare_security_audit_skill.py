"""Guard for the vendored Cloudflare `security-audit` skill.

The skill ships 20 files, two of which are zero-dependency Node validators that
the workflow's phases 4 and 5 tell the agent to RUN. A vendored asset that does
not parse, or a validator whose own suite is red, is a playbook that fails at the
worst moment — so this file drives the shipped bytes rather than trusting that
they were copied correctly.

It is also the RED step that satisfies the pre-commit TDD gate for the two added
production `.cjs` files: the gate exempts `*.test.cjs` as added files but not the
validators themselves, and requires a staged test matching its own pattern. This
is a real guard over those exact assets, not an unrelated test staged to please
the gate (see tests/test_skill_code_assets_parse.py, which states that intent).

Run: bash tests/run-tests.sh tests/test_cloudflare_security_audit_skill.py -q
"""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO / "skills" / "security" / "codebase-security-audit"
SKILL_NAME = "codebase-security-audit"

# The upstream file set, pinned. A partial copy is the failure this catches: the
# six phases reference the companions by relative path, so a missing one is a
# phase that cannot execute.
EXPECTED_FILES = {
    "SKILL.md",
    "RECONNAISSANCE.md",
    "HUNTING.md",
    "ATTACK-CLASSES.md",
    "VALIDATION-AND-REPORTING.md",
    "AI-AND-LLM.md",
    "CLIENT-SIDE.md",
    "CLOUD-AND-DEPLOYMENT.md",
    "DATA-ISOLATION-AND-LIFECYCLE.md",
    "DESKTOP-MOBILE-AND-LOCAL-IPC.md",
    "MEMORY-SAFETY-AND-BINARY.md",
    "PROTOCOLS-RPC-AND-MESSAGING.md",
    "RESOURCE-EXHAUSTION-AND-AVAILABILITY.md",
    "SUPPLY-CHAIN-AND-RELEASE.md",
    "WEB-PROTOCOL-AND-AUTH.md",
    "report-schema.json",
    "validate-findings.cjs",
    "validate-findings.test.cjs",
    "validate-coverage-ledger.cjs",
    "validate-coverage-ledger.test.cjs",
}

NODE_VALIDATORS = ("validate-findings.cjs", "validate-coverage-ledger.cjs")
NODE_SUITES = ("validate-findings.test.cjs", "validate-coverage-ledger.test.cjs")

# Sections whose absence means the body was truncated or swapped.
REQUIRED_BODY_MARKERS = (
    "## Universal execution safety",
    "## Full audit workflow",
    "## Anti-patterns",
)


def _node():
    return shutil.which("node")


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---"), f"{path.name} does not start with ---"
    parts = text.split("---", 2)
    assert len(parts) >= 3, f"{path.name} has no closing ---"
    return yaml.safe_load(parts[1]), text


def _skill_names():
    """First `name:` of every SKILL.md in the tree, via the same traversal a loader uses."""
    names = []
    for skill_md in (REPO / "skills").rglob("SKILL.md"):
        for line in skill_md.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("name:"):
                names.append(line.split(":", 1)[1].strip().strip("\"'"))
                break
    return names


def test_skill_directory_and_full_file_set_landed():
    assert SKILL_DIR.is_dir(), f"missing skill directory: {SKILL_DIR}"
    found = {p.name for p in SKILL_DIR.iterdir() if p.is_file()}
    assert found == EXPECTED_FILES, (
        f"missing: {sorted(EXPECTED_FILES - found)}; unexpected: {sorted(found - EXPECTED_FILES)}"
    )


def test_frontmatter_parses_and_declares_the_renamed_skill():
    fm, _ = _frontmatter(SKILL_DIR / "SKILL.md")
    assert isinstance(fm, dict), "frontmatter is not a YAML mapping"
    assert fm.get("name") == SKILL_NAME, f"name is {fm.get('name')!r}, expected {SKILL_NAME!r}"
    description = fm.get("description")
    assert isinstance(description, str) and description.strip(), "description missing or blank"


def test_the_name_does_not_collide_with_the_server_hardening_skill():
    """`security-audit` already exists in devops; two skills answering one name is ambiguous."""
    names = _skill_names()
    assert names.count(SKILL_NAME) == 1, (
        f"{SKILL_NAME!r} appears {names.count(SKILL_NAME)}x — a duplicate name is ambiguous to load"
    )
    assert "security-audit" in names, "the pre-existing devops security-audit skill vanished"


def test_body_is_the_upstream_workflow_not_a_stub():
    _, text = _frontmatter(SKILL_DIR / "SKILL.md")
    for marker in REQUIRED_BODY_MARKERS:
        assert marker in text, f"body is missing {marker!r} — truncated or replaced"


def test_report_schema_is_valid_json():
    import json

    schema = json.loads((SKILL_DIR / "report-schema.json").read_text(encoding="utf-8"))
    assert isinstance(schema, dict) and schema, "report-schema.json is not a non-empty object"


@pytest.mark.parametrize("asset", NODE_VALIDATORS)
def test_shipped_validators_parse(asset):
    node = _node()
    if not node:
        pytest.skip("no node on PATH — validators NOT checked on this host")
    r = subprocess.run([node, "--check", str(SKILL_DIR / asset)], capture_output=True, text=True)
    assert r.returncode == 0, f"{asset}: {r.stderr.strip()}"


@pytest.mark.parametrize("suite", NODE_SUITES)
def test_shipped_validator_suites_pass(suite):
    """Drive the upstream suite and read its OWN verdict, not just the exit code."""
    node = _node()
    if not node:
        pytest.skip("no node on PATH — validator suites NOT run on this host")
    r = subprocess.run([node, str(SKILL_DIR / suite)], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, f"{suite} exited {r.returncode}:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}"
    assert "# fail 0" in r.stdout, f"{suite} reported failures:\n{r.stdout[-2000:]}"
