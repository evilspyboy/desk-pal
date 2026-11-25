"""
Desk-Pal Wellness Check & Hydration Companion Microservice
Supervised background service running on Raspberry Pi port 8096.

Features:
- Dual Mode: Uses Radar presence & absence if available; falls back to scheduled timer.
- Configurable active schedule (days of week e.g. Mon-Thu, start time e.g. 09:00, end time e.g. 15:00).
- Auto-resets sitting timer if user takes a sustained break (30 min away via radar).
- Calls native Desk-Pal POST /api/v1/notify with attention wave_arms and voice escalation ladder.
- Supplies interactive slider configuration for on-screen touch adjustment.
"""

import http.server
import json
import os
import signal
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

PORT = int(os.environ.get("PORT", 8096))
DESKPAL_HOST = "http://127.0.0.1:7777"
CONFIG_FILE = Path(__file__).parent / "config.json"

DEFAULT_SETTINGS = {
    "days_of_week": ["mon", "tue", "wed", "thu", "fri"],
    "start_time": "09:00",
    "end_time": "17:00",
    "interval_minutes": 45,
    "absence_reset_minutes": 2,
    "voice_phrase": "Hey pal, time for a stretch and some water!",
}


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    # Allow env defaults if present
    if "DAYS_OF_WEEK" in os.environ and os.environ["DAYS_OF_WEEK"].strip():
        s["days_of_week"] = [d.strip().lower() for d in os.environ["DAYS_OF_WEEK"].split(",") if d.strip()]
    if "START_TIME" in os.environ and os.environ["START_TIME"].strip():
        s["start_time"] = os.environ["START_TIME"].strip()
    if "END_TIME" in os.environ and os.environ["END_TIME"].strip():
        s["end_time"] = os.environ["END_TIME"].strip()
    if "DEFAULT_INTERVAL_MINUTES" in os.environ:
        try:
            s["interval_minutes"] = int(os.environ["DEFAULT_INTERVAL_MINUTES"])
        except ValueError:
            pass
    if "ABSENCE_RESET_MINUTES" in os.environ:
        try:
            s["absence_reset_minutes"] = int(os.environ["ABSENCE_RESET_MINUTES"])
        except ValueError:
            pass

    # Saved config file takes priority over initial defaults
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                s.update(json.load(f))
        except Exception as e:
            print(f"[Wellness] Error reading config.json: {e}", flush=True)
    return s


def save_settings(new_s):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(new_s, f, indent=2)
    except Exception as e:
        print(f"[Wellness] Error saving config.json: {e}", flush=True)


class WellnessMonitor:
    def __init__(self):
        self.settings = load_settings()
        self.lock = threading.RLock()
        self.started_at = time.time()
        self.consecutive_sitting_seconds = 0
        self.consecutive_absence_seconds = 0
        self.last_alert_time = time.time()
        self.mode = "timer"
        self.radar_available = False
        self.running = True

    def is_within_schedule(self):
        now = datetime.now()
        day_str = now.strftime("%a")[:3].lower()
        if day_str not in self.settings.get("days_of_week", []):
            return False
        current_hm = now.strftime("%H:%M")
        start = self.settings.get("start_time", "00:00")
        end = self.settings.get("end_time", "23:59")
        return start <= current_hm <= end

    def check_hardware_radar(self):
        # 1. Prefer Desk-Pal native /api/v1/presence which filters to desk presence_range_m (2.0m) with jump rejection
        try:
            url = f"{DESKPAL_HOST}/api/v1/presence"
            req = urllib.request.Request(url, headers={"User-Agent": "WellnessCheck/1.0"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("radar_enabled", False):
                self.radar_available = True
                is_pres = bool(data.get("present", False))
                self.last_user_present = is_pres
                return True, is_pres
        except Exception:
            pass

        # 2. Fallback to /api/hardware with explicit distance filtering (distance <= presence_range_m * 1000)
        url = f"{DESKPAL_HOST}/api/hardware"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "WellnessCheck/1.0"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            radar = data.get("radar", {})
            radar_settings = data.get("settings", {}).get("radar", {})
            enabled = bool(radar_settings.get("enabled", False))
            state = radar.get("state", "unavailable")
            if enabled and state in ("receiving", "live"):
                self.radar_available = True
                max_range_mm = float(radar_settings.get("presence_range_m", 2.0)) * 1000.0
                targets = radar.get("targets", [])
                nearby = [t for t in targets if t.get("distance_mm", 99999) <= max_range_mm]
                is_pres = len(nearby) > 0
                self.last_user_present = is_pres
                return True, is_pres
            self.radar_available = False
            self.last_user_present = False
            return False, False
        except Exception:
            self.radar_available = False
            self.last_user_present = False
            return False, False

    def sync_from_deskpal(self):
        url = f"{DESKPAL_HOST}/api/config"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "WellnessCheck/1.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                cfg = json.loads(resp.read().decode("utf-8"))
            apps = cfg.get("apps", [])
            w_app = next((a for a in apps if a.get("id") == "wellness_check"), None)
            if w_app and isinstance(w_app.get("settings"), dict):
                s = w_app["settings"]
                changed = False
                for k in ("days_of_week", "start_time", "end_time", "interval_minutes", "absence_reset_minutes", "voice_phrase"):
                    if k in s and s[k] != self.settings.get(k):
                        self.settings[k] = s[k]
                        changed = True
                if changed:
                    print(f"[Wellness] Synced settings from Desk-Pal room config: {self.settings}", flush=True)
                    save_settings(self.settings)
        except Exception:
            pass

    def trigger_alert(self, reason="sitting_interval"):
        print(f"[Wellness] Triggering wellness alert ({reason})...", flush=True)
        interval = max(15, min(180, int(self.settings.get("interval_minutes", 45))))
        payload = {
            "app_id": "wellness_check",
            "event": "wellness_reminder",
            "title": "WELLNESS & HYDRATION",
            "summary": "Time for a quick stretch and some water! 💧\n• Stand up & roll your shoulders\n• Drink a tall glass of fresh water\n• Rest your eyes: look 6 metres away for 20s",
            "layout": "wellness",
            "badge": "HYDRATE",
            "color": [56, 189, 248],
            "attention": True,
            "voice_escalation": True,
            "voice_phrase": self.settings.get("voice_phrase", "Hey pal, time for a stretch and some water!"),
            "animation": "wave_arms",
            "wellness": {
                "metric": True,
                "eye_rule_meters": 6,
                "eye_rule_seconds": 20
            },
            "slider": {
                "label": "Next reminder in",
                "min": 15,
                "max": 120,
                "step": 5,
                "value": interval,
                "unit": "min",
                "callback_url": f"http://127.0.0.1:{PORT}/set_next_timer"
            }
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{DESKPAL_HOST}/api/v1/notify",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            self.last_alert_time = time.time()
            self.consecutive_sitting_seconds = 0
            print(f"[Wellness] Alert dispatched to Desk-Pal: {result}", flush=True)
            return True
        except Exception as e:
            print(f"[Wellness] Failed to dispatch alert: {e}", flush=True)
            return False

    def loop(self):
        print(f"[Wellness] Monitor loop started. Active days: {self.settings['days_of_week']}, Window: {self.settings['start_time']} - {self.settings['end_time']}", flush=True)
        ticks = 0
        presence_streak = 0
        while self.running:
            time.sleep(5)
            ticks += 1
            if ticks % 2 == 0:
                self.sync_from_deskpal()
            with self.lock:
                has_radar, user_present = self.check_hardware_radar()
                self.mode = "radar" if has_radar else "timer"

                if not self.is_within_schedule():
                    self.consecutive_sitting_seconds = 0
                    self.consecutive_absence_seconds = 0
                    presence_streak = 0
                    continue

                if has_radar:
                    if user_present:
                        presence_streak += 5
                        # Only wipe away accumulated absence if the user has returned and stayed at the desk for at least 15s
                        if presence_streak >= 15:
                            self.consecutive_absence_seconds = 0
                        self.consecutive_sitting_seconds += 5
                    else:
                        presence_streak = 0
                        self.consecutive_absence_seconds += 5
                        reset_threshold = max(30.0, float(self.settings.get("absence_reset_minutes", 2)) * 60.0)
                        if self.consecutive_absence_seconds >= reset_threshold and self.consecutive_sitting_seconds > 0:
                            print(f"[Wellness] User away from desk for {int(self.consecutive_absence_seconds // 60)}m (threshold {reset_threshold/60:.1f}m). Natural break credited! Sitting timer reset.", flush=True)
                            self.consecutive_sitting_seconds = 0
                else:
                    self.mode = "timer"
                    self.consecutive_sitting_seconds += 5

                target_seconds = max(15, int(self.settings.get("interval_minutes", 45))) * 60
                # Must accumulate full sitting interval and must have passed startup grace period
                if self.consecutive_sitting_seconds >= target_seconds and (time.time() - self.started_at) >= target_seconds:
                    self.trigger_alert(reason="interval_reached")


monitor = WellnessMonitor()


class WellnessHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/status" or self.path == "/":
            with monitor.lock:
                target_sec = monitor.settings.get("interval_minutes", 45) * 60
                remaining_sec = max(0, target_sec - monitor.consecutive_sitting_seconds)
                rem_m = round(remaining_sec / 60.0, 1)
                sit_m = round(monitor.consecutive_sitting_seconds / 60.0, 1)
                sched_str = "Active window" if monitor.is_within_schedule() else "Outside active hours"
                summary = f"Next reminder in {rem_m}m · Sitting: {sit_m}m ({sched_str})"
                payload = {
                    "status": "healthy",
                    "app_id": "wellness_check",
                    "name": "Wellness & Hydration Monitor",
                    "mode": monitor.mode,
                    "radar_available": monitor.radar_available,
                    "within_schedule": monitor.is_within_schedule(),
                    "sitting_minutes": sit_m,
                    "user_present": getattr(monitor, "last_user_present", False),
                    "absence_minutes": round(monitor.consecutive_absence_seconds / 60.0, 1),
                    "interval_minutes": monitor.settings.get("interval_minutes", 45),
                    "absence_reset_minutes": monitor.settings.get("absence_reset_minutes", 2),
                    "next_reminder_in_minutes": rem_m,
                    "summary": summary,
                    "activity": f"Wellness ({monitor.mode.title()}): {rem_m}m to break",
                    "button_summary": f"Break: {rem_m}m",
                    "badge": "HYDRATE" if monitor.is_within_schedule() else "OFF",
                    "dashboard": {
                        "hero_value": f"{rem_m} min",
                        "hero_subhead": f"Next stretch & water break ({monitor.mode.title()} mode)",
                        "badge": "ACTIVE" if monitor.is_within_schedule() else "OFF HOURS",
                        "badge_color": "#38bdf8" if monitor.is_within_schedule() else "#94a3b8",
                        "tiles": [
                            {"label": "SITTING TIME", "value": f"{sit_m} min"},
                            {"label": "INTERVAL", "value": f"{monitor.settings.get('interval_minutes', 45)} min"},
                            {"label": "SCHEDULE", "value": f"{monitor.settings.get('start_time','09:00')}–{monitor.settings.get('end_time','17:00')}"},
                            {"label": "RADAR TRACK", "value": "Present" if monitor.radar_available else "Timer Mode"}
                        ]
                    },
                    "settings": monitor.settings,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
                }
            self._send_json(payload)
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            data = {}

        if self.path == "/set_next_timer":
            minutes = data.get("minutes") or data.get("value")
            if minutes is not None:
                try:
                    m_val = max(5, min(180, int(minutes)))
                    with monitor.lock:
                        monitor.settings["interval_minutes"] = m_val
                        monitor.consecutive_sitting_seconds = 0
                        save_settings(monitor.settings)
                    print(f"[Wellness] Next reminder interval set to {m_val} minutes from slider.", flush=True)
                    self._send_json({"status": "ok", "interval_minutes": m_val})
                    return
                except Exception as e:
                    self.send_error(400, f"Invalid minutes: {e}")
                    return
            self.send_error(400, "Missing 'minutes' parameter")

        elif self.path == "/trigger":
            success = monitor.trigger_alert(reason="manual_trigger")
            self._send_json({"status": "triggered" if success else "failed"})

        elif self.path == "/settings":
            with monitor.lock:
                for k in ("days_of_week", "start_time", "end_time", "interval_minutes", "absence_reset_minutes", "voice_phrase"):
                    if k in data:
                        monitor.settings[k] = data[k]
                save_settings(monitor.settings)
            self._send_json({"status": "saved", "settings": monitor.settings})

        else:
            self.send_error(404, "Not Found")

    def _send_json(self, payload):
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        # Clean logging for Desk-Pal supervisor
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]} - {args[1]}", flush=True)


def run():
    print(f"💧 Desk-Pal Wellness Check Microservice starting on port {PORT}...", flush=True)
    t = threading.Thread(target=monitor.loop, daemon=True)
    t.start()

    server = http.server.HTTPServer(("0.0.0.0", PORT), WellnessHandler)

    def shutdown(signum, frame):
        print("Shutting down Wellness Check...", flush=True)
        monitor.running = False
        server.server_close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
