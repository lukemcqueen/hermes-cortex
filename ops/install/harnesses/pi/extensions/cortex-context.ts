/**
 * cortex-context.ts — Pi extension: the LIFECYCLE half of cortex context (S2c).
 *
 * VERIFIED AGAINST PI 1.0.0, NOT GUESSED.
 *
 *   ExtensionHandler<E> = (event: E, ctx: ExtensionContext) => R | void
 *   — the FIRST parameter is the EVENT, not the ctx. An earlier version of this
 *   file read `ctx.completed?.()` off that parameter; it returned undefined, the
 *   optional chain hid it, and every checkpoint was written EMPTY. A checkpoint
 *   that looks like continuity and carries none is worse than none.
 *
 *   before_agent_start: injection is the RETURN VALUE
 *     (BeforeAgentStartEventResult { message?, systemPrompt? }).
 *     There is NO ctx.addSystemPrompt() — calling one silently does nothing.
 *
 * WHY THIS FILE NO LONGER REGISTERS TOOLS (2026-10-03):
 *   The memory/session TOOLS come from the shared MCP server
 *   (`~/.hermes-cortex/scripts/cortex-context-mcp.py`, registered for Pi by
 *   `install-pi-mcp.sh`) — the SAME server Claude Code and Codex use, with
 *   schemas DERIVED from `ops/services/mycortex-mem/context_tools.py`.
 *
 *   They used to be registered HERE, by hand, as `{ run: async (input) => … }`.
 *   That was the pi 0.87.1 shape; on pi 1.0.0 every call failed with
 *   "definition.execute is not a function" — the store was healthy, the tool
 *   WIRING was not. The hand-written parameter maps were also a SECOND
 *   definition of tools that already existed in the contract, and two ways in
 *   for one capability is the defect the interop layer exists to remove: one of
 *   them becomes a phantom that fails silently.
 *
 *   What is left is the half MCP CANNOT provide: WHEN a checkpoint is written.
 *   The session that most needs a checkpoint is the one that got killed, and a
 *   killed session cannot call a tool — so the trigger lives in the lifecycle.
 *
 * INSTALL (in the Pi project):
 *   cp <cortex>/ops/install/harnesses/pi/extensions/cortex-context.ts extensions/
 *   pi -e extensions/cortex-context.ts --tools read,bash,edit,write
 *   (the memory/session tools are NOT listed in --tools: they arrive via MCP)
 *
 * ENV: CORTEX_SESSION_HARNESS / _REPO / _BRANCH / _KEY (else derived from git;
 *      the gateway pins _KEY per chat so separate chats never share a
 *      checkpoint), CORTEX_CONTEXT_CLI to override the CLI path,
 *      CORTEX_CONTEXT_LOG + CORTEX_CONTEXT_LOG_MAX_BYTES (routine trace sink,
 *      bounded, defaults to ~/.hermes-cortex/logs/pi-context.log) and
 *      CORTEX_CONTEXT_DEBUG=1 to also echo the routine trace to stderr.
 *
 * EVERY call is fail-open — but a failure is REPORTED on stderr (a silent
 * failure reads as "the agent had no memory", which is a different, wrong
 * conclusion).
 */

import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

const run = promisify(execFile);

const CLI =
  process.env.CORTEX_CONTEXT_CLI ??
  `${process.env.HOME}/.hermes-cortex/scripts/cortex-context.py`;

/**
 * The GOVERNANCE CLI. The reflexion gate keys its question to the ACTIVE
 * GOVERNANCE LOCK's session id, so the writer has to ask the same implementation
 * for that id (`session_identity`) instead of inventing a second key. Same rule
 * the write gate follows: one implementation, asked, never re-derived.
 */
const GOV_CLI =
  process.env.CORTEX_GOVERNANCE_CLI ??
  `${process.env.HOME}/.hermes-cortex/scripts/loop-gov.py`;

/**
 * The interpreter. macOS matters here: `python3` may not be on Pi's PATH (a
 * Homebrew python is at /opt/homebrew/bin on Apple Silicon, /usr/local/bin on
 * Intel), and a GUI-launched Pi sees a narrower PATH than your shell. Override
 * explicitly rather than assuming:
 *   export CORTEX_CONTEXT_PYTHON=/opt/homebrew/bin/python3
 */
const PYTHON = process.env.CORTEX_CONTEXT_PYTHON ?? "python3";

async function cortex(tool: string, args: Record<string, unknown> = {}): Promise<string> {
  try {
    const { stdout, stderr } = await run(PYTHON, [CLI, tool, JSON.stringify(args)], {
      timeout: 15_000,
      maxBuffer: 4 * 1024 * 1024,
      encoding: "utf8",
    });
    // stderr from child processes must never leak into the Pi TUI prompt area.
    // The fail-open contract means we continue regardless, but a silent failure
    // reads as "the agent had no memory" — so stderr is captured (not forwarded)
    // and only genuine exec failures surface on our own stderr below.
    void stderr;
    return (stdout ?? "").trim();
  } catch (err) {
    fail(`CORTEX_FAIL ${tool}: ${String(err)}\n`);
    return "";
  }
}

function parse<T>(raw: string, fallback: T): T {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

/** Best-effort text from an AgentMessage: content may be a string or parts. */
function messageText(msg: unknown): string {
  const c = (msg as { content?: unknown; text?: unknown })?.content ??
            (msg as { text?: unknown })?.text;
  if (typeof c === "string") return c;
  if (Array.isArray(c)) {
    return c
      .map((p) => (typeof p === "string" ? p : (p as { text?: string })?.text ?? ""))
      .join(" ")
      .trim();
  }
  return "";
}

type Restored = {
  restored: {
    done?: string[];
    pending?: string[];
    blockers?: string[];
    decisions?: string[];
    notes?: string;
    session_key?: string;
  } | null;
};

// ── Diagnostics: a bounded cortex log, NEVER the harness's stderr ───────────
// In Pi the harness's stderr IS the prompt area, so a stray line scribbles over what
// the user is typing (the reported TUI pollution). Routine trace therefore goes to the
// cortex tree's own log dir — the same convention `mcp-servers/loop-gov-mcp.py` uses,
// with the same two rules: bounded by rotation, and never able to break the tool.
//
// Failures stay LOUD on stderr: a silent memory failure reads as "the agent had no
// memory", which is a different and wrong conclusion. They are recorded in the log too,
// because stderr is ephemeral. CORTEX_CONTEXT_DEBUG=1 additionally echoes the routine
// trace to stderr for live debugging.
const LOG_PATH =
  process.env.CORTEX_CONTEXT_LOG ??
  `${process.env.HOME ?? ""}/.hermes-cortex/logs/pi-context.log`;
const LOG_MAX_BYTES = Number(process.env.CORTEX_CONTEXT_LOG_MAX_BYTES ?? 1_048_576);
const DEBUG = process.env.CORTEX_CONTEXT_DEBUG === "1";

/** Append one line, rotating to `<log>.1` at the cap. Non-fatal by design. */
function appendBounded(message: string) {
  try {
    fs.mkdirSync(path.dirname(LOG_PATH), { recursive: true });
    let size = 0;
    try {
      size = fs.statSync(LOG_PATH).size;
    } catch {
      size = 0;
    }
    if (size >= LOG_MAX_BYTES) {
      try {
        fs.renameSync(LOG_PATH, `${LOG_PATH}.1`);
      } catch {
        // Keep appending rather than lose this line: rotation is housekeeping.
      }
    }
    fs.appendFileSync(LOG_PATH, message, { mode: 0o600 });
  } catch {
    // A logging failure must never change what the extension does.
  }
}

/** Routine trace: the log file, plus stderr only when explicitly debugging. */
const note = (message: string) => {
  appendBounded(message);
  if (DEBUG) process.stderr.write(message);
};

/** A genuine failure: reported on stderr AND recorded. */
const fail = (message: string) => {
  process.stderr.write(message);
  appendBounded(message);
};

/**
 * The session id the reflexion gate will query, asked of the SHARED governance
 * implementation (`loop-gov.py session_identity` → loop-gov-mcp.py's predicate).
 *
 * The gate answers from the active lock's session id, so the writer must use that
 * same id. It is deliberately NOT read out of a file or out of CORTEX_SESSION_KEY:
 * either would be a second derivation of "which session is this", and a second
 * derivation is how the writer and the checker come to disagree — which is the
 * defect this replaces (every Pi commit was refused because the evidence landed
 * under `hc-pi-<chat>` while the gate asked about `sess_<hex>`).
 *
 * Returns "" when the id cannot be resolved. The caller REPORTS that failure and
 * records nothing: inventing a key would recreate the disagreement silently.
 * Read-only and side-effect-free apart from the CLI's own id file.
 */
async function gateSessionKey(): Promise<string> {
  try {
    const { stdout } = await run(PYTHON, [GOV_CLI, "session_identity", "{}"], {
      timeout: 20_000,
      maxBuffer: 1 * 1024 * 1024,
      encoding: "utf8",
    });
    const parsed = JSON.parse((stdout ?? "").trim() || "{}");
    const key = typeof parsed?.effective_session_id === "string"
      ? parsed.effective_session_id.trim()
      : "";
    if (!key) {
      fail("CORTEX_GOV_SESSION no effective_session_id in the CLI's answer\n");
    }
    return key;
  } catch (err) {
    // Missing CLI, a non-zero exit, a timeout, or malformed JSON all land here.
    // They are the SAME outcome for this writer — no key, so no evidence — and
    // they are reported with the reason rather than swallowed.
    fail(`CORTEX_GOV_SESSION unavailable (${String(err).split("\n")[0]})\n`);
    return "";
  }
}

export default function (pi: any) {
  // ── 1. Session start: RESUME, injected via the return value ──────
  pi.on("before_agent_start", async (event: any) => {
    const snap = parse<Restored>(await cortex("session_restore", {}), { restored: null }).restored;
    if (!snap) {
      note("CORTEX_RESUME none\n");
      return;
    }
    const line = (label: string, items?: string[]) =>
      items && items.length ? `${label}: ${items.join("; ")}` : "";
    const parts = [
      line("Done", snap.done),
      line("Pending", snap.pending),
      line("Blocked", snap.blockers),
      line("Decided", snap.decisions),
      snap.notes ? `Notes: ${snap.notes}` : "",
    ].filter(Boolean);
    note(`CORTEX_RESUME ${snap.session_key ?? ""} facts=${parts.length}\n`);
    if (!parts.length) return; // nothing recorded yet — do not inject an empty block
    return {
      systemPrompt:
        `${event?.systemPrompt ?? ""}\n\n## Session context (cortex, ` +
        `${snap.session_key ?? "this session"})\n${parts.join("\n")}\n` +
        `Resume from this — do not re-derive what is already recorded.`,
    };
  });

  // ── 2. THE TRIGGER: checkpoint at turn end, without asking the model ──
  pi.on("turn_end", async (event: any) => {
    // turn_end carries: turnIndex, message, toolResults, entries, outcome.
    const toolResults = Array.isArray(event?.toolResults) ? event.toolResults : [];
    const done = toolResults
      .map((r: any) => r?.toolName ?? r?.name)
      .filter((n: unknown): n is string => typeof n === "string" && n.length > 0);
    const notes = messageText(event?.message).slice(0, 800);

    if (!done.length && !notes) {
      // Never write a silently-empty checkpoint, and never hide why.
      note(
        `CORTEX_CHECKPOINT_EMPTY turn=${event?.turnIndex} ` +
        `keys=${Object.keys(event ?? {}).join(",")}\n`);
      return;
    }
    await cortex("session_checkpoint", { done, notes });
  });

  // ── 3. Before compaction: the moment continuity is most at risk ──
  pi.on("session_before_compact", async () => {
    await cortex("session_checkpoint", {
      notes: "checkpoint taken before context compaction",
    });
  });

  // ── 4. Record skill loads: the pre-commit reflexion gate's evidence ──────
  //
  // A Pi commit is gated by the same global git hook as a Hermes one, and that gate
  // asks HC's own store "did this session load skill X?".
  //
  // HERMES loads a skill with `skill_view`. PI HAS NO SUCH TOOL — verified by
  // driving the installed Pi package through its own factory, 2026-10-15:
  // `createReadToolDefinition(...).parameters` is `{path, offset, limit}`, the Pi
  // bundle contains no `skill_view` at all, and Pi's OWN system prompt says "Use
  // the read tool to load a skill's file when the task matches its description".
  //
  // Keying this handler on `toolName === "skill_view"` therefore recorded NOTHING
  // for a Pi session: the reflexion gate refused every Pi commit no matter how
  // well the agent behaved, and an agent that read a skill the only way its
  // harness allows was indistinguishable from one that loaded nothing. Both
  // mechanisms are recorded now, each under its TRUE tool name — the store must
  // never claim a `skill_view` that did not happen.
  //
  // The event is keyed to the session the GATE will query (`session_identity`),
  // not to CORTEX_SESSION_KEY: the gate asks about the governance lock's session
  // id, so a second key can only ever disagree with it.
  //
  // Only gate-relevant tool calls are recorded, not every call: the store is
  // evidence, not a transcript. A failure is reported, never silent — a silent
  // failure here is indistinguishable from an agent that loaded nothing, which is
  // exactly the bug this handler exists to remove.
  pi.on("tool_result", async (event: any) => {
    // The base ToolResultEvent has no toolName; the concrete variants do, so read
    // it defensively rather than assuming the general shape.
    const toolName = typeof event?.toolName === "string" ? event.toolName : "";
    const input = event?.input ?? {};
    const readPath = typeof input?.path === "string" ? input.path : "";

    // Pi's mechanism: a read of the skill's own file (<dir>/<skill>/SKILL.md).
    const skillFromPath = readPath.endsWith("/SKILL.md")
      ? readPath.slice(0, -"/SKILL.md".length).split("/").pop() ?? ""
      : "";
    const isPiSkillLoad = toolName === "read" && skillFromPath !== "";
    if (toolName !== "skill_view" && !isPiSkillLoad) return;

    const sessionKey = await gateSessionKey();
    if (!sessionKey) {
      fail(
        `CORTEX_TOOL_EVENT ${toolName} NOT RECORDED — could not resolve the ` +
          `governance session id (see the CORTEX_GOV_SESSION line above); the ` +
          `reflexion gate will report this skill as NOT-LOADED.\n`
      );
      return;
    }
    const raw = await cortex("session_tool_event", {
      tool_name: toolName,
      content: input,
      session_key: sessionKey,
    });
    if (raw) note(`CORTEX_TOOL_EVENT ${toolName} recorded\n`);
    else fail(`CORTEX_TOOL_EVENT ${toolName} FAILED\n`);
  });

  // ── NO registerTool CALLS HERE, DELIBERATELY ─────────────────────
  // The tools live in the shared MCP server, so there is exactly ONE definition
  // of them. Registering them again here would recreate the phantom-surface bug
  // this file was rewritten to fix (a second definition silently wins or loses).
  // Guarded by tests/test_context_harnesses.py and verify-extension.mjs.
}
