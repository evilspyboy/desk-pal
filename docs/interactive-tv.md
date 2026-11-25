# Custom Interactive Props & On-Tap Interactions

Props can use your own still images or animation sequences, and every prop supports customizable **On-Tap Interaction** behaviors. A screen prop can open a full CRT-style viewer, trigger in-scene animation bursts, invoke application integration actions, or launch mini-games while background monitoring and telemetry continue uninterrupted.

## On-Tap Interaction Modes

Every placed prop supports five standardized interaction modes configured right inside the **Animation Grid → Props** panel or under **View Props**:

1. **`none` — None (Walk & Inspect)**:
   - Default mode. Tapping on or near the prop causes the character to walk over to inspect it, or treats the tap as a floor walk destination.
2. **`tv` / `overlay_popup` — Open Overlay Viewer (CRT TV / Monitor)**:
   - Tapping the prop opens the interactive CRT TV/monitor viewer overlay.
   - The prop's assigned animation choices act as channels that can be navigated sequentially.
   - Background telemetry and monitoring continue in the background behind the overlay.
3. **`trigger_animation` — Trigger In-Scene Animation Burst**:
   - Tapping the prop plays a specified animation from the prop library (e.g., turning on a desk lamp, toggling audio equipment, activating a glowing crystal).
   - Keeps the character in scene without opening an overlay modal.
4. **`app_action` — Trigger Application Action**:
   - Tapping the prop immediately dispatches a registered integration action (e.g., tapping the desk computer triggers a status check or fuel update).
   - Configurable by choosing the target **Application** and **Action** from the dropdowns populated from `config.integrations`.
5. **`game_script` — Launch Mini-Game / Script**:
   - Tapping the prop launches an interactive mini-game overlay (e.g. Breakout Arcade on the Study Computer Screen) with authentic CRT monitor / arcade bezels, multi-input controls (touch, buttons, IMU, radar), and automatic background task suspension. See [Interactive Mini-Games](mini-games.md).


## Configuring Props in Animation Grid → Props

1. Open **Animation Grid → Props & Objects**.
2. Select your prop using the top prop selector tabs or the dropdown (e.g., `📺 Apartment TV`, `🖥️ Study Computer Screen`).
3. Under **On-Tap Interaction**:
   - Choose the interaction mode (`None`, `Open Overlay Viewer`, `Trigger In-Scene Animation`, `Trigger Application Action`, or `Launch Mini-Game`).
   - Configure the contextual parameters (tap animation, target app & action, or game script).
4. Under **Currently Assigned Animations / TV Channels**:
   - View assigned animations, cycle through channels live with **◀ Prev Channel** / **Next Channel ▶**, reorder with **▲** / **▼**, or remove with **✕**.
   - Click **▶ Edit Frames Below** to load any sequence directly into the Sequencer to edit frame timings, playback mode, or FPS.
   - Attach additional library animations using the dropdown or checklist, or create a new animation sequence with **✨ Create New Animation for this Prop**.
5. Click **Save Library & Props to Pi** to persist your configuration.

## Background Activity & Attention

- Background monitoring, satellite runners, and the attention queue continue to run uninterrupted behind interactive screens and overlays.
- Application attention notifications remain safely queued until acknowledged.
- Exiting an overlay (via power button or escape key) smoothly returns to normal interaction without dropping telemetry.

See [Image props](image-props.md) for frame upload, placement polygons, and depth layer instructions.
