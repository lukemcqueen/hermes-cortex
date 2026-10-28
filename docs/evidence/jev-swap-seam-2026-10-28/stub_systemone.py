#!/usr/bin/env python3
"""A minimal /v1/systemone endpoint, so the DECISION MODEL can be proved swappable.

This stands in for a future steadfaste / self-hosted von endpoint (von is
wire-compatible with /v1/systemone, Apache-2.0). Pointing `TYPESAFE_BASE_URL` at
it must be enough: no consumer code changes, and the real provider credential
must NOT travel to it.

It answers every question type the client validates:
  noul   -> {"type":"noul","noul":<0..1>}
  choice -> {"type":"choice","choice":<argmax option>,"probabilities":{...} sum=1,"confidence":p}
  score  -> {"type":"score","score":<mean of its own spread>,"probabilities":{...} sum=1}
A wrong shape here would be refused by the client as invalid_response, which is
the client working — so this file follows jevkit/client.py's validators exactly.

Usage: python3 stub_systemone.py [port] [--report PATH]
Never prints an Authorization VALUE: only whether one arrived and whether it
matched the proxy key this run was told to expect.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPORT = []
EXPECTED_PROXY = os.environ.get("EXPECT_PROXY_KEY", "")
REPORT_PATH = os.environ.get("STUB_REPORT", "")


def _answer(question):
    kind = question.get("type")
    if kind == "noul":
        return {"type": "noul", "noul": 0.93}
    if kind == "choice":
        options = list(question.get("criteria") or {})
        if not options:
            return {"type": "choice", "choice": "", "probabilities": {}, "confidence": 0.0}
        rest = 0.1 / max(len(options) - 1, 1)
        probabilities = {opt: (0.9 if i == 0 else rest) for i, opt in enumerate(options)}
        return {"type": "choice", "choice": options[0], "probabilities": probabilities,
                "confidence": 0.93}
    rubric = list(question.get("criteria") or [])
    levels = len(rubric) or 1
    share = 1.0 / levels
    probabilities = {str(i): share for i in range(levels)}
    mean = sum(i * share for i in range(levels))
    return {"type": "score", "score": round(mean, 4), "probabilities": probabilities,
            "legend": {str(i): str(rubric[i]) if i < len(rubric) else f"level {i}"
                       for i in range(levels)}}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep stdout clean for the report
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            request = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError):
            request = {}
        auth = self.headers.get("Authorization") or ""
        bearer = auth[7:] if auth.startswith("Bearer ") else ""
        REPORT.append({
            "path": self.path,
            "model": request.get("model"),
            "question_types": sorted({q.get("type") for q in (request.get("questions") or {}).values()}),
            "questions": sorted((request.get("questions") or {}).keys()),
            "authorization_present": bool(auth),
            # never the value: only whether it is the proxy key this run expected
            "bearer_is_expected_proxy_key": bool(bearer) and bearer == EXPECTED_PROXY,
            "bearer_equals_env_typesafe_key": bool(bearer) and bearer == os.environ.get("TYPESAFE_API_KEY", ""),
        })
        if REPORT_PATH:
            with open(REPORT_PATH, "w", encoding="utf-8") as handle:
                json.dump(REPORT, handle, indent=2)
        answers = {name: _answer(q) for name, q in (request.get("questions") or {}).items()}
        body = json.dumps({
            "answers": answers,
            "model": "steadfaste-stub-1",
            "usage": {"input_tokens": 11, "output_tokens": 3},
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        body = b'{"ok":true,"answers":{},"model":"steadfaste-stub-1"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8799
    report_path = None
    if "--report" in sys.argv:
        report_path = sys.argv[sys.argv.index("--report") + 1]
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)

    def dump():
        if report_path:
            with open(report_path, "w", encoding="utf-8") as handle:
                json.dump(REPORT, handle, indent=2)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        dump()


if __name__ == "__main__":
    main()
