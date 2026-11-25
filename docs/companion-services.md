# Companion Services & Scripts

Desk-Pal provides an integrated **Companion Services Supervisor** (`src/companion_supervisor.py`) that manages lightweight background Python scripts, API scrapers, and microservices running directly on the Raspberry Pi alongside Desk-Pal.

This allows users and developers to deploy custom telemetry producers (e.g., flight trackers, local weather sensors, smart plug checkers, custom scrapers) without manually configuring Linux virtual environments, `systemd` units, or SSH sessions.

---

## Key Features

1. **Direct on-Pi Execution**: Runs as supervised background child processes on the Raspberry Pi using the Pi's Python runtime.
2. **Web Studio Management**: View, start, stop, restart, edit code, and stream live console logs directly from the Web Studio interface (`http://<pi-ip>:7777`).
3. **Automatic Application Linking**:
   - Saving a companion script with **Add to Desk-Pal Apps** automatically adds it to Desk-Pal's Application list in App Studio (`config.apps`) with a direct local loopback endpoint (`http://127.0.0.1:<port>/status`).
   - In App & Action Studio, clicking **+ Application** automatically detects active companion scripts on the Pi and offers a 1-click import button.
4. **Crash Detection & Auto-Restart**: If a service marked with `"auto_start": true` exits unexpectedly, the supervisor automatically restarts it with a rate limiter (up to 5 attempts per 60 seconds) to prevent infinite crash loops.
5. **Live Log Streaming**: Captures `stdout` and `stderr` in real time. Logs are streamed to the browser and persisted to `logs/services/<service_id>.log`.
6. **Clean Shutdown**: When Desk-Pal exits, all companion processes receive `SIGTERM` (and `SIGKILL` after 3s if needed) to prevent orphan processes.

---

## Directory Structure

Companion services live in `/home/admin/services/` on the Raspberry Pi (or `services/` in the local workspace):

```text
services/
├── flight_radar/          # Flight deal corridor anomaly tracker
│   ├── service.json
│   └── main.py
└── wellness_check/        # Posture stretch & hydration monitor
    ├── service.json
    ├── main.py
    └── config.json
```

### Bundled Companion Microservices

1. **`flight_radar` (Port 8095)**: Scans air corridors for discounted flight anomalies and price drops. Runs natively on the Raspberry Pi under loopback address `http://127.0.0.1:8095/`.
2. **`wellness_check` (Port 8096)**: Smart posture stretch and hydration monitor. Automatically uses mmWave radar presence to track sitting time and auto-credits breaks (resets sitting timer) after 2 minutes of absence away from the desk. Configured for standard office hours (`09:00–17:00` Mon–Fri). Outside active hours, it displays `OFF HOURS` and suspends notifications. Triggers attention with an initial silent arm-waving period to catch the eye first before escalating to voice, followed by a dedicated graphic modal with pixel-art water glass and stretching sprites, metric 20-20-20 rule (6 metres for 20 seconds), and an interactive touch slider rail (15m–120m). Upon startup or service recovery, any stale or queued outage alerts are automatically purged so notifications never linger.
3. **`calendar` (Port 8097)**: Private iCalendar (`.ics`) companion microservice. Parses personal secret calendar feeds from Google Calendar, Apple iCloud, or Microsoft Outlook with zero Google Cloud Developer project requirements or third-party cloud apps. Supports single events, all-day events, and recurring events (`RRULE`). Implements smart lookahead logic ($\le 3$ days, bridging Thursday/Friday across weekends to Monday) and clear-week detection (`"This Week: Nothing scheduled"`). Configured directly inside Desk-Pal's Application Studio and Companion Scripts panels with automatic hot-reload on save.

### Manifest Schema (`service.json`)

```json
{
  "id": "flight_radar",
  "name": "Flight Radar Tracker",
  "description": "Scans flight corridors for discount anomalies",
  "entrypoint": "main.py",
  "port": 8095,
  "auto_start": true,
  "env": {}
}
```

- **`id`** *(string, required)*: Unique slug identifier and folder name.
- **`name`** *(string)*: Human-readable display name shown in Web Studio and Desk-Pal.
- **`description`** *(string)*: Description of what the service does.
- **`entrypoint`** *(string)*: Primary script file (defaults to `main.py`).
- **`port`** *(integer, optional)*: Local port the service listens on (e.g. `8095`).
- **`auto_start`** *(boolean)*: If `true`, the service launches automatically when Desk-Pal starts.
- **`env`** *(object)*: Custom environment variables passed to the subprocess.

---

## JSON Status API Contract

For services that expose an HTTP endpoint (polling mode), your script should bind to `0.0.0.0` or `127.0.0.1` and return JSON at `/status` (or any path). 

### Minimal Working Example

```python
import http.server
import json
import os

PORT = int(os.environ.get("PORT", 8090))

class StatusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        payload = {
            "status": "healthy",
            "app_id": "my_service",
            "activity": "Monitoring Background Tasks",
            "summary": "All systems operating normally. 0 errors detected.",
            "badge": "ONLINE",
            "ticker": ["Service active on Pi", "Latency: 1ms"],
            "ttl_seconds": 60
        }
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", PORT), StatusHandler)
    server.serve_forever()
```

### Supported Dashboard Fields

If your application uses the **5" High-Vis Dashboard** modal layout, Desk-Pal reads:
- **`summary`**: Primary text summary displayed on screen and spoken by the character.
- **`badge`**: Accent badge in the upper right (e.g. `"BUY NOW"`, `"-50%"`, `"ONLINE"`).
- **`activity`**: Short ticker line shown while the character is wandering or reacting.
- **`hero_value`** *(optional)*: Large central figure (e.g. `"250.5¢"` or `"$520"`).
- **`hero_subhead`** *(optional)*: Label below the hero value (e.g. `"CHEAPEST U98"`).
- **`tiles`** *(optional array)*: Up to 3 metric boxes with `label` and `value`.

---

## User Interface & Controls

In **Web Studio** (`http://<pi-ip>:7777`):

1. **Bottom Taskbar**: Click **`⚡ Companion Scripts (<count>)`** to open the supervisor panel.
2. **Service Cards**:
   - Status badge: 🟢 `RUNNING` (with PID and uptime), ⚪ `STOPPED`, or 🔴 `CRASHED`.
   - **`▶ Start` / `⏹ Stop` / `🔄 Restart`**: Controls process execution.
   - **`📄 Logs`**: Opens the live terminal drawer, auto-refreshing console output every 2 seconds.
   - **`✏️ Edit`**: Opens the in-browser code editor to modify `main.py` and settings.
   - **`🔗 Link to Desk-Pal App`**: Instantly creates or updates an App Studio integration pointing to `http://127.0.0.1:<port>/status`.
3. **App & Action Studio Integration**:
   - In App Studio, clicking **`+ Application`** shows an **⚡ Companion Scripts on Pi** quick-picker.
   - Clicking any companion script pre-fills the Application Name, ID, and local endpoint URL automatically.

---

## REST API Reference

The supervisor is controlled via Desk-Pal's HTTP server:

| Endpoint | Method | Description |
|---|---|---|
| `/api/services` | `GET` | Returns list of all discovered services and their runtime statuses. |
| `/api/services/logs?id=<id>&lines=100` | `GET` | Returns the recent log lines for a service. |
| `/api/services/code?id=<id>` | `GET` | Returns the script contents and manifest. |
| `/api/services/action` | `POST` | Dispatches `{"id": "<id>", "action": "start"|"stop"|"restart"}`. |
| `/api/services/save` | `POST` | Saves script code and manifest; restarts if running. |
| `/api/services/delete` | `POST` | Stops and permanently removes a service directory. |
