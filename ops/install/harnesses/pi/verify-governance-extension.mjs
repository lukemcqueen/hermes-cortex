#!/usr/bin/env node
/**
 * verify-governance-extension.mjs — EXECUTE the pi write gate, don't grep it.
 *
 * A guard that greps cannot see a classifier's SHAPE: a gate whose `tool_call`
 * handler exists and whose file mentions "block" can still pass every write
 * through. So this loads the REAL extension through pi's OWN TypeScript loader,
 * hands it a stub `pi`, fires synthetic `tool_call` events, and asserts on the
 * DECISION the extension returns.
 *
 * It is pinned in BOTH directions, which is the only thing that makes it a
 * guard rather than a happy path:
 *
 *   unlocked + write   -> BLOCKED
 *   unlocked + read    -> allowed, and the governance CLI was never even called
 *   locked   + write   -> allowed
 *   unavailable        -> BLOCKED (fail closed)
 *
 * and it drives the commands an earlier plan would have missed: `cp`, `mv`,
 * `rm`, `tee`, `dd`, `mkdir`, `touch` contain NO shell metacharacter, so a gate
 * that classified by syntax let every one of them through. They are asserted
 * here by name.
 *
 * Hermetic: CORTEX_GOVERNANCE_CLI points at a throwaway stub, so the real
 * governance store is never consulted and no lock is touched.
 *
 *   node ops/install/harnesses/pi/verify-governance-extension.mjs
 *
 * Exit 0 = the gate is correct. Non-zero = it is broken, with the reason.
 */
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
// PI_GOV_EXT is the discrimination seam: point the guard at a deliberately
// broken copy and it MUST fail. A guard that has never failed on the broken
// artifact is a happy path, not a guard.
const EXT = process.env.PI_GOV_EXT ?? path.join(HERE, "extensions", "cortex-governance.ts");

const failures = [];
const note = (ok, msg) => {
  console.log(`${ok ? "✅" : "❌"} ${msg}`);
  if (!ok) failures.push(msg);
};

// ── locate pi's jiti loader (version-agnostic) ───────────────────────────────
function findJiti() {
  const roots = [
    process.env.PI_INSTALL_ROOT,
    path.join(os.homedir(), ".pi", "agent", "install"),
  ].filter(Boolean);
  for (const root of roots) {
    const rel = path.join(root, "releases");
    if (!fs.existsSync(rel)) continue;
    for (const v of fs.readdirSync(rel).sort().reverse()) {
      const p = path.join(rel, v, "node_modules", "jiti", "lib", "jiti.cjs");
      if (fs.existsSync(p)) return p;
    }
  }
  return null;
}

const jitiPath = findJiti();
if (!jitiPath) {
  console.log("❌ cannot find pi's jiti loader — SKIP: this host uses a binary/mise pi install " +
    "(set PI_INSTALL_ROOT to an npm-managed release with node_modules/jiti to run this guard)");
  console.log("EXTENSION SKIPPED");
  process.exit(0);
}
console.log(`jiti: ${jitiPath}`);
console.log(`ext : ${EXT}\n`);

// ── a stub governance CLI: decides from GOV_STUB_MODE, touches no store ─────
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cortex-gov-verify-"));
const callsLog = path.join(tmp, "calls.log");
const stubCli = path.join(tmp, "stub-loop-gov.py");
fs.writeFileSync(stubCli, `import json, os, sys
mode = os.environ.get("GOV_STUB_MODE", "allowed")
with open(os.environ["GOV_STUB_LOG"], "a") as fh:
    fh.write("called\\n")
if mode == "allowed":
    print(json.dumps({"covered": True, "match": "path", "repo_path": "/tmp/fake-repo"}))
    sys.exit(0)
if mode == "unavailable":
    print("governance is unavailable", file=sys.stderr)
    sys.exit(3)
others = [{"task_id": "other-project-task", "agent": "peer-agent",
           "session_id": "sess-other", "repo_path": "/tmp/some-other-repo",
           "status": "executing", "heartbeat_at": "2026-10-16T06:00:00Z"}]
if mode == "refused-no-others":
    others = []
if mode == "refused-unscoped":
    others = [{"task_id": "legacy-task", "agent": "legacy-agent",
               "session_id": "sess-legacy", "repo_path": None,
               "status": "executing", "heartbeat_at": "2026-10-16T06:00:00Z"}]
print(json.dumps({"covered": False, "repo_path": "/tmp/fake-repo", "lock": None,
                  "live_lock_count": len(others),
                  "unscoped_locks": 1 if mode == "refused-unscoped" else 0,
                  "other_locks": others,
                  "note": "Not locked: no live governance lock covers this repo."}))
sys.exit(1)
`);

process.env.CORTEX_GOVERNANCE_CLI = stubCli;
process.env.CORTEX_GOVERNANCE_PYTHON = process.env.CORTEX_GOVERNANCE_PYTHON || "python3";
process.env.CORTEX_GOVERNANCE_LOG = path.join(tmp, "gov.log");
process.env.GOV_STUB_LOG = callsLog;
process.env.CORTEX_SESSION_REPO = "/tmp/fake-repo"; // deterministic; no git needed
delete process.env.CORTEX_GOVERNANCE_DEBUG;

const callCount = () => (fs.existsSync(callsLog)
  ? fs.readFileSync(callsLog, "utf8").split("\n").filter(Boolean).length
  : 0);

// ── load the REAL extension through pi's loader ─────────────────────────────
const createJiti = require(jitiPath).createJiti || require(jitiPath);
const jiti = createJiti(import.meta.url);

let register;
try {
  register = await jiti.import(EXT, { default: true });
} catch (err) {
  console.error(`❌ the extension failed to LOAD: ${err}`);
  process.exit(1);
}
note(typeof register === "function", "extension default export is a function (pi registers it)");
if (typeof register !== "function") {
  console.error(failures.join("\n"));
  process.exit(1);
}

// ── a stub `pi` that captures the handlers ─────────────────────────────────
const hooks = {};
const tools = [];
const pi = {
  on: (name, fn) => { hooks[name] = fn; },
  registerTool: (def) => { tools.push(def); },
};
try {
  register(pi);
} catch (err) {
  console.error(`❌ registering the extension threw: ${err}`);
  process.exit(1);
}

note(typeof hooks["tool_call"] === "function",
     "the gate registers a `tool_call` handler (this is what pi's native tools were missing)");
if (typeof hooks["tool_call"] !== "function") {
  console.error(failures.join("\n"));
  process.exit(1);
}

/** Drive one synthetic tool call. Returns {blocked, reason}. */
async function call(toolName, input) {
  const res = await hooks["tool_call"]({ type: "tool_call", toolCallId: "t1", toolName, input });
  return {
    blocked: !!(res && res.block === true),
    reason: String((res && res.reason) || ""),
  };
}

// ── 1. LOCKED: writes pass ──────────────────────────────────────────────────
process.env.GOV_STUB_MODE = "allowed";
let r = await call("write", { file_path: "/tmp/fake-repo/x.txt", content: "hi" });
note(!r.blocked, "covered by a live lock => write ALLOWED");
r = await call("edit", { file_path: "/tmp/fake-repo/x.txt" });
note(!r.blocked, "covered by a live lock => edit ALLOWED");
r = await call("bash", { command: "cp a b" });
note(!r.blocked, "covered by a live lock => write-classified bash ALLOWED (the lock is the gate, not the classifier)");

// ── 2. UNLOCKED: writes blocked ─────────────────────────────────────────────
process.env.GOV_STUB_MODE = "refused";
r = await call("write", { file_path: "/tmp/fake-repo/x.txt", content: "hi" });
note(r.blocked, "NO lock => write BLOCKED");
note(r.reason.includes("GOVERNANCE LOCK REQUIRED"),
     "the block names the gate (GOVERNANCE LOCK REQUIRED)");
note(r.reason.includes("begin_change"),
     "the block names the remedy (begin_change) — a block an agent cannot act on is a deadlock");

r = await call("edit", { file_path: "/tmp/fake-repo/x.txt" });
note(r.blocked, "NO lock => edit BLOCKED");

// ── 2b. the refusal NAMES the live lock that does not cover this repo ───────
// A block that prints `live_lock_count: 1` beside `covered: false` and names
// nothing leaves the reader unable to tell a broken gate from someone else's
// lock. Asserted on the RENDERED line (a format the raw JSON cannot produce),
// not merely on the path appearing somewhere.
note(r.reason.includes("Live locks on this host — none covers this repo:"),
     "the refusal names the locks that do NOT cover this repo");
note(r.reason.includes("  - /tmp/some-other-repo  (task: other-project-task, agent: peer-agent)"),
     "each named lock shows its repo, task and agent — the reader learns whose lock it is");

// nothing to name => no section (a section that always prints is noise)
process.env.GOV_STUB_MODE = "refused-no-others";
r = await call("write", { file_path: "/tmp/fake-repo/x.txt" });
note(r.blocked, "NO lock and no other live lock => write still BLOCKED");
note(!r.reason.includes("none covers this repo"),
     "no live locks exist => the named-lock section is ABSENT");

// a legacy lock that records no repo_path is named as covering nothing
process.env.GOV_STUB_MODE = "refused-unscoped";
r = await call("write", { file_path: "/tmp/fake-repo/x.txt" });
note(r.reason.includes("(records no repo_path — covers nothing)"),
     "a lock with no repo_path is named as covering NOTHING, not silently dropped");
process.env.GOV_STUB_MODE = "refused";

// ── 3. the ADV-1 case: write commands with NO metacharacter ─────────────────
// A gate that classified by shell syntax let every one of these through.
for (const cmd of [
  "cp a b", "mv a b", "rm -rf /tmp/fake-repo/x", "tee /tmp/fake-repo/out",
  "dd if=/dev/zero of=/tmp/fake-repo/blob bs=1 count=1", "mkdir /tmp/fake-repo/newdir",
  "touch /tmp/fake-repo/newfile", "ln -s a b", "truncate -s 0 f", "install a b",
  "python3 -c import_os", "sh -c echo", "git commit -m x", "git push", "git checkout main",
  "git branch newbranch", "git tag v9",
]) {
  const res = await call("bash", { command: cmd });
  note(res.blocked, `NO lock => bash WRITE-CLASSIFIED blocked: \`${cmd}\``);
}

// ── 4. compound commands need a lock even when every part reads ─────────────
for (const cmd of ["ls | grep foo", "cat f > out", "echo hi; ls", "ls && rm x"]) {
  const res = await call("bash", { command: cmd });
  note(res.blocked, `NO lock => COMPOUND bash blocked: \`${cmd}\``);
}

// ── 5. read-only stays lock-free, and must not even consult governance ──────
const before = callCount();
for (const cmd of ["ls -la /tmp/fake-repo", "cat /tmp/fake-repo/x", "grep -rn TODO .",
                   "git status --short", "git log --oneline -5", "git branch -a",
                   "git diff HEAD", "find . -name '*.py'"]) {
  const res = await call("bash", { command: cmd });
  note(!res.blocked, `read-only bash stays lock-free: \`${cmd}\``);
}
for (const tool of ["read", "grep", "find", "ls"]) {
  const res = await call(tool, { path: "/tmp/fake-repo/x" });
  note(!res.blocked, `read-only tool stays lock-free: ${tool}`);
}
note(callCount() === before,
     "read-only work never spawned the governance CLI (a lock-free read costs nothing)");

// ── 6. custom / MCP tools are NOT pi's write surface — they pass ────────────
r = await call("begin_change", { task_id: "x", description: "y" });
note(!r.blocked, "a non-native (MCP/custom) tool passes — this gate covers pi's own write surface");

// ── 7. governance UNAVAILABLE => fail CLOSED ───────────────────────────────
process.env.GOV_STUB_MODE = "unavailable";
r = await call("write", { file_path: "/tmp/fake-repo/x.txt" });
note(r.blocked, "governance UNAVAILABLE => write BLOCKED (fail CLOSED, never fail open)");
note(r.reason.includes("GOVERNANCE UNAVAILABLE"), "the unavailable block says so explicitly");
note(r.reason.includes("THE COST"), "the unavailable block states what the refusal costs");

// ── 8. CLI missing entirely => fail CLOSED ────────────────────────────────
process.env.CORTEX_GOVERNANCE_CLI = path.join(tmp, "does-not-exist.py");
r = await call("write", { file_path: "/tmp/fake-repo/x.txt" });
note(r.blocked, "governance CLI missing => write BLOCKED (fail CLOSED, not a silent pass)");
process.env.CORTEX_GOVERNANCE_CLI = stubCli;

// ── 9. no repo resolvable => fail CLOSED ──────────────────────────────────
delete process.env.CORTEX_SESSION_REPO;
const cwdBefore = process.cwd();
const nonRepo = fs.mkdtempSync(path.join(os.tmpdir(), "not-a-repo-"));
process.chdir(nonRepo);
r = await call("write", { file_path: "/tmp/x.txt" });
process.chdir(cwdBefore);
note(r.blocked, "no repo + no CORTEX_SESSION_REPO => write BLOCKED (nothing to govern)");
note(r.reason.includes("CANNOT DETERMINE THE REPO"), "the unresolved block says which one is missing");
process.env.CORTEX_SESSION_REPO = "/tmp/fake-repo";

// ── 10. the gate registers no tools (one way in per capability) ───────────
note(tools.length === 0,
     `the gate registers ZERO tools (got ${tools.length}) — it is an adapter over the shared implementation, not a second surface`);

// ── cleanup + verdict ──────────────────────────────────────────────────────
try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* best effort */ }
try { fs.rmSync(nonRepo, { recursive: true, force: true }); } catch { /* best effort */ }

console.log("");
if (failures.length) {
  console.error(`❌ GOVERNANCE GATE BROKEN — ${failures.length} check(s) failed:`);
  for (const f of failures) console.error(`   - ${f}`);
  process.exit(1);
}
console.log("✅ GOVERNANCE GATE OK — pi's native write tools are gated on the shared lock predicate.");
