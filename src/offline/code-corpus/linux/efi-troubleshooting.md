---
language: shell
tags: [linux, boot, efi, uefi, troubleshooting, recovery]
title: Linux EFI/UEFI Troubleshooting
description: Diagnosing and repairing EFI boot issues — efibootmgr, boot-repair, ESP recovery, secure boot.
source: pattern
---

```bash
# ── Check EFI boot entries ──
efibootmgr -v                    # list all boot entries
efibootmgr                       # compact list (BootCurrent, BootOrder, BootXXXX)
efibootmgr -o 0001,0002,0003     # set boot order

# ── Create / delete EFI entries ──
efibootmgr -c -d /dev/nvme0n1 -p 1 \
  -L "Linux Mint" -l \\EFI\\ubuntu\\shimx64.efi    # add entry
efibootmgr -b 0004 -B                                 # delete entry 0004

# ── Mount & inspect ESP (EFI System Partition) ──
lsblk -f                          # find the ESP (usually vfat, ~100-500MB)
sudo mkdir -p /mnt/esp
sudo mount /dev/nvme0n1p1 /mnt/esp     # adjust device
ls -la /mnt/esp/EFI/                   # contents: ubuntu, Boot, Microsoft, etc.

# ── Repair with boot-repair ──
sudo add-apt-repository ppa:yannubuntu/boot-repair
sudo apt update && sudo apt install boot-repair
sudo boot-repair                     # GUI tool — "Recommended repair"

# ── Manual reinstall GRUB to ESP ──
sudo mount /dev/nvme0n1p1 /mnt/esp          # mount ESP
sudo grub-install --target=x86_64-efi \
  --efi-directory=/mnt/esp --bootloader-id=GRUB --recheck
sudo update-grub

# ── Secure Boot ──
mokutil --sb-state                  # check if Secure Boot is enabled
sudo apt install shim-signed        # install Shim for Secure Boot
sudo mokutil --disable-validation   # disable module validation (for DKMS)

# ── Kernel panic / boot hang ──
# At GRUB prompt, press 'e' and add to linux line:
#   nomodeset                        # fix GPU-related hangs
#   acpi=off                         # fix ACPI-related hangs
#   single                           # boot to single-user (recovery) mode
```
