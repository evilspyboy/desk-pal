#!/usr/bin/env python3
"""Minimal Desk-Pal Companion Microservice Template.

Exposes GET /status on 127.0.0.1:8099 so Desk-Pal's native IntegrationPoller
can monitor it directly with zero external dependencies.
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", "8099"))
STARTED_AT = time.time()


class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/status"):
            self.send_error(404, "Not found")
            return
        uptime_min = int((time.time() - STARTED_AT) // 60)
        payload = {
            "status": "healthy",
            "summary": f"Example service online ({uptime_min}m uptime)",
            "badge": "OK",
            "uptime_seconds": int(time.time() - STARTED_AT),
            "timestamp": time.time(),
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), StatusHandler)
    print(f"[example_service] Listening on http://127.0.0.1:{PORT}/status")
    server.serve_forever()
