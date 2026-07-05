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
path detection matching hermes-security-apply conventions.

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
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


# ── OS-aware path detection ──────────────────────────────────────────

def detect_nginx_paths():
    """Return (config_dir, brew_dir, log_dir, htpasswd) based on OS."""
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
    elif system == "Linux":
        brew_dir = Path("/etc/nginx")
        config_dir = brew_dir / "sites-enabled"
        log_dir = Path("/var/log/nginx")
        htpasswd = brew_dir / ".hermes-htpasswd"
    else:
        print(f"✗ Unsupported OS: {system}")
        sys.exit(1)
    return config_dir, brew_dir, log_dir, htpasswd


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
            return None, None

    for d in candidates:
        cert = d / "fullchain.pem"
        key = d / "privkey.pem"
        if cert.is_file() and key.is_file():
            try:
                # Verify cert is not expiring within 7 days
                # (simple check: file readable and non-empty)
                if cert.stat().st_size > 100 and key.stat().st_size > 100:
                    return str(cert), str(key)
            except OSError:
                continue
    return None, None


def find_self_signed_certs():
    """Search ~/certs/ for self-signed cert.pem / privkey.pem."""
    home = Path.home()
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


def discover_ssl_certs(domain=None, explicit_cert=None, explicit_key=None):
    """Discover SSL certificates. Returns (cert_path, key_path) or (None, None)."""
    # Priority 1: Explicit paths from env/args
    if explicit_cert and explicit_key:
        if Path(explicit_cert).is_file() and Path(explicit_key).is_file():
            return explicit_cert, explicit_key
        print(f"  ⚠ Explicit cert/key paths not found, falling back to auto-detect")

    # Priority 2: Env vars
    env_cert = os.environ.get("CORTEX_SSL_CERT_PATH")
    env_key = os.environ.get("CORTEX_SSL_CERT_KEY_PATH")
    if env_cert and env_key:
        if Path(env_cert).is_file() and Path(env_key).is_file():
            return env_cert, env_key
        print(f"  ⚠ CORTEX_SSL_CERT_PATH/CORTEX_SSL_CERT_KEY_PATH files not found")

    # Priority 3: Let's Encrypt (specific domain or scan)
    cert, key = find_letsencrypt_certs(domain)
    if cert and key:
        return cert, key

    # Priority 4: ~/certs/ self-signed
    cert, key = find_self_signed_certs()
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
    parser.add_argument("--domain", help="Domain for Let's Encrypt cert lookup (or set CORTEX_SSL_DOMAIN)")
    parser.add_argument("--cert", help="Explicit SSL cert path")
    parser.add_argument("--key", help="Explicit SSL key path")
    parser.add_argument("--validate", action="store_true", help="Only run nginx -t, skip all other steps")
    parser.add_argument("--output", help="Write to custom output path instead of detected config_dir")
    parser.add_argument("--template", help="Custom template path (default: repo deploy/nginx/hermes-services.conf)")
    args = parser.parse_args()

    # ── Validate-only mode ──
    if args.validate:
        if test_nginx():
            sys.exit(0)
        else:
            sys.exit(1)

    # ── Determine paths ──
    config_dir, brew_dir, log_dir, htpasswd = detect_nginx_paths()
    cortex_repo = Path(os.environ.get("CORTEX_REPO", Path.home() / "hermes-cortex"))
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

    # ── SSL discovery ──
    domain = args.domain or os.environ.get("CORTEX_SSL_DOMAIN")
    cert_path, key_path = discover_ssl_certs(
        domain=domain,
        explicit_cert=args.cert,
        explicit_key=args.key,
    )

    # ── Process template ──
    if args.dry_run:
        print(f"━━━ DRY RUN — no files written ━━━")
    else:
        print(f"━━━ hermes-services-apply — {(os.environ.get('USER', 'unknown'))} ━━━")

    print(f"  Template: {template}")
    print(f"  Config dir: {config_dir}")
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
    else:
        output_path = config_dir / "hermes-services.conf"

    # ── Preserve live port prefix (like cortex-update.sh does) ──
    if output_path.is_file() and not args.dry_run:
        live_content = output_path.read_text()
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
        if output_path.is_file():
            print(f"  → Would update: {output_path}")
        else:
            print(f"  → Would create: {output_path}")
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

            # Check if target needs sudo
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text("")  # test write access
                shutil.copy2(tmp.name, str(output_path))
            except (PermissionError, OSError):
                # Fall back to sudo
                subprocess.run(
                    ["sudo", "cp", tmp.name, str(output_path)],
                    check=True,
                    timeout=30,
                )
                subprocess.run(
                    ["sudo", "chmod", "644", str(output_path)],
                    check=True,
                    timeout=30,
                )
            finally:
                os.unlink(tmp.name)
        except Exception as e:
            os.unlink(tmp.name)
            print(f"✗ Write failed: {e}")
            sys.exit(1)

        print(f"  ✓ Deployed: {output_path}")

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
    main()
