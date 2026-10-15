/**
 * probe-pi-skill-mechanism.mjs — ask PI ITSELF how a skill is loaded.
 *
 * WHY THIS FILE EXISTS
 *
 * The reflexion gate's evidence writer was keyed on a tool Pi does not have
 * (`skill_view`), which made every Pi commit unsatisfiable. The fix's whole
 * correctness rests on Pi's ACTUAL mechanism, so that mechanism is not inferred
 * from a doc, a skill, or a comment: this probe loads the INSTALLED Pi package by
 * its own public entry point and prints
 *
 *   1. the `read` tool's JSON schema (the parameter name the model actually
 *      emits, which the extension must read), and
 *   2. the skill-loading instruction Pi injects into its own system prompt.
 *
 * Output is captured to docs/evidence/ so a later reader can re-run it:
 *
 *   node ops/install/harnesses/pi/probe-pi-skill-mechanism.mjs
 *
 * Exits 2 if the installed Pi cannot be driven (a moved export), rather than the
 * misleading "Pi has no read tool".
 */
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const PI_ROOT =
  process.env.PI_INSTALL_ROOT ??
  `${process.env.HOME}/.pi/agent/install`;
const PI_VERSION = (process.env.PI_VERSION ?? "").trim();

function releaseDir() {
  if (PI_VERSION) return `${PI_ROOT}/releases/${PI_VERSION}`;
  const fs = require("node:fs");
  const current = `${PI_ROOT}/current-version`;
  if (fs.existsSync(current)) {
    return `${PI_ROOT}/releases/${fs.readFileSync(current, "utf8").trim()}`;
  }
  const list = fs.existsSync(`${PI_ROOT}/releases`)
    ? fs.readdirSync(`${PI_ROOT}/releases`).sort()
    : [];
  if (!list.length) throw new Error(`no Pi release under ${PI_ROOT}/releases`);
  return `${PI_ROOT}/releases/${list[list.length - 1]}`;
}

function main() {
  const rel = releaseDir();
  const pkg = `${rel}/node_modules/@earendil-works/pi-coding-agent/dist`;
  console.log(`pi release: ${rel}`);

  const mod = require(`${pkg}/index.js`);
  const defs = {};
  // Pi's own factory, in preference order. Each is a PUBLIC export; the probe
  // reports which one it used, so a build that renames one is visible rather
  // than silently reading as "no read tool".
  let via = "";
  if (typeof mod.createReadToolDefinition === "function") {
    defs.read = mod.createReadToolDefinition(process.cwd(), {});
    via = "createReadToolDefinition";
  } else if (typeof mod.createCodingTools === "function") {
    Object.assign(defs, mod.createCodingTools(process.cwd(), {}));
    via = "createCodingTools";
  } else if (typeof mod.createReadOnlyTools === "function") {
    Object.assign(defs, mod.createReadOnlyTools(process.cwd(), {}));
    via = "createReadOnlyTools";
  } else {
    console.error(
      "COULD NOT VERIFY: no read-tool factory is exported by this Pi build — " +
        "the probe ran, the host moved. Exports mentioning 'tool': " +
        Object.keys(mod).filter((k) => /tool/i.test(k)).join(", ")
    );
    return 2;
  }
  console.log(`driven via: ${via}`);
  console.log(`base tools: ${Object.keys(defs).sort().join(", ")}`);

  const read = defs.read;
  if (!read) {
    console.error("COULD NOT VERIFY: Pi reports no `read` tool.");
    return 2;
  }
  const schema = read.parameters ?? read.inputSchema ?? null;
  console.log(`read.parameters: ${JSON.stringify(schema)}`);
  const keys = schema?.properties ? Object.keys(schema.properties) : [];
  console.log(`read parameter keys: ${keys.join(", ") || "(none)"}`);

  const skills = require(`${pkg}/core/skills.js`);
  const sample = [
    {
      name: "reflexion-check",
      description: "Pre-delivery self-critique",
      filePath: "/skills/software-development/reflexion-check/SKILL.md",
      baseDir: "/skills/software-development/reflexion-check",
      sourceInfo: {},
      disableModelInvocation: false,
    },
  ];
  console.log("--- formatSkillsForPrompt(skills, 'read') ---");
  console.log(skills.formatSkillsForPrompt(sample, "read").trim());

  const hasSkillView = /skill_view/.test(
    require("node:fs").readFileSync(`${pkg}/index.js`, "utf8")
  );
  console.log(`pi bundle mentions skill_view: ${hasSkillView}`);
  return 0;
}

process.exit(main());
