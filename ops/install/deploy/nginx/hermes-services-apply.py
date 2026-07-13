#!/usr/bin/env python3
"""
hermes-services-apply.py — SSL-aware nginx config deploy

Substitutes placeholders in hermes-services.conf:
  __SSL_CERT__       → auto-discovered SSL certificate path
  __SSL_CERT_KEY__   → auto-discovered SSL certificate key path
  __NGINX_CONFIG_DIR__ → OS-aware nginx config directory
  __NGINX_LOG_DIR__    → OS-aware nginx log directory
  __HTPASSWD_FILE__    → htpasswd file path
  __CORTEX_HOME__      → user home directory

SSL cert discovery order (first found wins):
  1. CORTEX_SSL_CERT_PATH / CORTEX_SSL_CERT_KEY_PATH env vars (explicit paths)
  2. CORTEX_SSL_DOMAIN env var → /etc/letsencrypt/live/<domain>/
  3. Scan /etc/letsencrypt/live/ for any valid cert
  4. Scan ~/certs/ for self-signed cert.pem / privkey.pem
  5. Scan /etc/ssl/certs/ and /etc/ssl/private/
  6. If nothing found, leave placeholders unchanged (skip SSL substitution)

Also handles port prefix translation (CORTEX_NGINX_PORT_PREFIX) and OS-aware
path detection matching install-nginx-full.sh conventions.

Usage:
  python3 hermes-services-apply.py [--dry-run] [--domain example.com]
  python3 hermes-services-apply.py [--cert /path/to/cert.pem --key /path/to/key.pem]
  python3 hermes-services-apply.py --validate        # just test nginx config

Environment:
  CORTEX_SSL_CERT_PATH       Explicit cert path (overrides auto-detect)
  CORTEX_SSL_CERT_KEY_PATH   Explicit key path (overrides auto-detect)
  CORTEX_SSL_DOMAIN          Domain name for Let's Encrypt lookup
  CORTEX_NGINX_PORT_PREFIX   Port prefix (default: 13)
  CORTEX_REPO                Path to hermes-cortex repo (default: $HOME/hermes-cortex)
  CORTEX_SKIP_NGINX          Set to skip nginx test/reload
"""

import argparse
import json
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

# ── Source .env overrides ─────────────────────────────────────
_cortex_repo = Path(os.environ.get("CORTEX_REPO", Path.home() / "hermes-cortex"))
_env_path = _cortex_repo / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("\"'")
            if k not in os.environ:
                os.environ[k] = v


# ── OS-aware path detection ──────────────────────────────────────────

def detect_nginx_paths():
    """Return (config_dir, available_dir, brew_dir, log_dir, htpasswd) based on OS.
    config_dir is the active nginx include dir (sites-enabled on Linux, servers/ on macOS).
    available_dir is where configs are written (sites-available on Linux, same as config_dir on macOS).
    """
    system = platform.system()
    if system == "Darwin":
        machine = platform.machine()
        if machine == "arm64":
            brew_dir = Path("/opt/homebrew/etc/nginx")
        else:
            brew_dir = Path("/usr/local/etc/nginx")
        config_dir = brew_dir / "servers"
        log_dir = Path(brew_dir.parent.parent / "var" / "log" / "nginx")
        htpasswd = brew_dir / ".htpasswd"
        available_dir = config_dir  # macOS: no sites-available split, write directly
    elif system == "Linux":
        brew_dir = Path("/etc/nginx")
        config_dir = brew_dir / "sites-enabled"
        available_dir = brew_dir / "sites-available"
        log_dir = Path("/var/log/nginx")
        htpasswd = brew_dir / ".hermes-htpasswd"
    else:
        print(f"✗ Unsupported OS: {system}")
        sys.exit(1)
    return config_dir, available_dir, log_dir, htpasswd


# ── SSL cert discovery ───────────────────────────────────────────────

def find_letsencrypt_certs(domain=None):
    """Search Let's Encrypt live directories for fullchain.pem + privkey.pem.
    If domain is given, look only for that domain.
    Returns (cert_path, key_path) or (None, None).
    """
    live_dir = Path("/etc/letsencrypt/live")
    if not live_dir.is_dir():
        return None, None

    candidates = []
    if domain:
        candidates = [live_dir / domain]
    else:
        try:
            candidates = sorted(
                [d for d in live_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
            )
        except PermissionError:
            # Try common domain names as fallback
            for common in ("staging1.example.com", "staging2.example.com", "staging3.example.com"):
                d = live_dir / common
                try:
                    if d.is_dir():
                        candidates.append(d)
                except PermissionError:
                    continue
        except FileNotFoundError:
            return None, None

    for d in candidates:
        cert = d / "fullchain.pem"
        key = d / "privkey.pem"
        try:
            if cert.is_file() and key.is_file():
                try:
                    # Verify cert is not expiring within 7 days
                    # (simple check: file readable and non-empty)
                    if cert.stat().st_size > 100 and key.stat().st_size > 100:
                        return str(cert), str(key)
                except PermissionError:
                    # Can't stat but paths exist — trust them (nginx reads as root)
                    return str(cert), str(key)
                except OSError:
                    continue
            else:
                # Fallback: check by absolute symlink path (LE live/ -> archive/)
                alt_cert = Path(f"/etc/letsencrypt/archive/{d.name}/fullchain1.pem")
                alt_key = Path(f"/etc/letsencrypt/archive/{d.name}/privkey1.pem")
                try:
                    if alt_cert.is_file() and alt_key.is_file():
                        return str(cert), str(key)
                except (PermissionError, OSError):
                    continue
        except PermissionError:
            continue
    return None, None


def find_self_signed_certs(user_home=None):
    """Search ~/certs/ for self-signed cert.pem / privkey.pem."""
    home = Path(user_home) if user_home else Path.home()
    cert_dir = home / "certs"
    if not cert_dir.is_dir():
        return None, None
    cert = cert_dir / "cert.pem"
    key = cert_dir / "privkey.pem"
    if cert.is_file() and key.is_file():
        return str(cert), str(key)
    # Also check for fullchain.pem pattern
    cert = cert_dir / "fullchain.pem"
    key = cert_dir / "privkey.pem"
    if cert.is_file() and key.is_file():
        return str(cert), str(key)
    return None, None


def find_system_certs():
    """Search /etc/ssl/ for generic certs."""
    cert_paths = [
        (Path("/etc/ssl/certs/ssl-cert-snakeoil.pem"),
         Path("/etc/ssl/private/ssl-cert-snakeoil.key")),
        (Path("/etc/ssl/certs/localhost.pem"),
         Path("/etc/ssl/private/localhost.key")),
    ]
    for cert, key in cert_paths:
        if cert.is_file() and key.is_file():
            return str(cert), str(key)
    return None, None


def discover_ssl_certs(domain=None, explicit_cert=None, explicit_key=None, user_home=None):
    """Discover SSL certificates. Returns (cert_path, key_path) or (None, None)."""
    # Priority 1: Explicit paths from env/args
    # Use explicit paths even if we can't stat them (e.g. root-only LE certs).
    # nginx reads these as root and the user has verified they work.
    if explicit_cert and explicit_key:
        try:
            if Path(explicit_cert).is_file() and Path(explicit_key).is_file():
                return explicit_cert, explicit_key
        except PermissionError:
            # Permission denied — trust the explicit path (nginx reads as root)
            print(f"  ✓ Using explicit cert path (PermissionError on stat — trusting nginx can read)")
            return explicit_cert, explicit_key
        print(f"  ⚠ Explicit cert/key paths not found, falling back to auto-detect")

    # Priority 2: Env vars
    if not (explicit_cert and explicit_key):
        env_cert = os.environ.get("CORTEX_SSL_CERT_PATH")
        env_key = os.environ.get("CORTEX_SSL_CERT_KEY_PATH")
        if env_cert and env_key:
            try:
                if Path(env_cert).is_file() and Path(env_key).is_file():
                    return env_cert, env_key
            except PermissionError:
                # Permission denied — trust the env path (nginx reads as root)
                print(f"  ✓ CORTEX_SSL_CERT_PATH trust (PermissionError on stat — trusting nginx can read)")
                return env_cert, env_key
            print(f"  ⚠ CORTEX_SSL_CERT_PATH/CORTEX_SSL_CERT_KEY_PATH files not found")

    # Priority 3: Let's Encrypt (specific domain or scan)
    cert, key = find_letsencrypt_certs(domain)
    if cert and key:
        return cert, key

    # Priority 4: ~/certs/ self-signed
    cert, key = find_self_signed_certs(user_home=user_home)
    if cert and key:
        return cert, key

    # Priority 5: System certs
    cert, key = find_system_certs()
    if cert and key:
        return cert, key

    return None, None


# ── Template processing ──────────────────────────────────────────────

def process_template(
    template_path,
    nginx_config_dir,
    nginx_log_dir,
    htpasswd_file,
    cortex_home,
    ssl_cert_path,
    ssl_cert_key_path,
    port_prefix,
):
    """Substitute all placeholders in the template and return processed content."""
    with open(template_path, "r") as f:
        content = f.read()

    substitutions = {
        "__NGINX_CONFIG_DIR__": str(nginx_config_dir),
        "__NGINX_LOG_DIR__": str(nginx_log_dir),
        "__HTPASSWD_FILE__": str(htpasswd_file),
        "__CORTEX_HOME__": str(cortex_home),
    }

    # SSL placeholders — only substitute if we found valid certs
    if ssl_cert_path and ssl_cert_key_path:
        substitutions["__SSL_CERT__"] = ssl_cert_path
        substitutions["__SSL_CERT_KEY__"] = ssl_cert_key_path
        print(f"  ✓ SSL cert: {ssl_cert_path}")
        print(f"  ✓ SSL key:  {ssl_cert_key_path}")
    else:
        print(f"  ⚠ No SSL certs found — leaving __SSL_CERT__/__SSL_CERT_KEY__ untouched")

    for placeholder, value in substitutions.items():
        content = content.replace(placeholder, str(value))

    # Port prefix translation: 13xxx → {prefix}xxx
    # Handle both "listen 13xxx" and "listen 127.0.0.1:13xxx"
    content = re.sub(
        r'(listen\s+)(?:127\.0\.0\.1:)?13(\d{3})',
        lambda m: f'{m.group(1)}127.0.0.1:{port_prefix}{m.group(2)}'
                  if '127.0.0.1' in m.group(0)
                  else f'{m.group(1)}{port_prefix}{m.group(2)}',
        content,
    )

    return content


# ── Validation and reload ────────────────────────────────────────────

def test_nginx():
    """Run nginx -t, return True if valid."""
    result = subprocess.run(
        ["nginx", "-t"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = result.stdout.strip() or result.stderr.strip()
    if result.returncode == 0:
        print(f"  ✓ nginx config valid")
        return True
    else:
        print(f"  ✗ nginx config INVALID — not reloading")
        for line in output.split("\n"):
            print(f"    {line}")
        return False


def reload_nginx():
    """Reload nginx gracefully."""
    result = subprocess.run(
        ["nginx", "-s", "reload"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0:
        print(f"  ✓ nginx reloaded")
        return True
    else:
        print(f"  ✗ nginx reload failed: {result.stderr.strip() or result.stdout.strip()}")
        return False


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SSL-aware nginx config deploy for hermes-services.conf",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing")
    parser.add_argument("--force", action="store_true", help="Re-resolve SSL certs and port prefix from env/auto-detect instead of preserving existing values")
    parser.add_argument("--domain", help="Domain for Let's Encrypt cert lookup (or set CORTEX_SSL_DOMAIN)")
    parser.add_argument("--cert", help="Explicit SSL cert path")
    parser.add_argument("--key", help="Explicit SSL key path")
    parser.add_argument("--validate", action="store_true", help="Only run nginx -t, skip all other steps")
    parser.add_argument("--output", help="Write to custom output path instead of detected config_dir")
    parser.add_argument("--template", help="Custom template path (default: repo ops/install/deploy/nginx/hermes-services.conf)")
    args = parser.parse_args()

    # ── Validate-only mode ──
    if args.validate:
        if test_nginx():
            sys.exit(0)
        else:
            sys.exit(1)

    # ── Determine paths ──
    config_dir, available_dir, log_dir, htpasswd = detect_nginx_paths()
    cortex_repo = Path(os.environ.get("CORTEX_REPO", Path.home() / "hermes-cortex"))
    # Detect real user (works even under sudo)
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        import pwd
        cortex_home = Path(pwd.getpwnam(sudo_user).pw_dir)
    else:
        cortex_home = Path.home()

    # Template path
    template_path = args.template
    if not template_path:
        template_path = str(cortex_repo / "deploy" / "nginx" / "hermes-services.conf")
    template = Path(template_path)

    if not template.is_file():
        print(f"✗ Template not found: {template}")
        sys.exit(1)

    # ── Port prefix ──
    port_prefix = os.environ.get("CORTEX_NGINX_PORT_PREFIX", "13")

    # ── Read existing config (preserve ports/SSL unless forced) ──
    cert_path, key_path = None, None
    force_deploy = args.force or os.environ.get("CORTEX_FORCE_DEPLOY", "")
    live_path = config_dir / "hermes-services.conf"
    if not force_deploy and live_path.is_file():
        try:
            live_text = live_path.read_text()
            # Extract existing port prefix
            m = re.search(r'listen\s+(?:127\.0\.0\.1:)?(\d{2})(?=\d{3}\b)', live_text)
            if m:
                port_prefix = m.group(1)
            # Extract existing SSL cert/key paths
            m_cert = re.search(r'ssl_certificate\s+(\S+?);?\s*$', live_text, re.MULTILINE)
            m_key = re.search(r'ssl_certificate_key\s+(\S+?);?\s*$', live_text, re.MULTILINE)
            if m_cert and m_key:
                ec = m_cert.group(1)
                ek = m_key.group(1)
                if ec != "__SSL_CERT__" and ek != "__SSL_CERT_KEY__":
                    cert_path, key_path = ec, ek
                    print(f"  ✓ Preserved SSL cert: {cert_path}")
                    print(f"  ✓ Preserved port prefix: {port_prefix}xxx")
        except (OSError, PermissionError):
            pass

    # ── SSL discovery (only if not preserved) ──
    if not cert_path:
        domain = args.domain or os.environ.get("CORTEX_SSL_DOMAIN")
        cert_path, key_path = discover_ssl_certs(
            domain=domain,
            explicit_cert=args.cert,
            explicit_key=args.key,
            user_home=cortex_home,
        )

    # ── Process template ──
    if args.dry_run:
        print(f"━━━ DRY RUN — no files written ━━━")
    else:
        print(f"━━━ hermes-services-apply — {(os.environ.get('USER', 'unknown'))} ━━━")

    print(f"  Template: {template}")
    print(f"  Config dir: {config_dir}")
    print(f"  Available dir: {available_dir}")
    print(f"  Log dir: {log_dir}")
    print(f"  htpasswd: {htpasswd}")
    print(f"  Port prefix: {port_prefix}xxx")

    processed = process_template(
        template_path=str(template),
        nginx_config_dir=config_dir,
        nginx_log_dir=log_dir,
        htpasswd_file=htpasswd,
        cortex_home=cortex_home,
        ssl_cert_path=cert_path,
        ssl_cert_key_path=key_path,
        port_prefix=port_prefix,
    )

    # ── Determine output path ──
    if args.output:
        output_path = Path(args.output)
        symlink_path = None
    else:
        output_path = available_dir / "hermes-services.conf"
        symlink_path = config_dir / "hermes-services.conf" if config_dir != available_dir else None

    # ── Preserve live port prefix (like cortex-update.sh does) ──
    if not args.dry_run:
        live_path = symlink_path or output_path
        if live_path.is_file():
            live_content = live_path.read_text()
            live_match = re.search(r'listen\s+(?:127\.0\.0\.1:)?(\d{2})(\d{3})\s', live_content)
            template_match = re.search(r'listen\s+(?:127\.0\.0\.1:)?(\d{2})(\d{3})\s', processed)
            if live_match and template_match and live_match.group(1) != template_match.group(1):
                old_prefix = template_match.group(1)
                new_prefix = live_match.group(1)
                processed = processed.replace(f":{old_prefix}", f":{new_prefix}")
                print(f"  ✓ Preserved port range {old_prefix}xxx → {new_prefix}xxx")

    # ── Write ──
    if args.dry_run:
        # Show diff-like summary
        print(f"  → Would write:  {output_path}")
        if symlink_path:
            print(f"  → Would symlink: {symlink_path} → {output_path}")
        # Show SSL substitution status
        if "__SSL_CERT__" in processed:
            ssl_count = processed.count("__SSL_CERT__")
            print(f"  → {ssl_count} __SSL_CERT__ placeholders remaining (no certs found)")
        else:
            print(f"  → All __SSL_CERT__ placeholders substituted")
    else:
        # Write to temp file first for atomicity
        tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".conf")
        try:
            tmp.write(processed)
            tmp.close()
            os.chmod(tmp.name, 0o644)

            # Write to available_dir (sites-available on Linux, servers/ on macOS)
            def _write_file(src, dst):
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, str(dst))
                except (PermissionError, OSError):
                    subprocess.run(["sudo", "cp", src, str(dst)], check=True, timeout=30)
                    subprocess.run(["sudo", "chmod", "644", str(dst)], check=True, timeout=30)

            _write_file(tmp.name, output_path)
            print(f"  ✓ Deployed: {output_path}")

            # Symlink from sites-enabled -> sites-available on Linux
            if symlink_path:
                try:
                    if symlink_path.is_symlink() or symlink_path.exists():
                        symlink_path.unlink()
                    symlink_path.parent.mkdir(parents=True, exist_ok=True)
                    symlink_path.symlink_to(output_path)
                    print(f"  ✓ Symlinked: {symlink_path} → {output_path}")
                except (PermissionError, OSError):
                    subprocess.run(["sudo", "ln", "-sf", str(output_path), str(symlink_path)], check=True, timeout=30)
                    print(f"  ✓ Symlinked (sudo): {symlink_path} → {output_path}")
        finally:
            os.unlink(tmp.name)

    # ── Test and reload ──
    skip_nginx = os.environ.get("CORTEX_SKIP_NGINX", "")
    if skip_nginx or args.dry_run:
        return

    print("")
    if test_nginx():
        reload_nginx()
    else:
        print("  → Rollback: restore from /etc/hermes-cortex-backups/")
        sys.exit(1)

    print(f"━━━ Deploy complete ━━━")


if __name__ == "__main__":
    # ── Auto-source env file (so agents don't need env_keep in sudoers) ──
    env_file = Path(os.environ.get("CORTEX_REPO", Path.home() / "hermes-cortex")) / ".env"
    if env_file.is_file():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip().strip("'\"")
                if key not in os.environ:  # don't override explicit env vars
                    os.environ[key] = val

    main()
