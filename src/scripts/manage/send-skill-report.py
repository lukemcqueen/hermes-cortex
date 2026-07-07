#!/usr/bin/env python3
import json,os,urllib.request,urllib.parse,base64,datetime,subprocess
from pathlib import Path
C=Path.home()/".hermes"/"hermes-inbox.conf"
M=Path.home()/".hermes-cortex"/"state"/"skills-manifest.json"
if C.exists():
 for l in open(C):
  l=l.strip()
  if l and not l.startswith("#") and "=" in l:
   k,v=l.split("=",1)
   os.environ[k]=v.strip(chr(39)+chr(34))
U=os.environ.get("CORTEX_INBOX_URL")
A=os.environ.get("CORTEX_INBOX_AUTH")
if not U or not A:exit(0)
subprocess.run(["python3","/tmp/rebuild-manifest.py"],capture_output=True)
if not M.exists():exit(0)
m=json.load(open(M));n=m.get("custom_skills",0)
if n==0:exit(0)
h=os.uname().nodename;t=datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
sk=m.get("total_skills","?")
L=[f"--- Skill Report {h} ---",f"Generated: {t}",f"Total: {sk}",f"Custom: {n}",""]
for s in m.get("skills",[]):
 nm=s.get("name","?")
 c=s.get("category","")
 sm=s.get("summary","")[:200]
 L.append(f"* {nm}"+(f" ({c})" if c else "")+f": {sm}")
body="\n".join(L)+"\n"
d=urllib.parse.urlencode({"from":h,"topic":"reports","subject":"Skill Report: "+str(n)+" custom","priority":"normal","body":body}).encode()
rq=urllib.request.Request(U,data=d)
rq.add_header("Authorization","Basic "+base64.b64encode(A.encode()).decode())
rq.add_header("Content-Type","application/x-www-form-urlencoded")
try:
 r=urllib.request.urlopen(rq,timeout=30);print("Sent "+str(n)+" custom skills",flush=True)
except Exception as e:print("ERR: "+str(e),flush=True);exit(1)
