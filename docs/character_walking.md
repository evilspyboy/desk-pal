# Character walking

In Animation Grid, select the character tag (for example `adventurer_v1`), arrange its frames, and set FPS. Check **Use for**, choose the walk/idle direction, and click **Save animation**. This selects that character on the display and immediately applies the ordered frames, FPS, and ping-pong setting. **Saved animation** loads any sequence; **Load saved walk** restores the side walk. Tag sprites in the Sprite Browser before including them; mixed-character and untagged frames are rejected.

The display supports side walking (mirrored left/right), up/away and down/toward walking, and matching directional idle loops. Predominantly vertical travel uses up/down; predominantly horizontal travel uses side. Explicit left/right orientation on an interaction spot takes precedence on arrival. The generated directional-v1 draft uses the existing side walk unchanged, new four-frame up/down walks, and quiet standing loops with breathing and front/side blinks.

## Floor and obstacles

The saved convex floor polygon (including legacy trapezoids) constrains the character's foot anchor, not the full sprite rectangle. Movement follows checked straight segments around obstacles; it no longer moves straight through blocks or curves outside sloping floor edges. Unreachable destinations are cancelled instead of crossing a blocked route. After floor edits, an invalid current position is relocated to the nearest free point.

Web Studio blocks now have four independent corners. Drag a corner to match a ground footprint, or drag the body to move the whole shape. New blocks start as trapezoids; old rectangles retain their outlines until edited. Crossing or collapsing corners is prevented. Save to Pi applies the geometry. `points` holds the clockwise polygon; `x`, `y`, `w`, `h` remain its bounding box for compatibility. Blocks lacking `points` are treated as legacy rectangles. The Pi's built-in editor displays polygons and preserves their shape during whole-block movement and size adjustments.

`python3 scripts/test_floor_navigation.py src/deskpal_app.py` tests floor boundaries, polygon collision, detours, disconnected routes, overlapping blocks and movement steps without starting the display.

## Configuration

- `active_character`: selected character tag.
- `characters[character].animations.walk`: side-walk sequence ID (also accepts `walk_side`). Additional roles: `walk_up`, `walk_down`, `idle_side`, `idle_up`, `idle_down`.
- `animation_sequences[sequence_id]`: named sequence containing `character`, `fps`, `ping_pong`, and ordered `frames` with full asset URLs.
- New sequence IDs use `character:name` so different characters can have equally named animations.
- `sprite_tags.json` supplies each frame's `variant` (character identity).
- Optional frame/tag `crop`: `[x, y, width, height]` render window; `anchor_x` adjusts horizontal registration and `reference_height` controls common scale when needed. Runtime/stager rendering uses these without changing original PNGs.

The runtime resolves full URLs, including subdirectories, instead of guessing numbered filenames. Once a character is active, only its tagged static poses are available; missing poses fall back to its idle (or first walk frame if no idle exists). Old installations retain legacy walking until a sequence is explicitly assigned. Existing legacy exports remain stored but must be saved with a character binding to drive movement.

Config updates retain all fields, including animation sequences and reference sprites. Deploy code only; do not replace Pi assets or curated config with desktop copies.

## Validation

`python3 scripts/test_character_walk.py src/deskpal_app.py` runs headless pygame regression tests for frame order, timing, ping-pong, invalid character/frame rejection, and persistence using temporary generated assets.
