---
language: shell
tags: [fail2ban, error, distutils, python312, remediation]
title: fail2ban exits 255 at boot: Backend 'systemd' failed to initialize due to No module named 'distutils'
description: fail2ban 1.0.2 filtersystemd.py imports distutils.version.LooseVersion; Python 3.12 removed distutils; broken python3-setuptools (setuptools.extern missing) prevents the _distutils_hack shim; jail creation fails -> server aborts exit 255. Fix: apt install --reinstall python3-setuptools (repair distutils shim) then systemctl start fail2ban; or set backend=polling for sshd jail (auth.log exists) to bypass filtersystemd.
source: learned
---

```shell
apt install --reinstall -y python3-setuptools && sudo systemctl start fail2ban && sudo fail2ban-client status
```
