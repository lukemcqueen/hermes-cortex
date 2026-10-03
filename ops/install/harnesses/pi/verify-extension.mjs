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
const EXT = path.join(HERE, "extensions", "cortex-context.ts");

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
  console.error("❌ cannot find pi's jiti loader — set PI_INSTALL_ROOT");
  process.exit(2);
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
if tool == "session_restore":
    print(json.dumps({"restored": {"done": ["MARKER-DONE"], "pending": ["MARKER-PENDING"],
                                   "session_key": "pi:verify:main"}, "session_key": "pi:verify:main"}))
else:
    print(json.dumps({"ok": True, "tool": tool}))
`);
process.env.CORTEX_CONTEXT_CLI = stubCli;
process.env.CORTEX_CONTEXT_PYTHON = process.env.CORTEX_CONTEXT_PYTHON || "python3";
process.env.CORTEX_STUB_LOG = callsLog;

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

// ── cleanup + verdict ───────────────────────────────────────────────────────
try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* best effort */ }

console.log("");
if (failures.length) {
  console.error(`❌ EXTENSION BROKEN — ${failures.length} check(s) failed:`);
  for (const f of failures) console.error(`   - ${f}`);
  process.exit(1);
}
console.log("✅ EXTENSION OK — registers no tools (MCP owns them) and its lifecycle hooks execute.");
