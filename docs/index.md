# Documentation index

Current documentation entry point. Source code and saved installation settings take precedence if a discrepancy is found. [README](../README.md) is the user overview.

## Architecture and integrations

- [Current architecture](architecture.md): renderer, HTTP, events, hardware and speech ownership.
- [Integration contract](external_integration_spec.md), [monitored applications guide](monitored-applications.md), [adding applications](adding-integrations.md), [companion services & scripts](companion-services.md), [producer example](producer-interface-example.md).

## Install, preserve and share

- [Fresh starter setup](fresh-setup.md), [Pi installer](pi-installation.md), [Desktop Companion window](desktop-companion.md), [PC Live preview](local-preview.md).
- [Backups and updates](backups-and-updates.md): content packages and explicit exclusions for Hardware/AI settings, models and credentials.
- [Maintenance](maintenance.md): bounded caches/logs and read-only inventory.

## Scenes and animations

- [Theme Management System](theme-management.md): swappable visual themes, UI palettes, popup card radiuses/accents, characters, props, and REST APIs without disrupting background services.
- [Editor workflows](editor-workflows.md), [scene placements/travel](scene-placements.md), [floor editor](floor-editor.md).
- [Foreground objects](foreground-objects.md), [image props](image-props.md), [interactive props/Easter eggs](interactive-tv.md), [mini-games & arcade overlays](mini-games.md).
- [Character walking](character_walking.md), [playback](animation-playback.md), [skeleton/reference exports](animation-references.md).
- [Idle/standby](idle-and-standby.md), [day/night authoring](day-night-authoring.md).

## Hardware, integrations and speech

- [Hardware wiring and models](hardware.md), [live diagnostics/calibration](hardware-testing.md), [sensor reactions](sensor-triggers.md).
- [Weather/morning briefing](weather-and-morning-briefing.md), [Pi connectivity health](system-health.md).
- [AI and speech](ai-and-speech.md), [Piper voice setup](../integrations/piper-tts/README.md).
- [Agent activity](agent-activity.md), [REST API Reference](rest_api.md), [MCP bridge](../integrations/agent-mcp/README.md).

## Asset provenance

Markdown under `assets/` records generation prompts and artwork provenance. Runtime bindings/crops/anchors come from saved configuration and sprite tags; reference exports use the installed guides.
