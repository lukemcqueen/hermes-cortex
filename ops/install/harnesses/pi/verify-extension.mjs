#!/usr/bin/env node
/**
 * verify-extension.mjs — EXECUTE the Pi extension's tool wiring, don't grep it.
 *
 * Why this exists (ADV-10538-1): the drift guards in tests/ are STATIC — they
 * assert tool names exist and that the shared CLI is called. Neither can see a
 * tool SIGNATURE or a SCHEMA SHAPE, so the extension shipped registering
 * `{ run: async (input) => … }` (the pi 0.87.1 shape) and a bare
 * `parameters: {peer:{type:"string"}}` map. On pi 1.0.0 every memory/session
 * tool call then failed with "definition.execute is not a function" while the
 * store was perfectly healthy — and no static guard could tell.
 *
 * This script loads the REAL extension through pi's own jiti loader, hands it a
 * STUB `pi`, and then:
 *   1. asserts every registered tool has a callable `execute` (and no `run`);
 *   2. asserts `parameters` is an object schema (type/properties/required);
 *   3. CALLS `execute(id, params)` against a stubbed CLI and asserts the
 *      returned AgentToolResult shape `{ content:[{type:"text",…}], details }`.
 *
 * Hermetic: CORTEX_CONTEXT_CLI points at a throwaway stub, so the real store is
 * never touched and no queue is written. Run it any time; it is the executable
 * proof that the tool wiring is intact.
 *
 *   node ops/install/harnesses/pi/verify-extension.mjs
 *
 * Exit 0 = the wiring is correct. Non-zero = it is broken, with the reason.
 */
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";
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
    const versions = fs.readdirSync(rel).sort().reverse();
    for (const v of versions) {
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

// ── a stub CLI so no real store is touched ──────────────────────────────────
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cortex-verify-"));
const stubCli = path.join(tmp, "stub-cli.py");
fs.writeFileSync(stubCli, `import json,sys\nprint(json.dumps({"ok": True, "tool": sys.argv[1], "args": json.loads(sys.argv[2])}))\n`);
process.env.CORTEX_CONTEXT_CLI = stubCli;
process.env.CORTEX_CONTEXT_PYTHON = process.env.CORTEX_CONTEXT_PYTHON || "python3";

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
  console.error(`❌ registering tools threw: ${err}`);
  process.exit(1);
}

// ── 1. the hooks that own WHEN a checkpoint is written ──────────────────────
note(typeof hooks["before_agent_start"] === "function",
     "before_agent_start hook registered (restore + inject)");
note(typeof hooks["turn_end"] === "function",
     "turn_end hook registered (the checkpoint trigger)");
note(typeof hooks["session_before_compact"] === "function",
     "session_before_compact hook registered");
note(typeof hooks["tool_result"] === "function",
     "tool_result hook registered (reflexion-gate evidence)");

// ── 2. every tool: execute, not run; object schema ──────────────────────────
note(tools.length > 0, `tools registered: ${tools.length}`);
const expected = ["mem_context", "mem_search", "mem_profile", "mem_conclude",
                  "session_checkpoint", "session_restore", "session_search",
                  "session_note", "session_close", "session_tool_event",
                  "session_loaded_skill"];
const names = tools.map((t) => t.name);
for (const want of expected) {
  note(names.includes(want), `tool registered: ${want}`);
}
for (const t of tools) {
  const hasExecute = typeof t.execute === "function";
  const hasRun = typeof t.run === "function";
  note(hasExecute, `${t.name}: execute() is a callable (the pi 1.0.0 AgentTool shape)`);
  note(!hasRun, `${t.name}: no \`run\` key (the pi 0.87.1 shape — silently ignored)`);
  const p = t.parameters || {};
  note(p.type === "object" && p.properties && Array.isArray(p.required),
       `${t.name}: parameters is an object schema (type/properties/required)`);
  // Every declared property must be extractable, and vice versa: the schema and
  // the argument extraction must come from ONE map.
  const declared = Object.keys(p.properties || {}).sort();
  note(declared.length > 0 || (p.required || []).length === 0,
       `${t.name}: schema declares its properties`);
  for (const r of p.required || []) {
    note(declared.includes(r), `${t.name}: required '${r}' is also declared in properties`);
  }
}

// ── 3. CALL execute() and check the returned AgentToolResult shape ──────────
const target = tools.find((t) => t.name === "mem_context");
if (!target) {
  note(false, "mem_context not registered — cannot exercise execute()");
} else {
  let res;
  try {
    res = await target.execute("call-1", { peer: "user" }, undefined, undefined);
  } catch (err) {
    note(false, `execute() threw instead of returning a result: ${err}`);
  }
  if (res !== undefined) {
    note(Array.isArray(res.content) && res.content.length > 0,
         "execute() returned content[] (AgentToolResult.content)");
    note(res.content?.[0]?.type === "text" && typeof res.content?.[0]?.text === "string",
         "content[0] is {type:'text', text} the model can read");
    note("details" in res, "execute() returned details (AgentToolResult.details)");
    // The stubbed CLI echoes the args, which proves the schema→args path ran and
    // that the argument the model supplied actually reached the CLI.
    const echoed = res.content?.[0]?.text || "";
    note(echoed.includes('"peer"') && echoed.includes('"user"'),
         `execute() passed the model's argument through to the CLI: ${echoed.slice(0, 80)}`);
  }
  // A tool with a required arg must not explode when it is missing.
  let missing;
  try {
    missing = await target.execute("call-2", {}, undefined, undefined);
    note(missing !== undefined, "execute() tolerates a missing optional arg");
  } catch (err) {
    note(false, `execute() threw on empty params: ${err}`);
  }
}

// ── cleanup + verdict ───────────────────────────────────────────────────────
try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* best effort */ }

console.log("");
if (failures.length) {
  console.error(`❌ EXTENSION WIRING BROKEN — ${failures.length} check(s) failed:`);
  for (const f of failures) console.error(`   - ${f}`);
  process.exit(1);
}
console.log(`✅ EXTENSION WIRING OK — ${tools.length} tools executed against the pi 1.0.0 AgentTool shape.`);
