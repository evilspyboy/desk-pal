# Agent activity through MCP

An optional, separate producer lets an LLM agent use Desk-Pal as its activity display. The agent does the work elsewhere. Desk-Pal receives phase changes through its existing HTTP event API and maps them to scenes, placements, animations and attention reactions. No model or MCP SDK is needed on the Pi.

For the purpose, limits and distinction from normal application monitoring, read [Optional LLM agent activity display](../../docs/agent-activity.md). This file covers installing and connecting the separate adapter.

## Configure Desk-Pal

1. Import [integration.json](integration.json) using **App & Action Studio → Add application → Import integration file**. It declares the `llm_agent` application and events; it sends no sample events and includes no scene mappings.
2. In Events & mappings, choose your reactions. Suggestions: researching → inspect/notebook; coding → typing; completed → a brief finite gesture; needs input/failed → wave with **Loop until interaction**. Select scenes and placements visually. No particular character or scene is required by the adapter.
3. Keep heartbeat reactions suppressed. The adapter sends a cached-status heartbeat after each real report, to give an optional physical button useful text without playing two reactions. Polling and stopped-feed monitoring should remain off: this is an intermittent push producer, not a continuously scheduled monitor.
4. Optionally assign a physical button using the existing application controls. Nothing changes the six button assignments automatically.

You can rename/import under another application ID; configure the same ID in the adapter. Use separate IDs/state files for separate agents when you want independent mappings. Updates from one agent share the same FIFO as other applications. Physical buttons retain priority, standby retains/coalesces events using the existing policy, and attention depends on the configured reaction. Attention-marked payloads alone do not force a particular gesture or indefinite loop.

## Install separately on the agent host

Python 3.10 or newer. Create a dedicated environment outside Desk-Pal's runtime:

```text
python -m venv .venv-agent
# Windows:
.venv-agent\Scripts\python -m pip install -r integrations/agent-mcp/requirements.txt
# Linux/macOS:
.venv-agent/bin/python -m pip install -r integrations/agent-mcp/requirements.txt
```

The adapter uses the official SDK's maintained v1 interface, with `mcp>=1.12,<2` to avoid an accidental major-version migration. See the [official v1 SDK documentation](https://py.sdk.modelcontextprotocol.io/v1/).

Configure your MCP-capable host to launch `server.py` over **stdio**. Generic host configuration (replace all paths and the URL):

```json
{
  "mcpServers": {
    "deskpal": {
      "command": "/absolute/path/to/.venv-agent/bin/python",
      "args": [
        "/absolute/path/to/desk-pal/integrations/agent-mcp/server.py",
        "--deskpal", "http://YOUR-DESKPAL:7777",
        "--app-id", "llm_agent",
        "--agent-name", "LLM agent"
      ]
    }
  }
}
```

On Windows use the full path to `.venv-agent\Scripts\python.exe`, escaping backslashes in JSON. A host may use a different configuration format; the executable and arguments are the same. Set `--state-dir` to choose a private writable directory; default is `~/.deskpal-agent`. Environment alternatives: `DESKPAL_URL`, `DESKPAL_AGENT_ID`, `DESKPAL_AGENT_NAME`, `DESKPAL_AGENT_STATE_DIR`.

The adapter opens no listening port, starts no polling loop and runs only while the host launches it. It sends activity solely to the configured Desk-Pal origin. Keep that origin on a trusted local network or a protected private connection; redirects are rejected. Do not expose Desk-Pal's editor/API directly to the public internet.

A cloud-hosted model using a local agent host can use this adapter exactly like a local model: connectivity depends on where the tools execute. A fully cloud-hosted agent without a route to your device needs a separately authenticated relay/remote MCP deployment; that is **not supplied by this stdio adapter**.

## Tools and agent instructions

The MCP server exposes 13 tools for embodied interaction, spatial navigation, notification display, speech, visual inspection, and presence sensing:

### Discovery & World State
- `deskpal_get_capabilities()` — dynamically introspects Desk-Pal's live profile, physical touchscreen hardware, Piper TTS voice library, 24GHz mmWave radar status, available scenes (`cozy_study`, `video_store`, `resort_beach`, `apartment`), interaction spots (with `x, y` coordinates), full animations catalog (39+ animations), installed companion microservices, and etiquette rules.
- `deskpal_get_world()` — inspects real-time room state: active scene, character position `(x, y)`, facing direction, current animation, human radar presence, and all scene spots.
- `deskpal_get_presence()` — queries the 24GHz mmWave radar sensor to verify if the human is actively sitting at their desk before speaking or demanding attention.
- `deskpal_get_sensors()` — queries real-time environmental sensors and display sleep status (ambient LUX light level, mmWave radar targets, bedtime schedule, screen power/backlight state, and sleep/wake policy decisions).
- `deskpal_get_preview_frame()` — captures a live screenshot/preview frame (1280x720 JPEG encoded as base64) of the current display canvas for visual verification.

### Character Piloting & Embodied Interaction
- `deskpal_puppeteer(scene, spot_id, x, y, animation, facing, speech, thought, duration_seconds, priority)` — directly pilots the character sprite across scenes, spots, or coordinates.
  - `scene`: navigate to any scene (`cozy_study`, `resort_beach`, etc.)
  - `spot_id`: walk to a named interaction spot (e.g. `computer_desk` for coding, `bookshelf` for research, `window` for pondering, `tiki_bar` for rest)
  - `animation`: play any animation sequence (e.g. `typing`, `inspect`, `shelf_reach_back`, `notebook_write`, `wave_arms`, `sitting_rest`)
  - `speech` / `thought`: display an in-world pixel thought bubble hovering above the character's head or speak aloud
- `deskpal_travel_scene(scene)` — triggers an animated walking journey between rooms.

### Output Display & Voice
- `deskpal_notify(title, message, layout, attention, speech)` — renders a full-screen interactive card modal on the 1280x720 touchscreen:
  - `layout`: `'classic'` (multiline text with page counter), `'dashboard'` (high-contrast telemetry with hero metric + tiles), `'wellness'` (hydration tracker + animated stretching adventurer sprite)
  - `attention`: when `True`, character waves arms and card waits for a physical touch tap to dismiss
  - `speech`: optional Piper TTS voice announcement spoken alongside the card
- `deskpal_dismiss_modal()` — programmatically dismisses any active on-screen modal card or popup notification.
- `deskpal_speak(text)` — speaks text aloud on the room speaker via on-device Piper Neural TTS without taking over PC system audio.
- `deskpal_control_display(action)` — puts physical touchscreen into standby (`'sleep'`) or wakes it up (`'wake'`).

### Activity Mapping & Status
- `deskpal_report_activity(activity, task_id, message, occurrence_id)` — reports a task phase update (`started`, `researching`, `coding`, `completed`, `needs_attention`, `failed`) mapped to user-configured activity rules and button tickers.
- `deskpal_get_status()` — reads reachability, global display queue state/count, and this adapter's last reported phase.

Suggested instruction for an external AI assistant:

> You can use Desk-Pal as your physical desk companion and second screen. Before beginning a task, call `deskpal_get_capabilities()` or `deskpal_get_world()` to discover available scenes, spots, and animations. When coding or researching in the background, use `deskpal_puppeteer()` with thought bubbles to show the character typing or inspecting bookshelf props. Check `deskpal_get_presence()` before speaking aloud so you don't talk to an empty room. Reserve full-screen cards (`deskpal_notify()` with `attention=True`) for when human intervention, approval, or task completion is reached.

Example tool arguments:

```json
{"scene":"cozy_study","spot_id":"computer_desk","animation":"typing","thought":"Running unit tests for auth module...","priority":true}
```

## Delivery and private state

Confirmed reports are deduplicated across restarts using a bounded 1000-entry local ledger. Reusing an occurrence ID with changed content is rejected. The private state also contains the latest short message/task ID for status; do not publish it. Only one server process should use a given state file at a time. For multiple simultaneous hosts use different `--state-dir` directories or application IDs. Ledger entries older than the retention bound may be replayed if resent.

`received` means Desk-Pal accepted the event; it does not promise playback, immediate travel, task success or human approval. Mappings, suppression, sleep and the queue still apply. There are no automatic retries: a timeout/lost response returns `unconfirmed`, because the device may already have received the event. Check activity history before retrying. This is not an exactly-once transport. A failed cached-status heartbeat is reported separately and must not cause the event to be resent. Cached last activity is historical, not proof that an agent is still running.

## Validation

```text
python integrations/agent-mcp/test_bridge.py
.venv-agent/bin/python integrations/agent-mcp/test_mcp_protocol.py
```

Tests use an isolated fake Desk-Pal and private temporary directories; they do not inject events into your real display. Protocol tests initialize a real SDK client/server, discover and call both tools, and reject invalid phases. No adapter is installed, started or imported on the Pi by these tests.

Verified: eight delivery/state tests, real stdio MCP initialization and both tool calls, invalid MCP arguments, import compatibility with polling/health disabled and buttons preserved, and publication ignore rules. The temporary SDK test environment was removed after validation. Connecting a particular user's agent host and choosing visual mappings remain user setup steps.
