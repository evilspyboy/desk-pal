# Desk-Pal REST API Reference

Desk-Pal exposes a lightweight HTTP REST API on port `7777` (`http://<deskpal-ip>:7777`) for external integrations, smart home hubs (Home Assistant, Node-RED), and local scripts.

All endpoints support CORS preflight (`OPTIONS`), receive and return standard `application/json`.

---

## Quick Reference Table

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/agent/capabilities` | Dynamic self-describing introspection: scenes, spots, props, animations catalog, functions schema, services, voices, sensors, etiquette. |
| `GET` | `/api/v1/world` | Real-time spatial world snapshot: active scene, character position (x, y), facing, current animation, radar presence, and all scene spots. |
| `GET` | `/api/v1/status` | Current character, scene, animation state, radar presence, and queue depth. |
| `GET` | `/api/v1/presence` | Radar sensor status, presence detection flag, target count, and distances. |
| `POST` | `/api/v1/notify` | Queue an interactive attention notification with waving animation, voice ladder escalation, and tap-to-open modal dialog. |
| `POST` | `/api/v1/action` | Queue character puppeteering: scene, spot_id, x, y coordinates, animation, thought bubble, or priority override. |
| `POST` | `/api/v1/say` | Instant TTS speech synthesis with talking sprite animation. |
| `POST` | `/api/v1/scene` | Instantly switch the active scene / room. |
| `POST` | `/api/v1/display` | Put touchscreen display into standby (`sleep`) or wake it up (`wake`). |
| `POST` | `/api/scenes/travel` | Trigger an animated walking journey between rooms. |
| `GET` | `/api/services` | List all companion background services, status, and PIDs. |
| `GET` | `/api/services/logs` | Fetch real-time buffered logs for a service (`?id=...&lines=100`). |
| `GET` | `/api/services/code` | Fetch code and manifest for a service (`?id=...`). |
| `POST` | `/api/services/action` | Perform control action (`start`, `stop`, `restart`) on a service. |
| `POST` | `/api/services/save` | Save/create service code, manifest, and optionally auto-link to apps. |
| `POST` | `/api/services/delete` | Terminate and delete a companion service directory. |
| `GET` | `/api/themes` | List all available themes, metadata, and active theme profile. |
| `POST` | `/api/themes/apply` | Hot-reload visual theme (palette, cards, character, scenes, props). |
| `POST` | `/api/themes/save` | Capture current visual setup into a new named theme profile. |
| `POST` | `/api/themes/duplicate` | Clone an existing theme to a new ID and display name. |
| `POST` | `/api/themes/delete` | Permanently delete a custom theme profile. |
| `GET` | `/api/themes/export` | Download a theme package as a `.zip` archive (`?theme=<id>`). |
| `POST` | `/api/themes/import` | Upload and unpack a `.zip` or `.json` theme package. |
| `GET` | `/api/system_stats` | Real-time RAM (memory) and Disk (storage) used, available, and percentage. |
| `GET` | `/api/ai/stt/status` | Real-time Voice Sentry & STT state, loaded model, and memory footprint. |
| `POST` | `/api/ai/stt/listen` | Start active listening mode (shows animated mic bubble above sprite). |
| `POST` | `/api/ai/stt/stop` | Stop listening mode and transcribe captured speech. |
| `POST` | `/api/ai/stt/test` | Record 5s from USB mic and transcribe with benchmark telemetry. |

---

## Attention Ladder & Voice Timing Architecture

Desk-Pal is designed for low-power edge hardware (such as Raspberry Pi 4/5 or Zero 2W).
Piper neural TTS generation on the Pi CPU can take 2–5 seconds depending on model size and sentence length.

### Dynamic Generation Delay Handling
Rather than relying on fixed wall-clock timers that collide when TTS generation is slow, Desk-Pal tracks true audio playback state:
1. **Busy State Protection (`is_speech_busy`)**: Checks if Piper is actively synthesizing audio in its background thread or actively streaming PCM samples to the speaker.
2. **Post-Speech Silence Tracking (`last_speech_finished_at`)**: Escalation phases measure silence *after* speech finishes playing, guaranteeing natural conversational pauses.
3. **Escalation Ladder**:
   - **Phase 1**: Initial announcement (`voice_phrase`, e.g. *"Hey, I have a fuel update!"*) + waving arm animation (`wave_arms`).
   - **Phase 2**: If no touch interaction after 24s of silence: *"Hey, it's me, your pal."*
   - **Phase 3**: If still no touch interaction after 52s: *"Hello? Over here!"*
   - **Dismissal**: If tapped on screen, the SCUMM modal dialog opens with details, and the voice ladder immediately cancels. If unattended, the notification gracefully times out (90s with radar, 45s without).
4. **`keep_loaded` Dynamic Offset**:
   - If `tts.keep_loaded` is **`true`**: The ONNX model stays resident in RAM (~222 MB), and synthesis takes only **~3.5s**. No offset is needed (`offset = 0s`).
   - If `tts.keep_loaded` is **`false`**: The synthesizer process unloads after each phrase. Spawning the process and initializing the ONNX session introduces an **~11–14s cold load delay** on the Pi. Desk-Pal dynamically adds `cold_load_offset_seconds` (+14s per phase, +28s to timeout) so the alerts never rush, collide, or expire prematurely while waiting on model loads.
5. **Radar Awareness**: If radar is enabled, voice escalation only fires when someone is physically present at the desk (`radar_nearby_present == True`). If nobody is nearby, the alert stays queued silently without disturbing an empty room.

---

## Endpoints

### 1. `GET /api/v1/agent/capabilities` (or `/api/v1/capabilities`)
Performs dynamic, self-describing introspection across Desk-Pal's virtual world, physical hardware, sensors, callable functions, installed companion microservices, and agent interaction rules. As new scenes, spots, custom poses, or services are added, they appear here automatically without code changes.

**Response `200 OK`**:
```json
{
  "name": "Desk-Pal",
  "version": "1.1.0",
  "description": "Embodied physical desk companion running on a 1280x720 touchscreen Raspberry Pi appliance.",
  "device_roles": [
    "Physical second-screen output for notifications and interactive decision cards",
    "Voice annunciator (Piper TTS) for concise room updates without hijacking PC audio",
    "Peripheral presence notifier (character waves arms in the room when human input is required)",
    "Embodied ambient worker (character types at PC desk, inspects bookshelf, or relaxes while tasks run)"
  ],
  "hardware": {
    "display": { "resolution": "1280x720", "fps": 60, "touchscreen": true, "sleeping": false },
    "speaker": { "available": true, "tts_enabled": true, "active_voice": "wheatley1", "installed_voices": ["wheatley1", "en_US-lessac-medium"] },
    "radar": { "enabled": true, "present": true, "range_m": 2.0 },
    "imu": { "enabled": true }
  },
  "world": {
    "current_scene": "cozy_study",
    "active_character": "adventurer_v1",
    "character_position": { "x": 669, "y": 596, "facing": "right", "current_animation": "sleeping" },
    "available_scenes": ["cozy_study", "video_store", "resort_beach", "apartment"],
    "scenes": {
      "cozy_study": {
        "id": "cozy_study",
        "label": "Study",
        "enabled": true,
        "is_current": true,
        "spots": [
          { "id": "computer_desk", "label": "Computer Desk", "x": 364, "y": 620, "facing": "left", "animation": "typing" },
          { "id": "bookshelf", "label": "Bookshelf", "x": 758, "y": 551, "facing": "left", "animation": "shelf_reach_back" },
          { "id": "window", "label": "Window", "x": 613, "y": 516, "facing": "left", "animation": "window_look" }
        ],
        "walkable_area": { "y_min": 492, "y_max": 722, "front_x_range": [211, 1255], "back_x_range": [432, 932] }
      }
    }
  },
  "animations": {
    "available_animations": ["bar_drink", "beach_dig", "deck_chair_rest", "idle_side", "inspect", "kneel_down", "notebook_write", "sitting_rest", "sleeping", "typing", "wave_arms", "window_look"],
    "catalog": {
      "typing": { "role": "typing", "category": "interaction", "fps": 8, "playback_mode": "loop", "allowed_scenes": ["all"], "supports_thought_bubble": true },
      "sitting_rest": { "role": "sitting_rest", "category": "rest", "fps": 6, "playback_mode": "loop", "allowed_scenes": ["all"], "supports_thought_bubble": true }
    }
  },
  "functions": {
    "puppeteer": { "description": "Direct character movement, scene travel, spot interaction, gestures, and thought bubbles.", "method": "POST", "path": "/api/v1/action" },
    "notify": { "description": "Display a full-screen interactive card modal on the 1280x720 touchscreen.", "method": "POST", "path": "/api/v1/notify" },
    "speak": { "description": "Speak text aloud on the room speaker using on-device Piper Neural TTS.", "method": "POST", "path": "/api/v1/say" },
    "get_presence": { "description": "Query 24GHz mmWave radar sensor for real-time human presence sitting at the desk.", "method": "GET", "path": "/api/v1/presence" },
    "get_world": { "description": "Query live spatial state of the virtual room: current scene, character position (x, y), animation, and radar presence.", "method": "GET", "path": "/api/v1/world" },
    "control_display": { "description": "Put the physical touchscreen display into standby or wake it up.", "method": "POST", "path": "/api/v1/display" }
  },
  "modal_layouts": {
    "wellness": { "description": "Dual-panel health card (hydration + animated stretch) with touch slider rail" },
    "dashboard": { "description": "High-contrast telemetry card with hero metric value and data tiles" },
    "classic": { "description": "Multiline formatted text card with pagination buttons and touch slider rail" }
  },
  "etiquette_for_agents": [
    "Check /api/v1/presence before speaking loudly if human might not be at desk.",
    "Use thought bubbles (speech in puppeteer) or quiet spot animations during routine background work.",
    "Use attention=True and full-screen modals only when waiting for human input or on critical task completion."
  ]
}
```

---

### 2. `GET /api/v1/world`
Returns the live virtual room state including character spatial position, active scene, current animation, and all interaction spots with screen coordinates.

**Response `200 OK`**:
```json
{
  "status": "ok",
  "current_scene": "cozy_study",
  "character": "adventurer_v1",
  "position": { "x": 364, "y": 620 },
  "facing": "left",
  "current_animation": "typing",
  "scenes": {
    "cozy_study": {
      "enabled": true,
      "label": "Study",
      "spots": [
        { "id": "computer_desk", "label": "Computer Desk", "animation": "typing", "facing": "left", "x": 364, "y": 620 },
        { "id": "bookshelf", "label": "Bookshelf", "animation": "shelf_reach_back", "facing": "left", "x": 758, "y": 551 }
      ]
    }
  },
  "available_animations": ["idle_side", "inspect", "sitting_rest", "sleeping", "typing", "wave_arms"],
  "sleeping": false,
  "radar_present": true
}
```

---

### 3. `GET /api/v1/status`
Returns general status of Desk-Pal.

**Response `200 OK`**:
```json
{
  "status": "ok",
  "character": "adventurer_v1",
  "scene": "cozy_study",
  "scenes_available": ["cozy_study", "video_store", "resort_beach"],
  "sleeping": false,
  "current_animation": "idle",
  "target_animation": "idle",
  "radar_present": true,
  "attention_waiting": false,
  "modal_active": false,
  "queue_depth": 0
}
```

---

### 2. `GET /api/v1/presence`
Returns human presence detection data from the onboard mmWave radar (LD2410 / HLK).

**Response `200 OK`**:
```json
{
  "radar_enabled": true,
  "present": true,
  "targets": 1,
  "presence_range_m": 2.0,
  "details": [
    { "target_id": 0, "distance_m": 0.85, "energy": 78 }
  ]
}
```

---

### 3. `POST /api/v1/notify`
Sends an interactive notification. If `attention: true`, Desk-Pal will wave its arms and initiate the voice attention ladder until someone taps the screen to view the popup modal.

**Request Payload**:
```json
{
  "title": "Home Assistant",
  "summary": "Front gate opened - delivery driver detected",
  "message": "A courier has dropped off a package at the front porch.",
  "attention": true,
  "voice_phrase": "Hey, someone is at the front gate!",
  "app_name": "SECURITY",
  "color": [240, 160, 80],
  "badge": "ALERT",
  "ticker": "Front gate opened",
  "priority": true
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `title` | string | `"Notification"` | Title shown on the SCUMM popup modal. |
| `summary` | string | Required | Brief summary for notification banner and TTS fallback. |
| `message` | string | `""` | Detailed description displayed inside the tap-to-open modal. |
| `attention` | boolean | `true` | When true, triggers waving arms, radar gating, and voice ladder. |
| `voice_phrase` | string | Optional | Custom speech announcement for Phase 1. |
| `app_name` | string | `"API"` | Tag for the activity audit queue. |
| `color` | array | `[0, 229, 255]` | RGB color tuple `[R, G, B]` for UI accents and ticker bar. |
| `badge` | string | Optional | Small badge text (e.g. `"NEW"`, `"HOT"`). |
| `ticker` | string | Optional | Marquee ticker text at the bottom of the screen. |
| `priority` | boolean | `false` | When true, jumps to the front of the queue. |

**Response `200 OK`**:
```json
{
  "status": "queued",
  "activity_id": "notify_8748431d",
  "attention": true
}
```

---

### 4. `POST /api/v1/action`
Queues a custom character activity with animation, speech bubble, and optional scene travel.

**Request Payload**:
```json
{
  "animation": "wave_arms",
  "speech": "Taking a quick break!",
  "scene": "resort_beach",
  "target_x": 160,
  "target_y": 140,
  "duration": 5.0,
  "app_name": "CUSTOM"
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `animation` | string | `"idle"` | Sprite animation (`idle`, `walk`, `wave_arms`, `talking`, `sleeping`, `custom`). |
| `speech` | string | `""` | Thought / speech bubble text displayed above character. |
| `scene` | string | `null` | Scene identifier to travel to before performing the animation. |
| `target_x` | integer | `null` | Walk coordinates (X) on scene floor mesh. |
| `target_y` | integer | `null` | Walk coordinates (Y) on scene floor mesh. |
| `duration` | float | `4.0` | Dwell duration in seconds. |

**Response `200 OK`**:
```json
{
  "status": "queued",
  "activity_id": "action_691e84fa",
  "animation": "wave_arms",
  "scene": "resort_beach"
}
```

---

### 5. `POST /api/v1/say` (or `/api/v1/speak`)
Immediately synthesizes speech using Piper TTS and triggers the talking mouth sprite animation.

**Request Payload**:
```json
{
  "text": "The garage door has been left open for 15 minutes."
}
```

**Response `200 OK`**:
```json
{
  "status": "speaking",
  "text": "The garage door has been left open for 15 minutes."
}
```

---

### 6. `POST /api/v1/scene`
Immediately transitions Desk-Pal to a new scene/room.

**Request Payload**:
```json
{
  "scene": "video_store"
}
```

**Response `200 OK`**:
```json
{
  "status": "ok",
  "scene": "video_store"
}
```

---

### 7. `POST /api/v1/display`
Controls the physical display standby state. Puts the touchscreen to sleep or wakes it up without power cycling the Pi.

**Request Payload**:
```json
{
  "action": "sleep"
}
```
* `action`: `"sleep"` (enter standby) or `"wake"` (wake display and character).

**Response `200 OK`**:
```json
{
  "status": "ok",
  "action": "sleep",
  "sleeping": true,
  "message": "Display entered standby"
}
```

---

## Companion Services Supervisor Endpoints

These endpoints manage background companion microservices and scripts running locally on the Raspberry Pi.

### 7. `GET /api/services`
Lists all discovered services in `services/`, their running state, PID, uptime, and configuration.

**Response `200 OK`**:
```json
{
  "status": "ok",
  "services": [
    {
      "id": "flight_radar",
      "name": "Flight Radar Tracker",
      "description": "Scans flight corridors for discount anomalies",
      "port": 8095,
      "auto_start": true,
      "running": true,
      "pid": 145444,
      "exit_code": null,
      "restarts": 0
    }
  ]
}
```

---

### 8. `GET /api/services/logs`
Fetches captured `stdout` and `stderr` lines from the supervisor's circular memory buffer (and log file).

**Query Parameters**:
- `id` *(string, required)*: The service ID.
- `lines` *(integer, optional)*: Maximum number of recent lines to return (default: 100).

**Response `200 OK`**:
```json
{
  "status": "ok",
  "id": "flight_radar",
  "logs": [
    "[2026-10-17 12:45:00] [flight_radar] Starting Flight Radar service on port 8095...",
    "[2026-10-17 12:45:01] [flight_radar] Scanned 4 corridors. Found deal: SYD->DPS $349."
  ]
}
```

---

### 9. `GET /api/services/code`
Fetches the primary Python script code and service manifest for editing in Web Studio.

**Query Parameters**:
- `id` *(string, required)*: The service ID.

**Response `200 OK`**:
```json
{
  "status": "ok",
  "id": "flight_radar",
  "manifest": {
    "id": "flight_radar",
    "name": "Flight Radar Tracker",
    "port": 8095,
    "auto_start": true
  },
  "code": "import http.server\n..."
}
```

---

### 10. `POST /api/services/action`
Sends a process control command to a service (`start`, `stop`, or `restart`).

**Request Payload**:
```json
{
  "id": "flight_radar",
  "action": "restart"
}
```

**Response `200 OK`**:
```json
{
  "status": "ok",
  "message": "Service flight_radar restarted (PID: 145444)"
}
```

---

### 11. `POST /api/services/save`
Creates or updates a service's entrypoint script and manifest. If `add_to_apps: true`, automatically updates Desk-Pal's `config.apps` with a loopback polling entry (`http://127.0.0.1:<port>/status`).

**Request Payload**:
```json
{
  "id": "local_scraper",
  "name": "Local Scraper",
  "description": "Polls electricity spot prices",
  "code": "import http.server\n...",
  "port": 8092,
  "auto_start": true,
  "add_to_apps": true
}
```

**Response `200 OK`**:
```json
{
  "status": "ok",
  "service": {
    "id": "local_scraper",
    "name": "Local Scraper",
    "port": 8092,
    "auto_start": true
  },
  "app_linked": true
}
```

---

### 12. `POST /api/services/delete`
Gracefully stops the service process (if running) and deletes its directory under `services/`.

**Request Payload**:
```json
{
  "id": "local_scraper"
}
```

**Response `200 OK`**:
```json
{
  "status": "ok",
  "message": "Service local_scraper deleted."
}
```

---

### 13. `GET /api/system_stats`
Returns system RAM (memory) and storage (disk) usage, available headroom, and percent utilization.

**Response `200 OK`**:
```json
{
  "memory": {
    "total_bytes": 3980181504,
    "used_bytes": 1027665920,
    "available_bytes": 2952515584,
    "total_gb": 3.71,
    "used_gb": 0.96,
    "available_gb": 2.75,
    "percent": 25.8
  },
  "storage": {
    "total_bytes": 30800633856,
    "used_bytes": 8256339968,
    "available_bytes": 21216972800,
    "total_gb": 28.7,
    "used_gb": 7.7,
    "available_gb": 19.8,
    "percent": 26.8
  }
}
```

---

## Integration Examples

### cURL Examples

```bash
# 1. Check if user is sitting at their desk
curl -s http://<pi-ip>:7777/api/v1/presence

# 2. Trigger an interactive attention notification
curl -X POST http://<pi-ip>:7777/api/v1/notify \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Fuel Alert",
    "summary": "Unleaded fuel dropped to 169.9c",
    "message": "7-Eleven Southport has dropped below 170c. Best price in 14 days.",
    "attention": true,
    "voice_phrase": "Hey, I have a fuel update for you!",
    "app_name": "FUEL"
  }'

# 3. Say something immediately
curl -X POST http://<pi-ip>:7777/api/v1/say \
  -H "Content-Type: application/json" \
  -d '{"text": "Good morning! You have 3 meetings scheduled today."}'

# 4. Switch scene
curl -X POST http://<pi-ip>:7777/api/v1/scene \
  -H "Content-Type: application/json" \
  -d '{"scene": "resort_beach"}'
```

---

### Home Assistant Integration

In your Home Assistant `configuration.yaml`:

```yaml
rest_command:
  deskpal_notify:
    url: "http://<pi-ip>:7777/api/v1/notify"
    method: POST
    content_type: "application/json"
    payload: >-
      {
        "title": "{{ title | default('Home Assistant') }}",
        "summary": "{{ summary }}",
        "message": "{{ message | default(summary) }}",
        "attention": {{ attention | default(true) | to_json }},
        "voice_phrase": "{{ voice_phrase | default('') }}",
        "app_name": "HOME_ASSISTANT"
      }

  deskpal_say:
    url: "http://<pi-ip>:7777/api/v1/say"
    method: POST
    content_type: "application/json"
    payload: '{"text": "{{ text }}"}'

  deskpal_switch_scene:
    url: "http://<pi-ip>:7777/api/v1/scene"
    method: POST
    content_type: "application/json"
    payload: '{"scene": "{{ scene }}"}'

sensor:
  - platform: rest
    name: "Desk-Pal Radar Presence"
    resource: "http://<pi-ip>:7777/api/v1/presence"
    value_template: "{{ 'on' if value_json.present else 'off' }}"
    scan_interval: 10
    json_attributes:
      - targets
      - presence_range_m
      - radar_enabled
```

#### Home Assistant Automation Example
```yaml
alias: "Desk-Pal Package Delivered Notification"
trigger:
  - platform: state
    entity_id: binary_sensor.front_door_package
    to: "on"
action:
  - service: rest_command.deskpal_notify
    data:
      title: "Package Delivered"
      summary: "Package detected at front door"
      message: "Delivery courier detected on the porch camera."
      attention: true
      voice_phrase: "Hey! A package just arrived at the front door."
```

---

## Voice Recognition & Sentry (STT) Endpoints

Desk-Pal includes an ambient on-device Speech-to-Text Voice Sentry powered by `faster-whisper` (`tiny.en` int8 on CPU) and ALSA USB microphone capture.

### Trigger Modes
1. **Push-to-Talk via Sprite Poking (`poke_sprite`)**: Tapping the character sprite on the touchscreen (or clicking in the web remote display) toggles listening mode. A retro thought bubble with a pulsing red recording dot appears above the character's head (`Listening... (tap to finish)`). Tapping again finishes listening immediately.
2. **Auto-Stop Silence Cutoff (`silence_seconds: 2.0`)**: Automatically finishes listening once **2.0 seconds** of silence is detected after speaking, allowing natural conversational pauses between sentences without premature cutoff.
3. **Always Loaded in Memory (`keep_loaded`)**: When enabled, the `faster-whisper` worker remains warm in memory (~120–150 MB RAM), allowing near-instant transcription without cold-booting models.

### `GET /api/ai/stt/status`
Returns the live status of the Voice Sentry and underlying STT engine.

```json
{
  "state": "idle",
  "enabled": true,
  "model": "tiny.en",
  "keep_loaded": true,
  "trigger_mode": "poke_sprite",
  "wake_word": "hey deskpal",
  "silence_seconds": 2.0,
  "latest_transcription": "hello deskpal",
  "engine": {
    "state": "ready",
    "error": "",
    "loaded": true,
    "memory_mb": 138.4
  }
}
```

### `POST /api/ai/stt/test`
Records 5.0 seconds from the USB microphone and transcribes directly, returning benchmark latency and memory metrics.

---

## 14. Theme Management Endpoints

Desk-Pal provides a dynamic Theme Management system allowing users to switch, save, duplicate, export, and import complete visual aesthetic profiles without modifying or interrupting running background companion microservices or hardware calibrations.

### `GET /api/themes`
Returns an array of all installed themes along with their metadata, color palette swatches, card styles, and an indicator of the active theme profile.

**Response (200 OK):**
```json
{
  "themes": [
    {
      "id": "cozy_study",
      "name": "Cozy Study",
      "description": "Warm ambient study with oak wood tones, CRT monitor, and arched window.",
      "active_scene": "cozy_study",
      "active_character": "adventurer_v1",
      "palette": {
        "background": [28, 22, 18],
        "surface": [45, 36, 30],
        "surface_light": [68, 54, 45],
        "border": [100, 80, 65],
        "accent": [212, 143, 56],
        "text": [245, 238, 225],
        "text_dim": [160, 145, 130]
      },
      "card_style": {
        "border_radius": 14,
        "accent_glow": true
      },
      "is_active": true,
      "is_builtin": true
    }
  ],
  "active_theme": "cozy_study"
}
```

### `GET /api/themes/current`
Returns the complete profile of the currently active theme.

**Response (200 OK):**
```json
{
  "theme": {
    "id": "cozy_study",
    "name": "Cozy Study",
    "palette": { ... },
    "card_style": { "border_radius": 14 },
    "active_scene": "cozy_study",
    "active_character": "adventurer_v1",
    "props": { ... }
  }
}
```

### `POST /api/themes/apply`
Hot-reloads the visual theme in memory. Dynamically updates UI color palettes, popup card border radiuses, scene backdrops, active character sprite bindings, and prop placements without restarting the app process or interrupting companion microservices.

**Request Payload:**
```json
{
  "theme_id": "retro_apartment"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "theme": "retro_apartment",
  "name": "Retro Apartment",
  "active_scene": "apartment",
  "message": "Theme 'Retro Apartment' applied successfully."
}
```

### `POST /api/themes/save`
Captures current live visual state (palette, card styles, scenes, character, prop placements) into a new permanent theme profile.

**Request Payload:**
```json
{
  "id": "cyber_study",
  "name": "Cyber Study",
  "description": "Custom neon-infused cozy study.",
  "card_style": {
    "border_radius": 12,
    "accent_glow": true
  }
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "theme": { ... },
  "message": "Theme 'Cyber Study' saved successfully."
}
```

### `POST /api/themes/duplicate`
Clones an existing theme profile under a new ID and name, allowing users to modify scenes and props without altering the baseline original.

**Request Payload:**
```json
{
  "source_id": "resort_beach",
  "new_id": "tropical_sunset",
  "new_name": "Tropical Sunset"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "theme": { ... },
  "message": "Theme duplicated as 'Tropical Sunset'."
}
```

### `POST /api/themes/delete`
Permanently deletes a custom theme profile directory. Built-in default themes and the currently active theme cannot be deleted.

**Request Payload:**
```json
{
  "theme_id": "tropical_sunset"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Theme 'tropical_sunset' deleted."
}
```

### `GET /api/themes/export?theme=<id>`
Streams a standalone `.zip` archive containing `theme.json` and `manifest.json`.

**Response (200 OK):**
Binary archive (`application/zip`), filename `deskpal_theme_<theme_id>.zip`.

### `POST /api/themes/import`
Accepts a binary `.zip` theme archive or a `.json` theme file and installs it into `/home/admin/themes/<theme_id>/`.

**Response (200 OK):**
```json
{
  "success": true,
  "theme_id": "custom_theme",
  "message": "Theme imported successfully."
}
```
