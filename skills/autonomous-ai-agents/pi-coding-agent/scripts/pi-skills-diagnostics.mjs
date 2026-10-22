#!/usr/bin/env node
// Print exactly what a coding agent's loader sees in a skills tree.
//
// Reading dist/core/skills.js tells you the RULES; running it tells you what an
// agent ACTUALLY gets — which skills were silently refused, and which names
// collided. Use it to reproduce a host's own report verbatim, or to prove a fix
// changed the outcome by pointing it at two revisions of the same tree.
//
// Usage:
//   node pi-skills-diagnostics.mjs [tree]        # default ~/.agents/skills
//   node pi-skills-diagnostics.mjs <tree> --json
//
// Exit: 0 = no diagnostics, 1 = diagnostics present, 2 = could not run.
//
// The loader is resolved from the INSTALLED release. Pi updates itself (a
// current-version moving 1.3.0 -> 1.4.0 mid-session was observed), so a probe
// importing a hardcoded releases/<old>/... path silently measures the OLD loader
// and reports rules that no longer apply. If a version move is suspected of
// changing behaviour, `diff` the two releases' skills.js first: byte-identical
// files mean the enumeration rules did not move.

import { readFileSync } from "fs";
import { homedir } from "os";
import { resolve } from "path";

const args = process.argv.slice(2);
const asJson = args.includes("--json");
const tree = resolve(args.find((a) => !a.startsWith("--")) ?? `${homedir()}/.agents/skills`);
const agentDir = `${homedir()}/.pi/agent`;

let version;
try {
  version = readFileSync(`${agentDir}/install/current-version`, "utf8").trim();
} catch (e) {
  console.error(`COULD NOT RUN: cannot read ${agentDir}/install/current-version (${e.code ?? e.message})`);
  process.exit(2);
}

const mod = `${agentDir}/install/releases/${version}/node_modules/@earendil-works/pi-coding-agent/dist/core/skills.js`;
let loadSkills;
try {
  ({ loadSkills } = await import(mod));
} catch (e) {
  console.error(`COULD NOT RUN: cannot import the loader at ${mod} (${e.code ?? e.message})`);
  process.exit(2);
}

// includeDefaults:false and a single explicit skillPaths entry, so the report is
// about the tree you named and nothing else. cwd is pinned to $HOME so a project
// `.pi/skills` cannot join the answer.
const res = loadSkills({ agentDir, skillPaths: [tree], includeDefaults: false, cwd: homedir() });

const byType = {};
for (const d of res.diagnostics) byType[d.type] = (byType[d.type] || 0) + 1;
const groups = {};
for (const d of res.diagnostics) {
  if (d.type !== "warning") continue;
  const key = d.message.split("\n")[0].slice(0, 120);
  (groups[key] = groups[key] || []).push(d.path);
}
const collisions = res.diagnostics.filter((d) => d.type === "collision");

if (asJson) {
  console.log(JSON.stringify({ tree, version, loader: mod, loaded: res.skills.length, byType, groups, collisions }, null, 2));
} else {
  console.log(`tree   : ${tree}`);
  console.log(`loader : Pi ${version} (${mod.replace(homedir(), "~")})`);
  console.log(`loaded : ${res.skills.length} skill(s)`);
  console.log(`diags  : ${JSON.stringify(byType)}`);
  for (const [msg, paths] of Object.entries(groups)) {
    console.log(`\n  ${paths.length} x ${msg}`);
    for (const p of paths.slice(0, 8)) console.log(`        ${p.replace(homedir(), "~")}`);
    if (paths.length > 8) console.log(`        ... and ${paths.length - 8} more`);
  }
  for (const d of collisions) {
    console.log(`\n  COLLISION "${d.collision.name}"`);
    console.log(`        winner: ${d.collision.winnerPath.replace(homedir(), "~")}`);
    console.log(`        skipped: ${d.collision.loserPath.replace(homedir(), "~")}`);
  }
}

process.exit(res.diagnostics.length ? 1 : 0);
