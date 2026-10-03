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
 *      checkpoint), CORTEX_CONTEXT_CLI to override the CLI path.
 *
 * EVERY call is fail-open — but a failure is REPORTED on stderr (a silent
 * failure reads as "the agent had no memory", which is a different, wrong
 * conclusion).
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";

const run = promisify(execFile);

const CLI =
  process.env.CORTEX_CONTEXT_CLI ??
  `${process.env.HOME}/.hermes-cortex/scripts/cortex-context.py`;

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
    const { stdout } = await run(PYTHON, [CLI, tool, JSON.stringify(args)], {
      timeout: 15_000,
      maxBuffer: 4 * 1024 * 1024,
    });
    return stdout.trim();
  } catch (err) {
    process.stderr.write(`CORTEX_FAIL ${tool}: ${String(err)}\n`);
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

export default function (pi: any) {
  // ── 1. Session start: RESUME, injected via the return value ──────
  pi.on("before_agent_start", async (event: any) => {
    const snap = parse<Restored>(await cortex("session_restore", {}), { restored: null }).restored;
    if (!snap) {
      process.stderr.write("CORTEX_RESUME none\n");
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
    process.stderr.write(
      `CORTEX_RESUME ${snap.session_key ?? ""} facts=${parts.length}\n`);
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
      process.stderr.write(
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

  // ── 4. Record tool events: the pre-commit reflexion gate's evidence ──────
  //
  // A Pi commit is gated by the same global git hook as a Hermes one, and that gate
  // asks HC's own store "did this session load skill X?". Nothing recorded it for
  // Pi, so a Pi session's commit was REFUSED no matter what the agent did — the
  // gate was satisfiable only by a harness that had a writer. Measured before this
  // hook existed: `hc-reflexion-check.py --session pi:<repo>:<branch>` => NOT-LOADED.
  //
  // Only gate-relevant tools are recorded, not every call: the store is evidence,
  // not a transcript. A failure is reported, never silent — a silent failure here is
  // indistinguishable from an agent that loaded nothing.
  pi.on("tool_result", async (event: any) => {
    // The base ToolResultEvent has no toolName; the concrete variants do, so read
    // it defensively rather than assuming the general shape.
    const toolName = typeof event?.toolName === "string" ? event.toolName : "";
    if (toolName !== "skill_view") return;
    const raw = await cortex("session_tool_event", {
      tool_name: toolName,
      content: event?.input ?? {},
    });
    process.stderr.write(
      `CORTEX_TOOL_EVENT ${toolName} ${raw ? "recorded" : "FAILED"}\n`);
  });

  // ── NO registerTool CALLS HERE, DELIBERATELY ─────────────────────
  // The tools live in the shared MCP server, so there is exactly ONE definition
  // of them. Registering them again here would recreate the phantom-surface bug
  // this file was rewritten to fix (a second definition silently wins or loses).
  // Guarded by tests/test_context_harnesses.py and verify-extension.mjs.
}
