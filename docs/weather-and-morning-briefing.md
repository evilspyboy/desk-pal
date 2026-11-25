# Weather and Daily Briefing

Weather appears in **App & Action Studio → Applications**. Enable or disable it there, then save. It uses the latitude, longitude and timezone configured for scene day/night lighting. Open-Meteo provides the data; its free endpoint supports personal non-commercial use without an API key. See [Open-Meteo documentation](https://open-meteo.com/en/docs) and [usage terms](https://open-meteo.com/en/terms).

The forecast includes today's minimum/maximum temperature, maximum rain probability, rainfall total, maximum wind speed, UV index and weather code. Temperatures are Celsius, rain is millimetres and wind is km/h. Refresh defaults to hourly, with a minimum of 15 minutes. Network requests run in a worker thread and do not block the display. Failures retain the cached forecast and retry after five minutes. Old forecasts are identified in the briefing rather than presented as today's weather.

In **Events & mappings**, map **Today's forecast changed** (`forecast_updated`) to a scene, animation and placement as with other application events. An unchanged forecast does not enqueue another reaction. Routine heartbeats refresh cached information but their animation is suppressed by default. Weather has no physical button assignment by default; the existing button configuration can assign one if desired.

---

## Daily Briefing & Modal Presentation

When the mmWave radar detects a person at the desk after sleeping, Desk-Pal presents the Daily Briefing modal (`layout: 'morning'`) across two split panels on the 1280×720 display:
1. **Left Panel (Weather Overview)**: Condition icon, high/low temperature, rain chance %, humidity %, and UV index badges.
2. **Right Panel Top (Hero Fuel Watch)**: Fuel type pill, Buy Now / Wait badge, large hero price (`font_hero`), price savings indicator, station name, and distance.
3. **Right Panel Bottom (Schedule & Routine Bar)**:
   - **Line 1 (Today)**: `Today: Nothing on` or occurrences of today's events (`Today: 10:00 AM Team Sync`).
   - **Line 2 (Upcoming / Week)**:
     - If events upcoming within the 3-day lookahead window: `Next: [Day] [Time] · [Summary]`.
     - If nothing scheduled this week: `This Week: Nothing scheduled`.

---

## Voice Commentary (Piper TTS)

Rather than repeating all textual data and statistics already visible on screen, Desk-Pal generates a fast, **conversational audio commentary** (15–20 words max) synthesized via on-device Piper TTS in under 1.5 seconds:

1. **Dynamic Time-of-Day Greeting**:
   - `05:00 – 11:59`: *"Good morning!"*
   - `12:00 – 16:59`: *"Good afternoon!"*
   - `17:00 – 20:59`: *"Good evening!"*
   - `Night`: *"Good day!"*
   *(The greeting modal header dynamically matches the greeting, e.g. `GOOD EVENING!`)*
2. **Weather**: Speaks only the extreme high and concise condition:
   - *"The weather is a top of X with rain."* (if rain probability $\ge 40$% or storms)
   - *"The weather is a top of X and sunny."* (clear / sunny)
   - *"The weather is a top of X and overcast."* (cloudy / overcast)
3. **Fuel**: A single direct price statement:
   - *"Fuel is at Y per litre."*
4. **Calendar Schedule**:
   - *"And you have nothing on."* (when no events scheduled this week)
   - *"And you have X events today."* (when events occur today)
   - *"And no events until tomorrow."* (when next event is tomorrow)
   - *"And X events left this week."* (when events remain later this week)

> **Live Example**: *"Good evening! The weather is a top of 28 with rain. Fuel is at 248.5 cents per litre. And you have nothing on."*

---

## Configuration & Trigger Window

In **Sensors & Hardware → Morning Greeting**:
- **Trigger Window**: Defaults to `06:00 – 21:30` (active during daytime and evening before bedtime).
- **Dark Room & Bedtime Protection**: If the room is dark (lights off) or Desk-Pal is in bedtime sleep, walking past the device in the dark will **never** wake the screen or trigger the greeting. The greeting triggers only when the room is illuminated (lights on / daylight) and bedtime is inactive.
- **Single Daily Trigger**: Greeted state is persisted in `morning_greeting_state.json` (`greeted_date = today`). Once triggered, it will not repeat until after the next sleep cycle on a new date.
- **Section Selection**: You can toggle which integrations are included in the briefing (Weather, Fuel, Calendar). Unchecked integrations are omitted from both the visual card and spoken audio.
