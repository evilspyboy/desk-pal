# Monitored Applications & Direct Integration Guide

Desk-Pal is designed as an ambient physical output appliance. It monitors external software services and presents their progress, milestones, and alerts through character animations, in-world placements, touchscreen cards, and voice announcements.

This document details:
1. How Desk-Pal monitors external applications directly.
2. Example built-in and external monitored applications.
3. Why feeds can appear quieter than expected (network binding, duplicate suppression, endpoint routing).
4. Candidate applications for integration.
5. The standalone runnable dummy reference application (`examples/dummy_monitored_app.py`) and starter templates (`examples/companion_service_template/`, `examples/monitoring_hook_example.py`).

---

## Direct Monitoring Architecture

Desk-Pal monitors external applications directly using three native communication paths:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        DIRECT NATIVE MONITORING                        │
│                                                                        │
│  External Host / Local Network        Desk-Pal Appliance (Pi)          │
│  ┌───────────────────────┐            ┌─────────────────────────────┐  │
│  │ CI / Build Server     │ ◄───────── │ IntegrationPoller (Native)  │  │
│  │ (http://...:8090)     │ HTTP GET   │ • Periodically polls JSON   │  │
│  └───────────────────────┘            │ • Evaluates value conditions│  │
│  ┌───────────────────────┐            │ • Ingests heartbeats/events │  │
│  │ Home Assistant / IoT  │ ◄───────── │ • Triggers room reactions   │  │
│  │ (http://...:8123)     │ HTTP GET   └──────────────▲──────────────┘  │
│  └───────────────────────┘                           │                 │
│                                                      │                 │
│  On-Pi Companion Microservices                       │                 │
│  ┌──────────────────────────────────────────────┐    │                 │
│  │ CompanionSupervisor (services/)              │ ───┘ (Internal Loop) │
│  │ • Runs scripts locally on Pi (port 809x)     │                      │
│  │ • Direct loopback polling (zero PC dependency)│                      │
│  └──────────────────────────────────────────────┘                      │
└────────────────────────────────────────────────────────────────────────┘
```

### Native Monitoring Paths:
1. **The Native Direct Poller (`src/integration_poller.py`)**:
   Runs inside `deskpal_app.py` on the Pi. It polls configured `source_url` endpoints across the local network asynchronously, parses the response JSON, extracts human-readable summaries and metric fields, and registers events directly without needing any background PC tasks.
2. **On-Pi Companion Microservices (`src/companion_supervisor.py`)**:
   Lightweight scrapers and monitors run directly on the Raspberry Pi under `services/` (e.g. `services/wellness_check`, `services/calendar`), polling `127.0.0.1` locally with zero external network dependency.
3. **Push Event Ingestion (`POST /api/v1/event` / `POST /api/v1/heartbeat`)**:
   External scripts, webhooks, or coding agents (via the FastMCP adapter) push milestones directly to Desk-Pal's REST API over HTTP port 7777.

---

## Example Monitored Applications

Desk-Pal ships with built-in companion services and can monitor any local or LAN HTTP/JSON endpoint (`GET /api/telemetry`):

| Application | Name | Source | Health | Notes |
|---|---|---|---|---|
| `wellness_check` | **Wellness & Hydration** | `http://127.0.0.1:8096/status` | **Healthy** | Built-in on-Pi companion service. Tracks radar presence to credit breaks automatically during configured active hours. |
| `calendar` | **Calendar & Agenda** | `http://127.0.0.1:8097/status` | **OK** | Built-in on-Pi ICS calendar feed service. |
| `deskpal_weather` | **Weather** | Open-Meteo direct API | **Healthy** | Self-contained on-Pi weather poller. |
| `deskpal_sensors` | **Hardware Sensors** | Local Pi GPIO / Serial | **Healthy** | Onboard mmWave radar, light sensor, and IMU. |
| `ci_monitor` *(example)* | **CI / Build Pipeline** | `http://<lan-host>:8090/status` | **Healthy** | Polls or receives build pass/fail webhooks (see `examples/monitoring_hook_example.py`). |
| `home_assistant` *(example)* | **Home Assistant** | `http://<lan-host>:8123/api/` | **Healthy** | Tracks doorbells, laundry cycles, solar generation, or climate alerts. |

---

## Health Checks, Outage Detection & Auto-Recovery

Desk-Pal maintains a high standard of service awareness while avoiding false alarms:

1. **Heartbeat Suppression**:
   Routine healthy heartbeats refresh the telemetry timestamps and cache without interrupting character animations or popping up dialogs.
2. **Outage Escalation**:
   Each polled HTTP request uses a `15s` timeout with an automatic `3s` retry on transient timeouts/errors. After a `45s` startup grace period, an external service must fail `5` consecutive polled checks (or stop reporting past its stale TTL, at least `max(180s, poll_seconds * 5 + 45s)`) before Desk-Pal triggers an outage alert (`wave_arms` animation, voice notice, and status modal). Services returning either `"healthy"` or `"ok"` are treated as healthy.
3. **Automatic Alert Purging upon Recovery**:
   The moment a service reports healthy status or recovers, `receive_heartbeat()` calls `ActivityQueue.purge_app_alerts()` and `AttentionVoiceManager.purge_deferred_alerts()`. Any active or queued outage alerts for that service are immediately dismissed so the user is never bothered about a service that is already online.
4. **Voice Sentry & CPU Optimization**:
   The onboard STT engine (`voice_sentry.py`) uses radar presence gating: wake word transcription is paused when the user is away from the desk, and silence peak thresholds are calibrated (2400) so background TV or room chatter does not trigger repetitive Whisper inference loops on the CPU.

---

## Candidate Applications to Integrate

To make Desk-Pal a more active and informative desk companion, here are high-value candidate services to monitor:

### 1. Developer Workstation & CI/CD Pipelines
* **GitHub Actions / GitLab CI**: Watch branch builds or PR statuses. When a test suite passes, Desk-Pal celebrates; when a build breaks, Desk-Pal waves arms with a popup showing failed test names.
* **Coding Assistants & Autonomous Agents**: Antigravity, Cursor, or Jules reporting active tasks, research phases, and awaiting human reviews (now supported natively via [`integrations/agent-mcp/`](../integrations/agent-mcp/README.md)).

### 2. Smart Home & Local Infrastructure
* **Home Assistant / Node-RED**: Export temperature, garage door state, or energy usage. For instance, Desk-Pal walks to the fireplace rug if outdoor temperature drops below 16°C.
* **3D Printer Status (OctoPrint / Moonraker)**: Monitor print progress percentage, layer count, bed temperatures, and print completion.
* **Home Server / NAS Storage Probes**: Disk space alerts, backup completions, or high CPU temperatures.

### 3. Media & Download Monitors
* **Download Queue (qBittorrent / SABnzbd / Sonarr)**: Show items currently downloading or notify when a video download finishes and is ready in the living room.

---

## Direct Monitoring Contract (What Apps Must Expose)

For Desk-Pal to monitor an external application directly, the application needs to expose a simple, unauthenticated HTTP `GET` endpoint returning JSON.

### Recommended JSON Format (`GET /api/v1/status`)
```json
{
  "status": "healthy",
  "summary": "Worker pool idle: 4/4 nodes ready, 0 jobs pending.",
  "button_summary": "Workers: 4 Ready",
  "data": {
    "active_workers": 4,
    "items_processed": 420
  }
}
```

* `status`: `"healthy"`, `"warning"`, or `"offline"`.
* `summary`: Human-readable text displayed in Desk-Pal telemetry, thought bubbles, and popups.
* `button_summary` *(optional)*: Brief 1-line label shown when the physical hardware button is pressed.
* Custom numeric/string keys (e.g., `items_processed`): Can be mapped to conditional animation rules in App & Action Studio.

---

## Standalone Dummy Reference Application

To test and verify direct monitoring immediately without needing live production services running, a reference dummy application is provided in [`examples/dummy_monitored_app.py`](../examples/dummy_monitored_app.py).

### 1. Launch the Dummy Application
Run it on your workstation:
```bash
python examples/dummy_monitored_app.py --port 8090
```
This starts an HTTP server listening on `http://0.0.0.0:8090`.

### 2. Verify Endpoint from the Pi or Browser
Open `http://<your-pc-ip>:8090/api/v1/status` in your browser. You will receive:
```json
{
  "status": "healthy",
  "summary": "Worker pool idle: 4/4 nodes ready, 0 jobs pending.",
  "button_summary": "Workers: 4 Ready",
  "batch_id": "batch-101",
  "items_processed": 420,
  "active_workers": 4,
  "last_updated": "2026-10-22T21:45:00"
}
```

### 3. Import Definition into Desk-Pal
In Web Studio on your Pi (`http://<pi-ip>:7777`):
1. Go to **App & Action Studio → Add application**.
2. Select **Import integration file** and upload [`examples/dummy_app_integration.json`](../examples/dummy_app_integration.json).
3. Confirm the application source URL points to `http://<your-pc-ip>:8090/api/v1/status` and click **Save to Pi**.

### 4. Simulate State Changes in Real Time
You can test Desk-Pal's reaction to state changes by sending a POST request:
```bash
# Simulate a warning/failure
curl -X POST http://localhost:8090/api/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{"status": "warning", "summary": "Node 2 reported high memory threshold (92%)"}'

# Simulate recovery to healthy
curl -X POST http://localhost:8090/api/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{"status": "healthy", "summary": "Worker pool healthy: 4/4 nodes ready, 500 items completed."}'
```
Within the configured polling interval (15s), Desk-Pal will detect the changed summary, update its telemetry, and trigger the mapped character animation or popup alert.
