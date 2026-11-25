"""
Breakout Arcade Companion Service for Desk-Pal.
Serves game statistics/telemetry over HTTP on port 8097,
and supports direct standalone execution when run directly.
"""

import http.server
import json
import os
import sys
import time

PORT = int(os.environ.get("PORT", 8097))
SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SERVICE_DIR))
SRC_DIR = os.path.join(REPO_ROOT, "src")

# State file for high scores
STATE_FILE = os.path.join(SERVICE_DIR, "state.json")


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"high_score": 0, "games_played": 0, "last_score": 0}


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


class GameStatusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        state = load_state()
        payload = {
            "status": "healthy",
            "app_id": "breakout",
            "activity": "Breakout Arcade",
            "summary": f"Arcade Ready · High Score: {state['high_score']}",
            "badge": f"{state['high_score']} pts",
            "high_score": state["high_score"],
            "games_played": state["games_played"],
            "ticker": ["Retro Breakout Mini-Game", "Tap study computer to play"],
            "ttl_seconds": 60,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        # Concise logging
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]} - {args[1]}", flush=True)


if __name__ == "__main__":
    if "--play" in sys.argv or sys.stdout.isatty():
        # Running directly in a terminal: launch standalone game
        if SRC_DIR not in sys.path:
            sys.path.insert(0, SRC_DIR)
        try:
            from games.breakout import run_standalone
            run_standalone()
            sys.exit(0)
        except Exception as e:
            print(f"Could not start standalone display: {e}")

    # Microservice mode
    print(f"🕹️ Breakout Arcade companion service starting on port {PORT}...", flush=True)
    server = http.server.HTTPServer(("0.0.0.0", PORT), GameStatusHandler)
    server.serve_forever()
