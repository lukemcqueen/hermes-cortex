"""Tests for webapp-deploy-verification/scripts/webapp-http-crawl.py.

Exercises the crawler against a real local HTTP server (stdlib http.server)
to verify OK/BAD classification, <title> capture, and exit codes.
"""
import http.server
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "devops"
    / "webapp-deploy-verification"
    / "scripts"
    / "webapp-http-crawl.py"
)

INDEX_HTML = b"<html><head><title>Test Home</title></head><body>ok</body></html>"
ABOUT_HTML = b"<html><head><title>About Page</title></head><body>about</body></html>"


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server API)
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(INDEX_HTML)
        elif self.path == "/about.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(ABOUT_HTML)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):  # noqa: A002 — silence request logging
        pass


@pytest.fixture(scope="module")
def server_url():
    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        yield f"http://127.0.0.1:{port}"
        httpd.shutdown()


def run_crawler(base, routes):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--base", base, "--routes", *routes],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_ok_route_with_title(server_url):
    r = run_crawler(server_url, ["/"])
    assert r.returncode == 0
    assert "[OK ] / -> 200" in r.stdout
    assert "<title>Test Home</title>" in r.stdout


def test_bad_route_nonzero_exit(server_url):
    r = run_crawler(server_url, ["/missing"])
    assert r.returncode == 1
    assert "[BAD] /missing" in r.stdout


def test_mixed_routes_summary(server_url):
    r = run_crawler(server_url, ["/", "/about.html", "/missing"])
    assert r.returncode == 1
    assert "2/3 routes OK" in r.stdout


def test_routes_from_file(server_url, tmp_path):
    routes_file = tmp_path / "routes.txt"
    routes_file.write_text("/\n/about.html\n/missing\n")
    r = run_crawler(server_url, [str(routes_file)])
    assert r.returncode == 1
    assert "2/3 routes OK" in r.stdout
