#!/usr/bin/env node
/**
 * live-gate-probe.mjs — drive the pi write gate against the REAL governance CLI.
 *
 * `verify-governance-extension.mjs` points the extension at a STUB CLI on purpose
 * (hermetic, deterministic), so on its own it proves the extension and the
 * predicate SEPARATELY — never the two together. This probe closes that gap: same
 * extension, real `loop-gov.py`, and it prints the reason the extension returns.
 *
 * Read-only in effect: it asks the predicate and reports the decision. It writes
 * no file and mints no lock. Kept under docs/evidence/ so the transcript beside it
 * can be re-run by anyone reading it.
 *
 *   node live-gate-probe.mjs <repo-path>
 *
 * Exit 0 only when the gate refuses a write in an unlocked repo AND allows a
 * read-only command there.
 */
import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const repo = process.argv[2];
if (!repo) {
  console.error("usage: live-gate-probe.mjs <repo-path>");
  process.exit(2);
}

const HOME = process.env.HOME ?? "";
const EXT = `${HOME}/.hermes-cortex/harnesses/pi/extensions/cortex-governance.ts`;

function findJiti() {
  const root = path.join(HOME, ".pi", "agent", "install", "releases");
  for (const v of fs.readdirSync(root).sort().reverse()) {
    const p = path.join(root, v, "node_modules", "jiti", "lib", "jiti.cjs");
    if (fs.existsSync(p)) return p;
  }
  throw new Error("no jiti loader found");
}

// THE REAL CLI — no stub. That is the whole point of this probe.
process.env.CORTEX_GOVERNANCE_CLI = `${HOME}/.hermes-cortex/scripts/loop-gov.py`;
process.env.CORTEX_SESSION_REPO = repo;
delete process.env.CORTEX_GOVERNANCE_DEBUG;

const require = createRequire(import.meta.url);
const jitiPath = findJiti();
const createJiti = require(jitiPath).createJiti ?? require(jitiPath);
const jiti = createJiti(import.meta.url);
const register = await jiti.import(EXT, { default: true });

const hooks = {};
register({ on: (n, fn) => { hooks[n] = fn; }, registerTool: () => {} });
if (typeof hooks["tool_call"] !== "function") {
  console.error("the extension registered no tool_call handler");
  process.exit(1);
}

async function probe(label, toolName, input) {
  const res = await hooks["tool_call"]({
    type: "tool_call", toolCallId: "probe-1", toolName, input,
  });
  const blocked = !!(res && res.block === true);
  console.log(`\n──── ${label}  (tool=${toolName})`);
  console.log(`DECISION: ${blocked ? "BLOCKED" : "allowed"}`);
  if (blocked) console.log(res.reason);
  return blocked;
}

const writeBlocked = await probe("unlocked repo, write tool", "write",
  { file_path: path.join(repo, "probe.txt"), content: "x" });
const readAllowed = await probe("unlocked repo, read-only bash", "bash", { command: "ls -la" });

console.log("\n──── SUMMARY");
console.log(`write blocked when unlocked : ${writeBlocked}`);
console.log(`read  allowed when unlocked : ${!readAllowed}`);
process.exit(writeBlocked && !readAllowed ? 0 : 1);
