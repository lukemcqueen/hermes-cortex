---
language: shell
tags: [permissions, ownership, chmod, chown, umask, setuid, setgid, stickybit, acls]
title: File Permissions & Ownership
description: Practical file and directory permission management — chmod, chown, umask, SUID/SGID, sticky bit, and ACLs
source: pattern
---

```bash
# ── 1. Basic ownership ──
chown user:group file.txt              # Set user and group
chown -R user:group /path/to/dir       # Recursive
chown --reference=ref.txt target.txt   # Copy ownership from ref.txt

# ── 2. Symbolic permissions ──
chmod u+x script.sh                    # Add execute for owner
chmod g-w file.txt                     # Remove write for group
chmod o=r file.txt                     # Set others to read-only
chmod a+rx /usr/local/bin/app          # Add read+execute for all
chmod u=rwx,g=rx,o= /srv/app           # owner rwx, group rx, others nothing

# ── 3. Numeric (octal) permissions ──
chmod 755 script.sh                    # rwxr-xr-x — typical executable
chmod 644 config.yml                   # rw-r--r-- — typical file
chmod 600 ~/.ssh/id_ed25519            # rw------- — private key
chmod 700 ~/.ssh                       # rwx------ — ssh directory
chmod 444 /etc/nginx/nginx.conf        # r--r--r-- — read-only config review
chmod 000 /path/to/private.key         # No access for anyone (root can still read)

# ── 4. Recursive with find (apply to files vs dirs separately) ──
find /srv/www -type f -exec chmod 644 {} +    # Files: rw-r--r--
find /srv/www -type d -exec chmod 755 {} +    # Dirs:  rwxr-xr-x

# ── 5. umask (default permission mask) ──
umask 0022    # Default files: 644, dirs: 755 (most common)
umask 0027    # Default files: 640, dirs: 750 (tighter)
umask 0077    # Default files: 600, dirs: 700 (private only)
# Set system-wide in /etc/profile or /etc/bash.bashrc:
echo "umask 0027" >> /etc/profile

# ── 6. SUID / SGID / Sticky Bit ──
chmod u+s /usr/bin/passwd              # SUID — runs as owner (root)
chmod g+s /srv/shared                  # SGID — new files inherit group
chmod +t /tmp                          # Sticky — only owners can delete files

# Numeric equivalents (prefix):
# 4xxx = SUID      chmod 4755 /usr/bin/app
# 2xxx = SGID      chmod 2755 /srv/shared
# 1xxx = Sticky    chmod 1777 /tmp
chmod 4775 /usr/local/bin/helper       # SUID + rwxrwsr-x
chmod 2770 /srv/team-project           # SGID + rwxrwx---
chmod 1777 /var/tmp                    # Sticky + rwxrwxrwt

# Find all SUID/SGID binaries (potential security risk):
find / -perm -4000 -type f 2>/dev/null # SUID files
find / -perm -2000 -type f 2>/dev/null # SGID files

# ── 7. Access Control Lists (ACLs) ──
# Install: apt install acl
# Mount with acl option: mount -o acl /dev/sda1 /mnt

setfacl -m u:alice:rwx file.txt        # Give alice rwx
setfacl -m g:devs:rx file.txt          # Give devs group rx
setfacl -m o::- file.txt               # Remove others' access
setfacl -m m::rx file.txt              # Set mask (max permissions ACLs can grant)
setfacl -R -m u:bob:rx /srv/project    # Recursive for bob
setfacl -x u:alice file.txt            # Remove alice's ACL entry
getfacl file.txt                       # View ACLs

# Default ACLs — new files/dirs inherit these:
setfacl -d -m g:www-data:rx /srv/www   # All new content gets www-data group rx
getfacl /srv/www                       # Verify default ACLs shown

# ── 8. Verify and audit ──
ls -la                                   # View permissions + ACL indicator (+)
stat -c "%a %A %U:%G %n" file.txt        # Octal + symbolic + owner:group
namei -l /var/www/html/index.html        # Trace path permissions
```