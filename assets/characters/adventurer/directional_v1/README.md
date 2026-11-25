# Adventurer v1 directional animation draft

> Artwork/provenance record. Runtime selection, crops, anchors and placements come from saved configuration; this record is not the current deployment or task list. See the [documentation index](../../../../docs/index.md).


Generated one image at a time with the built-in image generation tool, using the Pi's selected `/assets/characters/adventurer/walk/walk_0.png` as the character identity reference. The newly drawn guides in `guides/` are independent of the old puppet rig. Prompts are recorded in `prompts.json`.

16 original transparent PNGs are preserved in `raw/`:

- `walk_down_0` through `walk_down_3`: four toward-camera walking candidates.
- `walk_up_0` through `walk_up_3`: four away-from-camera walking candidates.
- `stand_down_0`, `stand_down_breathe`, `stand_down_blink`.
- `stand_up_0`, `stand_up_breathe`.
- `stand_side_0`, `stand_side_breathe`, `stand_side_blink`: right-facing, mirrored at playback for left-facing.

`manifest.json` defines `walk_up`, `walk_down`, `idle_side`, `idle_up`, and `idle_down` for `adventurer_v1`. The original side walk is preserved separately as `walk_side`. Walks run at 4 FPS. Idles use repeated frames at 4 FPS for a four-second loop, with front/side blinks held for one quarter-second. Repeated slots are intentional holds and can be edited in Animation Grid.

`frame_metrics.json` records measured image bounds. All original images are 1086x1448 RGBA. Playback uses 600x1360 crop windows recorded in the manifest and sprite tags, with a fixed scale, aligned foot baseline, and head-centre registration. The PNGs have not been resized or painted over. These are generated draft loops: subtle pixel/pose differences remain and should be judged in motion at the Pi's display size.

Use the Animation Grid's **Saved animation** selector to inspect each sequence. **Use for** assigns a sequence to a specific direction without replacing another role. The display chooses front/back walking for predominantly vertical movement, side walking for predominantly horizontal movement, and the corresponding idle when stopped. Explicit left/right facing on interaction spots still takes precedence when arriving there.
