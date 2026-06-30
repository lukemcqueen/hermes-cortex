#!/usr/bin/env python3
"""Generate correct blocked_ips.conf from blocked_ips.add source.

Usage:
  python3 deploy/nginx/fix-blocked-ips.py

Output: /tmp/blocked_ips.conf.new — proper deny <ip>; syntax.
Run this if blocked_ips.conf has bare IPs and nginx -t fails.

Then:
  sudo cp /tmp/blocked_ips.conf.new /etc/nginx/blocked_ips.conf      # Linux
  sudo cp /tmp/blocked_ips.conf.new /usr/local/etc/nginx/blocked_ips.conf  # macOS
  sudo /usr/local/sbin/hermes-security-apply

Install to ~/.hermes/scripts/ for agent use:
  cp deploy/nginx/fix-blocked-ips.py ~/.hermes/scripts/
"""
import os
import re
import sys
import platform

IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

def is_valid_ip(s):
    """Return True if s is a valid IPv4 address."""
    if not IPV4_RE.match(s):
        return False
    parts = [int(p) for p in s.split(".")]
    return all(0 <= p <= 255 for p in parts)


# Detect paths
is_linux = platform.system() == "Linux"
repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not repo_dir.endswith("hermes-cortex"):
    repo_dir = os.path.expanduser("~/hermes-cortex")

blocked_ips_add = os.path.join(repo_dir, "deploy", "nginx", "blocked_ips.add")
output_path = "/tmp/blocked_ips.conf.new"

# Detect nginx config dir for reference
nginx_conf_dir = "/etc/nginx" if is_linux else "/usr/local/etc/nginx"

if not os.path.exists(blocked_ips_add):
    print(f"✗ Source not found: {blocked_ips_add}")
    print(f"  Expected at {repo_dir}/deploy/nginx/blocked_ips.add")
    sys.exit(1)

# Preserve allow lines from current config
current_conf = os.path.join(nginx_conf_dir, "blocked_ips.conf")
allow_lines = []
if os.path.exists(current_conf):
    with open(current_conf) as f:
        for line in f:
            if line.startswith("allow "):
                allow_lines.append(line.rstrip())

# Read and validate IPs from source
ips = []
skipped = []
with open(blocked_ips_add) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if is_valid_ip(line):
            ips.append(line)
        else:
            skipped.append(line)

if skipped:
    print(f"⚠ Skipped {len(skipped)} invalid entries in blocked_ips.add")
    for s in skipped[:3]:
        print(f"   invalid: {s}")

# Write new config
output = list(allow_lines)
output.append("")
for ip in ips:
    output.append(f"deny {ip};")

content = "\n".join(output) + "\n"
with open(output_path, "w") as f:
    f.write(content)

print(f"✓ Generated: {len(ips)} blocked IPs (+ {len(allow_lines)} allow rules)")
print(f"  → {output_path}")
print(f"  → Install: sudo cp {output_path} {nginx_conf_dir}/blocked_ips.conf")