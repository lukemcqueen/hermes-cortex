# Hermes server sudoers audit — June 22, 2026

Audited sudoers NOPASSWD rules on Luke's Linux Mint 22 server (`moses` user).

## Rules found (via `sudo -n -l`)

```
(ALL : ALL) ALL                                          # Full access, password required (catch-all)
(ALL) NOPASSWD: /usr/sbin/nginx -t                       # nginx config validation
(ALL) NOPASSWD: /usr/bin/systemctl reload|start|stop|restart nginx    # nginx service management
(ALL) NOPASSWD: /usr/bin/systemctl start|stop|restart docker          # docker service management
(ALL) NOPASSWD: /usr/bin/apt autoremove, /usr/bin/apt clean           # apt cleanup (appears DUPLICATED)
(ALL) NOPASSWD: /usr/bin/cp /tmp/hermes-htpasswd /etc/nginx/.hermes-htpasswd   # htpasswd deploy
(root) NOPASSWD: /usr/bin/mintdrivers*                                 # Mint driver helpers
(root) NOPASSWD: /usr/lib/linuxmint/mintUpdate/dpkg_lock_check.sh     # Mint update helper
```

## Include files

| File | Size | Purpose |
|---|---|---|
| `/etc/sudoers.d/hermes` | 443 B | Main Hermes agent rules |
| `/etc/sudoers.d/hermes-apt-cleanup` | 70 B | Likely the duplicate apt rule |
| `/etc/sudoers.d/hermes-htpasswd` | 87 B | htpasswd deploy rule |
| `/etc/sudoers.d/0pwfeedback` | 20 B | Disable pwfeedback |
| `/etc/sudoers.d/mintdrivers` | 185 B | Mint driver helpers |
| `/etc/sudoers.d/mintupdate` | 206 B | Mint update helpers |

## Results

| Command | `sudo -n -l` (policy) | `sudo -n` (runtime) | Notes |
|---|---|---|---|
| `nginx -t` | ✅ Allowed | ✅ Works | Clean |
| `systemctl restart nginx` | ✅ Allowed | ✅ Works | |
| `systemctl restart docker` | ✅ Allowed | ✅ Works | |
| `apt clean` | ✅ Allowed | ✅ Works | NOPASSWD confirmed via auth.log |
| `apt autoremove` | ✅ Allowed | ❌ Password req | **Unresolved** — policy says allowed but execution requires password |
| `systemctl status nginx` | ❌ Not listed | ❌ Fails | `status` not in allowed verbs |
| `apt-get clean` | ❌ Not listed | ❌ Fails | Rule is for `/usr/bin/apt`, not `apt-get` |

## Key discoveries

1. **Mint `apt` wrapper**: `/usr/local/bin/apt` is a Python script that shadows `/usr/bin/apt`. When run as non-root, it prepends `sudo` to the command internally — creating a recursive sudo call that may interact oddly with NOPASSWD rules.

2. **`apt autoremove` mystery**: Despite the NOPASSWD rule parsing correctly (`sudo -n -l` exit 0), execution fails with "a password is required". `apt clean` from the same rule works fine. Auth.log confirms clean uses NOPASSWD (session opened/closed logged without "password required") while autoremove hits the password gate. Root cause not determined — possible file syntax issue in the 70B `hermes-apt-cleanup` file.

3. **Duplicate apt rule**: Appears twice in `sudo -n -l` output, likely from both `hermes` and `hermes-apt-cleanup` files. If one has a syntax error, the broken entry might parse for `-l` display but fail to apply the NOPASSWD tag at runtime for certain subcommands.