"""
Dummy Monitored Application for Desk-Pal.

A standalone reference application demonstrating how external services
can expose a clean, direct HTTP status endpoint for Desk-Pal's native
background IntegrationPoller to query across the network.

Run locally:
    python examples/dummy_monitored_app.py --port 8090

Endpoints:
    GET  /api/v1/status   - Current application status polled by Desk-Pal
    POST /api/v1/simulate - Simulate events or health state changes for testing
"""
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import time

# Mutable state for the dummy application
STATE = {
    "status": "healthy",
    "summary": "Worker pool idle: 4/4 nodes ready, 0 jobs pending.",
    "button_summary": "Workers: 4 Ready",
    "batch_id": "batch-101",
    "items_processed": 420,
    "active_workers": 4,
    "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S")
}


class DummyAppHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Keep console output concise
        print(f"[{time.strftime('%X')}] {format % args}")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/api/v1/status", "/status"):
            # Update dynamic timestamp
            STATE["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            data = json.dumps(STATE, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_error(404, "Endpoint not found. Use GET /api/v1/status")

    def do_POST(self):
        if self.path in ("/api/v1/simulate", "/simulate"):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
                if "status" in payload:
                    STATE["status"] = payload["status"]
                if "summary" in payload:
                    STATE["summary"] = payload["summary"]
                if "button_summary" in payload:
                    STATE["button_summary"] = payload["button_summary"]
                if "items_processed" in payload:
                    STATE["items_processed"] = payload["items_processed"]
                STATE["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")

                resp = json.dumps({"status": "ok", "updated_state": STATE}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                self.send_error(400, f"Invalid JSON payload: {e}")
            return

        self.send_error(404, "Endpoint not found. Use POST /api/v1/simulate")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (use 0.0.0.0 to accept LAN requests from Pi)")
    parser.add_argument("--port", type=int, default=8090, help="HTTP port to listen on (default: 8090)")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), DummyAppHandler)
    print(f"=== Desk-Pal Dummy Monitored Application ===")
    print(f"Listening on http://{args.host}:{args.port}")
    print(f"Status endpoint: http://<your-ip>:{args.port}/api/v1/status")
    print(f"Simulate state change: curl -X POST http://localhost:{args.port}/api/v1/simulate -H 'Content-Type: application/json' -d '{{\"status\": \"warning\", \"summary\": \"High memory usage detected\"}}'")
    print(f"Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dummy monitored app.")
        server.server_close()


if __name__ == "__main__":
    main()
