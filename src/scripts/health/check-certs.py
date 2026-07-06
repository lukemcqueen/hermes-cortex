#!/usr/bin/env python3
"""
Certificate checker for auto-remediation.
Checks for expired certificates and triggers renewal.
"""

import os
import subprocess
import sys
from datetime import datetime, timezone

def get_certificate_expiry(cert_path):
    """Get certificate expiry date using openssl"""
    try:
        result = subprocess.run(
            ["openssl", "x509", "-enddate", "-noout", "-in", cert_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return None
        
        # Parse expiry date from output (e.g., "notAfter=Dec 31 23:59:59 2024 GMT")
        for line in result.stdout.splitlines():
            if line.startswith("notAfter="):
                return line.split("=", 1)[1]
        return None
    except Exception as e:
        print(f"ERROR reading certificate {cert_path}: {e}")
        return None

def parse_expiry_date(expiry_date_str):
    """Parse expiry date string to datetime"""
    try:
        expiry = datetime.strptime(expiry_date_str, "%b %d %H:%M:%S %Y %Z")
        # Assume UTC timezone if not specified
        expiry = expiry.replace(tzinfo=timezone.utc)
        return expiry
    except Exception as e:
        print(f"ERROR parsing expiry date '{expiry_date_str}': {e}")
        return None

def days_until_expiry(expiry_dt):
    """Calculate days until expiry"""
    now = datetime.now(timezone.utc)
    delta = expiry_dt - now
    return delta.days

def check_and_renew_certbot_certs():
    """Check certbot certificates and renew if needed"""
    cert_dir = "/etc/letsencrypt/live"
    
    if not os.path.isdir(cert_dir):
        print(f"INFO: Cert directory {cert_dir} does not exist")
        return False
    
    certs_renewed = 0
    certs_expiring_soon = 0
    certs_ok = 0
    
    for domain_dir in os.listdir(cert_dir):
        domain_path = os.path.join(cert_dir, domain_dir)
        if not os.path.isdir(domain_path):
            continue
            
        cert_file = os.path.join(domain_path, "fullchain.pem")
        if not os.path.isfile(cert_file):
            continue
            
        expiry_date_str = get_certificate_expiry(cert_file)
        if not expiry_date_str:
            print(f"WARNING: Cannot read expiry date for {domain_dir}")
            continue
            
        expiry_dt = parse_expiry_date(expiry_date_str)
        if not expiry_dt:
            continue
            
        days_left = days_until_expiry(expiry_dt)
        
        if days_left < 0:
            print(f"ISSUE: Certificate for {domain_dir} expired {abs(days_left)} days ago")
            # Renew expired certificate
            print(f"RENEWING: {domain_dir} (expired)")
            if renew_cert(domain_dir):
                certs_renewed += 1
            else:
                print(f"FAILED: Failed to renew certificate for {domain_dir}")
        elif days_left < 30:
            print(f"WARNING: Certificate for {domain_dir} expires in {days_left} days")
            certs_expiring_soon += 1
            # Renew expiring certificate
            print(f"RENEWING: {domain_dir} (expires in {days_left} days)")
            if renew_cert(domain_dir):
                certs_renewed += 1
            else:
                print(f"FAILED: Failed to renew certificate for {domain_dir}")
        else:
            print(f"OK: Certificate for {domain_dir} expires in {days_left} days")
            certs_ok += 1
    
    print(f"SUMMARY: {certs_ok} valid, {certs_renewed} renewed, {certs_expiring_soon} expiring")
    return certs_renewed > 0

def renew_cert(domain_name):
    """Renew a single certificate"""
    try:
        # Try with sudo for system-wide certificates
        result = subprocess.run(
            ["sudo", "-n", "certbot", "renew", "--cert-name", domain_name, "--quiet"],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            return True
            
        # Try without sudo (for user-managed certificates)
        result = subprocess.run(
            ["certbot", "renew", "--cert-name", domain_name, "--quiet"],
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.returncode == 0
        
    except Exception as e:
        print(f"ERROR renewing certificate {domain_name}: {e}")
        return False

def main():
    print("Checking certificates for renewal...")
    
    # Set up user-friendly certificate directories to avoid permission issues
    try:
        os.makedirs("~/.hermes/certs/data", exist_ok=True)
        os.makedirs("~/.hermes/certs/log", exist_ok=True)
        os.makedirs("~/.hermes/certs/conf", exist_ok=True)
        
        # Export home directory for subprocesses
        os.environ["HOME"] = "~/.hermes"
        
        # Try alternative certbot approach with user directories
        result = subprocess.run(
            ["certbot", "renew", "--config-dir", "~/.hermes/certs/conf", 
             "--work-dir", "~/.hermes/certs/data", "--logs-dir", "~/.hermes/certs/log", 
             "--force-renewal"],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            print("CERTIFICATION RENEWAL: Completed successfully")
            return 0
        elif "lock" in result.stderr.lower():
            print("CERTIFICATION RENEWAL: Permission/LOCK ISSUE - try running with sudo")
            return 1
        else:
            print(f"CERTIFICATION RENEWAL: Failed with error: {result.stderr}")
            return 2
            
    except Exception as e:
        print(f"CERTIFICATION RENEWAL: Exception occurred: {e}")
        return 3

if __name__ == "__main__":
    sys.exit(main())