# Agent Install & Fix Prompt

Give this to each fleet agent (Gisu, Kustos, Joseph, Titus).

---

Task: Pull latest, force-update, run doctor, fix issues, report back

1. Pull latest from main branch:
```
cd ~/hermes-cortex && git pull --rebase origin main
```

2. Force-update all scripts and services:
```
bash ops/scripts/cortex-update.sh --force-all
```

3. Run the doctor and inspect ALL warnings:
```
python3 ops/scripts/manage/cortex-doctor.py
```

Fix every ⚠️ and ❌, then re-run until clean. Common fixes:
- `git pull --rebase origin main` if behind
- `bash ops/scripts/manage/symlink-audit.sh` for broken symlinks
- Target: ✅ Overall: HEALTHY with 0 warn · 0 fail

4. Verify the bus is reachable:
```
python3 -c "from lib.cortex_bus import bus_send, bus_read, bus_archive; print('OK')"
```

5. Send UPDATE_RESULT confirming completion:
```python
import json, os, sys
sys.path.insert(0, os.path.expanduser('~/hermes-cortex/ops/scripts/lib'))
from cortex_bus import bus_send

result = {
    'from': '<YOUR_AGENT_NAME>',
    'to': 'moses',
    'topic': 'fleet-update',
    'subject': 'UPDATE_RESULT',
    'correlation_id': '<MATCH THE CID FROM YOUR UPDATE_REQUEST>',
    'body': {
        'success': True,
        'git_sha_before': '<SHA BEFORE>',
        'git_sha_after': '<SHA AFTER>',
        'doctor_summary': '<ANY DOCTOR ISSUES FOUND>'
    }
}
bus_send('inbox_moses', result)
```

Critical: The inner body field must be a native dict, NOT json.dumps()'d — this avoids the double-encoding crash that's been blocking them.
