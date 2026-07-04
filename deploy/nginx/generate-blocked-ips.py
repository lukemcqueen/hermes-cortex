#!/usr/bin/env python3
"""Merge blocked_ips.add into blocked_ips.conf to generate new-blocked-ips.conf.

Also validates IPs to prevent garbage entries from fail2ban log parsing.
"""
import os
import re

IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

def is_valid_ip(s):
    """Return True if s is a valid, non-private IPv4 address."""
    if not IPV4_RE.match(s):
        return False
    parts = [int(p) for p in s.split(".")]
    if not all(0 <= p <= 255 for p in parts):
        return False
    # Skip private/reserved ranges
    if parts[0] == 10:
        return False
    if parts[0] == 127:
        return False
    if parts[0] == 0:
        return False
    if parts[0] == 172 and 16 <= parts[1] <= 31:
        return False
    if parts[0] == 192 and parts[1] == 168:
        return False
    return True


def main():
    # Read blocked_ips.add (the new IPs to add)
    add_path = os.path.join(os.path.dirname(__file__), "blocked_ips.add")
    with open(add_path) as f:
        raw = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    
    # Validate and filter IPs
    valid = [ip for ip in raw if is_valid_ip(ip)]
    invalid = [ip for ip in raw if not is_valid_ip(ip)]
    if invalid:
        print(f"⚠ Skipped {len(invalid)} invalid entries: {', '.join(invalid[:5])}{'...' if len(invalid) > 5 else ''}")

    # Read existing blocked_ips.conf (OS-aware path)
    conf_path = "/etc/nginx/blocked_ips.conf"
    if not os.path.exists(conf_path):
        conf_path = "/usr/local/etc/nginx/blocked_ips.conf"
    try:
        with open(conf_path) as f:
            existing_lines = f.readlines()
    except FileNotFoundError:
        existing_lines = []

    # Extract already-denied IPs from conf
    denied = set()
    for line in existing_lines:
        line = line.strip()
        if line.startswith("deny "):
            ip = line[5:].rstrip(";").strip()
            denied.add(ip)

    # Find new IPs not yet in conf
    new_ips = [ip for ip in valid if ip not in denied]

    if not new_ips:
        print("No new IPs to deploy")
        return

    # Generate full merged config: existing lines (but strip trailing deny lines),
    # then add new deny lines, then append existing comment lines and non-deny lines
    # Actually simpler: keep existing structure but append new deny statements before the comment block

    output_lines = []

    # Find where to insert new denies - before the # /storage/ section
    insertion_point = None
    for i, line in enumerate(existing_lines):
        if line.strip().startswith("# /storage/") or line.strip().startswith("# /storage"):
            insertion_point = i
            break

    if insertion_point is None:
        # Just append to end
        output_lines = existing_lines[:]
    else:
        # Insert new denies before the comment block
        output_lines = existing_lines[:insertion_point]

    # Add new IPs (sorted for cleanliness)
    for ip in sorted(new_ips):
        output_lines.append(f"deny {ip};\n")

    # Add the comment block + remaining lines
    if insertion_point is not None:
        output_lines.extend(existing_lines[insertion_point:])

    # Write output
    output_path = os.path.expanduser("~/.hermes/new-blocked-ips.conf")
    with open(output_path, "w") as f:
        f.writelines(output_lines)

    print(f"Generated {output_path} with {len(new_ips)} new blocked IPs")
    print(f"Total lines: {len(output_lines)}")

if __name__ == "__main__":
    main()