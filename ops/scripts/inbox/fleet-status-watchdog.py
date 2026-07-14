#!/usr/bin/env python3
"""fleet-status-watchdog.py — silent when idle, reports fleet health + stalled steps every 5min."""

import json, subprocess, sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

HOME = Path.home()
STATE_FILE = HOME / ".hermes" / "state" / "fleet-status.state"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
KST = timedelta(hours=9)
AGENTS = ["moses", "esther", "joseph", "gisu", "kustos", "titus"]
STALL_MIN = 5  # minutes before a running step is flagged as stalled


def psql(q):
    r = subprocess.run(["docker","exec","gbrain-postgres","psql","-U","gbrain","-d","gbrain","-t","-c",q],
                       capture_output=True, text=True, timeout=10)
    return r.stdout if r.returncode == 0 else ""


def utc_kst(s):
    try: return (datetime.strptime(s[:19],"%Y-%m-%d %H:%M:%S")+KST).strftime("%H:%M:%S")
    except: return s[11:16]


def main():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    now_kst = (now+KST).strftime("%H:%M")

    lines = [f"┌─ Fleet @ {now_kst} KST {'─'*28}", "│"]

    # Agent health
    any_issues = False
    for a in AGENTS:
        last = psql(f"""SELECT created_at::timestamp from bus.audit_log
            WHERE agent_name='{a}' ORDER BY created_at DESC LIMIT 1;""").strip()
        if not last:
            lines.append(f"│ {a:<8} ❓ never seen")
            any_issues = True
            continue
        last = last.split(".")[0]
        try:
            dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
            s = (now-dt).total_seconds()
            if s < 120:   icon = "✅ active"
            elif s < 600: icon = "⚠️ idle  "
            else:         icon = "🌙 offline"; any_issues = True
            lines.append(f"│ {a:<8} {icon} (last: {utc_kst(last)})")
        except:
            lines.append(f"│ {a:<8} ✅ (last: {utc_kst(last)})")

    lines.append("│")

    # Active workflows — check for stalls
    wf = psql("""SELECT name,state,id::text,created_at::timestamp::text FROM bus.agent_workflows
        WHERE state='running' AND created_at > NOW() - INTERVAL '1 hour'
        ORDER BY created_at DESC LIMIT 5;""").strip()
    stalled = []

    if wf:
        lines.append("│ Active workflows:")
        for w in [x.strip() for x in wf.split("\n") if x.strip()]:
            p = [v.strip() for v in w.split("|")]
            if len(p)<4: continue
            wf_name, wf_state, wf_id, wf_created = p[0], p[1], p[2][:8], p[3][:19]
            steps = psql(f"""SELECT step_name,assigned_to,state,started_at::timestamp::text
                FROM bus.agent_workflow_steps WHERE workflow_id='{p[2]}'
                ORDER BY step_order;""").strip()
            chain = []
            for s in [x.strip() for x in steps.split("\n") if x.strip()]:
                sp = [v.strip() for v in s.split("|")]
                if len(sp)<3: continue
                sn, who, st = sp[0][:20], sp[1], sp[2]
                started = sp[3][:19] if len(sp)>3 and sp[3] else ""
                ic = {"completed":"✅","running":"▶","pending":"⏳"}.get(st,"⏳")
                chain.append(f"{who}{ic}")
                # Stall detection: running > 5min
                if st == "running" and started:
                    try:
                        sd = datetime.strptime(started, "%Y-%m-%d %H:%M:%S")
                        if (now-sd).total_seconds() > STALL_MIN*60:
                            stalled.append(f"{who}@{sn}")
                    except: pass
            lines.append(f"│  {wf_name[:25]} {'→'.join(chain)}")

        if stalled:
            lines.append(f"│ ⚠️ Stalled: {', '.join(stalled)}")
            any_issues = True
    else:
        lines.append("│ No active workflows")

    # Pending inbox
    inbox = psql("""SELECT queue_name,count(*) FROM bus.messages
        WHERE queue_name LIKE 'inbox_%' AND state='pending'
        GROUP BY queue_name ORDER BY 1;""").strip()
    if inbox:
        pend = []
        for i in [x.strip() for x in inbox.split("\n") if x.strip()]:
            p = [v.strip() for v in i.split("|") if v.strip()]
            if len(p)>=2: pend.append(f"{p[0][6:]}:{p[1]}")
        if pend:
            lines.append(f"│ 📬 Pending: {', '.join(pend)}")

    lines.append("└"+"─"*46)
    out = "\n".join(lines)

    # Silent if no change AND no active workflows AND no issues
    prev = STATE_FILE.read_text().strip() if STATE_FILE.exists() else ""
    has_activity = bool(wf.strip()) or any_issues or inbox.strip()
    if not has_activity:
        STATE_FILE.write_text(out)
        return  # silent — nothing happening
    if out == prev:
        return  # silent — state unchanged

    STATE_FILE.write_text(out)
    print(out)


if __name__ == "__main__":
    main()
