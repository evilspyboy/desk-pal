# Optional LLM Agent & Embodied Companion Interface

Desk-Pal's original purpose is to show the status and activity of other applications. Those applications do their own work, publish heartbeats and events, and leave Desk-Pal to animate a character, manage scenes and props, and present useful notifications.

LLM agent integration is an optional, rich extension of the same device. Beyond simple status updates, Desk-Pal can act as an **embodied physical companion and dedicated second screen** for coding assistants (e.g., Antigravity, Cursor, Claude Code) without cluttering Desk-Pal's ambient pixel-art world or altering its core UI.

Desk-Pal remains entirely self-contained and useful without an external agent, AI subscription, or MCP.

## Two Ways Agents Can Interact

External agents can interact with Desk-Pal in two ways:

1. **Embodied Direct Control & Output Device (MCP / REST)**:
   - **Self-Describing Discovery (`GET /api/v1/agent/capabilities`)**: An agent can query Desk-Pal dynamically to discover what rooms exist, where the interaction spots and props are (with exact pixel coordinates), what animations the character can perform (locomotion, typing, reading, resting, inspecting), and what TTS voices or sensors are installed.
   - **Physical Presence Check (`GET /api/v1/presence`)**: Agents check the 24GHz mmWave radar before speaking aloud to make sure the human is actually seated at the desk.
   - **Direct Puppeteering (`POST /api/v1/action` or `deskpal_puppeteer`)**: Agents direct the sprite to walk to specific spots (e.g. `computer_desk` when coding, `bookshelf` when researching, `tiki_bar` on the beach when relaxing), play animations, and display comic thought bubbles above the sprite's head.
   - **Interactive Second Screen Cards (`POST /api/v1/notify` or `deskpal_notify`)**: Render full-screen cards (`classic`, `dashboard`, `wellness`) with touch sliders and arm-waving attention alerts when human review is needed.
   - **Spoken Room Updates (`POST /api/v1/say` or `deskpal_speak`)**: Announce completions or blockers aloud using on-device Piper TTS without taking over PC audio.

2. **Conventional Event Mapping (`POST /api/v1/event` or `deskpal_report_activity`)**:
   - The agent reports standard phases (`started`, `researching`, `coding`, `completed`, `needs_attention`, `failed`), and Desk-Pal maps them to user-configured animations and placements in the App & Action Studio.

```text
External LLM Agent (Antigravity / Cursor / Claude)
  ├── 1. Introspect: GET /api/v1/agent/capabilities & /api/v1/presence
  ├── 2. Background: deskpal_puppeteer(spot="computer_desk", animation="typing", thought="Running tests...")
  └── 3. Decision Needed: deskpal_notify(layout="classic", slider=true, speech="Review needed")
             │
             ▼
      Desk-Pal Appliance (1280x720 touchscreen Pi)
             ├── mmWave Radar tracks desk presence
             ├── Character moves to spots & emotes
             └── Piper TTS annunciates concise phrases
```

The character represents the reported activity. It does not research, write code, make decisions, or execute the agent's task. Reports are supplied by the agent/host; Desk-Pal does not independently verify their accuracy, watch its internal reasoning, or detect whether an arbitrary agent has stopped working.

| | Normal application monitoring | Optional agent reporting |
| --- | --- | --- |
| Source | Application status, real task results or a separate monitor | Explicit agent tool calls |
| Examples | A completed email check, changed price or new paid order | Researching, task finished or needs your input |
| Connection | HTTP events/heartbeats or a configured relay | Separate stdio MCP adapter forwarding HTTP events |
| Required by Desk-Pal | An input source when you want external activity | No; entirely optional |
| Where the work happens | In the external application | In the external agent and its tools |

## When it might be useful

Use it as a visible completion or attention signal while an agent works in another window. The display can wave when a decision is waiting and perform different gestures for meaningful task phases. It can also serve the kind of animated companion display sometimes called an “AI pet,” while keeping the actual agent separate from the device.

Existing application events still share the queue. Sleep, suppression, button priority and scene navigation retain their normal behaviour. An agent does not automatically take ownership of the character, replace other monitors, select arbitrary animations, or change scene configuration.

## What an acknowledgement means

Tapping the character or using a matching configured application button acknowledges the Desk-Pal notification. It does not send an answer to the agent, approve a requested action, or tell the agent to continue. Read and answer the underlying question in the agent's own interface. The current adapter has no return channel for human decisions.

A successful report means Desk-Pal received the event, not that the animation has already played or the task really succeeded. Detailed questions and results belong in the agent chat; send only a short factual display message, without secrets, transcripts or internal reasoning.

## Local and cloud agents

The supplied adapter runs on an MCP-capable tool host and uses stdio. A host on your computer can run a local model or call a cloud model; either can report to a Desk-Pal it can reach. The Pi needs neither the model nor the MCP SDK.

A fully cloud-hosted tool runtime without access to your private network would need a separately authenticated relay or remote MCP service. That service is not included, and no public endpoint is opened by this extension.

## Enable it only when wanted

Follow the [adapter setup guide](../integrations/agent-mcp/README.md) to install its separate dependencies, import its [event definition](../integrations/agent-mcp/integration.json), connect a compatible host, and choose scene/gesture mappings. Nothing is activated by reading the documentation or downloading Desk-Pal. The adapter has been tested against an isolated fake device; the personal Pi has no agent integration enabled by default.

For Desk-Pal's normal application interfaces instead, use [Adding integrations](adding-integrations.md) and the [worked producer example](producer-interface-example.md).
