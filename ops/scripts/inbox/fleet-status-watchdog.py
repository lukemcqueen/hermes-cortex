#!/usr/bin/env python3
"""fleet-status-watchdog.py — silent unless something changes."""

import json, subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone

HOME = Path.home()
STATE_FILE = HOME / ".hermes" / "state" / "fleet-status.state"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
KST = timedelta(hours=9)
AGENTS = ["moses", "esther", "joseph", "gisu", "kustos", "titus"]
STALL_MIN = 5

def psql(q):
    r = subprocess.run(["docker","exec","gbrain-postgres","psql","-U","gbrain","-d","gbrain","-t","-c",q],
                       capture_output=True, text=True, timeout=10)
    return r.stdout if r.returncode == 0 else ""

def utc_kst(s):
    try: return (datetime.strptime(s[:19],'%Y-%m-%d %H:%M:%S')+KST).strftime('%H:%M:%S')
    except: return s[11:16]

def icon_for_seconds(s):
    if s < 120:   return "✅"  # ✅ active
    elif s < 600: return "⚠️"  # ⚠️ idle
    else:         return "🌙"  # 🌙 offline

def main():
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    agent_sigs = {}
    for a in AGENTS:
        last = psql(f"""SELECT created_at::timestamp from bus.audit_log
            WHERE agent_name='{a}' ORDER BY created_at DESC LIMIT 1;""").strip()
        if not last: agent_sigs[a] = "❓"; continue  # ❓
        last = last.split(".")[0]
        try:
            dt = datetime.strptime(last, '%Y-%m-%d %H:%M:%S')
            agent_sigs[a] = icon_for_seconds((now-dt).total_seconds())
        except:
            agent_sigs[a] = "✅"

    labels = {"✅":"active","⚠️":"idle  ","🌙":"offline","❓":"never "}
    def label_for(i): return labels.get(i, i)

    wf = psql("""SELECT name,state,id::text,created_at::timestamp::text FROM bus.agent_workflows
        WHERE state='running' AND created_at > NOW() - INTERVAL '1 hour'
        ORDER BY created_at DESC LIMIT 5;""").strip()
    wf_count = len([w for w in wf.split('\n') if w.strip()]) if wf else 0

    stalled = []
    if wf:
        for w in [x.strip() for x in wf.split('\n') if x.strip()]:
            p = [v.strip() for v in w.split('|')]
            if len(p)<4: continue
            steps = psql(f"""SELECT step_name,assigned_to,state,started_at::timestamp::text
                FROM bus.agent_workflow_steps WHERE workflow_id='{p[2]}'
                ORDER BY step_order;""").strip()
            for s in [x.strip() for x in steps.split('\n') if x.strip()]:
                sp = [v.strip() for v in s.split('|')]
                if len(sp)<4: continue
                sn, who, st, started = sp[0][:20], sp[1], sp[2], sp[3][:19]
                if st == 'running' and started:
                    try:
                        sd = datetime.strptime(started, '%Y-%m-%d %H:%M:%S')
                        if (now-sd).total_seconds() > STALL_MIN*60: stalled.append(f'{who}@{sn}')
                    except: pass

    inbox = psql("""SELECT queue_name,count(*) FROM bus.messages
        WHERE queue_name LIKE 'inbox_%' AND state='pending'
        GROUP BY queue_name ORDER BY 1;""").strip()
    inbox_pend = []
    if inbox:
        for i in [x.strip() for x in inbox.split('\n') if x.strip()]:
            p = [v.strip() for v in i.split('|') if v.strip()]
            if len(p)>=2: inbox_pend.append(f'{p[0][6:]}:{p[1]}')

    sig = json.dumps({"a":agent_sigs,"wf":wf_count,"s":stalled,"i":inbox_pend}, sort_keys=True)
    prev = STATE_FILE.read_text().strip() if STATE_FILE.exists() else ""
    if sig == prev: return
    STATE_FILE.write_text(sig)

    now_kst = (now+KST).strftime('%H:%M')
    lines = [f'┌─ Fleet @ {now_kst} KST ──────────────────────────────', '│']

    for a in AGENTS:
        ic = agent_sigs[a]
        lb = label_for(agent_sigs[a])
        last = psql(f"""SELECT created_at::timestamp from bus.audit_log
            WHERE agent_name='{a}' ORDER BY created_at DESC LIMIT 1;""").strip()
        last = last.split('.')[0] if last else ''
        t = utc_kst(last) if last else ''
        lines.append(f'│ {a:<8} {ic} {lb} (last: {t})')

    lines.append('│')
    if wf:
        lines.append('│ Active workflows:')
        for w in [x.strip() for x in wf.split('\n') if x.strip()]:
            p = [v.strip() for v in w.split('|')]
            if len(p)<4: continue
            wf_name = p[0][:25]
            steps = psql(f"""SELECT step_name,assigned_to,state,started_at::timestamp::text
                FROM bus.agent_workflow_steps WHERE workflow_id='{p[2]}'
                ORDER BY step_order;""").strip()
            chain = []
            for s in [x.strip() for x in steps.split('\n') if x.strip()]:
                sp = [v.strip() for v in s.split('|')]
                if len(sp)<3: continue
                who, st = sp[1], sp[2]
                ic = {'completed':"✅",'running':"▶",'pending':"⏳"}.get(st,"⏳")
                chain.append(f'{who}{ic}')
            lines.append(f'│  {wf_name} {"→".join(chain)}')

    if stalled: lines.append(f'│ ⚠️ Stalled: {", ".join(stalled)}')
    if inbox_pend: lines.append(f'│ 📬 Pending: {", ".join(inbox_pend)}')
    lines.append('└' + '─'*46)
    print('\n'.join(lines))

if __name__ == '__main__':
    main()
