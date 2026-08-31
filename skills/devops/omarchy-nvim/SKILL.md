---
name: omarchy-nvim
description: Install omarchy-nvim (LazyVim) user-local without sudo.
version: 0.1.0
author: Esther, Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [nvim, lazyvim, omarchy, user-local, install]
---

# omarchy-nvim Skill

Installs Neovim with the **omarchy-nvim** config — omarchy's prebuilt LazyVim
setup — entirely user-local (`~/.local`), no sudo required. Replicates exactly
what the omacom/omarchy `omarchy-nvim` PKGBUILD builds, so the result matches
omarchy's own docs (manual/16-neovim.md). Does not touch apt packages, system
paths, or desktop/Wayland integrations (this is for servers).

## When to Use

- User asks to "install neovim and configure like omarchy"
- User references `https://github.com/omacom/omarchy/blob/quattro/manual/16-neovim.md`
- Setting up LazyVim on a Linux server without passwordless sudo

Don't use for: a plain Neovim install (apt `nvim` is fine if the version is
new enough), or a from-scratch LazyVim config the user wants to customize —
this skill reproduces omarchy's exact config, not a general LazyVim setup.

## Prerequisites

- Linux (Ubuntu/Debian verified; user-local so it works anywhere without root)
- `curl` and `tar` on PATH
- `zsh` (the `n` alias goes in `~/.aliases`, which `.zshrc` sources)
- `~/.local/bin` on PATH (create it if missing)
- The package age gate applies: only install releases **≥ 14 days old** —
  check `published_at` on the GitHub release API before choosing a version.

## Source of Truth

Do NOT re-research from scratch. The canonical sources are:

- omarchy manual: `https://raw.githubusercontent.com/omacom/omarchy/quattro/manual/16-neovim.md`
- Package recipe (what to replicate): `https://raw.githubusercontent.com/omacom/omarchy-pkgs/HEAD/pkgbuilds/omarchy-nvim/`
  - Files: `PKGBUILD`, `lazyvim.json`, `omarchy-nvim-setup`, `.omarchy/package.json`,
    `lua/config/options.lua`, `lua/config/remote_clipboard.lua`,
    `lua/plugins/all-themes.lua`, `lua/plugins/disable-news-alert.lua`,
    `lua/plugins/omarchy-theme-hotreload.lua`, `lua/plugins/snacks-animated-scrolling-off.lua`,
    `plugin/after/transparency.lua`
  - The PKGBUILD's install step (headless `Lazy! sync`) is the prime step to replicate.

## Procedure

1. **Resolve versions (age gate).** For nvim, fd, lazygit: query the GitHub
   release API (`https://api.github.com/repos/<owner>/<repo>/releases/tags/<tag>`),
   read `published_at`, and pick the newest tag that is ≥ 14 days old. On the
   verified run: nvim `v0.12.4` (0.12.5 was 7 days old — rejected), fd `10.4.2`
   (10.5.0 was 4 days old — rejected), lazygit `0.64.1`.
   - Completion: every chosen version's `published_at` is ≥ 14 days before today.

2. **Install Neovim** (apt nvim is 0.9.x — too old; LazyVim requires ≥ 0.11.2 LuaJIT):
   ```bash
   terminal(command="curl -sL https://github.com/neovim/neovim/releases/download/v0.12.4/nvim-linux-x86_64.tar.gz | tar xz -C ~/.local/opt --transform 's/^nvim-linux-x86_64/nvim/' && ln -sf ~/.local/opt/nvim/bin/nvim ~/.local/bin/nvim", timeout=180)
   ```
   - Completion: `nvim --version` shows `NVIM v0.12.x` with a LuaJIT build.

3. **Install fd** (apt's `fd-find` binary is `fdfind`, wrong name — use the
   user-local tarball to keep `fd`):
   ```bash
   terminal(command="curl -sL https://github.com/sharkdp/fd/releases/download/v10.4.2/fd-v10.4.2-x86_64-unknown-linux-gnu.tar.gz | tar xz -C ~/.local/opt --transform 's/^fd-[^/]*/fd/' && ln -sf ~/.local/opt/fd/fd ~/.local/bin/fd", timeout=120)
   ```
   - Completion: `fd --version` prints `fd 10.4.2`.

4. **Install lazygit** (sha256-verify against the release's `checksums.txt`):
   ```bash
   terminal(command="curl -sL -o /tmp/lazygit.tar.gz https://github.com/jesseduffield/lazygit/releases/download/v0.64.1/lazygit_0.64.1_Linux_x86_64.tar.gz && curl -sL https://github.com/jesseduffield/lazygit/releases/download/v0.64.1/checksums.txt | grep -q \"$(sha256sum /tmp/lazygit.tar.gz | cut -d' ' -f1)\" && tar xz -C ~/.local/opt -f /tmp/lazygit.tar.gz --transform 's/^lazygit/lazygit-0.64.1/' && ln -sf ~/.local/opt/lazygit-0.64.1/lazygit ~/.local/bin/lazygit", timeout=120)
   ```
   - Completion: `lazygit --version` runs; the checksum grep matched (exit 0).

5. **Build `~/.config/nvim`** — LazyVim starter as the base, omarchy's files
   layered on top:
   - Clone LazyVim starter: `git clone https://github.com/LazyVim/starter ~/.config/nvim` then remove the `.git` dir (it's a template, not your repo).
   - Fetch every file listed in Source of Truth from
     `.../pkgbuilds/omarchy-nvim/` into its matching path under `~/.config/nvim/`
     (e.g. `lua/config/options.lua` → `~/.config/nvim/lua/config/options.lua`,
     `plugin/after/transparency.lua` → `~/.config/nvim/plugin/after/transparency.lua`).
   - `lazyvim.json` → `~/.config/nvim/lazyvim.json` (enables the neo-tree extra).
   - Add `lua/plugins/theme.lua` = omarchy's tokyo-night theme spec:
     `colorscheme tokyonight-night` (omarchy's default theme).
   - omarchy's `options.lua` sets: relativenumber off, autoformat off, and
     OSC52/tmux-aware remote clipboard.
   - Completion: `tree ~/.config/nvim` (or equivalent) shows starter + the
     omarchy files above; no stray files.

6. **Prime plugins + parsers** (the PKGBUILD's install step):
   ```bash
   terminal(command="export PATH=$HOME/.local/bin:$PATH && cd /tmp && nvim --headless '+Lazy! sync' '+qa'", timeout=600)
   ```
   - Completion: 51 plugins installed, 24 treesitter parsers compiled (bash,
     c, python, lua, tsx, yaml, markdown, ...) under `~/.local/share/nvim`.

7. **Add the `n` alias** (omarchy's terminal equivalent of the Super+Shift+N
   desktop binding — this is a server):
   ```bash
   terminal(command="echo \"alias n='nvim'\" >> ~/.aliases", timeout=10)
   ```
   - Completion: `zsh -ic 'alias n'` prints `n=nvim`.

## Pitfalls

- **Headless keymap checks lie.** LazyVim registers most keymaps on the
  `VeryLazy` event, which **never fires headless** (`nvim --headless '+lua ...'`).
  `maparg('<leader>gg','n')` returning empty headless is a test artifact, NOT a
  config problem. Verify keymaps in a real PTY session (`nvim --listen /tmp/x.sock`
  then `--remote-send`), or just open nvim in a terminal and try the key.
- **apt nvim is too old.** Ubuntu ships 0.9.x; LazyVim needs ≥ 0.11.2 (LuaJIT).
  Always the official tarball, never apt, on stock Ubuntu.
- **`fd-find` ≠ `fd`.** The apt package installs `fdfind`; LazyVim calls `fd`.
  User-local tarball keeps the correct binary name.
- **Age gate (14 days).** Never install a release younger than 14 days
  (package-security rule). Pick the newest tag that clears it and note the
  upgrade path in the delivery.
- **Theme.** omarchy's theme spec sets `colorscheme tokyonight-night`; the
  `all-themes.lua` plugin installs the full theme set for switching.
- **Deliberately skipped on a server:** Super+Shift+N launch binding (Wayland
  desktop), bat/fzf/eza/zoxide (shell extras, not nvim deps), xdg-mime
  nvim.desktop (no file manager).

## Verification

```bash
terminal(command="export PATH=$HOME/.local/bin:$PATH && nvim --version | head -2 && zsh -lc 'which nvim fd lazygit' && zsh -ic 'alias n'", timeout=30)
```

- `nvim --version` → `NVIM v0.12.x`, LuaJIT build
- `which nvim fd lazygit` → all three resolve under `~/.local/bin`
- `alias n` → `n=nvim`
- Headless startup is clean (no Lua errors); `vim.colors_name` =
  `tokyonight-night` after `+lua print(vim.g.colors_name)` (or via
  `nvim --headless '+lua vim.cmd.colorscheme(...)'` in a real session)
- In a real nvim session: `<space><space>` find files, `<space>sg` grep,
  `<space>e` file tree, `<space>gg` lazygit all work
