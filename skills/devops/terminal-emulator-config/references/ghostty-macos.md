# Ghostty on macOS — verified findings (2026-08-21 session)

Sources: https://ghostty.org/docs/config/reference · https://ghostty.org/docs/config/keybind ·
GitHub discussions ghostty-org/ghostty #6005, #3622, #9368.
All quotes verified by fetching the pages directly (web_extract was search-only on this host;
curl + HTML-strip worked).

## Keybind consumption (keybind docs, verbatim)
> "unconsumed: Do not consume the input. By default, a keybind will consume the input, meaning
> that the associated encoding (if any) will not be sent to the running program in the terminal."
> "Keybind triggers are not unique per prefix combination... The keybind set later will overwrite
> the keybind set earlier."

## Kitty keyboard protocol does NOT override keybinds (#9368)
> "I found the issue, Ghostty ships with some default keybindings for Alt-left and Alt-right on
> MacOS, those remap Alt-left and Alt-right to legacy sequence ESC:b and ESC:f... It seems that
> activating the Kitty protocol doesn't override those keybinds."
> "The fix is to unbind them in your Ghostty config."
Verify kitty-protocol delivery with: `kitten show-key -m kitty`.

## macos-option-as-alt (config reference)
> "If your keyboard layout is one of the keyboard layouts listed below, then the default value
> is 'true'... U.S. Standard, U.S. International."
> "if an Option-sequence doesn't produce a printable character, it will be treated as Alt regardless."
So on US layouts, Option+letter special characters (Option+u → ¨, Option+e → ´) are dead by DEFAULT.
Fix: `macos-option-as-alt = false`.

## Alt+Shift system shortcuts (#3622)
> "I have a couple more mappings that rely on alt+shift+some_key does not work only in ghostty
> terminal." — user had `macos-option-as-alt = true`, `keybind = clear`, `alt+shift+m=unbind` and
> the macOS system shortcut STILL did not fire. Ghostty swallows Alt+Shift events; not fixable
> from config.

## Alt+letter special chars (#6005)
Swiss user on US layout, Ghostty 1.1.2:
> "None of the characters invoked with Alt+[character] is printed. Instead, some key combination
> is invoked (usually my prompt exits insert mode and sometimes some old command is inserted)."
Classic `macos-option-as-alt = true` (default on US) symptom. Same class as the 2026-08-21 review.

## term (config reference, verbatim)
> "term — This will be used to set the TERM environment variable.
> HACK: We set this with an xterm prefix because vim uses that to enable key protocols
> (specifically this will enable modifyOtherKeys), among other features."
Keep `term` unset (default xterm-ghostty). For SSH: `shell-integration-features` gains
`ssh-env` (auto-converts TERM to xterm-256color on remote hosts) and `ssh-terminfo`
(auto-installs terminfo remotely) — use those instead of a global `term = xterm-256color`.

## Platform support facts
- `gtk-single-instance`, `gtk-adwaita`, `gtk-tabs-location`, `gtk-wide-tabs`, `gtk-titlebar`,
  `gtk-titlebar-hide-when-maximized` — GTK/Linux only; no effect on macOS (ignored w/ warning).
- `linux-cgroup*` — require systemd; no effect on macOS.
- `quick-terminal-*` — macOS ONLY (note: no default keybind for toggle_quick_terminal).
- `background-blur` — supported on macOS; macOS 26 adds `macos-glass-regular`/`macos-glass-clear`.
- `font-family` repeated N times = documented fallback chain
  ("can be repeated multiple times to specify preferred fallback fonts"), NOT last-wins.

## Config-review checklist used (Linux→macOS config review)
1. Classify every key: macOS-valid / Linux-only (ignored) / duplicate (later wins).
2. List every keybind; flag (a) ctrl+shift walls, (b) app-chord collisions
   (ctrl+0 = Emacs digit-arg, ctrl+minus = readline undo C-_, ctrl+plus == ctrl+shift+equal
   on US layout), (c) alt+up/down vs macOS special chars.
3. Check `term` override vs native TERM.
4. Check `macos-option-as-alt` implications for the user's keyboard layout.
5. Distinguish typing vs pasting (clipboard-paste-protection dialog looks like "input broken").
6. Verify font-family chain intent (fallback order matters: Noto Color Emoji before a CJK font
   is odd but functional — emoji font has no CJK glyphs so fallback proceeds).
7. Deliver: verdict → ranked causes → concrete fix lines → ONE targeting question
   ("where does it fail: plain shell, vim/neovim, or the app?").

## Deliverable shape that worked
Lead with the verdict. Rank causes by likelihood with the evidence mechanism for each.
Give exact replacement config lines. State the honest caveat (plain Shift+letter in a bare
shell cannot be broken by terminal config — that's layout/IME territory).
