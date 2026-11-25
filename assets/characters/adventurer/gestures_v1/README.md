# Adventurer 1 gesture loops

> Artwork/provenance record. Runtime selection, crops, anchors and placements come from saved configuration; this record is not the current deployment or task list. See the [documentation index](../../../../docs/index.md).


22 selected original transparent PNGs form 11 first-pass loops, generated individually with the built-in image generator. Each second frame edits its own base frame to limit changes in identity and clothing. The reference is `../directional_v1/reference_side.png`, with the existing side/rear idle sprites as scale and view references. Full prompts, including unused sleeping alternatives, are in `prompts.json`.

| Saved animation / role | Gesture |
|---|---|
| kneel_down | Kneeling, low reach, side view |
| kneel_back | Kneeling, low reach, rear view |
| table_reach | Standing reach at table height |
| noticeboard_reach | Standing reach at eye height |
| reach_high | Stretched overhead reach, side view |
| shelf_reach_back | Stretched overhead reach, rear view |
| notebook_write | Writing with notebook and pencil |
| typing | Alternating typing fingers, keyboard supplied by scene |
| inspect | Small magnifying-glass sweep |
| sitting_rest | Seated against an unseen support, breathing |
| sleeping | Lying down with closed eyes, breathing |

All use 4 FPS. Writing/typing alternate two frames; reaching/inspection hold each frame for two slots; rest/sleep hold each for eight slots. Slots and speed remain editable in Animation Grid. These are working-pose loops, not stand-to-kneel, sit-down or lie-down transitions. Small generation differences remain; they are drafts for judging in motion. No skeleton rig was used for this pack: poses were specified from the character references and each adjacent frame edited from its base.

The manifest contains the exact selected files. `sleeping_0_clean.png` and `sleeping_0_v2.png` are unused alternatives, retained locally and not deployed. The apparent glow in some raw image viewers is RGB in transparent pixels; compositing on a coloured background was checked in `preview.html`.

`frame_metrics.json` records alpha bounds, crop windows, the 1360-pixel standing reference height and ground-anchor positions. The PNGs are untouched. The renderer applies this metadata so crouching and lying down retain their physical size rather than stretching to standing height. Side gestures mirror for left/right; rear roles are not mirrored. Sleeping's source has its head on the left. Furniture is omitted; notebook/pencil and magnifying glass are included.

In Web Studio, refresh and select Animation Grid → Saved animation. The Use for selector binds loops to action roles. Pose Stager previews the first bound frame for placement; action playback on the Pi uses the full loop. Existing side/front/rear walks and standing idles are preserved. Existing interaction/action names such as typing, inspect and notebook_write now resolve to this character's matching loop. New roles can be assigned to interaction spots/actions.

Other Adventurer 2 ideas identified for a later pass: pondering, waving, window-looking, leaning over a globe, mailbox interaction and a relaxed stretch. They have not been regenerated in this pack.
