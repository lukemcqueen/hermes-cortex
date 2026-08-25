---
name: dev-port-conflict
description: Diagnose and clear an orphaned server holding a dev port.
version: 1.0.0
category: devops
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [debugging, ports, dev-server, orphan, eaddrinuse]
    related_skills: [web-ui-debugging, prevent-crash-looping]
---

# Dev Port Conflict — EADDRINUSE from an Orphaned Server

A project's `./run dev` (or `next dev` / `uvicorn`) fails with
`Error: listen EADDRINUSE: address already in use :::<port>` because a
previous run's server is still alive and squatting on the port. The classic
culprit is an **orphaned dev server**: the terminal that launched it exited,
so the process was reparented to init (macOS launchd / PPID 1) and now lives
forever holding 13201/13202 etc. It is leftover, not wanted. This skill walks
find-holder → prove-stale → free → verify.

## When to Use

- `./run dev`, `./run dev:web`, `./run dev:api` (or any dev command) fails to
  start with EADDRINUSE / "address already in use".
- A web/API port never comes up and `lsof` shows a node/python process you
  did not start.
- After any multi-port dev command ejects partial output and dies.

Don't use for: page shows rows/empty despite the API returning data (that is
`web-ui-debugging`); systemd services crash-looping (that is
`prevent-crash-looping`).

## Procedure

1. **Find the holder.**
   ```
   lsof -nP -iTCP:<port> -sTCP:LISTEN
   ```
   `-nP` suppresses name/port resolution (fast, no DNS); `-sTCP:LISTEN`
   confines to listeners. Note the PID and what the command actually is.

   Completion: an output line with PID + command, or the port genuinely free.

2. **Trace the ancestry to classify orphan vs managed.** The command that
   matters is often the *grandparent*, not the PID lsof returned (a
   next-server child → `next dev` parent → `pnpm exec next dev` grandparent).
   ```
   ps -o pid,ppid,etime,command -p <pid>            # repeat for its PPID
   ```
   Orphan signature: the top ancestor has **PPID 1** (reparented to launchd
   after its terminal died) and an elapsed time of minutes-to-hours. An
   actively-managed server has a sitting terminal or a supervisor ancestor.

   Completion: you can state the full lineage and whether the top ancestor is
   PPID 1.

3. **Confirm no steward will respawn it.** PPID 1 alone doesn't mean
   unsupervised — check for a keepalive:
   ```
   launchctl list 2>/dev/null | grep -iE '<name>'      # macOS
   ```
   If a launchd/systemd label owns it, killing it makes the steward respawn
   it — don't fight the supervisor. A plain `pnpm`/`next`/`uvicorn` orphan
   reparented to launchd with NO matching launchd label is free to kill.

   Completion: you know whether the process is supervised (do not kill) or
   a dead-fit orphan (safe to kill).

4. **Clean SIBLING ports, not just the reported one.** A dev command binds
   several ports (e.g. a project's web 13201, api 13202). EADDRINUSE surfaces on the
   first busy one and hides the rest. After the fix, check every port the
   command binds so the next `./run dev` doesn't fail one step later:
   ```
   lsof -nP -iTCP:<port2> -sTCP:LISTEN    # repeat for each sibling
   ```
   Completion: every port the dev command binds has been checked.

5. **Kill the orphaned tree (TERM first), then verify.**
   ```
   kill -TERM <top> <mid> <leaf> 2>/dev/null; sleep 2
   lsof -nP -iTCP:<port> -sTCP:LISTEN || echo "port FREE"
   ps -p <pids> 2>/dev/null || echo "orphan pids gone"
   ```
   Completion: the port prints `FREE` and the orphan PIDs are gone.

## Verification

- The reported port prints `port FREE` and `orphan pids gone`.
- EVERY port the dev command binds is checked and free (step 4).
- Tell the user to re-run `./run dev`. Don't start the server on their behalf
  from an agent session, and don't claim done until the reproducible lsof
  check shows the bind is available.

## Pitfalls

- **Kill the whole lineage, not just the listening PID.** lsof returns the
  deepest child (next-server); killing only it leaves the `next dev` parent
  alive and it may respawn or keep a lock. Pass the full PID chain.
- **The reported port is one of several.** Skip step 4 and the user's next
  run dies on the sibling port. Reproduction (2026-08-20): web orphan
  on 13201 (`next dev v15.5.18`, 1h10m) masked an API orphan on 13202
  (uvicorn, 3h08m). Both cleared before `./run dev` was clean.
- **PID 1 ≠ killable by default.** Verify no keepalive first (step 3).
  Killing a supervised process makes the steward instantly respawn it — the
  port stays busy and the fix looks like it failed.
- **When uncertain whether a port-holder is stale**, curl it:
  `curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://localhost:<port>/`.
  A 301/307/200 proves it is serving; combined with PPID-1 ancestry and no
  steward, that is a stale leftover by definition — not a wanted server.

## Example

Example (2026-08-20): `./run dev` → `EADDRINUSE :::13201`, exit 48.
`lsof` → node PID 60768. Ancestry 60768→60762→60629
(`node .../pnpm exec next dev -p 13201`), top at PPID 1, 1h10m, no launchd
label → dead-fit orphan. Same sweep found uvicorn orphan PID 3317 on 13202
(3h08m, PPID 1). TERM'd the full trees; both ports verified free via lsof;
user re-ran `./run dev` clean.
