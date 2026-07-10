---
language: shell
tags: [linux, bootloader, grub, recovery, boot]
title: GRUB Bootloader — Configuration & Recovery
description: GRUB configuration, password protection, boot entry editing, recovery modes, and theme customization.
source: pattern
---

```bash
# ── GRUB config file ──
# /etc/default/grub — main config
# After editing, run: sudo update-grub

# Common settings:
# GRUB_TIMEOUT=5                   # seconds before auto-boot (set to -1 to wait forever)
# GRUB_TIMEOUT_STYLE=menu          # show menu (hidden = countdown without menu)
# GRUB_DEFAULT=saved               # remember last choice
# GRUB_CMDLINE_LINUX_DEFAULT="quiet splash nomodeset"  # kernel parameters
# GRUB_DISABLE_OS_PROBER=false     # detect other OS (Windows dual-boot)

# Apply changes
sudo update-grub                   # on Debian/Ubuntu/Mint
sudo grub2-mkconfig -o /boot/grub2/grub.cfg  # on RHEL/Fedora

# ── GRUB rescue shell ──
# If boot drops to "grub rescue>", manually boot:
# ls                               # list available drives/partitions
# ls (hd0,gpt1)                    # check filesystem
# set root=(hd0,gpt2)              # set root partition
# set prefix=(hd0,gpt2)/boot/grub
# insmod linux
# linux /vmlinuz root=/dev/nvme0n1p2
# initrd /initrd.img
# boot

# ── Reinstall GRUB from live USB ──
sudo mount /dev/nvme0n1p2 /mnt                     # root partition
sudo mount /dev/nvme0n1p1 /mnt/boot/efi            # ESP
sudo mount --bind /dev /mnt/dev
sudo mount --bind /proc /mnt/proc
sudo mount --bind /sys /mnt/sys
sudo chroot /mnt
grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=GRUB
update-grub
exit
sudo umount -R /mnt

# ── GRUB password protection ──
# /etc/grub.d/00_header (add before generating config):
# cat <<EOF
# set superusers="admin"
# password_pbkdf2 admin grub.pbkdf2.sha512.10000.xxxx...
# EOF
# Generate password hash: grub-mkpasswd-pbkdf2
```
