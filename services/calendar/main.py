"""
Desk-Pal Calendar & Daily Agenda Companion Service
Supervised background microservice running on Raspberry Pi port 8097.

Zero-Cloud-Project Architecture:
- Uses Google Calendar's built-in "Secret address in iCal format" (.ics)
  or standard Apple iCloud, Outlook, Fastmail, or Nextcloud iCal feeds.
- No developer console, no OAuth consent screens, no expiring tokens.
- Parses today's agenda locally, calculates upcoming events, and provides
  telemetry directly to Desk-Pal for the Good Morning card and spoken briefing.
"""

import http.server
import json
import os
import re
import signal
import sys
import threading
import time
import urllib.request
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

PORT = int(os.environ.get("PORT", 8097))
DESKPAL_HOST = os.environ.get("DESKPAL_HOST", "http://127.0.0.1:7777")
SERVICE_DIR = Path(__file__).parent
CONFIG_FILE = SERVICE_DIR / "config.json"

# State
state_lock = threading.Lock()
calendar_state = {
    "configured": False,
    "status": "not_configured",  # "ok", "not_configured", "error"
    "message": "Calendar feed URL not configured.",
    "last_synced": None,
    "last_error": None,
    "events_today": [],
    "events_tomorrow": [],
    "events_count": 0,
    "has_events": False,
    "agenda_text": "Today: No calendar configured",
    "spoken_summary": "No calendar configured.",
    "next_event": None
}


def load_config():
    cfg = {"feed_url": "", "poll_interval_minutes": 15}
    # 1. First check room_config.json on Desk-Pal
    for p in ["/home/admin/config/room_config.json", "config/room_config.json", str(SERVICE_DIR.parent.parent / "config" / "room_config.json")]:
        path_obj = Path(p)
        if path_obj.exists():
            try:
                data = json.loads(path_obj.read_text(encoding="utf-8"))
                for a in data.get("apps", []):
                    if a.get("id") == "calendar" and a.get("settings"):
                        s = a["settings"]
                        if s.get("feed_url"):
                            cfg["feed_url"] = s["feed_url"].strip()
                        if s.get("poll_interval_minutes"):
                            cfg["poll_interval_minutes"] = int(s["poll_interval_minutes"])
                        break
            except Exception:
                pass

    # 2. Local config.json override
    if CONFIG_FILE.exists():
        try:
            local_cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if local_cfg.get("feed_url"):
                cfg["feed_url"] = local_cfg["feed_url"].strip()
            if local_cfg.get("poll_interval_minutes"):
                cfg["poll_interval_minutes"] = int(local_cfg["poll_interval_minutes"])
        except Exception as e:
            print(f"[Calendar] Error loading config.json: {e}")
    return cfg


def save_config(cfg):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print(f"[Calendar] Error saving config.json: {e}")
        return False


def unfold_ical_lines(raw_text):
    """RFC 5545 line unfolding: lines starting with space or tab continue previous line."""
    lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    unfolded = []
    for line in lines:
        if (line.startswith(" ") or line.startswith("\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def parse_ical_datetime(val_str, default_tz=None):
    """Parse iCal date or datetime string into datetime object."""
    val = val_str.strip()
    is_date_only = False
    
    # Check for parameters like TZID=...:20261027T100000
    if ":" in val:
        val = val.split(":")[-1]
    
    # Date only format: YYYYMMDD
    if len(val) == 8 and val.isdigit():
        dt = datetime.strptime(val, "%Y%m%d")
        return dt, True
        
    # Date-time UTC: YYYYMMDDTHHMMSSZ
    if val.endswith("Z"):
        try:
            dt = datetime.strptime(val, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            # Convert to local time
            local_dt = dt.astimezone()
            return local_dt.replace(tzinfo=None), False
        except Exception:
            pass

    # Date-time without Z (or local floating)
    if "T" in val:
        clean = val[:15]
        try:
            dt = datetime.strptime(clean, "%Y%m%dT%H%M%S")
            return dt, False
        except Exception:
            pass

    return None, False


def clean_summary(text):
    """Unescape iCal summary characters."""
    if not text:
        return ""
    text = text.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ").replace("\\N", " ").replace("\\\\", "\\")
    return text.strip()


def parse_ical_feed(raw_text, target_date=None):
    """
    Parse an iCalendar (.ics) feed and extract events for target_date and the next 14 days.
    Supports single events, all-day events, and recurring events (RRULE).
    """
    if target_date is None:
        target_date = date.today()
    
    max_days_ahead = 14
    check_dates = [target_date + timedelta(days=i) for i in range(max_days_ahead + 1)]
    
    lines = unfold_ical_lines(raw_text)
    
    occurrences = []
    in_vevent = False
    cur_event = {}
    
    for line in lines:
        line_s = line.strip()
        if line_s == "BEGIN:VEVENT":
            in_vevent = True
            cur_event = {}
            continue
        elif line_s == "END:VEVENT":
            if in_vevent and cur_event.get("dtstart"):
                summary = clean_summary(cur_event.get("summary", "Untitled Event"))
                dt_start, is_all_day = cur_event["dtstart"]
                dt_end = cur_event.get("dtend", (None, False))[0]
                rrule = cur_event.get("rrule", "")
                
                # Check for each check_date in 0..14
                for offset, d in enumerate(check_dates):
                    matched = False
                    
                    if not rrule:
                        if dt_start.date() == d:
                            matched = True
                        elif dt_end and dt_start.date() <= d < dt_end.date():
                            matched = True
                    else:
                        if dt_start.date() <= d:
                            if "FREQ=DAILY" in rrule:
                                matched = True
                            elif "FREQ=WEEKLY" in rrule:
                                if "BYDAY=" in rrule:
                                    bydays = rrule.split("BYDAY=")[-1].split(";")[0].split(",")
                                    w = d.strftime("%a")[:2].upper()
                                    if w in bydays:
                                        matched = True
                                elif dt_start.weekday() == d.weekday():
                                    matched = True
                            elif "FREQ=MONTHLY" in rrule:
                                if dt_start.day == d.day:
                                    matched = True
                            elif "FREQ=YEARLY" in rrule:
                                if dt_start.month == d.month and dt_start.day == d.day:
                                    matched = True
                                    
                    if matched:
                        time_str = "All Day" if is_all_day else dt_start.strftime("%I:%M %p").lstrip("0")
                        occurrences.append({
                            "summary": summary,
                            "time": time_str,
                            "date": d.isoformat(),
                            "weekday": d.strftime("%A"),
                            "weekday_short": d.strftime("%a"),
                            "days_ahead": offset,
                            "start_dt": dt_start,
                            "all_day": is_all_day
                        })
                        
            in_vevent = False
            cur_event = {}
            continue
            
        if not in_vevent:
            continue
            
        if line_s.startswith("SUMMARY:"):
            cur_event["summary"] = line_s[8:]
        elif line_s.startswith("DTSTART"):
            dt, is_all_day = parse_ical_datetime(line_s)
            if dt:
                cur_event["dtstart"] = (dt, is_all_day)
        elif line_s.startswith("DTEND"):
            dt, is_all_day = parse_ical_datetime(line_s)
            if dt:
                cur_event["dtend"] = (dt, is_all_day)
        elif line_s.startswith("RRULE:"):
            cur_event["rrule"] = line_s[6:]

    def event_sort_key(ev):
        s_dt = ev.get("start_dt")
        if isinstance(s_dt, str):
            try:
                s_dt = datetime.fromisoformat(s_dt)
            except Exception:
                s_dt = datetime.min
        t = s_dt.time() if (s_dt and not ev.get("all_day")) else datetime.min.time()
        return (ev.get("days_ahead", 0), 0 if ev.get("all_day") else 1, t.hour, t.minute)

    occurrences.sort(key=event_sort_key)
    
    for ev in occurrences:
        if isinstance(ev.get("start_dt"), (datetime, date)):
            ev["start_dt"] = ev["start_dt"].isoformat()
    
    events_today = [ev for ev in occurrences if ev["days_ahead"] == 0]
    upcoming_events = [ev for ev in occurrences if ev["days_ahead"] > 0]
    
    return events_today, upcoming_events


def sync_calendar():
    global calendar_state
    cfg = load_config()
    feed_url = cfg.get("feed_url", "").strip()
    
    if not feed_url:
        with state_lock:
            calendar_state.update({
                "configured": False,
                "status": "not_configured",
                "message": "Calendar feed URL not configured.",
                "events_today": [],
                "events_tomorrow": [],
                "events_count": 0,
                "has_events": False,
                "agenda_text": "Today: No calendar configured",
                "spoken_summary": "Calendar feed not configured.",
                "next_event": None
            })
        return
        
    try:
        # Convert webcal:// to https://
        if feed_url.startswith("webcal://"):
            feed_url = "https://" + feed_url[9:]
            
        req = urllib.request.Request(
            feed_url,
            headers={"User-Agent": "DeskPal-Calendar/1.0 (RaspberryPi; Linux)"}
        )
        
        with urllib.request.urlopen(req, timeout=12) as response:
            raw_data = response.read().decode("utf-8", errors="replace")
            
        today = date.today()
        events_today, upcoming_events = parse_ical_feed(raw_data, today)
        
        days_until_sunday = 6 - today.weekday()
        # Lookahead: next few days is 3 days (covers Mon->Thu, Fri->Mon, etc.)
        max_lookahead = 4 if today.weekday() == 3 else 3
        
        upcoming_in_window = [ev for ev in upcoming_events if ev["days_ahead"] <= max_lookahead]
        this_week_events = [ev for ev in upcoming_events if ev["days_ahead"] <= days_until_sunday]
        
        count = len(events_today)
        has_events = count > 0
        
        if has_events:
            items = []
            for ev in events_today[:3]:
                if ev.get("all_day"):
                    items.append(ev["summary"])
                else:
                    items.append(f"{ev['time']} {ev['summary']}")
            line1 = "Today: " + " · ".join(items)
            
            speech_items = []
            for ev in events_today[:4]:
                if ev.get("all_day"):
                    speech_items.append(f"{ev['summary']} all day")
                else:
                    speech_items.append(f"{ev['time']}, {ev['summary']}")
            spoken_summary = f"You have {count} event{'s' if count != 1 else ''} on your calendar today: " + ", and ".join(speech_items)
            
            first_ev = events_today[0]
            t_str = "All Day" if first_ev.get("all_day") else first_ev.get("time", "")
            next_ev = {
                "summary": first_ev["summary"],
                "time": t_str,
                "time_str": t_str,
                "all_day": first_ev.get("all_day", False),
                "days_ahead": 0
            }
            if count > 1:
                line2 = f"Next: {t_str} · {first_ev['summary']}"
            else:
                line2 = f"Time: {t_str} · {first_ev['summary']}"
                
        elif upcoming_in_window:
            first_up = upcoming_in_window[0]
            days = first_up["days_ahead"]
            if days == 1:
                day_lbl = "Tomorrow"
                spoken_day = "tomorrow"
            else:
                day_lbl = first_up.get("weekday_short", "")
                spoken_day = f"this {first_up.get('weekday', '')}" if first_up.get('weekday') != "Monday" else "on Monday"
                
            line1 = "Today: Nothing on"
            time_str = "All Day" if first_up.get("all_day") else first_up.get("time", "")
            line2 = f"Next: {day_lbl} {time_str} · {first_up['summary']}" if time_str != "All Day" else f"Next: {day_lbl} · {first_up['summary']}"
            next_ev = {
                "summary": first_up["summary"],
                "time": f"{day_lbl} {time_str}",
                "time_str": f"{day_lbl} {time_str}",
                "all_day": first_up.get("all_day", False),
                "days_ahead": days
            }
            time_speech = "all day" if first_up.get("all_day") else f"at {first_up['time']}"
            spoken_summary = f"You have nothing on today. Your next event is {spoken_day}: {first_up['summary']} {time_speech}."
            
        elif this_week_events:
            first_up = this_week_events[0]
            line1 = "Today: Nothing on"
            time_str = "All Day" if first_up.get("all_day") else first_up.get("time", "")
            day_lbl = first_up.get("weekday_short", "")
            line2 = f"Next: {day_lbl} {time_str} · {first_up['summary']}" if time_str != "All Day" else f"Next: {day_lbl} · {first_up['summary']}"
            next_ev = {
                "summary": first_up["summary"],
                "time": f"{day_lbl} {time_str}",
                "time_str": f"{day_lbl} {time_str}",
                "all_day": first_up.get("all_day", False),
                "days_ahead": first_up["days_ahead"]
            }
            time_speech = "all day" if first_up.get("all_day") else f"at {first_up['time']}"
            spoken_summary = f"You have nothing on today. Your next event this week is on {first_up.get('weekday', '')}: {first_up['summary']} {time_speech}."
            
        else:
            line1 = "Today: Nothing on"
            line2 = "This Week: Nothing scheduled"
            spoken_summary = "You have nothing scheduled this week."
            next_ev = None
            
        agenda_text = line1
            
        with state_lock:
            calendar_state.update({
                "configured": True,
                "current_feed_url": feed_url,
                "status": "ok",
                "message": "Calendar synced successfully.",
                "last_synced": datetime.now().isoformat(timespec="seconds"),
                "last_error": None,
                "events_today": events_today,
                "events_tomorrow": [ev for ev in upcoming_events if ev["days_ahead"] == 1],
                "upcoming_events": upcoming_events[:8],
                "events_count": count,
                "has_events": has_events,
                "line1": line1,
                "line2": line2,
                "agenda_text": agenda_text,
                "spoken_summary": spoken_summary,
                "next_event": next_ev
            })
            
        print(f"[Calendar] Synced successfully: {count} events today ({datetime.now().strftime('%H:%M:%S')})")
        
    except Exception as e:
        err_msg = str(e)
        print(f"[Calendar] Sync failed: {err_msg}")
        with state_lock:
            calendar_state["status"] = "error"
            calendar_state["last_error"] = err_msg
            calendar_state["message"] = f"Failed to fetch calendar: {err_msg}"


def background_poller():
    """Periodically sync calendar in background."""
    while True:
        try:
            sync_calendar()
        except Exception as e:
            print(f"[Calendar Poller] Exception: {e}")
        
        cfg = load_config()
        interval = max(5, int(cfg.get("poll_interval_minutes", 15))) * 60
        time.sleep(interval)


# HTML Dashboard Template
HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Desk-Pal Calendar Companion</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #120e24;
      --surface: #1e1935;
      --surface-light: #2c254d;
      --border: #3d3568;
      --primary: #f0a050;
      --accent: #38bdf8;
      --green: #2ecc71;
      --red: #e74c3c;
      --text: #f1f5f9;
      --text-dim: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Outfit', -apple-system, sans-serif;
      padding: 24px 16px;
      display: flex;
      justify-content: center;
      min-height: 100vh;
    }
    .container {
      width: 100%;
      max-width: 680px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    .header {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 20px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .header-title h1 {
      font-size: 1.4rem;
      font-weight: 800;
      color: var(--primary);
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .header-title p {
      font-size: 0.85rem;
      color: var(--text-dim);
      margin-top: 4px;
    }
    .status-badge {
      font-size: 0.75rem;
      font-weight: 700;
      padding: 6px 14px;
      border-radius: 20px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .status-ok { background: rgba(46, 204, 113, 0.2); color: var(--green); border: 1px solid var(--green); }
    .status-not_configured { background: rgba(240, 160, 80, 0.2); color: var(--primary); border: 1px solid var(--primary); }
    .status-error { background: rgba(231, 76, 60, 0.2); color: var(--red); border: 1px solid var(--red); }
    
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
    }
    .card h2 {
      font-size: 1.1rem;
      font-weight: 700;
      margin-bottom: 12px;
      color: var(--accent);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .help-box {
      background: rgba(56, 189, 248, 0.08);
      border: 1px solid rgba(56, 189, 248, 0.3);
      border-radius: 12px;
      padding: 14px 18px;
      font-size: 0.88rem;
      color: #bae6fd;
      line-height: 1.5;
      margin-bottom: 18px;
    }
    .help-box ol { margin-left: 20px; margin-top: 6px; }
    .help-box li { margin-bottom: 4px; }
    
    .form-group {
      margin-bottom: 16px;
    }
    label {
      display: block;
      font-size: 0.85rem;
      font-weight: 600;
      margin-bottom: 6px;
      color: var(--text);
    }
    input[type="text"] {
      width: 100%;
      background: var(--bg);
      border: 1px solid var(--border);
      color: #fff;
      padding: 12px 14px;
      border-radius: 10px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      outline: none;
      transition: border 0.2s;
    }
    input[type="text"]:focus {
      border-color: var(--accent);
    }
    .btn-row {
      display: flex;
      gap: 12px;
      margin-top: 18px;
    }
    button {
      flex: 1;
      padding: 12px;
      border-radius: 10px;
      font-weight: 700;
      font-size: 0.95rem;
      cursor: pointer;
      border: none;
      transition: transform 0.1s, opacity 0.2s;
    }
    button:active { transform: scale(0.98); }
    .btn-primary { background: var(--primary); color: #120e24; }
    .btn-secondary { background: var(--surface-light); color: var(--text); border: 1px solid var(--border); }
    
    .events-list {
      margin-top: 14px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .event-item {
      background: var(--surface-light);
      border: 1px solid var(--border);
      border-left: 4px solid var(--accent);
      border-radius: 10px;
      padding: 12px 16px;
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .event-time {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--accent);
      min-width: 80px;
    }
    .event-summary {
      font-size: 0.95rem;
      font-weight: 600;
      color: #fff;
    }
    .no-events {
      padding: 24px;
      text-align: center;
      color: var(--text-dim);
      font-size: 0.95rem;
    }
    .toast {
      padding: 10px 16px;
      border-radius: 8px;
      font-size: 0.85rem;
      font-weight: 600;
      margin-top: 12px;
      display: none;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="header-title">
        <h1>📅 Desk-Pal Calendar</h1>
        <p>Private Agenda & Schedule Companion Microservice</p>
      </div>
      <div id="statusBadge" class="status-badge status-not_configured">Loading...</div>
    </div>

    <!-- Feed Configuration Card -->
    <div class="card">
      <h2>⚙️ Calendar Feed Setup</h2>
      <div class="help-box">
        <strong>How to find your Google Calendar secret link (No GCP Project Needed):</strong>
        <ol>
          <li>Open <a href="https://calendar.google.com" target="_blank" style="color:#38bdf8;">Google Calendar</a> on your computer.</li>
          <li>In the left sidebar, hover over your calendar, click the <strong>3 dots</strong> &rarr; <strong>Settings and sharing</strong>.</li>
          <li>Scroll down to <strong>"Secret address in iCal format"</strong> and copy the URL.</li>
          <li>Paste the link below and click <strong>Save &amp; Sync Now</strong>.</li>
        </ol>
      </div>

      <div class="form-group">
        <label for="feedUrl">Private iCal Secret Feed URL (.ics)</label>
        <input type="text" id="feedUrl" placeholder="https://calendar.google.com/calendar/ical/.../basic.ics">
      </div>

      <div class="btn-row">
        <button class="btn-primary" onclick="saveConfig()">Save &amp; Sync Now</button>
        <button class="btn-secondary" onclick="forceSync()">Force Refresh</button>
      </div>
      <div id="toast" class="toast"></div>
    </div>

    <!-- Live Agenda Preview Card -->
    <div class="card">
      <h2>📋 Today's Schedule Preview</h2>
      <div id="agendaPreview" class="events-list">
        <div class="no-events">Loading events...</div>
      </div>
    </div>
  </div>

  <script>
    async function loadStatus() {
      try {
        const res = await fetch('/status');
        const data = await res.json();
        
        const badge = document.getElementById('statusBadge');
        badge.className = 'status-badge status-' + (data.status || 'not_configured');
        badge.innerText = data.status === 'ok' ? 'Connected' : (data.status === 'error' ? 'Sync Error' : 'Not Configured');

        if (data.configured && data.feed_url) {
          document.getElementById('feedUrl').value = data.feed_url;
        }

        const preview = document.getElementById('agendaPreview');
        if (!data.configured) {
          preview.innerHTML = '<div class="no-events">Please paste your private iCal link above to load events.</div>';
        } else if (!data.has_events || data.events_today.length === 0) {
          preview.innerHTML = '<div class="no-events">🎉 No scheduled events today. Your calendar is clear!</div>';
        } else {
          preview.innerHTML = data.events_today.map(ev => `
            <div class="event-item">
              <div class="event-time">${ev.time}</div>
              <div class="event-summary">${ev.summary}</div>
            </div>
          `).join('');
        }
      } catch (e) {
        console.error("Failed to load status:", e);
      }
    }

    async function saveConfig() {
      const url = document.getElementById('feedUrl').value.trim();
      const toast = document.getElementById('toast');
      try {
        const res = await fetch('/api/v1/config', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ feed_url: url })
        });
        const data = await res.json();
        toast.style.display = 'block';
        if (data.status === 'ok') {
          toast.style.background = 'rgba(46, 204, 113, 0.2)';
          toast.style.color = '#2ecc71';
          toast.style.border = '1px solid #2ecc71';
          toast.innerText = 'Settings saved and calendar synced!';
          await loadStatus();
        } else {
          toast.style.background = 'rgba(231, 76, 60, 0.2)';
          toast.style.color = '#e74c3c';
          toast.style.border = '1px solid #e74c3c';
          toast.innerText = data.error || 'Failed to save settings.';
        }
      } catch (e) {
        toast.style.display = 'block';
        toast.style.background = 'rgba(231, 76, 60, 0.2)';
        toast.style.color = '#e74c3c';
        toast.innerText = 'Network error saving config: ' + e;
      }
      setTimeout(() => { toast.style.display = 'none'; }, 4000);
    }

    async function forceSync() {
      await fetch('/api/v1/sync', { method: 'POST' });
      await loadStatus();
    }

    loadStatus();
    setInterval(loadStatus, 10000);
  </script>
</body>
</html>
"""


class CalendarHTTPHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Quiet logging

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return

        elif self.path in ("/status", "/api/v1/status"):
            cfg = load_config()
            feed_url = cfg.get("feed_url", "").strip()
            with state_lock:
                needs_sync = bool(feed_url and (calendar_state.get("last_synced") is None or calendar_state.get("current_feed_url") != feed_url))
            if needs_sync:
                try:
                    sync_calendar()
                except Exception:
                    pass
            with state_lock:
                resp = dict(calendar_state)
                resp["feed_url"] = feed_url
                
            payload = json.dumps(resp, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == "/api/v1/config":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                feed_url = body.get("feed_url", "").strip()
                
                cfg = load_config()
                cfg["feed_url"] = feed_url
                save_config(cfg)
                
                # Immediate sync
                sync_calendar()
                
                resp = json.dumps({"status": "ok"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                self.send_error(400, f"Error saving config: {e}")
            return

        elif self.path == "/api/v1/sync":
            sync_calendar()
            resp = json.dumps({"status": "ok"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
            return

        self.send_error(404, "Not Found")


def run_service():
    print(f"[Calendar] Starting Desk-Pal Calendar companion microservice on port {PORT}...")
    
    # Start background poller thread
    poller = threading.Thread(target=background_poller, daemon=True)
    poller.start()
    
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), CalendarHTTPHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_service()
