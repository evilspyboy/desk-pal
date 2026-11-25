# Desk-Pal current architecture

Reviewed against the working source on 13 October 2026. The superseded early specification is preserved as [design history](ARCHITECTURE_DESIGN_HISTORY.md); it is not an installation or API guide.

## Purpose and runtime

Desk-Pal presents the activity and results of other applications as a character in configured scenes. Those applications perform their own work. The display does not scrape stores, send social posts or run producer jobs when a button is pressed.

`src/deskpal_app.py` runs the Pygame display loop and a standard-library `ThreadingHTTPServer`. The Pi editor/event server uses port 7777; Desktop Companion Mode also uses port 7777 by default for normal local operation; isolated PC Live preview uses loopback port 7779 by default. This is not a FastAPI service. HTTP handlers accept configuration, content and event requests; queued actions and character movement run through the display loop. Slow optional operations use workers or isolated processes.

The primary hardware target is a Pi 4 with a 5-inch Touch Display 2, configurable GPIO buttons, BH1750 light sensor, MPU6050 IMU, RD-03D radar, USB speaker and USB microphone. Drivers and reactions are optional. Alternatively, normal operation is supported in a resizable PC window via Desktop Companion Mode. Hardware power and shutdown are safely adapted on PC. See [installation](pi-installation.md), [desktop companion](desktop-companion.md), [local preview](local-preview.md) and [hardware](hardware.md).

## Events, producers and cached status

Producers or separate relays publish HTTP JSON heartbeats and named events. Desk-Pal also supports configured read-only source adapters and optional built-in Weather/connectivity checks, so it is not accurate to say it never makes network requests. These do not perform the monitored application's underlying jobs. The independent store monitor owns store authentication/polling and can run on the Pi without being part of the display engine.

- [Integration contract](external_integration_spec.md): `/api/v1/event`, `/api/v1/heartbeat` and `/api/v1/alert`.
- `integration_state.py` and telemetry state retain cached results, receipt identities and health state.
- `activity_queue.py` handles ordered reactions, finite milestones, attention, button priority and standby deferral.
- `activity_history.py` records bounded, rotated evidence for retrospective review.
- Normal application buttons show the latest cached heartbeat/button summary. They do not force a new producer/API poll. Attention acknowledgement shows the original alert information.

Scene/animation/location mappings belong to the consumer, not to producer code. Unchanged state need not create a new occurrence; stable IDs and the duplicate/suppression controls keep visual playback useful. Ordinary event loops with no duration override finish one cycle by default; idle and persistent attention/outage behavior are separate. See [adding integrations](adding-integrations.md) and [playback](animation-playback.md).

## Scenes, characters and authoring

`scene_world.py`, the `FloorNavigation` helpers in `deskpal_app.py`, and related navigation code constrain foot anchors to the saved floor and block footprints. Scene links connect editable entry/exit paths. Character-owned sequences resolve tagged frame URLs, crops, anchors, playback defaults and transitions. Perspective comes from scene geometry and configured front/back limits. Foreground masks and placement vectors determine partial occlusion; image props are separate reusable sequences with placement-specific transforms/triggers.

The browser editor stores scene-local placements, shared character/prop libraries, reference images and frame skeletons. Reference exports use the character reference plus guides/instructions, without copying existing animation artwork into generation sheets. See [editor workflows](editor-workflows.md), [scene placements](scene-placements.md), [foreground objects](foreground-objects.md) and [animation references](animation-references.md).

## Hardware sleep and sensor reactions

Hardware reader preferences/calibration are separate from scene/application settings. Lux policy includes hysteresis, debounce, evening keep-awake and manual wake grace. The shared bedtime takes precedence over radar wake/keep-awake until sunrise. Radar presence defaults to reported distances under 2 metres, independent of the diagnostic plot range. Distant raw targets remain visible; reflections and loss of stationary users remain known limitations.

Return greetings are opt-in under App & Action Studio → Sensors, using a one-handed hello. Hardware radar enable/wake settings do not themselves enable that greeting. Two-handed waving remains attention. Tilt/shake briefly pauses and resumes the character's route. Standby settles at a reachable eligible rest placement, then powers down the actual panel while monitoring continues. See [sensor reactions](sensor-triggers.md), [hardware diagnostics](hardware-testing.md) and [standby](idle-and-standby.md).

## Optional agents and speech

The external stdio MCP bridge reports explicit agent activity; automatic agent lifecycle hooks, conversational provider adapters and STT remain pending. OpenAI/Gemini/Claude/local profiles are configuration only.

Piper TTS runs in an isolated optional environment. Installed voices can be downloaded or imported through AI & Speech. Keep-loaded retains only the active voice worker; disabling retention, changing voices while idle, disabling speech or Stop releases it. Central playback drives the talking animation and pauses/resumes activity clocks. Speech follows the saved Hardware output/volume. Automatic spoken briefings are not enabled. See [AI and speech](ai-and-speech.md) and [Piper setup](../integrations/piper-tts/README.md).

## Data, updates and review boundaries

Private configuration, assets, sprite/skeleton metadata and runtime state remain outside code updates. Supported content packages and private backups use preview/confirmation/recovery copies. Hardware preferences, AI profiles, voice models and producer credentials are not all covered by the normal content ZIP; see [backup scope](backups-and-updates.md).

The editor is intended for a trusted LAN and has no authentication. Do not publish its ports as a public service. Code/artwork/model/3D-print licensing and a fresh-Pi rehearsal remain publication work. There is no published Git repository, and this working directory is not currently initialized as one. For review boundaries, current limitations and validation evidence, use [review handoff](review-handoff.md).
