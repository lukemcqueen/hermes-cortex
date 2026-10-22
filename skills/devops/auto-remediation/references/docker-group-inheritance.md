# Docker Group Inheritance — Session vs System

## Symptom

```
$ docker ps
permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
```

But:

```
$ groups $USER
esther : esther adm cdrom sudo docker
$ id $USER
uid=1000(esther) gid=1000(esther) groups=1000(esther),986(docker),...
```

The user IS in the `docker` group, yet the command fails.

## Root Cause

Supplementary GIDs from `/etc/group` are assigned at **login time**. If the user was added to the `docker` group after their current session started (e.g. via `usermod -aG docker` or a deploy script that modified `/etc/group`), the running shell and all its child processes — including cron jobs — inherit the original group set, not the updated one.

Cron daemons (both `cron` and `systemd --user` timers) read the user's groups at daemon start, not on every job. A cron job may run with stale groups until the daemon is restarted or the user re-logs in.

## Diagnosis

### Check current process groups
```bash
# Actual supplementary groups THIS shell has (not what /etc/group says)
groups
# Compare to:
id
```
If `docker` appears in `id` output but NOT in `groups` output, the session lacks the group.

### Check if sg wrapper works
```bash
sg docker -c "docker ps"
```
If this succeeds but `docker ps` alone fails, you have a group-inheritance problem.

### Check cron daemon groups
```bash
# For systemd timers:
cat /proc/$(pgrep -x systemd)/status | grep -i groups
# For traditional cron:
cat /proc/$(pgrep -x cron)/status | grep -i groups
```

## Fix Options

### Option A: Retry with sg in the script (recommended — fleet-first)

Modify the script's docker invocation to retry with `sg docker -c` when permission denied is detected. This is the most robust approach as it works regardless of how the script is launched.

Python pattern (from `langfuse-health-watchdog.py`):
```python
import shlex, subprocess

def run_cmd(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    # Retry docker cmds with sg if permission denied
    if r.returncode != 0 and "permission denied" in r.stderr.lower() and cmd[0] == "docker":
        sg_cmd = " ".join(shlex.quote(c) for c in cmd)
        r = subprocess.run(["sg", "docker", "-c", sg_cmd],
                           capture_output=True, text=True, timeout=10)
    return {"rc": r.returncode, "out": r.stdout.strip(), "err": r.stderr.strip()}
```

Shell pattern:
```bash
docker ps 2>/dev/null || sg docker -c "docker ps"
```

### Option B: Restart cron/systemd --user daemon
```bash
systemctl --user daemon-reexec  # re-reads supplementary groups
```
Only works for systemd user services, not traditional cron.

### Option C: Full logout/login
```bash
pkill -KILL -u $USER  # ends ALL processes — use with caution
```
Forces a full re-login, picking up the new group set. Only works for interactive sessions, not cron.

## Verification

```bash
# Test sg path directly
sg docker -c "docker ps -q" | wc -l

# Test that the fix actually works in cron context
python3 -c "
import shlex, subprocess
cmd = ['docker', 'ps', '--format', '{{.Names}}']
r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
if r.returncode != 0 and 'permission denied' in r.stderr.lower():
    sg_cmd = ' '.join(shlex.quote(c) for c in cmd)
    r = subprocess.run(['sg', 'docker', '-c', sg_cmd],
                       capture_output=True, text=True, timeout=5)
assert r.returncode == 0, f'fix failed: {r.stderr}'
print(f'{len(r.stdout.splitlines())} containers accessible')
"
```

## Related

- The `langfuse-health-watchdog.py` fix: commit `814dfb2` in `hermes-cortex`
- Auto-remediation skill's fix table has a row for this pattern
