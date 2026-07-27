# Headless gh CLI Install + OAuth Auth for Agent Servers

## Why

Switching from `git credential.helper store` (plaintext token in `~/.git-credentials`)
to `gh auth login` OAuth device-flow is more secure: no token on disk, OAuth scopes
are bound to the CLI, and revocation is per-app.

## Install gh without sudo (tarball)

Use this when `gh` is not available and you cannot use `apt` / `brew` / `sudo`:

```bash
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) GH_ARCH="amd64" ;;
  aarch64|arm64) GH_ARCH="arm64" ;;
  *) echo "Unsupported arch: $ARCH" >&2; exit 1 ;;
esac

cd /tmp
curl -fsSL -o gh.tar.gz \
  "https://github.com/cli/cli/releases/download/v2.67.0/gh_2.67.0_linux_${GH_ARCH}.tar.gz"
tar xzf gh.tar.gz
mkdir -p ~/.local/bin
cp gh_*/bin/gh ~/.local/bin/
export PATH="$HOME/.local/bin:$PATH"
rm -rf gh_* gh.tar.gz
```

## Device-code auth (headless/SSH)

The `-w` flag uses the device-code flow — prints a one-time code
that the human opens in their browser and types in:

```bash
gh auth login -h github.com -w -p https
# Output: First copy your one-time code: AF08-346F
#         Open: https://github.com/login/device
```

## Wire into git + remove old credential store

```bash
gh auth setup-git            # sets credential.helper to gh
rm -f ~/.git-credentials     # remove plaintext file
```

## Verify

```bash
git push --dry-run           # should complete without password prompt
```

## Pitfalls

- `gh auth login` without `-w` tries to open a browser on the server — fails headlessly
- `gh auth setup-git` must run AFTER `gh auth login` or it has no token to wire
- Arch must match the tarball — download the wrong one silently extracts but `gh --version` shows the binary exists
- If `~/.local/bin` isn't on PATH, `gh` will be installed but `command -v gh` won't find it
