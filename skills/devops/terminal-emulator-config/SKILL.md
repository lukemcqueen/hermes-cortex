---
name: terminal-emulator-config
description: "Diagnose terminal input issues and review emulator configs."
version: 1.0.0
category: devops
platforms: [linux, macos]
---

# Terminal Emulator Config Review & Input Troubleshooting

## When to use
- User reports keys/characters not working in a terminal (capital letters, special chars, Alt/Option combos, Ctrl+Shift combos)
- User asks to review a terminal emulator config (Ghostty, kitty, iTerm2, WezTerm, Alacritty)
- "X doesn't work in the terminal" where the terminal config is suspect

## Core mechanisms (verified against Ghostty docs + upstream discussions 2026-08)

### 1. Keybinds consume input by default
Official keybind docs: *"By default, a keybind will consume the input, meaning that the associated encoding (if any) will not be sent to the running program."*
- A wall of `keybind = ctrl+shift+...` / `alt+...` lines makes those combos dead in every app.
- The **kitty keyboard protocol does NOT override emulator keybinds** (Ghostty discussion #9368) — Ghostty's own binds swallow the event first. Apps that distinguish Shift+Ctrl+X from Ctrl+X (Neovim, vim with modifyOtherKeys, Helix, fish, readline 8+, prompt_toolkit CLIs like Hermes) lose the bound combos.
- Fix pattern: `keybind = performable:ctrl+shift+c=copy_to_clipboard` — only consumes when there is a selection; otherwise the key passes through to the app. Standard fix for copy/paste binds.

### 2. macOS Option/Alt handling
- `macos-option-as-alt` **defaults to true on U.S. Standard and U.S. International layouts** — Option+letter sends Alt+escapes instead of macOS special characters (Option+u dead-key → ä/ö/ü broken). Ghostty discussion #6005: "None of the characters invoked with Alt+[character] is printed."
- **Alt+Shift+key macOS system shortcuts don't fire inside Ghostty at all**, even with `keybind = clear` (#3622) — Ghostty swallows the events.
- If macOS special characters are wanted: `macos-option-as-alt = false`.

### 3. TERM overrides degrade key protocols
- Ghostty's default `term` is `xterm-ghostty`, deliberately xterm-prefixed because **vim uses the xterm prefix to enable modifyOtherKeys** (config reference, "HACK" note).
- Overriding `term = xterm-256color` degrades enhanced key reporting and protocol negotiation in vim/fish/tmux. Keep the native TERM; for SSH use the built-in conversion (Ghostty `shell-integration-features = ssh-env` auto-converts to xterm-256color remotely) instead of a global override.

### 4. Platform-specific keys
- Linux/GTK keys (`gtk-*`, `linux-cgroup-*`) are ignored with warnings on macOS; `quick-terminal-*` is macOS-only. Cosmetic noise, not fatal — but a Linux config pasted onto macOS is the #1 source of "why is my config wrong" questions. Always confirm the actual platform first.

### 5. Duplicate settings: later line wins
- Repeated single-value keys: last occurrence wins (`clipboard-read = ask` then `allow` → allow).
- Watch physical-key collisions: on a US layout `+` IS Shift+`=`, so `ctrl+plus` and `ctrl+shift+equal` are the same trigger — later line silently wins.
- Exception: repeated `font-family` is a **fallback chain** (primary + fallbacks), NOT last-wins. Verify before claiming.

### 6. Common app-chord collisions to look for
- `ctrl+0` → Emacs digit-argument / NUL — eaten by font-reset binds
- `ctrl+minus` → readline undo (C-_) — eaten by font-shrink binds
- `ctrl+shift+left/right/up/down` → macOS text selection + tab/prompt-nav conflicts
- `ctrl+shift+c/v` → vim/Neovim copy/paste patterns

### 7. Paste protection ≠ input broken
- `clipboard-paste-protection = true` shows a confirmation dialog for unsafe pastes — users perceive this as "special characters don't work" when pasting. Always ask whether the failure is typing or pasting.

## Workflow
1. Ask WHERE it fails: plain shell, vim/neovim, or a specific app (Hermes CLI, etc.). Plain Shift+letter in a bare shell CANNOT be broken by terminal config — check keyboard layout/IME/Caps Lock instead.
2. Use the emulator's own listing tools: `ghostty +list-keybinds`, `ghostty +list-keybinds --default`, `ghostty +list-themes`, `ghostty +list-fonts`.
3. Grep the config for: keybind walls, term overrides, platform-mismatched keys, duplicates, physical-key collisions.
4. Verify claims against the emulator's current docs before asserting (docs change — e.g. Ghostty renamed themes to Title Case in 1.2.0).

## Pitfalls
- Don't blame the terminal for plain-letter typing failures (layout/IME territory).
- Don't claim "font-family last-wins" — it's a fallback chain.
- Don't forget `performable:` — the standard fix for binds that shouldn't swallow app keys.
- Duplicate keybinds don't error — later silently wins.

## References
- `references/ghostty-macos.md` — verified Ghostty config-reference quotes, GH discussion findings (#6005, #3622, #9368), and the macOS config-review checklist from the 2026-08 session.
