/**
 * cortex-governance.ts — Pi extension: the WRITE GATE for pi's native tools.
 *
 * WHY THIS EXISTS (2026-10-14, titus)
 *
 *   Governance is enforced for Hermes at the TOOL level by the enforcer plugin
 *   (`~/.hermes/plugins/governance-enforcer/`), which is a Hermes plugin and
 *   therefore runs only in the Hermes agent loop. Pi's `read`/`bash`/`edit`/`write`
 *   are pi-NATIVE: they never cross that plugin, and the loop-governance MCP
 *   server (which pi IS connected to) is a tool SURFACE — it can hand the agent
 *   `begin_change`, but it cannot see a native write. So a pi session could edit
 *   and write files with no lock at all.
 *
 *   The commit-time hook is not a substitute. Its lock check exists, but it is
 *   scoped to the hermes-cortex repo only (`IS_CORTEX_REPO`), deliberately, so a
 *   pi session working in a PROJECT repo had no lock gate at write OR commit time.
 *
 * THIS FILE ADDS NO GOVERNANCE SEMANTICS. It is an adapter.
 *
 *   The verdict comes from the ONE shared implementation — `loop-gov.py`, the
 *   generic CLI over loop-gov-mcp.py — via the `check_repo_lock` predicate. The
 *   extension does not parse lock files, does not decide staleness, and does not
 *   match repos: a second implementation of "does a lock cover this repo" is how
 *   the rule stops binding, and the git hook already carries one copy.
 *
 *     rc 0  = a live lock covers this repo        -> allow
 *     rc 1  = governance REFUSED (not locked)     -> block
 *     rc 3  = governance UNAVAILABLE              -> block (fail CLOSED)
 *
 * FAIL CLOSED, INCLUDING ON CANNOT-VERIFY. If loop-gov.py is missing, the
 * interpreter cannot run it, or the repo cannot be resolved, the write is
 * BLOCKED with the reason. A gate that reads "could not check" as "carry on"
 * fails open exactly when the host is broken, which is worse than no gate. The
 * cost is stated in the block message — and it is real: a wedged fleet venv
 * stops file writes here. That is the intended trade; the remedy is printed.
 * There is deliberately NO agent-usable override. The only way to remove this
 * gate is for the operator to uninstall the extension, which is visible.
 *
 * BASH IS CLASSIFIED BY COMMAND, NOT BY SYNTAX. An earlier plan classified a
 * bash call as write-capable by metacharacters (`;` `|` `>` ...). That is a
 * bypass: `cp`, `mv`, `rm`, `tee`, `dd`, `mkdir` contain none of those tokens.
 * So the rule is inverted — a bash call passes ONLY when it is a SINGLE simple
 * command whose name is on a READ-ONLY allowlist, with no metacharacters at
 * all. Everything else (pipes included) needs a lock. Deny by default.
 *
 * INSTALL (user scope, so every pi project gets it):
 *   bash ~/hermes-cortex/ops/scripts/install/install-pi-integration.sh
 * ENV: CORTEX_SESSION_REPO pins the governed repo when pi's cwd is not it;
 *      CORTEX_GOVERNANCE_CLI overrides the loop-gov.py path;
 *      CORTEX_GOVERNANCE_PYTHON overrides the interpreter (macOS: a Homebrew
 *      python3 is often not on pi's PATH).
 */

import { execFile, execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

const run = promisify(execFile);

const CLI =
  process.env.CORTEX_GOVERNANCE_CLI ??
  `${process.env.HOME}/.hermes-cortex/scripts/loop-gov.py`;

/** macOS: `python3` may not be on pi's PATH (Homebrew lives in /opt/homebrew/bin
 *  on Apple Silicon, /usr/local/bin on Intel) and a GUI-launched pi sees a
 *  narrower PATH than a shell. Overridable rather than assumed. */
const PYTHON = process.env.CORTEX_GOVERNANCE_PYTHON ?? "python3";

// ── diagnostics: the cortex log, NEVER pi's stderr ──────────────────────────
// In pi the harness's stderr IS the prompt area, so a stray line scribbles over
// what the user is typing. Same convention as cortex-context.ts / loop-gov-mcp.py:
// bounded by rotation, and never able to break the gate.
const LOG_PATH =
  process.env.CORTEX_GOVERNANCE_LOG ??
  `${process.env.HOME ?? ""}/.hermes-cortex/logs/pi-governance.log`;
const LOG_MAX_BYTES = Number(process.env.CORTEX_GOVERNANCE_LOG_MAX_BYTES ?? 1_048_576);
const DEBUG = process.env.CORTEX_GOVERNANCE_DEBUG === "1";

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
        // keep appending rather than lose the line: rotation is housekeeping
      }
    }
    fs.appendFileSync(LOG_PATH, message, { mode: 0o600 });
  } catch {
    // a logging failure must never change what the gate does
  }
}

const note = (message: string) => {
  appendBounded(message);
  if (DEBUG) process.stderr.write(message);
};

// ── the repo this session is governing ──────────────────────────────────────
// Precedence matches every other cortex layer (args → env → git) — and it really does now:
// the ARGS leg was missing, so a session whose process cwd is not the checkout could never
// resolve the repo even when the command itself NAMED it. Measured on a macOS host (pi, titus,
// 2026-10-18): `cd /Users/luke/Developer/AI/steadfaste-s1-model && pwd && git rev-parse
// --show-toplevel` was refused with "CANNOT DETERMINE THE REPO" — a dead end, because the one
// command that would have proven the repo was itself the write being blocked.
/**
 * Where a repo lookup FAILED, in words. A fail-closed gate that discards the reason it refused is
 * unfixable from the outside: the operator sees "cannot determine the repo" and cannot tell a
 * missing `git` on PATH (ENOENT) from a genuinely non-repo folder from a dubious-ownership
 * refusal. Measured on a macOS host (pi, titus, 2026-10-18): pi WAS started inside the checkout and
 * the gate still said "not in a git repo", and nothing in the message could distinguish the causes.
 */
let repoDiagnostics: string[] = [];

type RootLookup = { root: string | null; why: string };

/**
 * The repo root found by WALKING UP for a `.git` entry — no subprocess, no PATH, no git binary.
 * #2 of the titus fix: the whole lookup used to depend on `git` being callable from THIS process,
 * and a launcher with a stripped PATH (macOS apps and services routinely lack /opt/homebrew/bin)
 * made every lookup fail while git worked fine in the operator's own shell. Finding where a repo
 * STARTS needs no git; only READING it does. A `.git` FILE counts too — that is a worktree or a
 * submodule — and the nearest enclosing one is exactly what `git rev-parse --show-toplevel` answers.
 */
function repoRootByWalk(startPath: string): string | null {
  let dir = startPath;
  try {
    if (!fs.statSync(dir).isDirectory()) dir = path.dirname(dir);
  } catch {
    dir = path.dirname(dir);
  }
  for (let hops = 0; hops < 64; hops++) {
    try {
      fs.statSync(path.join(dir, ".git"));
      return dir;
    } catch {
      /* not here — keep walking up */
    }
    const parent = path.dirname(dir);
    if (parent === dir) return null;   // filesystem root
    dir = parent;
  }
  return null;
}

function gitRootOf(target: string): RootLookup {
  const byWalk = repoRootByWalk(target);
  if (byWalk) return { root: byWalk, why: "" };
  // No `.git` anywhere above: ask git itself, in case of a layout the walk cannot see (a bare repo,
  // GIT_DIR/GIT_WORK_TREE in the environment). If THAT fails too, its words are the explanation.
  try {
    const out = execFileSync("git", ["rev-parse", "--show-toplevel"], {
      cwd: target,
      encoding: "utf8",
      timeout: 5000,
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
    if (!out) return { root: null, why: `${target}: no .git above it; git printed nothing` };
    return { root: path.resolve(out), why: "" };
  } catch (e: any) {
    const stderr = String(e?.stderr ?? "").trim().split("\n")[0] ?? "";
    const code = e?.code ?? e?.status ?? "?";
    const msg = String(e?.message ?? "").split("\n")[0];
    return {
      root: null,
      why: `${target}: no .git above it, and git said ${code} — ${stderr || msg || "no output"}`,
    };
  }
}

/** The repo this CALL touches, taken from the tool's own input. */
function repoFromToolInput(input: any): string | null {
  if (!input || typeof input !== "object") return null;
  const candidates: string[] = [];
  // File-shaped tools name the file they will touch.
  for (const key of ["path", "file_path", "filePath", "filename", "target"]) {
    const v = input[key];
    if (typeof v === "string" && v.trim()) {
      const expanded = v.trim().replace(/^~(?=\/|$)/, process.env.HOME ?? "~");
      candidates.push(path.resolve(process.cwd(), expanded));
    }
  }
  // A shell command may name the checkout itself — `cd <abs> && ...`, or any absolute path.
  const cmd = typeof input.command === "string" ? input.command : "";
  for (const m of cmd.matchAll(/\/[^\s"'`;&|()<>]+/g)) {
    candidates.push(m[0]);
  }
  for (const c of candidates) {
    // A FILE path is not a git cwd: try the path itself, then its directory.
    const look = gitRootOf(c);
    if (look.root) return look.root;
    const dirLook = gitRootOf(path.dirname(c));
    if (dirLook.root) return dirLook.root;
    repoDiagnostics.push(look.why);
  }
  return null;
}

function sessionRepo(input?: any): string | null {
  repoDiagnostics = [];
  const fromArgs = repoFromToolInput(input);                       // 1. what THIS call touches
  if (fromArgs) return fromArgs;
  const pinned = (process.env.CORTEX_SESSION_REPO ?? "").trim();   // 2. explicit pin
  if (pinned) {
    repoDiagnostics.push(`CORTEX_SESSION_REPO=${pinned} (used as given, never checked)`);
    return path.resolve(pinned);
  }
  const look = gitRootOf(process.cwd());                          // 3. pi's own cwd
  if (look.root) return look.root;
  repoDiagnostics.push(`cwd ${look.why}`);
  return null;
}

type Verdict = "allowed" | "refused" | "unavailable" | "unresolved";

/** Ask the SHARED implementation. No local lock parsing, ever. */
async function askGovernance(repo: string): Promise<{ verdict: Verdict; detail: string }> {
  let stdout = "";
  let stderr = "";
  let code = -1;
  try {
    const res = await run(PYTHON, [CLI, "check_repo_lock", JSON.stringify({ repo_path: repo })], {
      timeout: 20_000,
      maxBuffer: 4 * 1024 * 1024,
      encoding: "utf8",
    });
    stdout = res.stdout ?? "";
    stderr = res.stderr ?? "";
    code = 0;
  } catch (err: any) {
    // execFile throws on ANY non-zero exit, which is the normal refusal path
    // (rc 1) as well as a genuine failure (rc 3) — so read the status off the
    // error rather than treating every non-zero as "governance is down".
    stdout = String(err?.stdout ?? "");
    stderr = String(err?.stderr ?? "");
    code = typeof err?.code === "number" ? err.code : -1;
  }
  const detail = (stdout || stderr || "").trim();
  if (code === 0) return { verdict: "allowed", detail };
  if (code === 1) return { verdict: "refused", detail };
  return { verdict: "unavailable", detail: `rc=${code} ${stderr || stdout || ""}`.trim() };
}

// ── bash classification: a read-only ALLOWLIST, deny by default ─────────────
// Only these command names may run unlocked, and only as a SINGLE simple
// command (no pipe, no redirect, no substitution, no chaining).
const READ_ONLY_COMMANDS = new Set([
  "ls", "cat", "head", "tail", "wc", "file", "stat", "pwd", "echo", "printf",
  "which", "type", "date", "uname", "hostname", "id", "whoami", "ps", "du", "df",
  "basename", "dirname", "realpath", "readlink", "tree", "less", "more", "man",
  "sort", "uniq", "cut", "tr", "jq", "diff", "cmp", "sha256sum", "shasum",
  "md5sum", "command", "test", "true", "false", "grep", "rg", "egrep", "fgrep",
  "column", "nl", "seq", "tac", "rev",
]);

/** git subcommands whose BARE form only reads. `branch`/`tag`/`remote` are
 *  handled separately because they mutate given extra args. */
const READ_ONLY_GIT = new Set([
  "status", "log", "diff", "show", "rev-parse", "ls-files", "ls-tree", "blame",
  "describe", "reflog", "shortlog", "whatchanged", "grep", "cat-file",
]);

/** Only flags that cannot delete or create a ref. */
const LISTING_ONLY_FLAGS = new Set([
  "-a", "-r", "-v", "-vv", "-l", "--list", "--all", "--verbose", "-d-",
]);

/** Metacharacters that make a command compound or write-capable. Note this list
 *  is a NARROWING condition on top of the allowlist, never the classifier
 *  itself: `cp a b` has none of these and must still be refused (by name). */
const METACHARS = [";", "|", "&", ">", "<", "`", "$(", "\n", "\r", "\\"];

function isReadOnlyBash(command: unknown): boolean {
  if (typeof command !== "string") return false;
  const cmd = command.trim();
  if (!cmd) return false;
  for (const meta of METACHARS) if (cmd.includes(meta)) return false;

  // Split on whitespace only — no shell parsing, because metachars are already out.
  const parts = cmd.split(/\s+/).filter(Boolean);
  if (!parts.length) return false;
  const name = path.basename(parts[0]);
  const args = parts.slice(1);

  if (name === "git") {
    const sub = args[0];
    if (!sub) return false; // bare `git` prints help; not worth an allowance
    if (READ_ONLY_GIT.has(sub)) return true;
    if (sub === "branch" || sub === "tag" || sub === "remote") {
      const rest = args.slice(1);
      if (rest.length === 0) return true;
      // Only pure listing flags — `git branch -d x` / `git tag v1` mutate refs.
      return rest.every((a) => LISTING_ONLY_FLAGS.has(a));
    }
    return false;
  }
  if (name === "find") {
    // find READS, but -exec/-delete/-fprint make it a writer. Deny by default.
    return !args.some((a) => a.startsWith("-exec") || a.startsWith("-delete")
      || a.startsWith("-ok") || a.startsWith("-fprint") || a.startsWith("-fls"));
  }
  return READ_ONLY_COMMANDS.has(name);
}

function toolNeedsLock(toolName: string, input: any): boolean {
  if (toolName === "write" || toolName === "edit") return true;
  if (toolName === "bash" || toolName === "powershell") {
    return !isReadOnlyBash(input?.command ?? input?.cmd);
  }
  // read/grep/find/ls and every non-native (MCP/custom) tool pass: this gate
  // covers pi's own write surface, which is the reported gap. It is not a
  // sandbox for tools that are not pi's.
  return false;
}

// ── the block messages ─────────────────────────────────────────────────────
/** Name the live locks the predicate reported as NOT covering this repo.

 *  A refusal that prints `live_lock_count: 1` and names nothing leaves the
 *  reader unable to tell a broken gate from someone else's live lock. The
 *  predicate already answers which locks did not match, so this only RENDERS
 *  its `other_locks` — it does not open the state dir, test staleness, or
 *  compare repos. An unparseable detail yields no section, never an invented one.
 */
function foreignLockSection(detail: string): string[] {
  let parsed: any;
  try {
    parsed = JSON.parse(detail);
  } catch {
    return [];
  }
  const others = Array.isArray(parsed?.other_locks) ? parsed.other_locks : [];
  if (!others.length) return [];
  const MAX_NAMED = 3;
  const lines = ["Live locks on this host — none covers this repo:"];
  for (const lk of others.slice(0, MAX_NAMED)) {
    const repo =
      String(lk?.repo_path ?? "").trim() || "(records no repo_path — covers nothing)";
    lines.push(`  - ${repo}  (task: ${lk?.task_id ?? "unknown"}, agent: ${lk?.agent ?? "unknown"})`);
  }
  if (others.length > MAX_NAMED) lines.push(`  … and ${others.length - MAX_NAMED} more`);
  return lines.concat([""]);
}

/** The predicate's own JSON, bounded — and the bound DISCLOSED.

 *  A silently cut block reads as a whole one: the reader cannot tell an omitted
 *  lock from a field that was never returned. Bump this only with the note.
 */
function boundedDetail(detail: string): string {
  if (!detail) return "(no detail)";
  const RAW_LINES = 16;
  const lines = detail.split("\n");
  if (lines.length <= RAW_LINES) return detail;
  return (
    lines.slice(0, RAW_LINES).join("\n") +
    `\n… ${lines.length - RAW_LINES} more line(s) omitted`
  );
}

function refusedMessage(repo: string, detail: string): string {
  return [
    "🛑 GOVERNANCE LOCK REQUIRED — this pi tool call writes, and no live lock covers this repo.",
    "",
    `Repo: ${repo}`,
    "",
    "Pi's native edit/write/bash tools do not pass through the Hermes enforcer",
    "plugin, so this gate asks the shared governance implementation instead.",
    "It answered: no lock.",
    "",
    ...foreignLockSection(detail),
    "Open one (any of these reaches the SAME implementation):",
    "  pi's loop-governance MCP tool:  begin_change(task_id=\"...\", description=\"...\")",
    `  the generic CLI:                python3 ${CLI} begin_change '{"task_id":"...","description":"..."}'`,
    "",
    "Read-only work needs no lock: use the read/grep/find/ls tools, or a SINGLE",
    "simple read-only command (ls, cat, grep, git status, ...). Anything compound",
    "— a pipe, a redirect, a second command — counts as a write here.",
    "",
    "Governance said:",
    boundedDetail(detail),
  ].join("\n");
}

function unavailableMessage(repo: string, detail: string): string {
  return [
    "🛑 GOVERNANCE UNAVAILABLE — refusing this write (fail CLOSED).",
    "",
    `Repo: ${repo}`,
    `Command: ${PYTHON} ${CLI} check_repo_lock ...`,
    `Result: ${detail || "could not run"}`,
    "",
    "The gate cannot verify that a lock covers this repo, so it must not allow",
    "the write. This is deliberate: reading 'could not check' as 'carry on'",
    "fails open exactly when the host is broken.",
    "",
    "THE COST, stated plainly: until governance can be reached, pi cannot edit or",
    "write files on this host. That is intended for an enforcement gate, not a",
    "bug to route around — there is no agent-side override.",
    "",
    "Operator remedy (in order):",
    "  1. python3 ~/hermes-cortex/ops/scripts/manage/fix-cortex-venv.py --check",
    "  2. bash ~/hermes-cortex/ops/scripts/cortex-update.sh",
    "  3. confirm: python3 ~/.hermes-cortex/scripts/loop-gov.py --list",
    "  4. to remove the gate entirely (operator decision, and visible): drop",
    "     cortex-governance.ts from \"extensions\" in ~/.pi/agent/settings.json",
  ].join("\n");
}

function unresolvedMessage(diagnostics: string[] = []): string {
  return [
    "🛑 GOVERNANCE CANNOT DETERMINE THE REPO — refusing this write (fail CLOSED).",
    "",
    "Pi is not in a git repo and CORTEX_SESSION_REPO is unset, so there is no",
    "tree to govern. Run pi from inside the repo you are working in, or set",
    "CORTEX_SESSION_REPO to its absolute path, then retry.",
    "",
    "WHAT WAS TRIED (this part used to be swallowed, which made the refusal",
    "impossible to act on):",
    ...(diagnostics.length
      ? diagnostics.map((d) => `  - ${d}`)
      : ["  - no lookup ran: the call named no usable path"]),
    "",
    "  A line ending in ENOENT means git is not on THIS PROCESS's PATH — the",
    "  folder may well be a repo. Give pi a PATH that includes git, or set",
    "  CORTEX_SESSION_REPO to the checkout. Anything else quotes git's own words.",
  ].join("\n");
}

export default function (pi: any) {
  // The extension's ONLY hook: block a write-capable native tool call before it
  // runs. A tool_call handler may return { block: true, reason } to stop the
  // call; the agent sees the reason and that the block is final.
  pi.on("tool_call", async (event: any) => {
    const toolName = typeof event?.toolName === "string" ? event.toolName : "";
    if (!toolNeedsLock(toolName, event?.input)) return; // read-only pass-through

    const repo = sessionRepo(event?.input);
    if (!repo) {
      note(`GOV_UNRESOLVED tool=${toolName}\n`);
      return { block: true, reason: unresolvedMessage(repoDiagnostics) };
    }

    const { verdict, detail } = await askGovernance(repo);
    note(`GOV_VERDICT tool=${toolName} repo=${repo} verdict=${verdict}\n`);

    if (verdict === "allowed") return; // covered by a live lock
    if (verdict === "unavailable") {
      return { block: true, reason: unavailableMessage(repo, detail) };
    }
    return { block: true, reason: refusedMessage(repo, detail) };
  });
}
