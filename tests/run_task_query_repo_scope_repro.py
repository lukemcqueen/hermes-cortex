#!/usr/bin/env python3
"""Reproduction: cross-repo task leakage — PINNED BEFORE/AFTER on the real path.

Reported by Titus: `mcp__tasks__task_pending` (and task_list/task_board/the queue
views) returned EVERY repo's tasks for an agent, so an agent working in repo A
picked up and reported work belonging to repo B.

What this drives, against a REAL Postgres (scratch DB, live rows untouched) and
the REAL MCP server over stdio:

  PRE-FIX   `git show <base>:ops/scripts/manage/task-db.py` — the revision named
            on the command line (default: the last commit that touched the file
            BEFORE the fix). It must LEAK: `pending` returns all repos' rows.
  CURRENT   the working-tree engine + the working-tree MCP server. It must SCOPE:
            repo=steadfaste sees its own rows + untagged rows, never the
            `steadfaste-s1-model` row; an unresolvable repo returns [].
  DEPLOYED  the deployed copies (<deploy>/scripts/task-db.py + task-mcp.py) — a
            green check on the repo copy proves nothing about what agents run.

The comparison is pinned to an immutable revision and BOTH revisions are named
in the artifact, so it stays re-runnable after this change lands.

Usage:
  python3 tests/run_task_query_repo_scope_repro.py [--base <sha>] [--write-artifact]
Exit: 0 all expectations held; 1 an expectation was violated; 2 could not verify.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TASK_DB_REL = "ops/scripts/manage/task-db.py"
TASK_MCP_REL = "mcp-servers/task-mcp.py"
DEPLOY = Path.home() / ".hermes-cortex"
SCRATCH_DB = os.environ.get("TASK_REPO_SCOPE_TEST_DB", "tasks_repo_scope_test")
READER_ROLE = "mycortex_reader"
CONTAINER = "mycortex-postgres"

# The PRE-FIX revision, PINNED. 55887b47 = the commit before the repo-scoping
# change (`fix(tasks): scope every task query to the caller's own repo`,
# aa293f41). Pinned HERE, in the script's own default, because a baseline that
# defaults to HEAD stops discriminating the moment the change lands: HEAD then
# IS the fix, `git show HEAD:` materialises the FIXED engine, and the PRE-FIX
# expectation fails for the wrong reason (measured 2026-10-14). Override with
# --base only to compare a different revision deliberately.
DEFAULT_BASE = "55887b47f0fd1f7d689931a292e2997fa4d0b10f"

# Seeded rows: the session repo, a DIFFERENT repo (the leak), and an untagged row.
OWN_REPO = "steadfaste"
OTHER_REPO = "steadfaste-s1-model"
SEEDS = (("probe-own", OWN_REPO), ("probe-other", OTHER_REPO), ("probe-untagged", None))

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    RESULTS.append((ok, f"{label}{(' — ' + detail) if detail else ''}"))
    return ok


def venv_python() -> str:
    cand = DEPLOY / "venv" / "bin" / "python3"
    return str(cand) if cand.is_file() else sys.executable


# ── scratch DB ────────────────────────────────────────────────

def _psql(sql: str) -> subprocess.CompletedProcess:
    if platform.system() == "Darwin":
        cmd = ["docker", "exec", "-i", CONTAINER, "psql", "-U", "mycortex",
               "-d", "mycortex", "-t", "-A", "-v", "ON_ERROR_STOP=1"]
    else:
        cmd = ["docker", "exec", "-i", CONTAINER, "psql", "-U", "mycortex",
               "-d", "mycortex", "-t", "-A", "-v", "ON_ERROR_STOP=1"]
    return subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=60)


def setup_scratch() -> bool:
    _psql(f"DROP DATABASE IF EXISTS {SCRATCH_DB};")
    r = _psql(f"CREATE DATABASE {SCRATCH_DB};")
    if r.returncode != 0 and "already exists" not in (r.stderr or ""):
        check(False, "scratch DB created", (r.stderr or "").strip()[:160])
        return False
    migrate = REPO / "ops" / "services" / "tasks" / "migrate.py"
    m = subprocess.run([venv_python(), str(migrate), "--db-name", SCRATCH_DB],
                       capture_output=True, text=True, timeout=180)
    ok = m.returncode == 0
    check(ok, "scratch DB schema applied", (m.stdout or m.stderr or "").strip()[-160:])
    return ok


def teardown_scratch() -> None:
    _psql(f"DROP DATABASE IF EXISTS {SCRATCH_DB};")


def _engine_env() -> dict:
    env = dict(os.environ)
    env.update({"TASK_DB_NAME": SCRATCH_DB, "TASK_DB_ROLE": READER_ROLE,
                "HERMES_PROFILE": READER_ROLE})
    env.pop("CORTEX_SESSION_REPO", None)
    return env


def _run_engine(engine: Path, args: list[str], cwd: Path) -> tuple[int, str, str]:
    r = subprocess.run([venv_python(), str(engine), *args],
                       capture_output=True, text=True, timeout=120,
                       env=_engine_env(), cwd=str(cwd))
    return r.returncode, r.stdout, r.stderr


# ── real MCP server over stdio ────────────────────────────────

class McpClient:
    def __init__(self, server: Path, cwd: Path):
        self.proc = subprocess.Popen(
            [venv_python(), str(server)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=_engine_env(), cwd=str(cwd), bufsize=1)

    def request(self, obj: dict) -> dict:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError(f"MCP server closed (stderr: "
                                   f"{self._stderr()[:300]})")
            line = line.strip()
            if not line.startswith("{"):
                continue
            msg = json.loads(line)
            if msg.get("id") == obj.get("id"):
                return msg

    def notify(self, obj: dict) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def _stderr(self) -> str:
        try:
            return self.proc.stderr.read()  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            return ""

    def close(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self.proc.kill()


def _call_tool(client: McpClient, name: str, args: dict) -> str:
    resp = client.request({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                           "params": {"name": name, "arguments": args}})
    content = resp.get("result", {}).get("content", [])
    return content[0]["text"] if content else ""


def _timeout(signum, frame):  # noqa: ANN001
    raise TimeoutError("step exceeded its wall-clock budget")


# ── Main ──────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None,
                    help="pre-fix revision (default: HEAD)")
    ap.add_argument("--write-artifact", action="store_true")
    args = ap.parse_args()

    signal.signal(signal.SIGALRM, _timeout)
    base = args.base or DEFAULT_BASE
    tip = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()

    print(f"REPO      {REPO}")
    print(f"BASE      {base}  (pre-fix engine, materialised from git)")
    print(f"TIP       {tip}  (working tree = the change under test)")
    print(f"SCRATCH   {SCRATCH_DB} on {CONTAINER} (live rows untouched)")
    print()

    if not setup_scratch():
        print("COULD NOT VERIFY: scratch DB setup failed")
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="repo-scope-repro-"))
    nongit = tmp / "non-git-cwd"
    nongit.mkdir()
    try:
        # PRE-FIX engine, materialised from the pinned revision.
        raw = subprocess.run(["git", "-C", str(REPO), "show",
                              f"{base}:{TASK_DB_REL}"],
                             capture_output=True, text=True)
        if raw.returncode != 0:
            print(f"COULD NOT VERIFY: cannot read {TASK_DB_REL} at {base}")
            return 2
        (tmp / "task-db-prefix.py").write_text(raw.stdout)
        prefix_engine = tmp / "task-db-prefix.py"

        current_engine = REPO / TASK_DB_REL
        mcp_server = REPO / TASK_MCP_REL

        # ── 1. seed three rows through the CURRENT engine ────────
        for content, repo in SEEDS:
            cmd = ["add", content, "--source", "manual", "--no-notify"]
            if repo:
                cmd += ["--repo", repo]
            rc, out, err = _run_engine(current_engine, cmd, REPO)
            if not check(rc == 0, f"seed '{content}'",
                         (out + err).strip().splitlines()[0] if (out or err) else ""):
                print("COULD NOT VERIFY: seeding failed")
                return 2
        print()

        # ── 2. PRE-FIX must LEAK the other repo's row ────────────
        signal.alarm(120)
        rc, out, err = _run_engine(prefix_engine, ["pending"], REPO)
        signal.alarm(0)
        try:
            items = json.loads(out)
        except json.JSONDecodeError:
            items = []
        repos = sorted({str(i.get("repo")) for i in items})
        check(rc == 0 and OTHER_REPO in repos,
              "PRE-FIX leaks the other repo's task (the reported bug)",
              f"repo=steadfaste pending -> repos {repos}")

        # ── 3. CURRENT engine scopes ─────────────────────────────
        signal.alarm(120)
        rc, out, _err = _run_engine(current_engine,
                                    ["pending", "--repo", OWN_REPO], nongit)
        signal.alarm(0)
        items = json.loads(out) if out.strip() else []
        seen = {i.get("content") for i in items}
        check(rc == 0 and "probe-own" in seen,
              "scoped pending returns the caller's own repo's task", f"seen={sorted(seen)}")
        check("probe-untagged" in seen,
              "scoped pending still returns legacy untagged rows", f"seen={sorted(seen)}")
        check("probe-other" not in seen,
              "scoped pending NEVER returns another repo's task", f"seen={sorted(seen)}")

        # ── 4. unknown repo -> NO tasks (operator rule) ──────────
        signal.alarm(120)
        rc, out, err = _run_engine(current_engine, ["pending"], nongit)
        signal.alarm(0)
        check(rc == 0 and json.loads(out) == [],
              "unresolvable repo returns NO tasks (never all repos)",
              f"stdout={out.strip()[:40]} stderr={err.strip()[:120]}")

        # ── 5. explicit fleet view still possible ────────────────
        signal.alarm(120)
        rc, out, _err = _run_engine(current_engine, ["pending", "--repo", "ALL"], nongit)
        signal.alarm(0)
        items = json.loads(out) if out.strip() else []
        seen = {i.get("content") for i in items}
        check(rc == 0 and {"probe-own", "probe-other", "probe-untagged"} <= seen,
              "explicit repo=ALL is the deliberate fleet view", f"seen={sorted(seen)}")

        # ── 6. the REAL MCP server over stdio ────────────────────
        signal.alarm(180)
        client = McpClient(mcp_server, REPO)
        try:
            init = client.request({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                   "params": {"protocolVersion": "2024-11-05",
                                              "capabilities": {},
                                              "clientInfo": {"name": "repro",
                                                             "version": "1"}}})
            check("result" in init, "MCP initialize handshake",
                  str(init.get("result", {}).get("serverInfo", {})))
            client.notify({"jsonrpc": "2.0", "method": "notifications/initialized",
                           "params": {}})

            tools = client.request({"jsonrpc": "2.0", "id": 2,
                                    "method": "tools/list", "params": {}})
            by_name = {t["name"]: t for t in tools["result"]["tools"]}
            for name in ("task_pending", "task_list", "task_board",
                         "task_list_claimable", "task_list_handed_out"):
                props = by_name[name]["inputSchema"].get("properties", {})
                check("repo" in props, f"tools/list: {name} exposes repo")

            text = _call_tool(client, "task_pending", {"repo": OWN_REPO})
            items = json.loads(text) if text.strip().startswith("[") else []
            seen = {i.get("content") for i in items}
            check("probe-other" not in seen and "probe-own" in seen,
                  "MCP task_pending(repo=steadfaste) is scoped", f"seen={sorted(seen)}")
        finally:
            client.close()
            signal.alarm(0)

        # Same server, launched OUTSIDE any git repo and with no injected
        # identity: nothing can be resolved, so it must answer with [].
        signal.alarm(180)
        client_nc = McpClient(mcp_server, nongit)
        try:
            client_nc.request({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2024-11-05",
                                          "capabilities": {},
                                          "clientInfo": {"name": "repro",
                                                         "version": "1"}}})
            client_nc.notify({"jsonrpc": "2.0",
                              "method": "notifications/initialized", "params": {}})
            text = _call_tool(client_nc, "task_pending", {})
            check(text.strip() == "[]",
                  "MCP task_pending() with no resolvable repo returns []",
                  f"text={text.strip()[:60]}")
        finally:
            client_nc.close()
            signal.alarm(0)

        # ── 7. deployed copies (what agents actually run) ────────
        deployed_engine = DEPLOY / "scripts" / "task-db.py"
        deployed_mcp = DEPLOY / "scripts" / "task-mcp.py"
        if deployed_engine.is_file():
            signal.alarm(120)
            rc, out, _err = _run_engine(deployed_engine,
                                        ["pending", "--repo", OWN_REPO], nongit)
            signal.alarm(0)
            items = json.loads(out) if out.strip() else []
            seen = {i.get("content") for i in items}
            check(rc == 0 and "probe-other" not in seen and "probe-own" in seen,
                  "DEPLOYED engine is scoped", f"seen={sorted(seen)}")
        else:
            check(False, "DEPLOYED engine present", "not deployed on this host")
        if deployed_mcp.is_file():
            signal.alarm(180)
            client = McpClient(deployed_mcp, REPO)
            try:
                client.request({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                "params": {"protocolVersion": "2024-11-05",
                                           "capabilities": {},
                                           "clientInfo": {"name": "repro",
                                                          "version": "1"}}})
                client.notify({"jsonrpc": "2.0",
                               "method": "notifications/initialized", "params": {}})
                text = _call_tool(client, "task_pending", {"repo": OWN_REPO})
                items = json.loads(text) if text.strip().startswith("[") else []
                seen = {i.get("content") for i in items}
                check("probe-other" not in seen and "probe-own" in seen,
                      "DEPLOYED MCP task_pending is scoped", f"seen={sorted(seen)}")
            finally:
                client.close()
                signal.alarm(0)
        else:
            check(False, "DEPLOYED MCP server present", "not deployed on this host")
    finally:
        teardown_scratch()
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    failed = [label for ok, label in RESULTS if not ok]
    for ok, label in RESULTS:
        print(f"  {'✅' if ok else '❌'} {label}")
    print()
    print(f"{len(RESULTS) - len(failed)} passed, {len(failed)} failed "
          f"(base {base[:9]} vs tip {tip[:9]})")

    if args.write_artifact:
        art = REPO / "tests" / "artifacts" / "task-query-repo-scope-repro.txt"
        art.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"base {base}", f"tip  {tip}", f"scratch-db {SCRATCH_DB}",
                 f"host {platform.system()} {platform.release()}", ""]
        lines += [f"  {'PASS' if ok else 'FAIL'}  {label}" for ok, label in RESULTS]
        lines += ["", f"{len(RESULTS) - len(failed)} passed, {len(failed)} failed"]
        art.write_text("\n".join(lines) + "\n")
        print(f"artifact: {art}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
