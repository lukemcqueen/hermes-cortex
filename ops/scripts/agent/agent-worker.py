#!/usr/bin/env python3
"""
Hermes Agent Worker — checks inbox via timeout-safe method.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
import logging
import base64
from pathlib import Path

# Agent identity — env → agent.env → .env. NEVER USER/hostname: a missing
# identity must fail loudly instead of acting under the OS account name
# (Luke directive 2026-08-14).
AGENT_NAME = os.environ.get("AGENT_NAME", "").strip()
if not AGENT_NAME:
    for _idf in (Path.home() / ".hermes-cortex" / "agent.env",
                 Path.home() / "hermes-cortex" / ".env"):
        try:
            if _idf.is_file():
                for _line in _idf.read_text().splitlines():
                    _line = _line.strip()
                    if _line.startswith("AGENT_NAME="):
                        _val = _line.split("=", 1)[1].strip().strip("\"'")
                        if _val:
                            AGENT_NAME = _val
                            break
        except OSError:
            continue
if not AGENT_NAME or AGENT_NAME == "unknown":
    print("❌ AGENT_NAME not configured — set AGENT_NAME= in "
          "~/.hermes-cortex/agent.env / ~/hermes-cortex/.env or export AGENT_NAME",
          file=sys.stderr)
    sys.exit(1)
BUS_URL = os.environ.get("BUS_URL") or os.environ.get("CORTEX_BUS_URL", "http://127.0.0.1:8903")
CORTEX_BASIC_AUTH = os.environ.get("CORTEX_BASIC_AUTH") or os.environ.get("CORTEX_BUS_AUTH") or os.environ.get("CORTEX_INBOX_AUTH", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
VT_SECONDS = int(os.environ.get("VT_SECONDS", "120"))

HOME = Path.home()
PENDING_DIR = HOME / ".hermes" / "state" / "worker-pending"
LOG_DIR = HOME / ".hermes" / "logs"
STATE_DIR = HOME / ".hermes" / "state" / "worker-completed"

HEADERS = {"Content-Type": "application/json", "X-Forwarded-User": AGENT_NAME}
if CORTEX_BASIC_AUTH:
    HEADERS["Authorization"] = f"Basic {base64.b64encode(CORTEX_BASIC_AUTH.encode()).decode()}"


def _request(method, path, data=None, timeout=30):
    url = f"{BUS_URL}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, method=method, headers=HEADERS, data=body)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        logging.error(f"HTTP {e.code} on {method} {path}")
        raise
    except urllib.error.URLError as e:
        logging.error(f"Bus unavailable: {e.reason}")
        raise


def read_inbox():
    """Read (peek with vt=0 — don't consume) messages. Non-workflow messages stay pending for handler."""
    return _request("POST", "/api/pgmq/read", {"queue": f"inbox_{AGENT_NAME}", "count": 5, "vt": 0})


def archive_message(msg_id):
    return _request("POST", "/api/pgmq/archive", {"queue": f"inbox_{AGENT_NAME}", "msg_id": msg_id})


def post_result(wf_id, step_id, status, result, error=None):
    msg = {"queue": "workflow_step_result", "message": {"workflow_id": wf_id, "step_id": step_id, "status": status, "result": result}}
    if error:
        msg["message"]["error"] = error
    return _request("POST", "/api/pgmq/send", msg)


def run_ollama(prompt):
    data = json.dumps({"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.1, "num_predict": 2000}})
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=data.encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode()
    parts = [json.loads(line) for line in raw.strip().split("\n") if line]
    return parts[-1].get("response", "") if parts else ""


def is_completed(step_id):
    return (STATE_DIR / f"{step_id}.done").exists()


def mark_completed(step_id, step_name):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / f"{step_id}.done").write_text(json.dumps({"step_id": step_id, "step_name": step_name, "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))


def check_ollama():
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        models = [m["name"] for m in data.get("models", [])]
        ok = any(OLLAMA_MODEL in m for m in models)
        if not ok:
            logging.warning(f"Model '{OLLAMA_MODEL}' not in Ollama: {models}")
        return ok
    except Exception as e:
        logging.warning(f"Ollama check failed: {e}")
        return False


def flag_human(step):
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    (PENDING_DIR / f"{step.get('step_name','?')}.review.json").write_text(json.dumps(step, indent=2))


def flag_fail(step, err, retries):
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    (PENDING_DIR / f"{step.get('step_name','?')}.failed.json").write_text(json.dumps({"step_name": step.get("step_name"), "step_id": step.get("step_id"), "error": err, "retries": retries}))


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"agent-worker-{AGENT_NAME}.log"
    logging.basicConfig(filename=str(log_file), level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logging.info(f"═══ Worker started: {AGENT_NAME} ═══")

    ollama_ok = check_ollama()
    retries = {}

    while True:
        try:
            if not ollama_ok:
                ollama_ok = check_ollama()
                if not ollama_ok:
                    time.sleep(POLL_INTERVAL)
                    continue

            msgs = read_inbox()
            if not msgs:
                time.sleep(POLL_INTERVAL)
                continue
            if isinstance(msgs, dict):
                msgs = [msgs] if "msg_id" in msgs else []

            for msg in msgs:
                if not isinstance(msg, dict) or "msg_id" not in msg:
                    continue
                msg_id = msg["msg_id"]
                body = msg.get("body", {})
                if isinstance(body, str):
                    try:
                        body = json.loads(body)
                    except json.JSONDecodeError:
                        continue
                if body.get("type") != "workflow_step":
                    continue

                step_id = body["step_id"]
                step_name = body.get("step_name", "?")
                wf_id = body.get("workflow_id", "?")
                prompt = body.get("prompt", "")
                max_retries = body.get("max_retries", MAX_RETRIES)
                human = body.get("human_review", False)
                logging.info(f"→ {step_name} (wf={wf_id[:8]})")

                if is_completed(step_id):
                    try:
                        archive_message(msg_id)
                    except Exception:
                        print("expected — silently handled", file=sys.stderr)
                    continue

                if human:
                    flag_human(body)
                    try:
                        archive_message(msg_id)
                    except Exception:
                        print("expected — silently handled", file=sys.stderr)
                    continue

                if step_id not in retries:
                    retries[step_id] = 0
                retries[step_id] += 1

                try:
                    logging.info(f"  Ollama attempt {retries[step_id]}/{max_retries}...")
                    output = run_ollama(prompt)
                    post_result(wf_id, step_id, "success", {"output": output})
                    archive_message(msg_id)
                    mark_completed(step_id, step_name)
                    retries.pop(step_id, None)
                    logging.info(f"  ✓ Completed")
                except Exception as e:
                    logging.error(f"  ✗ Attempt {retries[step_id]}: {e}")
                    if retries[step_id] >= max_retries:
                        try:
                            post_result(wf_id, step_id, "failed", {}, error=str(e))
                            archive_message(msg_id)
                        except Exception:
                            print("expected — silently handled", file=sys.stderr)
                        flag_fail(body, str(e), retries[step_id])
                        retries.pop(step_id, None)

        except Exception as e:
            logging.error(f"Cycle error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
