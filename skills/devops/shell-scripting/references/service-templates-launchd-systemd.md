# Service templates that must start on every host (launchd + systemd)

A service template that cannot start tells the operator nothing, which puts it in the same
family as a wrapper that dies on a bare `exec`: the supervisor's own message is generic, and
the cause is one of several. These are the rules for `docs/templates/*.plist` (macOS) and
`*.service` (Linux), plus how to keep them portable without a fixture host.

## launchd (macOS): three rules, each of which cost a service

1. **launchd expands NOTHING inside plist strings.** `$HOME/...` or a `PLACEHOLDER/...` written
   literally is passed as a literal filename, the job never starts, and nothing explains why.
   `launchd.plist(5)`: `ProgramArguments` is "an array of strings … passed to `execvp(3)`" —
   there is no shell in that path, so expansion needs an interpreter:

   ```xml
   <key>ProgramArguments</key>
   <array>
       <string>/bin/bash</string>
       <string>-lc</string>
       <string>cd "$HOME/<dir>" || exit 78; exec "$HOME/<venv>/bin/python3" "$HOME/<dir>/server.py"</string>
   </array>
   ```

2. **`StandardOutPath` / `StandardErrorPath` must be literal paths**, so a log file that lives
   under a home directory is created and appended *inside* the shell command instead
   (`mkdir -p "$HOME/...logs"; exec … >>"$HOME/...logs/x.log" 2>&1`). A fixed absolute path
   (a `/tmp/…` file) is fine when the log is disposable; anything the operator keeps belongs
   under `$HOME` and therefore inside the command.

3. **An XML comment may not contain a double hyphen.** A comment mentioning a flag like
   `--unattended` makes the whole plist unparseable and `launchctl` rejects it. The file looks
   fine to the eye, which is why this is checked mechanically (below).

Related: `KeepAlive` is a DICT of real conditions (`SuccessfulExit`, `NetworkState`,
`PathState`, `OtherJobEnabled`, `Crashed`) — an invented key leaves launchd with no reason to
relaunch the job at all, so a `/restart` mechanism silently stops working. With
`SuccessfulExit=false` the job restarts after a NON-zero exit, which is why a daemon that
supports `/restart` under launchd exits **75 (EX_TEMPFAIL)** where the same daemon under
systemd `Restart=always` exits **0**. Keep both paths in one place and don't "normalise" them.

## systemd (Linux): the same conventions, different specifier

- `%h` is the home specifier — never `/home/<user>` in a unit. It expands inside
  `ExecStart`/`ExecStartPre` arguments, including inside a shell string.
- `ExecStart=/bin/bash -lc '<guard>; exec %h/…'` mirrors the launchd shape, so a missing
  interpreter/payload lands in the journal as a named path rather than a generic exec failure.
- A user unit (`~/.config/systemd/user/`) only: a system-level copy puts a second process on
  the same resource (a second poller on a bot token 409s; a second server collides on its port).

## Running the same guard on both

Source the shared launcher guard before the `exec` on BOTH supervisors — the service then names
what is missing (`NO INTERPRETER at <path>`, `NOT DEPLOYED at <path>`) and exits 78 instead of
failing generically:

```bash
. "$HOME/.hermes-cortex/scripts/lib/require-fleet-venv.sh"
require_fleet_venv "$HOME/.hermes-cortex/<payload>"
exec "$HOME/.hermes-cortex/venv/bin/python3" "$HOME/.hermes-cortex/<payload>"
```

## Keep templates portable mechanically, not by review

Four mechanical rules catch this whole class. Put them in the sweep that runs in CI/locally:

| Rule | Why |
|---|---|
| No `/home/<name>/` or `/Users/<name>/` in a template's STRING VALUES (strip comments first — the prose explaining the rule legitimately names one) | An absolute home launches a dead path on every other host |
| `$HOME` in `ProgramArguments` only when the first argv entry is `/bin/bash` or `/bin/sh` | launchd does not expand it; a shell must |
| Every plist PARSES (`plistlib.loads`) with a `Label` and non-empty `ProgramArguments` | An unescaped `&` in a redirect and a `--` in a comment both produce an unparseable file |
| Shipped shell avoids bash-4-only constructs (`declare -A`, `mapfile`, `readarray`, `${v,,}`, `&>>`) | macOS ships bash 3.2; the failure is `invalid option` on a host you are not testing on |

**XML escaping inside a plist shell string:** `2>&1` must be written `2>&amp;1`. This is the
single most common way a hand-edited plist stops parsing.

## Widen a portability probe to BOTH platform layouts

A check written for the Linux layout silently PASSES over the macOS one. A pattern like
`/(?:home)/[A-Za-z0-9_-]+/` matched every `/home/<user>` path and not one `/Users/<user>`, so
the sweep reported "no template hardcodes a user home" while a template hardcoded one — on the
host the rule existed for. Match both layouts, and confirm the detector FIRES on a synthetic
sample before trusting a green run: for a portability check, a passing result over a file the
pattern cannot see is the default failure mode.

## Verify without a macOS host

What a Linux session can honestly prove, and what it cannot:

- **Can**: templates parse (`plistlib`), no hardcoded home in string values, `$HOME` only
  behind a shell, shipped shell is bash-3.2-safe, and the guard's behaviour when the resource
  is absent (constructed by stubbing the root the script resolves against).
- **Cannot**: that the supervisor actually starts the job. Do not present static checks as a
  live confirmation — say which parts were static and let the owner run `plutil -lint`,
  `launchctl list <label>` and the log tail on the real host.
