# Desktop Companion Mode

Desk-Pal can run as a normal interactive companion in a resizable desktop window on Windows, macOS, or Linux, without requiring a Raspberry Pi or physical hardware display.

Unlike the browser-based **Live Preview** (which runs headless via `SDL_VIDEODRIVER=dummy` and streams JPEG frames to Web Studio on port 7779), **Desktop Companion Mode** runs the full native graphics engine, animation playback, event queue, interactive props, and background integration monitoring in an interactive PC window.

---

## Launching Desktop Companion Mode

### 1. Python Runner (Recommended)

Run the desktop launcher from the repository root:

```powershell
python scripts/run_desktop.py --size 960x540
```

Supported options:
- `--size WxH` or `--window-size WxH`: Sets initial window dimensions (e.g. `960x540`, `1280x720`, `640x360`). Defaults to `960x540` (75% scaling of the logical canvas).
- `--port PORT`: Port for the local Web Studio & REST API (default: `7777`).
- `--data-dir PATH`: Optional isolated directory for configuration and assets.

### 2. PowerShell Script

Windows users can use the PowerShell launcher:

```powershell
.\scripts\start_desktop.ps1 -Size 960x540 -Port 7777
```

### 3. Direct Application Flag

Desk-Pal can also be launched directly through `src/deskpal_app.py`:

```powershell
python src/deskpal_app.py --desktop --size 960x540
```

On Windows and systems where Linux panel backlight controls (`/sys/class/backlight`) and GPIO are absent, Desk-Pal automatically defaults to Desktop Companion Mode rather than attempting fullscreen hardware takeover.

---

## Window Scaling and Interaction

The logical coordinate space of Desk-Pal remains fixed at `1280×720` pixels. This ensures all scenes, character perspective heights, walkable trapezoids, interactive props, dialog cards, and font sizes render identically to hardware.

### Aspect Ratio & Scaling
- The window is freely resizable (`pygame.RESIZABLE`).
- `DesktopWindow` scales the logical `1280×720` canvas to fit the window surface preserving 16:9 aspect ratio.
- Non-16:9 window geometries are cleanly letterboxed (black bars top/bottom) or pillarboxed (black bars left/right).

### Mouse & Touch Coordinate Mapping
- Mouse clicks, drags, and touch events are automatically translated from window coordinates to the `1280×720` canvas space.
- Clicks outside the canvas (in letterbox bars) are clamped to the canvas bounds.
- Character navigation, prop inspection, interactive screens (such as the TV viewer), and the pull-down header operate seamlessly at any window size.

---

## Desktop Controls & Keyboard Shortcuts

When physical GPIO buttons are absent, equivalent controls are available via keyboard and screen:

| Input | Action |
| --- | --- |
| `1` | Switch 1: Enter / Exit Standby (Sleep) |
| `2` | Switch 2: BMCBF integration popup |
| `3` | Switch 3: Fuel Tracker integration popup |
| `4` | Switch 4: Travel Radar integration popup |
| `5` | Switch 5: Store Monitor integration popup |
| `6` | Switch 6: Open Exit / Shutdown confirmation |
| `S` | Toggle / pin the on-screen bottom switch keys |
| `H` | Toggle the pull-down header panel |
| `Esc` | Dismiss modal dialog, close TV viewer, or cancel edit mode |

---

## Power and Shutdown Behavior

- **Standby / Sleep (`DesktopDisplayPower`)**:
  - Standby does not attempt to control Linux backlight hardware (`/sys/class/backlight`).
  - When the character settles into sleep or standby is triggered, the window displays a dark standby state with a subtle wake prompt:
    `[ Desk-Pal Standby - Click or press any key to wake ]`
  - Clicking anywhere on the window or pressing any key immediately wakes Desk-Pal back up.
- **Shutdown / Exit**:
  - The shutdown modal UI displays `"EXIT DESK-PAL?"` and `"Close companion desktop application?"` with an `"EXIT"` button.
  - Confirming exit cleanly shuts down the application loop and frees all resources without calling `sudo shutdown`.

---

## Audio Output

- Audio playback in `audio_output.py` uses the host operating system's native audio output:
  - **Windows**: Built-in `winsound` playback for WAV audio.
  - **macOS**: Built-in `afplay`.
  - **Linux / Pi**: PipeWire (`pw-play`) with ALSA (`aplay`) fallback.
- Audio drivers and speaker output remain completely optional; missing or unconfigured audio devices will not halt execution.

---

## Remote Mirroring Mode (Pi to PC / Mac / Browser)

You can run the full Desk-Pal engine on your Raspberry Pi (with all sensors, integrations, and character logic active) and mirror its live display output directly onto any networked PC, Mac, phone, or tablet.

### 1. Zero-Install Web Display

Open your web browser on any networked device and navigate to:

```
http://<pi-ip>:7777/display
```

- **Features**:
  - Full-screen / windowed interactive 16:9 canvas with aspect-preserving letterboxing.
  - Interactive touch: click or tap the screen to move the character, interact with props, or dismiss popups.
  - Controls drawer: Sleep / Wake button, dynamic app switches, and fullscreen toggle.
  - Keyboard shortcuts: `1`–`5` for buttons, `Space` for Sleep/Wake, `F` for fullscreen.
  - **Zero Idle CPU**: Uses on-demand frame capture; the Pi encodes JPEG frames only when a viewer is actively connected. When the browser tab is hidden or closed, Pi frame encoding stops immediately.

You can also click the **"Remote Display"** button in the Web Studio header navigation bar at `http://<pi-ip>:7777/` at any time.

### 2. Native Desktop Companion Remote Client

If you prefer a floating native desktop window on your PC/Mac rather than a browser tab, run the desktop launcher with `--remote`:

```powershell
python scripts/run_desktop.py --remote http://<pi-ip>:7777 --size 960x540
```

Or using PowerShell:

```powershell
.\scripts\start_desktop.ps1 -Remote http://<pi-ip>:7777 -Size 960x540
```

- **Features**:
  - Opens a lightweight native resizable PC window.
  - Streams frames at ~15 FPS from the remote Pi.
  - Translates mouse clicks and touches directly to the remote Pi.
  - Keys `1`–`5` trigger remote switches, `Space` triggers Sleep/Wake, `Esc` cleanly exits the PC viewer without affecting the running Pi.

---

## Comparison: Modes at a Glance

| Feature | Desktop Companion (Local) | Desktop Companion (Remote) | Remote Web Display | Local Live Preview | Pi Hardware Mode |
| --- | --- | --- | --- | --- | --- |
| **Engine Location** | Local PC | Raspberry Pi | Raspberry Pi | Local PC | Raspberry Pi |
| **Viewer** | Resizable PC window | Resizable PC window | Browser (`/display`) | Web Studio panel | 5" DSI touchscreen |
| **Installation** | Python + Pygame | Python + Pygame | Zero-install (any browser) | Python + Pygame | Dedicated hardware |
| **Display Stream** | Native direct render | HTTP JPEG stream (~15 FPS) | HTTP JPEG stream (~15 FPS) | HTTP JPEG stream (~10 FPS) | Linux framebuffer |
| **Input** | Local keyboard/mouse | Forwarded over HTTP | Forwarded over HTTP | Web Studio controls | Physical touch & buttons |
| **Idle Overhead** | Normal PC app | 0% Pi CPU when idle | 0% Pi CPU when idle | N/A (offline) | Standard Pi display |

