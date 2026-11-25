# Desk-Pal Specification & Implementation Plan

> Archived early design plan. Its hardware pin table, proposed APIs, force-check behavior and unimplemented examples are superseded. Do not use it for wiring or installation. See [current architecture](architecture.md), [hardware wiring](hardware.md), [integration contract](external_integration_spec.md) and [active backlog](BACKLOG.md).


## 1. Concept Summary
Desk-Pal is a physical 16-bit ambient companion living in a miniature virtual world on a 5-inch touchscreen (Raspberry Pi 4).

Rather than reading dashboards, the user glances at Desk-Pal to see what background applications on the main PC are doing in real-time. Heavy computations (LLMs, TimesFM forecasting, scrapers) remain on the main PC, while Desk-Pal acts as an ultra-responsive, glanceable physical telemetry screen.

---

## 2. Verified Physical Hardware Mapping (Left to Right)

```
[SW 1: Moon]      [SW 2: BMCBF]     [SW 3: Fuel]      [SW 4: Orders]    [SW 5: Travel]    [SW 6: Power (RED)]
 Pin 37 (BCM 26)   Pin 35 (BCM 19)   Pin 33 (BCM 13)   Pin 31 (BCM 6)    Pin 29 (BCM 5)    Pin 27 (BCM 0)
─────────────────────────────────────────────────────────────────────────────────────────────────────────────
Night / Sleep     BottyMcBotface    Fuel Tracker QLD  Store Monitor     Travel Deals      Safe Shutdown
(Blank Screen)    (Pop-culture AI)  (Price Drops)     (Etsy/Cartel)     (Deal Threshold)  (Large Touch Dialog)
```

| Switch # | Physical Pin | BCM GPIO | App / Target | Passive Display | On-Demand "Force Check" Action |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SW 1** (Far Left) | Pin 37 | GPIO 26 | **Sleep / Night Mode** | Ambient room brightness | Instantly blanks screen/backlight. Tap screen or press any key to wake. |
| **SW 2** | Pin 35 | GPIO 19 | **BottyMcBotface (`bmcbf`)** | Pet working / reading / typing | **Force-Check BMCBF**: Pulls live current task, last Discord dispatch, and agent queue status. |
| **SW 3** | Pin 33 | GPIO 13 | **Fuel Tracker QLD** | Gas nozzle / bargain alert | **Force-Check Fuel**: Instantly queries & displays current cheapest local station, price, and trend. |
| **SW 4** | Pin 31 | GPIO 6 | **Store Orders (Etsy & Cartel)** | Parcel at door on new order | **Force-Check Orders**: Refreshes order queues, shows today's sales count, and pending fulfillments. |
| **SW 5** | Pin 29 | GPIO 5 | **Travel Deals Tracker** | Plane flying past window | **Force-Check Travel**: Pulls top active deal exceeding the savings threshold right now. |
| **SW 6** (Far Right) | Pin 27 | GPIO 0 | **Safe Power Off (RED)** | Normal operation | Opens chunky 5-inch touchscreen shutdown confirmation modal (`[SHUTDOWN]` vs `[CANCEL]`). |

---

## 3. Visual Aesthetic & World Engine (LucasArts SCUMM / Sierra Style)

### Aesthetic Inspiration
The visual design is inspired by classic 16-bit point-and-click adventure games (**LucasArts SCUMM** like *Monkey Island*, *Day of the Tentacle*, and **Sierra On-Line** like *Space Quest*, *King's Quest*):
- Richly detailed 16-bit rooms with perspective depth and interactive environment props.
- Characters with expressive walking cycles, idle fidgets, and contextual interactions (e.g. pulling out a magnifying glass, typing on a terminal, inspecting a map, sipping coffee).

---

## 4. Theme & Character Skin System ("Worlds & Avatars")

Desk-Pal is designed with a pluggable **Theme & Skin Engine**, allowing you to switch both the virtual environment ("World") and your companion ("Character") at any time:

### Switchable Character Avatars:
1. **The Classic Companion**: A bouncy, curious Tamagotchi creature.
2. **The Curious Cat**: Lounging on the desk, batting at notification bubbles, stretching, and purring when petted.
3. **The Retro Robot**: Rolling on treads or hovering, antenna flashing when processing data, emitting tiny pixel sparks on errors.
4. **The Pixel Adventurer (Boy / Girl)**: Walking around in classic SCUMM sprite style, inspecting bookshelves, drinking tea at the desk, looking through a telescope.

### Switchable Worlds / Environments:
1. **Cozy Retro Study**: Wooden floorboards, warm fireplace, CRT computer desk, bookshelf, postbox by the door.
2. **Sci-Fi Starship Bridge**: Glowing holographic consoles, sliding airlock doors, starfield window, server rack.
3. **Fantasy Wizard / Alchemist Laboratory**: Bubbling cauldrons (build jobs), scroll shelves, stone hearth, familiar perch.
4. **90s Tech Workshop**: Soldering station, retro beige PC towers, corkboard with pinned notes, mini coffee pot.

### HUD Layout & Screen Real Estate Evolution
- **Physical 3D-Printed Keycaps**: Because the 6 physical switches will have custom 3D-printed labeled keycaps, a permanent on-screen button bar is unnecessary.
- **Maximized Diorama Viewport**: By default, the bottom bar will be hidden to grant the full 1280×720 display to the 16-bit room diorama (expanding room height from ~490px to ~630px).
- **Top-Left Quick-Keys Drawer**: A discrete top-left icon (`[ ⌨ ]` or `[ ☰ ]`) allows toggling an on-screen quick-access overlay whenever you want touch-based inspection without hitting the physical keys.
- **Decoupled Visual Assets**: All room layouts, walk boundaries, and prop placements are stored in JSON configuration files (`room_config.json`) so visual themes can be swapped or modified without touching application logic.

### Dynamic Animations Linked to Your Apps:
1. **BottyMcBotface (`bmcbf`)** (Primary Driver):
   - **Checking Emails**: Pet walks to the postbox, flips through letters.
   - **Reviewing Events / Locations**: Pet unrolls a map or inspects a desk calendar.
   - **Running LLM Inference / Generating**: Lightbulb flashes above head, typing fast on the tiny PC.
   - **Discord Dispatch**: Pet drops a stamped envelope or rings a tiny bell.
2. **Fuel Tracker QLD**:
   - **Bargain Price Drop Detected**: Pet holds a petrol nozzle, or a gas pump icon lights up with green arrows.
   - **Price Peak / No Good Deals**: Pet shrugs with empty pockets.
3. **Etsy & Big Cartel Store Orders**:
   - **New Order Received**: A gift box / parcel drops in front of the door with an alert chime/sparkle! Pet points excitedly at the parcel until acknowledged.
4. **Travel Deals Tracker**:
   - **Deal Above Threshold Spotted**: A paper airplane or vintage plane flies across the window outside.

---

## 4. Touchscreen Interaction Model (Direct Play & Inspection)

Because the 5-inch display is a full digitizer touchscreen, it provides tactile direct interaction beyond the physical switches:

### 1. Direct Pet Interactions (Tamagotchi Mechanics)
- **Petting / Stroking**: Rubbing a finger across the character sprite triggers happy feedback (blushing, floating hearts, tail wagging).
- **Tapping the Pet**: Pokes the character; it reacts with a surprised blink or shows a thought bubble representing its overall system health/mood.
- **Feeding / Treats**: Double-tapping the pet's food bowl drops a pixel snack (rewarding the pet when your background jobs complete successfully).

### 2. Environmental Room Taps (Contextual Inspection)
Instead of pressing a physical switch, you can simply tap the objects in the pet's room:
- **Tap the Mini PC / Desk**: Immediately opens BottyMcBotface (`bmcbf`)'s current task card.
- **Tap the Parcel / Postbox**: Opens the Etsy & Big Cartel order summary.
- **Tap the Fuel Gauge on the wall**: Pops up today's cheapest petrol stations.
- **Tap the Window**: Shows weather or active travel deals.

### 3. Touch Gestures & Alerts
- **Alert Acknowledgment**: When the companion panics or knocks on the glass for an alert, tapping the exclamation bubble acknowledges and dismisses it.
- **Wake on Tap**: When in night/sleep mode, tapping anywhere on the glass wakes the screen.
- **Chunky Modals**: Shutdown confirmation uses oversized (minimum 64×64 pixel) tap targets tailored for easy finger tapping on a 5-inch screen.

---

## 5. Telemetry Integration Pattern (Zero Overhead on PC)

The Pi hosts a lightweight asynchronous REST ingestion server (`http://<pi-ip>:7777/api/v1`).

### Integration Snippet (`deskpal_client.py`)
Each of your existing applications simply calls a 1-line helper function:

```python
from deskpal_client import DeskPal

# In botty_mc_botface:
deskpal = DeskPal(host="<pi-ip>", app_id="ci_monitor")
deskpal.report(activity="reviewing_events", summary="Updating pop-culture calendar")

# In fuel_tracker:
deskpal = DeskPal(host="<pi-ip>", app_id="home_sensors")
deskpal.alert(title="Cheap Fuel Alert", message="BP Everton Park dropped to $1.69", severity="high")

# In store_order_watcher:
deskpal = DeskPal(host="<pi-ip>", app_id="store_orders")
deskpal.report(pending_orders=2, latest_store="Etsy")
```

---

## 6. Implementation Milestones & Current Status

### Phase 1: Hardware & Network (Completed & Verified)
- [x] Hardware verification (6/6 switches, BCM pin assignments, pullups, debouncing).
- [x] Network configuration (pure Wi-Fi on `<pi-ip>`, hostname `deskpal-pi`).
- [x] Passwordless safe shutdown (`sudo shutdown -h now`) with 2s hold or touch modal.
- [x] Systemd/Desktop autostart on boot (`~/.config/autostart/deskpal.desktop`).

### Phase 2: Core Engine & Web Studio Bridge (Completed & Verified)
- [x] Pygame 16-bit rendering pipeline running fullscreen at 1280x720 on `DISPLAY=:0`.
- [x] Authentic 16-bit LucasArts SCUMM background and dynamic perspective depth scaling.
- [x] Zero-dependency embedded HTTP server on Port 7777 (`http://<pi-ip>:7777/`).
- [x] Interactive Web Studio with mouse zoom, pan, 4-corner block stretching, and character toggle.
- [x] Live hot-reload endpoint (`POST /api/config`) saving to disk and updating display in real time.
- [x] Telemetry event ingestion (`POST /api/v1/event`, `POST /api/v1/heartbeat`).
- [x] Authentic 4-beat walk cycle with vertical step bobbing.
- [x] Real-Time Day / Night Environment Cycle (live local time: dusk amber window, midnight starry sky with twinkling stars and crescent moon, cozy room tint).
- [x] Sleep / Bedtime Routine on SW 1 (companion rests on the rug with animated floating zZZ, screen dims, waking up stretches and refreshes).
- [x] Standalone Sprite Forge Tool (`scripts/sprite_forge.py`) for chroma-keying and slicing prop and character sprite sheets.

### Phase 3: Immediate Next Steps (Strategic Handover Roadmap)
1. **Procedural Prop Overlay Framework (Self-Contained Python)**:
   - Implement dynamic prop overlays in `deskpal_app.py` for props defined in `room_config.json`.
   - Use `scripts/sprite_forge.py` to slice multi-frame prop loops (flickering candle, fireplace, CRT monitor).
   - Render real-time CRT phosphor text and scanlines onto the monitor crop at `x: 390, y: 415` (on the desk, not the floor).
   - Keep all animation logic self-contained in pure Python/Pygame (no external 3D software or heavy frameworks required).
2. **4-Way Directional Walk Sprites**:
   - Add Front-facing (walking down towards camera) and Back-facing (walking up away from camera) sprites.
   - Prevents left/right flipping when navigating purely vertically across the floor.
3. **Web Studio Hotspot & Exit Visual Tools**:
   - Add `+ Add Hotspot` and `+ Add Exit` buttons to the Web Studio canvas.
   - Allow users to drag interactive target pins onto furniture, doors, or screen edges.
4. **Satellite Agent Connectors**:
   - Drop `deskpal_client.py` into `fuel_tracker` and `bmcbf` to begin streaming live telemetry to Desk-Pal.


