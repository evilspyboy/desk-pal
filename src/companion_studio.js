/**
 * Desk-Pal Companion Services & Scripts Studio
 * UI Controller for managing lightweight background Python daemons, microservices,
 * and scrapers running directly on the Raspberry Pi alongside Desk-Pal.
 */

(function () {
  let companionPollInterval = null;
  let activeLogServiceId = null;
  let activeLogPollInterval = null;

  const TEMPLATES = {
    simple_json: {
      name: "Simple JSON Microservice",
      description: "Lightweight HTTP server on port 8090 returning status and metrics for Desk-Pal",
      port: 8090,
      auto_start: true,
      entrypoint: "main.py",
      code: `"""
Simple JSON Status Microservice for Desk-Pal
Runs directly on the Pi and serves real-time status and metrics.
"""
import http.server
import json
import os
import time

PORT = int(os.environ.get("PORT", 8090))

class StatusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        payload = {
            "status": "healthy",
            "app_id": "my_service",
            "activity": "Monitoring Background Tasks",
            "summary": "All systems operating normally. 0 errors detected.",
            "badge": "ONLINE",
            "ticker": ["Service active on Raspberry Pi", "Latency: 2ms"],
            "data": {
                "metric_a": 42,
                "metric_b": "Normal"
            },
            "ttl_seconds": 60,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]} - {args[1]}", flush=True)

if __name__ == "__main__":
    print(f"🚀 Microservice starting on port {PORT}...", flush=True)
    server = http.server.HTTPServer(("0.0.0.0", PORT), StatusHandler)
    server.serve_forever()
`,
    },
    system_monitor: {
      name: "Raspberry Pi System & Hardware Monitor",
      description: "Real-time CPU Temperature, RAM %, Disk %, and Load Average on port 8092",
      port: 8092,
      auto_start: true,
      entrypoint: "main.py",
      code: `\"\"\"
Raspberry Pi System & Hardware Monitor for Desk-Pal
Reports real-time CPU Temperature, RAM %, Disk %, and Load on port 8092.
\"\"\"
import http.server
import json
import os
import time

PORT = int(os.environ.get("PORT", 8092))

def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return round(int(f.read().strip()) / 1000.0, 1)
    except Exception:
        return 42.0

def get_sys_stats():
    load1 = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.5
    temp = get_cpu_temp()
    return {
        "status": "healthy",
        "app_id": "system_monitor",
        "activity": "Monitoring Pi Hardware",
        "summary": f"Pi CPU: {temp}°C · 1m Load: {load1:.2f}",
        "badge": f"{temp}°C",
        "temp_c": temp,
        "load_1m": load1,
        "dashboard": {
            "hero_value": f"{temp}°C",
            "hero_subhead": "Raspberry Pi CPU Temp",
            "badge": "NORMAL" if temp < 70 else "WARM",
            "tiles": [
                {"label": "1m Load", "value": f"{load1:.2f}"},
                {"label": "Status", "value": "Healthy"}
            ]
        },
        "ticker": [f"Pi CPU Temp: {temp}°C", f"System Load: {load1:.2f}"],
        "ttl_seconds": 60,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
    }

class SysHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        payload = get_sys_stats()
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    print(f"🖥️ System Monitor starting on port {PORT}...", flush=True)
    server = http.server.HTTPServer(("0.0.0.0", PORT), SysHandler)
    server.serve_forever()
`,
    },
    uptime_ping: {
      name: "Network & Server Uptime Monitor",
      description: "Pings a network target or website and serves latency and availability on port 8093",
      port: 8093,
      auto_start: true,
      entrypoint: "main.py",
      code: `\"\"\"
Network Ping & Website Uptime Monitor for Desk-Pal
Pings target host and serves latency and availability on port 8093.
\"\"\"
import http.server
import json
import os
import subprocess
import time

PORT = int(os.environ.get("PORT", 8093))
TARGET_HOST = os.environ.get("TARGET_HOST", "1.1.1.1")

def check_ping():
    try:
        out = subprocess.check_output(["ping", "-c", "1", "-W", "2", TARGET_HOST], stderr=subprocess.DEVNULL).decode()
        for line in out.splitlines():
            if "time=" in line:
                ms = line.split("time=")[1].split()[0]
                return True, float(ms)
        return True, 15.0
    except Exception:
        return False, None

class PingHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        up, ms = check_ping()
        latency_str = f"{ms:.0f}ms" if ms is not None else "Timeout"
        payload = {
            "status": "healthy" if up else "degraded",
            "app_id": "uptime_ping",
            "activity": f"Pinging {TARGET_HOST}",
            "summary": f"{TARGET_HOST} is {'ONLINE' if up else 'OFFLINE'} ({latency_str})",
            "badge": "ONLINE" if up else "OFFLINE",
            "latency_ms": ms,
            "dashboard": {
                "hero_value": latency_str,
                "hero_subhead": f"Ping: {TARGET_HOST}",
                "badge": "UP" if up else "DOWN",
                "tiles": [
                    {"label": "Target", "value": TARGET_HOST},
                    {"label": "Status", "value": "Reachable" if up else "Unreachable"}
                ]
            },
            "ticker": [f"{TARGET_HOST}: {latency_str}", "Internet connection active"],
            "ttl_seconds": 60,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    print(f"📡 Uptime Monitor starting on port {PORT}...", flush=True)
    server = http.server.HTTPServer(("0.0.0.0", PORT), PingHandler)
    server.serve_forever()
`,
    },
    home_assistant: {
      name: "Home Assistant Entity Relay",
      description: "Polls a Home Assistant entity (temperature, sensor, or switch) on port 8094",
      port: 8094,
      auto_start: false,
      entrypoint: "main.py",
      code: `\"\"\"
Home Assistant Entity Relay for Desk-Pal
Fetches sensor states from a local Home Assistant instance and serves to Desk-Pal.
\"\"\"
import http.server
import json
import os
import time
import urllib.request

PORT = int(os.environ.get("PORT", 8094))
HASS_URL = os.environ.get("HASS_URL", "http://homeassistant.local:8123")
HASS_TOKEN = os.environ.get("HASS_TOKEN", "YOUR_LONG_LIVED_ACCESS_TOKEN")
ENTITY_ID = os.environ.get("ENTITY_ID", "sensor.living_room_temperature")

def fetch_hass():
    req = urllib.request.Request(
        f"{HASS_URL}/api/states/{ENTITY_ID}",
        headers={"Authorization": f"Bearer {HASS_TOKEN}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.load(resp)

class HassHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            state_data = fetch_hass()
            state = state_data.get("state", "unknown")
            unit = state_data.get("attributes", {}).get("unit_of_measurement", "")
            friendly = state_data.get("attributes", {}).get("friendly_name", ENTITY_ID)
            val = f"{state} {unit}".strip()
            payload = {
                "status": "healthy",
                "app_id": "home_assistant",
                "activity": f"Home Assistant: {friendly}",
                "summary": f"{friendly}: {val}",
                "badge": val,
                "dashboard": {
                    "hero_value": val,
                    "hero_subhead": friendly,
                    "badge": "HASS",
                    "tiles": [
                        {"label": "Entity", "value": ENTITY_ID.split(".")[-1]},
                        {"label": "State", "value": str(state)}
                    ]
                },
                "ttl_seconds": 60,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
        except Exception as e:
            payload = {
                "status": "degraded",
                "app_id": "home_assistant",
                "summary": f"Home Assistant: {e}",
                "badge": "CONFIG",
                "dashboard": {
                    "hero_value": "Setup Required",
                    "hero_subhead": "Set HASS_URL & HASS_TOKEN",
                    "badge": "ERROR",
                    "tiles": [{"label": "HASS", "value": "Offline"}]
                },
                "ttl_seconds": 30
            }
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

if __name__ == "__main__":
    print(f"🏠 Home Assistant Relay starting on port {PORT}...", flush=True)
    server = http.server.HTTPServer(("0.0.0.0", PORT), HassHandler)
    server.serve_forever()
`,
    },
    wellness_check: {
      name: "Wellness & Hydration Monitor",
      description: "Supervised background service on port 8096 for stretch reminders, hydration goals, and radar presence",
      port: 8096,
      auto_start: true,
      entrypoint: "main.py",
      code: `\"\"\"
Desk-Pal Wellness Check & Hydration Companion Microservice
Supervised background service running on Raspberry Pi port 8096.
\"\"\"
import http.server
import json
import os
import time

PORT = int(os.environ.get("PORT", 8096))

class WellnessHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        payload = {
            "status": "healthy",
            "app_id": "wellness_check",
            "activity": "Desk Wellness & Hydration",
            "summary": "Hydration at 60% goal. Posture check passed.",
            "badge": "HYDRATE",
            "sitting_minutes": 25,
            "remind_interval_minutes": 60,
            "water_ml": 1250,
            "water_goal_ml": 2000,
            "ticker": ["Stay hydrated! Next stretch in 35m", "Hydration: 1250 / 2000 ml"],
            "ttl_seconds": 30,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]} - {args[1]}", flush=True)

if __name__ == "__main__":
    print(f"💧 Wellness & Hydration Service starting on port {PORT}...", flush=True)
    server = http.server.HTTPServer(("0.0.0.0", PORT), WellnessHandler)
    server.serve_forever()
`,
    },
    flight_radar: {
      name: "Flight Radar Tracker",
      description: "Scans air corridors for discounted flight deals and price dislocation alerts",
      port: 8095,
      auto_start: true,
      entrypoint: "main.py",
      code: `"""
Flight Radar Tracker - Lightweight Desk-Pal Companion Microservice
Runs directly on the Pi and serves real-time flight deals telemetry over HTTP.
"""
import http.server
import json
import os
import time

PORT = int(os.environ.get("PORT", 5000))
DEALS = [
    {"destination": "Singapore", "flightDeal": 520, "flightNormal": 1040, "discount": 50},
    {"destination": "Bali (Denpasar)", "flightDeal": 596, "flightNormal": 850, "discount": 30},
    {"destination": "Ho Chi Minh City", "flightDeal": 546, "flightNormal": 850, "discount": 36},
    {"destination": "Tokyo (Narita)", "flightDeal": 840, "flightNormal": 1350, "discount": 38},
]

class FlightRadarHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        best = DEALS[0]
        payload = {
            "status": "healthy",
            "app_id": "flight_radar",
            "origin": "BNE",
            "destination": best["destination"],
            "price": best["flightDeal"],
            "savings_pct": best["discount"],
            "activity": f"BNE Deals: {best['destination']} \${best['flightDeal']} (-{best['discount']}%)",
            "summary": f"✈️ Travel Radar (BNE Hub):\\n• {best['destination']}: \${best['flightDeal']} return (save {best['discount']}%)\\n• {DEALS[1]['destination']}: \${DEALS[1]['flightDeal']} return (save {DEALS[1]['discount']}%)",
            "ticker": [
                f"✈️ {best['destination']}: \${best['flightDeal']} return (save {best['discount']}%)",
                f"✈️ {DEALS[1]['destination']}: \${DEALS[1]['flightDeal']} return (save {DEALS[1]['discount']}%)"
            ],
            "badge": f"-{best['discount']}%",
            "ttl_seconds": 180,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]} - {args[1]}", flush=True)

if __name__ == "__main__":
    print(f"✈️ Flight Radar Tracker starting on port {PORT}...", flush=True)
    server = http.server.HTTPServer(("0.0.0.0", PORT), FlightRadarHandler)
    server.serve_forever()
`,
    },
    webhook_relay: {
      name: "Desk-Pal Webhook Relay / Poller",
      description: "Periodically fetches an external public website/API and posts events into Desk-Pal",
      port: 0,
      auto_start: false,
      entrypoint: "main.py",
      code: `"""
Periodic Scraper / Webhook Relay for Desk-Pal
Fetches external telemetry and directly pushes heartbeats or alerts to Desk-Pal port 7777.
"""
import time
import urllib.request
import json

DESKPAL_URL = "http://127.0.0.1:7777/api/v1/heartbeat"
INTERVAL_SECONDS = 30

def check_and_relay():
    payload = {
        "app_id": "custom_worker",
        "status": "healthy",
        "activity": "Periodic Scraper Active",
        "summary": "Custom worker successfully scraped remote endpoint.",
        "badge": "OK",
        "ttl_seconds": INTERVAL_SECONDS * 3
    }
    req = urllib.request.Request(
        DESKPAL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        print(f"[{time.strftime('%H:%M:%S')}] Relayed status to Desk-Pal: HTTP {resp.status}", flush=True)

if __name__ == "__main__":
    print("🚀 Custom background worker starting...", flush=True)
    while True:
        try:
            check_and_relay()
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Poll error: {e}", flush=True)
        time.sleep(INTERVAL_SECONDS)
`,
    },
  };

  window.openCompanionServicesModal = function () {
    const modal = document.getElementById("companionServicesModal");
    if (!modal) return;
    modal.style.display = "flex";
    closeServiceEditor();
    closeServiceLogs();
    refreshCompanionServices();

    if (companionPollInterval) clearInterval(companionPollInterval);
    companionPollInterval = setInterval(refreshCompanionServices, 4000);
  };

  window.closeCompanionServicesModal = function () {
    const modal = document.getElementById("companionServicesModal");
    if (modal) modal.style.display = "none";
    if (companionPollInterval) {
      clearInterval(companionPollInterval);
      companionPollInterval = null;
    }
    closeServiceLogs();
  };

  window.refreshCompanionServices = async function () {
    const container = document.getElementById("servicesListContainer");
    const countBadge = document.getElementById("serviceCountBadge");
    if (!container) return;

    try {
      const res = await fetch("/api/services");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      const services = data.services || [];

      if (countBadge) countBadge.textContent = services.length;

      if (services.length === 0) {
        container.innerHTML = `
          <div style="background:#191627; border:1px dashed var(--border); border-radius:12px; padding:32px; text-align:center;">
            <div style="font-size:2.4rem; margin-bottom:8px;">📦</div>
            <h3 style="color:#fff; margin-bottom:6px;">No Companion Scripts Installed</h3>
            <p style="color:var(--text-dim); font-size:0.85rem; max-width:480px; margin:0 auto 16px;">
              You can run any lightweight Python script, background scraper, or microservice directly on your Pi.
            </p>
              <button class="btn btn-primary" onclick="openNewServiceEditor('system_monitor')" style="background:#8b5cf6; border-color:#8b5cf6;">🖥️ Install Pi System Monitor</button>
              <button class="btn btn-primary" onclick="openNewServiceEditor('wellness_check')" style="background:#0284c7; border-color:#0284c7;">💧 Install Wellness Monitor</button>
              <button class="btn btn-accent" onclick="openNewServiceEditor('simple_json')">+ New Custom Script</button>
          </div>
        `;
        return;
      }

      container.innerHTML = services
        .map((svc) => {
          const isRunning = svc.status === "running";
          const isCrashed = svc.status === "crashed";
          const statusBg = isRunning ? "#10b981" : isCrashed ? "#ef4444" : "#6b7280";
          const statusText = isRunning
            ? `RUNNING · PID ${svc.pid} (${formatUptime(svc.uptime_seconds)})`
            : isCrashed
            ? `CRASHED (Exit: ${svc.exit_code})`
            : "STOPPED";

          const portHtml = svc.port
            ? `<div style="display:flex; align-items:center; gap:8px; margin-top:6px; font-size:0.8rem;">
                 <span style="color:#00e5ff; font-family:monospace; background:rgba(0,229,255,0.1); padding:2px 8px; border-radius:4px; border:1px solid rgba(0,229,255,0.3);">
                   http://127.0.0.1:${svc.port}/status
                 </span>
                 <button class="btn" style="padding:2px 8px; font-size:0.72rem; background:#249ca5; color:#fff;" onclick="linkServiceToDeskpalApp('${svc.id}', ${svc.port}, '${escapeHtml(svc.name)}')">
                   🔗 Link to Desk-Pal App
                 </button>
               </div>`
            : "";

          const isCalendar = (svc.id === 'calendar');
          const calendarControlsHtml = isCalendar
            ? `<div style="display:flex; align-items:center; gap:8px; margin-top:8px;">
                 <button class="btn" style="padding:4px 12px; font-size:0.78rem; background:#a855f7; color:#fff; font-weight:700; border-color:#a855f7;" onclick="openCalendarAppControls('${svc.id}')">
                   📅 Configure Calendar Feed URL &amp; Schedule
                 </button>
                 <span style="font-size:0.75rem; color:var(--text-dim);">Set secret iCal URL and daily agenda settings in App Studio</span>
               </div>`
            : "";
          const isGame = (svc.id === 'breakout' || svc.category === 'game');
          const gameControlsHtml = isGame
            ? `<div style="display:flex; align-items:center; gap:8px; margin-top:8px;">
                 <button class="btn" style="padding:4px 12px; font-size:0.78rem; background:#6abe30; color:#111; font-weight:700; border-color:#6abe30;" onclick="openGameAppControls('${svc.id}')">
                   🎮 Configure Game Controls &amp; Bezel
                 </button>
                 <span style="font-size:0.75rem; color:var(--text-dim);">Configure buttons, IMU tilt, radar, or touch controls</span>
               </div>`
            : "";

          return `
            <div style="background:#191627; border:1px solid ${isRunning ? "rgba(16,185,129,0.3)" : "var(--border)"}; border-radius:10px; padding:14px 18px; display:flex; flex-direction:column; gap:8px;">
              <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <div>
                  <div style="display:flex; align-items:center; gap:10px;">
                    <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:${statusBg}; box-shadow:0 0 8px ${statusBg};"></span>
                    <strong style="color:#fff; font-size:1.05rem;">${escapeHtml(svc.name)}</strong>
                    <span style="font-size:0.72rem; color:${statusBg}; font-weight:700; border:1px solid ${statusBg}; border-radius:10px; padding:1px 7px;">${statusText}</span>
                    ${svc.auto_start ? '<span style="font-size:0.68rem; color:#a855f7; border:1px solid rgba(168,85,247,0.4); border-radius:8px; padding:1px 6px;">Auto-start</span>' : ""}
                  </div>
                  <div style="color:var(--text-dim); font-size:0.82rem; margin-top:4px;">
                    ${escapeHtml(svc.description || "No description provided.")} · Entry: <code>${escapeHtml(svc.entrypoint)}</code>
                  </div>
                  ${portHtml}
                  ${gameControlsHtml}
                  ${calendarControlsHtml}
                </div>

                <div style="display:flex; gap:6px; flex-shrink:0;">
                  ${
                    isRunning
                      ? `<button class="btn" onclick="doServiceAction('${svc.id}', 'restart')" style="padding:4px 8px; font-size:0.78rem;">🔄 Restart</button>
                         <button class="btn" onclick="doServiceAction('${svc.id}', 'stop')" style="padding:4px 8px; font-size:0.78rem; background:#374151; color:#fff;">⏹ Stop</button>`
                      : `<button class="btn btn-primary" onclick="doServiceAction('${svc.id}', 'start')" style="padding:4px 10px; font-size:0.78rem; background:#10b981; border-color:#10b981; color:#111; font-weight:700;">▶ Start</button>`
                  }
                  <button class="btn" onclick="viewServiceLogs('${svc.id}', '${escapeHtml(svc.name)}')" style="padding:4px 8px; font-size:0.78rem; background:#3b82f6; color:#fff;">📄 Logs</button>
                  <button class="btn" onclick="editServiceCode('${svc.id}')" style="padding:4px 8px; font-size:0.78rem;">✏️ Edit</button>
                  <button class="btn" onclick="deleteServicePrompt('${svc.id}', '${escapeHtml(svc.name)}')" style="padding:4px 8px; font-size:0.78rem; color:#ef4444;">🗑</button>
                </div>
              </div>
            </div>
          `;
        })
        .join("");
    } catch (e) {
      container.innerHTML = `<div style="color:#ef4444; padding:16px;">Failed to load services: ${e.message}</div>`;
    }
  };

  window.doServiceAction = async function (serviceId, action) {
    try {
      const res = await fetch("/api/services/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: serviceId, action: action }),
      });
      const data = await res.json();
      if (!data.success) {
        alert("Action failed: " + (data.error || "Unknown error"));
      }
      refreshCompanionServices();
    } catch (e) {
      alert("Error: " + e.message);
    }
  };

  window.deleteServicePrompt = async function (serviceId, serviceName) {
    if (!confirm(`Are you sure you want to stop and delete '${serviceName}' (${serviceId})?`)) return;
    try {
      const res = await fetch("/api/services/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: serviceId }),
      });
      const data = await res.json();
      if (!data.success) alert("Failed: " + data.error);
      refreshCompanionServices();
    } catch (e) {
      alert("Error: " + e.message);
    }
  };

  window.openNewServiceEditor = function (templateKey) {
    const editor = document.getElementById("serviceEditorView");
    const list = document.getElementById("servicesListContainer");
    if (!editor || !list) return;

    list.style.display = "none";
    editor.style.display = "block";
    closeServiceLogs();

    const tpl = TEMPLATES[templateKey] || TEMPLATES.simple_json;
    const defaultId = templateKey || "my_service";

    editor.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid var(--border); padding-bottom:8px;">
        <h3 style="color:#fff; margin:0;">${templateKey ? "New Service from Template" : "Create New Companion Script"}</h3>
        <div style="display:flex; gap:8px;">
          <select onchange="applyTemplateToEditor(this.value)" style="background:#1f1b2e; color:#fff; border:1px solid var(--border); padding:3px 8px; border-radius:4px; font-size:0.75rem;">
            <option value="">-- Choose Template --</option>
            <option value="system_monitor" ${templateKey === "system_monitor" ? "selected" : ""}>🖥️ Pi System & Hardware Monitor (Port 8092)</option>
            <option value="uptime_ping" ${templateKey === "uptime_ping" ? "selected" : ""}>📡 Network & Uptime Ping Monitor (Port 8093)</option>
            <option value="home_assistant" ${templateKey === "home_assistant" ? "selected" : ""}>🏠 Home Assistant Entity Relay (Port 8094)</option>
            <option value="wellness_check" ${templateKey === "wellness_check" ? "selected" : ""}>💧 Wellness & Hydration Monitor (Port 8096)</option>
            <option value="simple_json" ${templateKey === "simple_json" ? "selected" : ""}>🚀 Simple JSON Status API (Port 8090)</option>
            <option value="webhook_relay" ${templateKey === "webhook_relay" ? "selected" : ""}>🔄 Periodic Scraper / Push Relay</option>
            <option value="flight_radar" ${templateKey === "flight_radar" ? "selected" : ""}>✈️ Flight Deals Scraper API (Port 5000)</option>
          </select>
          <button class="btn" onclick="closeServiceEditor()">Cancel</button>
          <button class="btn btn-primary" onclick="submitServiceEditor()" style="background:#10b981; color:#111; font-weight:700;">💾 Save & Deploy to Pi</button>
        </div>
      </div>

      <div style="display:grid; grid-template-columns: 1fr 1fr 120px 140px; gap:10px; margin-bottom:12px;">
        <div>
          <label style="font-size:0.75rem; color:var(--text-dim); display:block; margin-bottom:3px;">Service ID (Folder name):</label>
          <input type="text" id="svcEditId" value="${defaultId}" style="width:100%; background:#1a1727; color:#fff; border:1px solid var(--border); border-radius:4px; padding:5px 8px; font-size:0.85rem;" />
        </div>
        <div>
          <label style="font-size:0.75rem; color:var(--text-dim); display:block; margin-bottom:3px;">Display Name:</label>
          <input type="text" id="svcEditName" value="${escapeHtml(tpl.name)}" style="width:100%; background:#1a1727; color:#fff; border:1px solid var(--border); border-radius:4px; padding:5px 8px; font-size:0.85rem;" />
        </div>
        <div>
          <label style="font-size:0.75rem; color:var(--text-dim); display:block; margin-bottom:3px;">Port (optional):</label>
          <input type="number" id="svcEditPort" value="${tpl.port || ""}" placeholder="e.g. 5000" style="width:100%; background:#1a1727; color:#fff; border:1px solid var(--border); border-radius:4px; padding:5px 8px; font-size:0.85rem;" />
        </div>
        <div style="display:flex; flex-direction:column; gap:4px; padding-top:14px;">
          <label style="font-size:0.8rem; color:#fff; display:flex; align-items:center; gap:6px; cursor:pointer;">
            <input type="checkbox" id="svcEditAutoStart" ${tpl.auto_start ? "checked" : ""} /> Auto-start on boot
          </label>
          <label style="font-size:0.8rem; color:#00e5ff; font-weight:600; display:flex; align-items:center; gap:6px; cursor:pointer;" title="Automatically add to Desk-Pal Applications list in App Studio">
            <input type="checkbox" id="svcEditAddToApps" checked /> Add to Desk-Pal Apps
          </label>
        </div>
      </div>

      <div style="margin-bottom:10px;">
        <label style="font-size:0.75rem; color:var(--text-dim); display:block; margin-bottom:3px;">Description:</label>
        <input type="text" id="svcEditDesc" value="${escapeHtml(tpl.description)}" style="width:100%; background:#1a1727; color:#fff; border:1px solid var(--border); border-radius:4px; padding:5px 8px; font-size:0.85rem;" />
      </div>

      <div>
        <label style="font-size:0.75rem; color:var(--text-dim); display:block; margin-bottom:3px;">Python Code (main.py):</label>
        <textarea id="svcEditCode" rows="18" style="width:100%; background:#0b0914; color:#a5f3fc; font-family:'Fira Code',Consolas,monospace; font-size:0.82rem; border:1px solid var(--border); border-radius:6px; padding:10px; line-height:1.45; resize:vertical;">${escapeHtml(tpl.code)}</textarea>
      </div>
    `;
  };

  window.applyTemplateToEditor = function (tplKey) {
    const tpl = TEMPLATES[tplKey];
    if (!tpl) return;
    document.getElementById("svcEditName").value = tpl.name;
    document.getElementById("svcEditDesc").value = tpl.description;
    document.getElementById("svcEditPort").value = tpl.port || "";
    document.getElementById("svcEditAutoStart").checked = !!tpl.auto_start;
    document.getElementById("svcEditCode").value = tpl.code;
  };

  window.editServiceCode = async function (serviceId) {
    try {
      const res = await fetch("/api/services/code?id=" + encodeURIComponent(serviceId));
      const data = await res.json();
      if (!data.success) throw new Error(data.error);

      window.openNewServiceEditor();
      const manifest = data.manifest || {};
      document.getElementById("svcEditId").value = serviceId;
      document.getElementById("svcEditId").disabled = true; // don't rename folder
      document.getElementById("svcEditName").value = manifest.name || serviceId;
      document.getElementById("svcEditDesc").value = manifest.description || "";
      document.getElementById("svcEditPort").value = manifest.port || "";
      document.getElementById("svcEditAutoStart").checked = !!manifest.auto_start;
      document.getElementById("svcEditCode").value = data.code || "";
    } catch (e) {
      alert("Could not load service code: " + e.message);
    }
  };

  window.closeServiceEditor = function () {
    const editor = document.getElementById("serviceEditorView");
    const list = document.getElementById("servicesListContainer");
    if (editor) editor.style.display = "none";
    if (list) list.style.display = "flex";
  };

  window.submitServiceEditor = async function () {
    const id = document.getElementById("svcEditId").value.trim();
    const name = document.getElementById("svcEditName").value.trim();
    const desc = document.getElementById("svcEditDesc").value.trim();
    const port = document.getElementById("svcEditPort").value.trim();
    const autoStart = document.getElementById("svcEditAutoStart").checked;
    const code = document.getElementById("svcEditCode").value;

    const addToApps = document.getElementById("svcEditAddToApps")?.checked;

    if (!id) return alert("Service ID is required");
    if (!code) return alert("Code cannot be empty");

    try {
      const res = await fetch("/api/services/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: id,
          name: name,
          description: desc,
          port: port ? parseInt(port, 10) : null,
          auto_start: autoStart,
          code: code,
          entrypoint: "main.py",
        }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);

      if (addToApps) {
        window.linkServiceToDeskpalApp(id, port ? parseInt(port, 10) : 0, name, false);
      }

      closeServiceEditor();
      refreshCompanionServices();
    } catch (e) {
      alert("Failed to save service: " + e.message);
    }
  };

  window.viewServiceLogs = function (serviceId, serviceName) {
    activeLogServiceId = serviceId;
    const logsView = document.getElementById("serviceLogsView");
    const list = document.getElementById("servicesListContainer");
    if (!logsView || !list) return;

    list.style.display = "none";
    closeServiceEditor();
    logsView.style.display = "block";

    logsView.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; border-bottom:1px solid var(--border); padding-bottom:6px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <strong style="color:#fff; font-size:0.95rem;">Live Logs: ${escapeHtml(serviceName || serviceId)}</strong>
          <span style="font-size:0.72rem; color:#10b981; animation:pulse 1.5s infinite;">● Live streaming</span>
        </div>
        <div style="display:flex; gap:6px;">
          <button class="btn" onclick="fetchAndRenderLogs('${serviceId}')" style="font-size:0.75rem; padding:2px 8px;">↻ Refresh</button>
          <button class="btn" onclick="closeServiceLogs()" style="font-size:0.75rem; padding:2px 8px;">✕ Close Logs</button>
        </div>
      </div>
      <div id="serviceLogOutput" style="background:#05040a; color:#34d399; font-family:'Fira Code',Consolas,monospace; font-size:0.8rem; padding:12px; border-radius:6px; height:340px; overflow-y:auto; line-height:1.45; white-space:pre-wrap; word-break:break-all;">Loading logs...</div>
    `;

    fetchAndRenderLogs(serviceId);
    if (activeLogPollInterval) clearInterval(activeLogPollInterval);
    activeLogPollInterval = setInterval(() => fetchAndRenderLogs(serviceId), 2000);
  };

  async function fetchAndRenderLogs(serviceId) {
    const out = document.getElementById("serviceLogOutput");
    if (!out) return;
    try {
      const res = await fetch("/api/services/logs?id=" + encodeURIComponent(serviceId) + "&lines=100");
      const data = await res.json();
      const logs = data.logs || [];
      if (logs.length === 0) {
        out.textContent = "[No logs recorded yet. Start the service to see output.]";
      } else {
        const wasAtBottom = out.scrollHeight - out.clientHeight <= out.scrollTop + 30;
        out.textContent = logs.join("\n");
        if (wasAtBottom) out.scrollTop = out.scrollHeight;
      }
    } catch (e) {
      out.textContent = "[Error fetching logs: " + e.message + "]";
    }
  }

  window.closeServiceLogs = function () {
    if (activeLogPollInterval) {
      clearInterval(activeLogPollInterval);
      activeLogPollInterval = null;
    }
    activeLogServiceId = null;
    const logsView = document.getElementById("serviceLogsView");
    const list = document.getElementById("servicesListContainer");
    if (logsView) logsView.style.display = "none";
    if (list && document.getElementById("serviceEditorView")?.style.display !== "block") {
      list.style.display = "flex";
    }
  };

  window.linkServiceToDeskpalApp = function (serviceId, port, serviceName, showAlert = true) {
    if (!window.config) return showAlert ? alert("Desk-Pal configuration not loaded yet.") : null;
    if (!window.config.apps) window.config.apps = [];

    const existing = window.config.apps.find((a) => a.id === serviceId);
    const sourceUrl = port ? `http://127.0.0.1:${port}/status` : "";
    const isWellness = serviceId === "wellness_check";

    if (existing) {
      if (sourceUrl) existing.source_url = sourceUrl;
      existing.source_enabled = !!sourceUrl;
      if (!existing.adapter || existing.adapter === "json" || isWellness) {
        existing.adapter = isWellness ? "wellness_check" : (existing.adapter || "json");
      }
      if (isWellness) {
        existing.poll_seconds = existing.poll_seconds || 15;
        existing.color = [56, 189, 248];
        const s = existing.settings || (existing.settings = {});
        if (!Array.isArray(s.days_of_week)) s.days_of_week = ["mon", "tue", "wed", "thu", "fri"];
        s.start_time = s.start_time || "09:00";
        s.end_time = s.end_time || "17:00";
        s.interval_minutes = Number(s.interval_minutes) || 45;
        s.absence_reset_minutes = Number(s.absence_reset_minutes) || 30;
        s.voice_phrase = s.voice_phrase || "Hey pal, time for a stretch and some water!";
        for (const act of (existing.actions || [])) {
          act.modal_layout = "wellness";
        }
        if (!existing.actions?.some((a) => a.id === "wellness_reminder")) {
          existing.actions = existing.actions || [];
          existing.actions.push({
            id: "wellness_reminder",
            label: "Wellness check reminder",
            event: "wellness_reminder",
            is_primary: false,
            scene: window.currentSceneId ? window.currentSceneId() : "cozy_study",
            animation: "read_paper",
            target_mode: "any",
            duration_seconds: 0,
            speech: "{wellness_message}",
            display_mode: "popup_modal",
            modal_layout: "wellness",
          });
        }
      }
      if (showAlert) alert(`Updated existing app '${existing.name}' to poll local companion service at ${sourceUrl}!`);
    } else {
      const newApp = {
        id: serviceId,
        name: serviceName || (isWellness ? "Wellness & Hydration" : serviceId),
        adapter: isWellness ? "wellness_check" : "json",
        source_url: sourceUrl,
        source_enabled: !!sourceUrl,
        poll_seconds: isWellness ? 15 : 30,
        summary_field: "summary",
        monitor_health: true,
        switch_id: 0,
        color: isWellness ? [56, 189, 248] : [0, 229, 255],
        actions: isWellness ? [
          {
            id: "status_check",
            label: "Status / button response",
            event: "status_check",
            is_primary: true,
            scene: window.currentSceneId ? window.currentSceneId() : "cozy_study",
            animation: "read_paper",
            target_mode: "any",
            duration_seconds: 0,
            speech: "{summary}",
            display_mode: "popup_modal",
            modal_layout: "wellness",
          },
          {
            id: "wellness_reminder",
            label: "Wellness check reminder",
            event: "wellness_reminder",
            is_primary: false,
            scene: window.currentSceneId ? window.currentSceneId() : "cozy_study",
            animation: "read_paper",
            target_mode: "any",
            duration_seconds: 0,
            speech: "{wellness_message}",
            display_mode: "popup_modal",
            modal_layout: "wellness",
          },
        ] : [
          {
            id: "status_check",
            label: "Status / button response",
            event: "status_check",
            is_primary: true,
            scene: window.currentSceneId ? window.currentSceneId() : "cozy_study",
            animation: "read_paper",
            target_mode: "any",
            duration_seconds: 0,
            speech: "{summary}",
            display_mode: "popup_modal",
            modal_layout: "dashboard",
          },
        ],
        integration_events: isWellness ? [
          { name: "wellness_reminder", label: "Wellness reminder notification" },
          { name: "water_goal_reached", label: "Hydration goal achieved" },
        ] : [],
      };
      if (isWellness) {
        newApp.settings = {
          days_of_week: ["mon", "tue", "wed", "thu", "fri"],
          start_time: "09:00",
          end_time: "17:00",
          interval_minutes: 45,
          absence_reset_minutes: 30,
          voice_phrase: "Hey pal, time for a stretch and some water!",
        };
      }
      window.config.apps.push(newApp);
      if (showAlert) alert(`Created new Desk-Pal App '${newApp.name}' linked to local companion service at ${sourceUrl}!`);
    }

    if (window.updateAppCountBadge) window.updateAppCountBadge();
    if (window.renderAppStudio && document.getElementById("appStudioModal")?.style.display !== "none") {
      window.renderAppStudio();
    }
    if (window.saveConfigToPi) window.saveConfigToPi();
    if (showAlert) {
      closeCompanionServicesModal();
      if (document.getElementById("btnOpenAppStudio")) {
        document.getElementById("btnOpenAppStudio").click();
      }
    }
  };

  function formatUptime(seconds) {
    if (!seconds || seconds < 1) return "just started";
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    if (m === 0) return `${s}s`;
    const h = Math.floor(m / 60);
    const remM = m % 60;
    if (h === 0) return `${m}m ${s}s`;
    return `${h}h ${remM}m`;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  window.openCalendarAppControls = function (appId) {
    if (window.closeCompanionServicesModal) {
      window.closeCompanionServicesModal();
    }
    if (typeof selectedAppId !== "undefined") {
      selectedAppId = appId || "calendar";
    }
    if (typeof appStudioSection !== "undefined") {
      appStudioSection = "connection";
    }
    if (typeof renderAppStudio === "function") {
      renderAppStudio();
    }
    const modal = document.getElementById("appStudioModal");
    if (modal) {
      modal.style.display = "flex";
    }
  };

  window.openGameAppControls = function (appId) {
    if (window.closeCompanionServicesModal) {
      window.closeCompanionServicesModal();
    }
    if (typeof selectedAppId !== "undefined") {
      selectedAppId = appId;
    }
    if (typeof appStudioSection !== "undefined") {
      appStudioSection = "connection";
    }
    if (typeof renderAppStudio === "function") {
      renderAppStudio();
    }
    const modal = document.getElementById("appStudioModal");
    if (modal) {
      modal.style.display = "flex";
    }
  };

  // Initial count update on load
  setTimeout(async () => {
    try {
      const res = await fetch("/api/services");
      if (res.ok) {
        const data = await res.json();
        const countBadge = document.getElementById("serviceCountBadge");
        if (countBadge && data.services) countBadge.textContent = data.services.length;
      }
    } catch (_) {}
  }, 1000);
})();
