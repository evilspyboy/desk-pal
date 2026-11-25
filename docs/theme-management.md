# Desk-Pal Theme Management System

The Theme Management System allows users to save, duplicate, switch, export, and import complete visual aesthetics ("Themes") in Desk-Pal without modifying or restarting persistent background companion microservices or hardware calibrations.

---

## 1. Overall Theme vs Per-Scene Styling

Desk-Pal organizes visuals in a hierarchical two-tier architecture:

### Tier 1: Overall Theme (Master Profile)
An Overall Theme encapsulates the entire visual identity across the 1280×720 display:
* **UI Palette**: Colors for `background`, `surface`, `surface_light`, `border`, `accent`, `green`, `red`, `blue`, `text`, and `text_dim`.
* **Card & Modal Styling**: Controls the `border_radius` (e.g. 10px–18px), header accent glow, and border treatment for popup modals (Morning Greeting, Calendar reminders, Fuel notifications, Wellness hydration/movement alerts, and on-screen button bezels).
* **Active Scene & Scene Graph**: Which scene the device primarily presents (e.g., `cozy_study`, `apartment`, `resort_beach`, `video_store`), along with linked rooms in the scene world diorama.
* **Active Character & Sequences**: The character avatar (e.g. `adventurer_v1`), spritesheet bindings, and rest postures.
* **Placed Props & Interactive Objects**: Image props, CRT monitor effects, and TV Easter egg sequences (ALF, Transformers, Doctor Who K-9).

### Tier 2: Per-Scene Styling (Environment)
Within each theme, individual scenes retain their own spatial characteristics:
* **Day & Night Backdrops**: Stored in `assets/themes/<scene_id>/`.
* **Floor Geometry**: Walkable trapezoid / polygon vertices and scale bounds.
* **Obstacles & Collisions**: Furniture footprints and pathfinding blocks.
* **Interaction Spots**: Named waypoints, vector offsets, and animation bindings.

---

## 2. Persistent Systems (Never Disrupted)

When swapping between themes, the following systems remain **completely active, uninterrupted, and unchanged**:
1. **Companion Services**: Calendar URL (`port 8097`), Fuel Tracker QLD satellite, Weather forecasts, Flight Radar.
2. **Hardware Calibrations**: mmWave radar detection distance/sensitivity, I2C ambient light sensor lux thresholds, bedtime schedule (`06:00 – 21:30`), and physical GPIO switch assignments (Pins 37, 35, 33, 31, 29, 27).
3. **Telemetry & History**: Background activity queue, pending alerts, and attention notifications.

---

## 3. Built-in Baseline Themes

Four default themes are provided out of the box in `/home/admin/themes/` and local repo `themes/`:

| Theme ID | Display Name | Active Scene | Visual Characteristics |
|---|---|---|---|
| `cozy_study` | Cozy Study | `cozy_study` | Classic oak & amber study, CRT monitor, arched window, warm dark mode palette, 14px rounded cards. |
| `retro_apartment` | Retro Apartment | `apartment` | 90s pop-culture collector apartment, CRT TV playing ALF & Transformers, neon magenta & cyan synthwave palette, 12px cards. |
| `resort_beach` | Resort Beach | `resort_beach` | Tropical coastline with animated ocean ripples, thatched tiki bar, sunlit gold & seafoam azure palette, 16px soft cards. |
| `video_store` | Video Store | `video_store` | Late 80s / early 90s VHS rental store, movie shelves, CRT counter, Blockbuster royal blue & yellow palette, 10px retro cards. |

---

## 4. Web Studio User Interface

In Web Studio (`http://<pi_ip>:7777`):
* **Top Navigation Bar**: Features an immediate **Theme Dropdown Selector** `[ Theme: Cozy Study ▼ ]` and a **🎨 Themes** button. Switching the dropdown applies the new theme immediately on both the Web Studio canvas and the physical Raspberry Pi display.
* **Bottom Taskbar**: Includes a dedicated **🎨 Themes Studio** button under the *System* row.
* **Themes Studio Modal Window**:
  * **Theme Cards**: Displays live color swatch chips, active scene/character badges, card border radius, and description.
  * **Actions**:
    * `🚀 Apply Theme`: Hot-reloads the theme instantly.
    * `📋 Duplicate`: Clones any existing theme under a new ID and name for safe experimentation.
    * `💾 Export`: Downloads a `.zip` package containing `theme.json` and `manifest.json`.
    * `🗑️ Delete`: Deletes custom themes (built-in themes and the active live theme are protected).
  * **Save Current As Theme**: Captures any custom scene placements, prop adjustments, and palette tweaks made in Web Studio into a permanent, named theme profile.
  * **Import Theme**: Uploads `.zip` or `.json` theme archives.

---

## 5. REST API Endpoints

The embedded HTTP server on Port 7777 exposes the following endpoints:

### `GET /api/themes`
Returns all installed themes, metadata, and identifies the currently active theme:
```json
{
  "themes": [
    {
      "id": "cozy_study",
      "name": "Cozy Study",
      "active_scene": "cozy_study",
      "active_character": "adventurer_v1",
      "palette": { ... },
      "card_style": { "border_radius": 14 },
      "is_active": true,
      "is_builtin": true
    }
  ],
  "active_theme": "cozy_study"
}
```

### `POST /api/themes/apply`
Hot-reloads a theme in memory without process restart:
```json
{
  "theme_id": "retro_apartment"
}
```

### `POST /api/themes/save`
Captures current live visual state into a new theme profile:
```json
{
  "id": "cyber_lounge",
  "name": "Cyber Lounge",
  "description": "Neon lounge with blue accent cards",
  "card_style": { "border_radius": 12 }
}
```

### `POST /api/themes/duplicate`
Clones an existing theme:
```json
{
  "source_id": "resort_beach",
  "new_id": "tropical_sunset",
  "new_name": "Tropical Sunset"
}
```

### `POST /api/themes/delete`
Deletes a custom theme (disallows active or built-in):
```json
{
  "theme_id": "tropical_sunset"
}
```

### `GET /api/themes/export?theme=<id>`
Downloads `deskpal_theme_<id>.zip`.

### `POST /api/themes/import`
Accepts a theme archive or JSON binary payload to install a new theme.
