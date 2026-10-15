#!/usr/bin/env node
/**
 * verify-extension.mjs — EXECUTE the Pi extension, don't grep it.
 *
 * Two things are asserted, both by RUNNING the extension rather than reading it:
 *
 *  1. IT REGISTERS NO TOOLS. The memory/session tools come from the shared
 *     cortex-context MCP server, so a registerTool call here would be a SECOND
 *     definition of the same capability — and when the hand-written one went
 *     stale (pi 0.87.1 -> 1.0.0) every call failed silently while the store was
 *     healthy. A grep can see the word "registerTool"; only running it proves
 *     the count is zero.
 *
 *  2. THE LIFECYCLE HOOKS STILL WORK, because that is the half MCP cannot
 *     provide. The guard drives `before_agent_start` (restore + inject) and
 *     `turn_end` (the checkpoint trigger) against a throwaway CLI and asserts on
 *     what the extension actually asked the store to do.
 *
 * Hermetic: CORTEX_CONTEXT_CLI points at a temp stub, so the real store is never
 * touched and no checkpoint is written.
 *
 *   node ops/install/harnesses/pi/verify-extension.mjs
 *
 * Exit 0 = the extension is correct. Non-zero = it is broken, with the reason.
 */
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
// PI_EXTENSION_UNDER_TEST is the DISCRIMINATION SEAM: point it at a PRE-FIX copy
// (git show <rev>:ops/install/harnesses/pi/extensions/cortex-context.ts) and this
// guard MUST fail on the skill-load cases. A guard that has never failed on the
// broken revision proves nothing about the fix.
const EXT =
  process.env.PI_EXTENSION_UNDER_TEST ??
  path.join(HERE, "extensions", "cortex-context.ts");

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
  // No jiti loader = this pi is a mise/binary install (launcher ~/.local/bin/pi,
  // package ~/.local/share/mise/installs/pi/<v>/pi, no extracted node_modules/jiti).
  // The guard cannot drive a .ts extension without a TS loader — that is an
  // environment SKIP (a host with the npm-managed layout still exercises it), not a
  // broken extension. Exit 0 with an explicit marker so the pytest wrapper skips
  // cleanly instead of reading a probe failure as a broken wiring.
  console.log("❌ cannot find pi's jiti loader — SKIP: this host uses a binary/mise pi install " +
    "(set PI_INSTALL_ROOT to an npm-managed release with node_modules/jiti to run this guard)");
  console.log("EXTENSION SKIPPED");
  process.exit(0);
}
console.log(`jiti: ${jitiPath}`);
console.log(`ext : ${EXT}\n`);

// ── a stub CLI: records what the extension asked for, touches no store ──────
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cortex-verify-"));
const callsLog = path.join(tmp, "calls.jsonl");
const stubCli = path.join(tmp, "stub-cli.py");
fs.writeFileSync(stubCli, `import json, os, sys
tool, args = sys.argv[1], json.loads(sys.argv[2])
with open(os.environ["CORTEX_STUB_LOG"], "a") as fh:
    fh.write(json.dumps({"tool": tool, "args": args}) + "\\n")
print("MARKER-CHILD-NOISE: stub wrote to stderr", file=sys.stderr)
if os.environ.get("CORTEX_STUB_FAIL") == "1":
    sys.exit(3)
if tool == "session_restore":
    print(json.dumps({"restored": {"done": ["MARKER-DONE"], "pending": ["MARKER-PENDING"],
                                   "session_key": "pi:verify:main"}, "session_key": "pi:verify:main"}))
else:
    print(json.dumps({"ok": True, "tool": tool}))
`);
process.env.CORTEX_CONTEXT_CLI = stubCli;
process.env.CORTEX_CONTEXT_PYTHON = process.env.CORTEX_CONTEXT_PYTHON || "python3";
process.env.CORTEX_STUB_LOG = callsLog;

// ── a stub GOVERNANCE CLI, for the session id the evidence must be keyed to ──
// The extension reads CORTEX_GOVERNANCE_CLI at MODULE LOAD, so it is set before
// the import below. The stub reads its mode from the environment at RUN time, so
// the failure modes (missing key, malformed output, non-zero exit) are exercised
// in one process instead of three.
const govStub = path.join(tmp, "stub-gov.py");
const govLog = path.join(tmp, "gov-calls.jsonl");
fs.writeFileSync(govStub, `import json, os, sys
mode = os.environ.get("CORTEX_GOV_STUB_MODE", "ok")
tool = sys.argv[1] if len(sys.argv) > 1 else ""
with open(os.environ["CORTEX_GOV_STUB_LOG"], "a") as fh:
    fh.write(json.dumps({"tool": tool}) + "\\n")
if mode == "fail":
    sys.stderr.write("governance unreachable\\n"); sys.exit(3)
if mode == "badjson":
    print("not json at all"); sys.exit(0)
if mode == "nokey":
    print(json.dumps({"session_id": "", "effective_session_id": ""})); sys.exit(0)
if tool == "session_identity":
    print(json.dumps({"session_id": "sess_own", "effective_session_id": "sess_test_govkey"}))
else:
    print(json.dumps({"ok": True, "tool": tool}))
`);
process.env.CORTEX_GOVERNANCE_CLI = govStub;
process.env.CORTEX_GOV_STUB_LOG = govLog;

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

// ── a stub `pi` that records what the extension registers ───────────────────
const tools = [];
const hooks = {};
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

// ── 1. NO tools: one way in per capability ──────────────────────────────────
note(tools.length === 0,
     `extension registers ZERO tools (got ${tools.length}) — the tools come from the ` +
     `shared cortex-context MCP server, so a second definition here is the phantom bug`);

// ── 2. the hooks that own WHEN a checkpoint is written ──────────────────────
for (const h of ["before_agent_start", "turn_end", "session_before_compact", "tool_result"]) {
  note(typeof hooks[h] === "function", `hook registered: ${h}`);
}

// ── 3. DRIVE the hooks and check what the extension asked the store to do ───
const readCalls = () => fs.existsSync(callsLog)
  ? fs.readFileSync(callsLog, "utf8").trim().split("\n").filter(Boolean).map((l) => JSON.parse(l))
  : [];

if (typeof hooks["before_agent_start"] === "function") {
  let injected;
  try {
    injected = await hooks["before_agent_start"]({ systemPrompt: "BASE" });
  } catch (err) {
    note(false, `before_agent_start threw: ${err}`);
  }
  const prompt = injected?.systemPrompt ?? "";
  note(typeof prompt === "string" && prompt.includes("BASE"),
       "before_agent_start returns { systemPrompt } built on the event's prompt (injection IS the return value)");
  note(prompt.includes("MARKER-DONE") && prompt.includes("MARKER-PENDING"),
       "the restored checkpoint is INJECTED (done + pending present)");
  note(prompt.includes("pi:verify:main"), "the injection names the session key it restored");
}

if (typeof hooks["turn_end"] === "function") {
  try {
    await hooks["turn_end"]({
      turnIndex: 1,
      message: { content: "MARKER-NOTE: did the thing" },
      toolResults: [{ toolName: "read" }, { toolName: "edit" }],
    });
  } catch (err) {
    note(false, `turn_end threw: ${err}`);
  }
  const cp = readCalls().filter((c) => c.tool === "session_checkpoint").pop();
  note(!!cp, "turn_end WROTE a checkpoint (the trigger fired without the model asking)");
  if (cp) {
    const done = cp.args?.done ?? [];
    note(done.includes("read") && done.includes("edit"),
         `the checkpoint carries the turn's tool names: ${JSON.stringify(done)}`);
    note(String(cp.args?.notes ?? "").includes("MARKER-NOTE"),
         "the checkpoint carries the turn's note text");
  }
}

if (typeof hooks["turn_end"] === "function") {
  // A turn with nothing recognisable must NOT write a silently-empty checkpoint.
  const before = readCalls().filter((c) => c.tool === "session_checkpoint").length;
  await hooks["turn_end"]({ turnIndex: 2 });
  const after = readCalls().filter((c) => c.tool === "session_checkpoint").length;
  note(after === before,
       "an empty turn writes NO checkpoint (a checkpoint that looks like continuity and carries none is worse than none)");
}

// ── 4. DRIVE tool_result: the reflexion gate's skill-load evidence ──────────
//
// Pi has NO `skill_view` tool (verified against the installed package: the bundle
// contains no such identifier, `createReadToolDefinition` exposes {path,...}, and
// Pi's own prompt says "Use the read tool to load a skill's file"). The handler keyed
// on `skill_view` therefore recorded NOTHING, so the pre-commit reflexion gate refused
// every Pi commit. These cases execute the real handler and assert what it asked the
// store to record — a grep could not tell a registered hook from a working one.
const evts = () => readCalls().filter((c) => c.tool === "session_tool_event");

if (typeof hooks["tool_result"] === "function") {
  const skillPath = "/skills/software-development/reflexion-check/SKILL.md";

  // (a) Pi's mechanism: a read of the skill's own file.
  let before = evts().length;
  await hooks["tool_result"]({ toolName: "read", input: { path: skillPath } });
  let got = evts().slice(before);
  note(got.length === 1,
       `a read of a SKILL.md records skill-load evidence (recorded ${got.length})`);
  if (got.length === 1) {
    note(got[0].args?.tool_name === "read",
         `…under its TRUE tool name 'read', never a fabricated skill_view (got ${JSON.stringify(got[0].args?.tool_name)})`);
    note(got[0].args?.content?.path === skillPath,
         `…carrying the read's own input (got ${JSON.stringify(got[0].args?.content?.path)})`);
    note(got[0].args?.session_key === "sess_test_govkey",
         `…keyed to the session the GATE queries, not CORTEX_SESSION_KEY (got ${JSON.stringify(got[0].args?.session_key)})`);
  }

  // (b) a read of something that is NOT a skill must record nothing.
  before = evts().length;
  await hooks["tool_result"]({ toolName: "read", input: { path: "/etc/hostname" } });
  note(evts().length === before,
       "a read of a NON-skill file records nothing (the store is evidence, not a transcript)");

  // (c) a harness that DOES have skill_view still records, unchanged.
  before = evts().length;
  await hooks["tool_result"]({ toolName: "skill_view", input: { name: "reflexion-check" } });
  got = evts().slice(before);
  note(got.length === 1 && got[0].args?.tool_name === "skill_view",
       "skill_view still records (the Hermes mechanism is untouched)");

  // (d) the skill name is derived from the PATH, not hardcoded.
  before = evts().length;
  await hooks["tool_result"]({
    toolName: "read",
    input: { path: "/skills/devops/shell-scripting/SKILL.md", limit: 200 },
  });
  got = evts().slice(before);
  note(got.length === 1 && String(got[0].args?.content?.path).includes("shell-scripting/SKILL.md"),
       "the recorded path is the one actually read (no hardcoded skill) — offset/limit keys do not confuse it");

  // (e) EVERY failure to resolve the session id must record nothing AND not throw.
  //     A silently-invented key is the original bug; a thrown error would break the
  //     harness's tool call, which this extension must never do.
  for (const mode of ["fail", "badjson", "nokey"]) {
    process.env.CORTEX_GOV_STUB_MODE = mode;
    before = evts().length;
    let threw = "";
    try {
      await hooks["tool_result"]({ toolName: "read", input: { path: skillPath } });
    } catch (err) {
      threw = String(err);
    }
    note(!threw, `governance CLI mode '${mode}': the handler does not throw (${threw || "no throw"})`);
    note(evts().length === before,
         `governance CLI mode '${mode}': NO evidence recorded under an invented key`);
    process.env.CORTEX_GOV_STUB_MODE = "ok";
  }

  // The extension must have ASKED the shared implementation for the id rather
  // than deriving one — that question is the whole reason the writer and the
  // checker can no longer disagree.
  const govAsked = fs.existsSync(govLog)
    ? fs.readFileSync(govLog, "utf8").includes("session_identity")
    : false;
  note(govAsked, "the extension asked the SHARED governance CLI for the session id (session_identity)");
} else {
  note(false, "tool_result hook is NOT registered — Pi skill loads would go unrecorded");
}

// ── cleanup + verdict ───────────────────────────────────────────────────────
try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* best effort */ }

console.log("");
if (failures.length) {
  console.error(`❌ EXTENSION BROKEN — ${failures.length} check(s) failed:`);
  for (const f of failures) console.error(`   - ${f}`);
  process.exit(1);
}
console.log("✅ EXTENSION OK — registers no tools (MCP owns them) and its lifecycle hooks execute.");
