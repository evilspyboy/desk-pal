# Interactive Mini-Games & Arcade Overlay System

Desk-Pal supports interactive mini-games and arcade overlays embedded directly into the room scene (e.g. launching Breakout by tapping the retro computer monitor in the cozy study). Games run inside authentic hardware bezels with isolated multi-input control adapters, background task suspension to maintain 60 FPS on the Raspberry Pi, and safe attention queuing.

---

## 1. Architecture Overview

Mini-games use a three-layer decoupled architecture located in [`src/games/`](../src/games/):

```
┌────────────────────────────────────────────────────────┐
│                   GameOverlay                          │
│                                                        │
│  ┌──────────────────┐  ┌────────────────────────────┐  │
│  │   GameBezel      │  │   GameControllerAdapter    │  │
│  │                  │  │                            │  │
│  │ • CRT Monitor    │  │ • Physical Switches (2-5)  │  │
│  │ • Arcade Cabinet │  │ • MPU-6050 IMU Tilt        │  │
│  │ • Handheld       │  │ • RD-03D Lateral Radar     │  │
│  │ • Touch Buttons  │  │ • On-Screen Touch Buttons  │  │
│  │ • Room Shadows   │  │ • Keyboard (Local/PC)      │  │
│  └──────────────────┘  └────────────────────────────┘  │
│              ▲                      ▲                  │
│              │                      │                  │
│  ┌───────────┴──────────────────────┴───────────────┐  │
│  │               BreakoutGame / Game                │  │
│  │   (Render to Surface & Update with GameInput)    │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

1. **`GameOverlay` ([src/games/overlay.py](../src/games/overlay.py))**:
   - Manages game lifecycle, per-frame updates, and render dispatch.
   - Suspends background companion services and heavy polling tasks on launch.
   - Restores background tasks and flushes queued attention alerts upon game exit.
2. **`GameBezel` ([src/games/bezel.py](../src/games/bezel.py))**:
   - Decoupled frame overlays with responsive viewport clipping.
   - Caches ambient room dimming and drop shadow surfaces to eliminate per-frame allocations.
   - Renders tactile on-screen touch buttons (`◄`, `►`, `▲ LAUNCH`, `✕ EXIT`).
3. **`GameControllerAdapter` ([src/games/controller.py](../src/games/controller.py))**:
   - Unifies diverse input sources into a standardized `GameInputState` (axis X, action button, exit).
   - Isolates mapped gameplay switches, overriding background application triggers while preserving system protections (Switch 1 Sleep and Switch 6 Power).
4. **`BreakoutGame` ([src/games/breakout.py](../src/games/breakout.py))**:
   - 60 FPS retro brick-breaking arcade game with paddle deflection physics, tiered brick palettes, bounce particles, lives, and high scores.

---

## 2. CRT Computer Screen Bezel & Room Integration

When launching a game configured with the `crt_monitor` bezel (default for the Study Computer Screen):

- **Room Scene Visibility**: The game does not black out the room. Desk-Pal draws the room background, bookshelves, desk, and animated character first, then layers the monitor on top with a pre-cached ambient room dimming overlay and drop shadows behind the chassis and pedestal stand.
- **Authentic 1990s PC Aesthetics**:
  - Warm retro PC beige chassis (`#dad5c6`) with 3D beveled highlight edges (`#f4f1e9`) and shadow contours (`#918a7c`).
  - Pedestal stand neck and base resting directly on the desk.
  - Top ventilation cooling slats.
  - Dark recessed CRT screen tube frame (`#1c1e24`) with subtle glass glare reflection.
  - Metal/plastic OEM badge plate (`DESKPAL 486`), glowing green LED power indicator, and power button molding.
- **On-Screen Touch Controls**:
  - `[ ◄ ]` Move Left
  - `[ ► ]` Move Right
  - `[ ▲ LAUNCH ]` Launch ball / action
  - `[ ✕ EXIT ]` Lower exit button + top-right quick-close button (`✕`)

---

## 3. Configuring Game Controls & Settings

Game settings and controller assignments can be customized in Web Studio:

1. Open Web Studio (`http://<pi-ip>:7777`).
2. Navigate to **Applications & Events**.
3. Select **Breakout Arcade** from the application list.
4. Click the **🎮 Game & Controls** tab:
   - **Active Controller**: Choose between `Physical Buttons / Switches`, `MPU-6050 IMU Accelerometer Tilt`, `RD-03D Lateral Radar Tracking`, or `On-Screen Touch Buttons`.
   - **Bezel Frame**: Select `CRT Computer Monitor`, `Arcade Cabinet`, or `Handheld`.
   - **Hardware Switch Assignments**: Map physical pins/switches for Left, Right, Launch, and Exit (defaults: Switch 2 = Left, Switch 3 = Right, Switch 4 = Action, Switch 5 = Exit).
   - **IMU Tilt Sensitivity & Deadband**: Tune roll sensitivity and deadband threshold for smooth tilt steering.
   - **Radar Lateral Steering**: Tune horizontal presence tracking for hands-free paddle control.
5. Click **Save Settings** to persist the configuration to `room_config.json`.

---

## 4. Background Suspension & Performance

On low-power hardware like the Raspberry Pi:
- **Zero Allocations**: Glass glare and drop shadow surfaces are allocated once on initialization and resolution changes, eliminating garbage collection pauses during gameplay.
- **Background Suspension**: When a game launches, background polling, heavy AI scripts, and companion services are suspended so that the display thread holds an uninterrupted 60 FPS.
- **Safe Attention Queue**: System notifications and monitored application alerts (Fuel, Store, Flights, BMCBF) are queued safely behind the game. If an alert arrives while playing, a subtle in-bezel status bar appears (`⚠️ Application alert waiting · Close game to view`). Exiting the game immediately resumes background tasks and plays waiting alerts.

---

## 5. Adding New Mini-Games

To add a new mini-game to Desk-Pal:
1. Implement your game engine in `src/games/<game_name>.py` adhering to the interface:
   - `update(dt: float, input_state: GameInputState) -> None`
   - `draw(surface: pygame.Surface) -> None`
   - `reset() -> None`
2. Register the game in `src/games/__init__.py` and `src/games/overlay.py`.
3. Register the game in `config/room_config.json` under `apps` and bind it to any prop in `Animation Grid → Props` with the `game_script` interaction mode.
