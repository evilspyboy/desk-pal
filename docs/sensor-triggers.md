# Sensor reactions

Open **App & Action Studio → Sensors**. This built-in source uses the same scene/animation mapping cards as applications, with only Sensor triggers and Events & mappings tabs. It has no polling URL or hardware-button assignment.

Enable the IMU/radar readers on Hardware first. Calibrate the IMU in its mounted position. Sensor reactions can be independently disabled without turning off live hardware diagnostics.

Motion events include mild/strong left, right, toward-you and away tilt, plus shake. Defaults: 12° mild, 28° strong, 0.25-second confirmation, 0.18-second sampling smoothing, a 3° neutral-return margin and 0.5-second per-event cooldown. Strong tilt must exceed mild by at least 2°. A held tilt does not keep firing. Shake requires two acceleration excursions within 0.8 seconds, default 0.45g away from normal gravity. These are starting values to tune on the real unit, not hardware sensitivity settings.

The adventurer has two new four-frame one-shot sequences: `balance_mild` and `balance_strong` (also the default shake reaction). These are not idle or sleep animations. Generated sheets were split without rescaling the artwork; visible boot anchors align across frames. They are available in Animation Grid for changing playback/frames.

Each reaction offers **Where the character is** or **Saved scene / location**. Current-position targeting resolves when playback begins, preserves facing, needs no placed pose and ignores stale coordinates/scene IDs. Placed targeting uses the normal visual scene picker and floor routing. Current-position reactions do not reserve every placement of the same animation from idle selection.

Current-position reactions also offer **Facing / mirror**: keep facing, left (mirrored), or right (original). Following the physical direction test, left-tilt mappings use original playback and right-tilt mappings use mirrored playback, for both mild and strong levels. These are animation-facing choices, separate from IMU axis calibration.

Current-position tilt/shake reactions briefly interrupt walking or ordinary standing activity. The renderer plays the balance sequence without changing the destination, route or queued application; movement/playback clocks pause, then resume after the sequence. Reactions do not stack or interrupt rest poses, transitions, popups, button responses or attention alerts. Saved-location reactions and greetings use the normal queue; waiting sensor reactions older than five seconds expire. Sleeping, editor mode and active hardware capture do not accumulate motion reactions. Default reactions have no message/label. Return toward neutral to rearm a held tilt; the configured cooldown still applies.

**Person returned** is separately opt-in. After fresh radar frames show no target inside the configured Hardware presence range for the absence interval (default 60 seconds), a nearby target present for one second can trigger the greeting. Initial presence and a reader outage do not count as a person returning.

To ensure stability during normal seated work and prevent false absence/return cycles, the radar pipeline includes an active tracker (`RadarTracker` in `src/radar_tracker.py`):
- **Dropout coasting (2.5 seconds)**: When a stationary seated person's micro-Doppler falls below sensor thresholds, previous target coordinates coast for up to 2.5 seconds before declaring absence.
- **Multipath jump rejection (600 mm / 0.5s)**: Sudden jumps greater than 600 mm (such as virtual reflections from high-RCS objects like aluminium drink cans in the near field) are held as unconfirmed until sustained for at least 0.5 seconds.
- **Physical environment note**: Metallic objects (drink cans, metal laptop chassis, aluminium mounts) placed directly in the radar's near-field can cause strong specular reflection and multipath ghosting (often manifesting as virtual returns at ~3.4 m). Moving metallic items out of the immediate transceiver cone dramatically improves centroid accuracy.

The personal mapping is a four-second one-handed `wave_hello` where the character is, and may be changed to a saved placement. It is a welcome-back greeting with no alert popup; the two-handed `wave_arms` is reserved for attention. The personal installation currently uses a 180-second absence interval; the generic default remains 60 seconds.
 
### Planned: Sedentary & Wellness Reminders
Using continuous radar presence tracking, an opt-in wellness trigger or companion "app" can monitor when someone has remained seated at the desk without standing or leaving for a prolonged interval (e.g., 45–60 minutes), prompting a reminder to stretch or drink water. See [BACKLOG.md](BACKLOG.md).

## Bedtime presence & stay-awake policy

Under **Hardware → Light sensor / Radar**, configure bedtime (default 22:00) and presence range (default 2.0m):
- **Working late**: When working at the desk past the configured bedtime, confirmed radar presence inside the 2.0m bubble keeps Desk-Pal awake so it will not enter standby while you are still working.
- **Bedtime sleep on departure**: As soon as no presence is detected within the 2.0m bubble after bedtime for the configured absence delay (default 30 seconds), Desk-Pal enters standby for the night.
- **Nighttime silence**: Once asleep at night, ordinary radar presence will not wake Desk-Pal back up (preventing accidental middle-of-the-night disturbance). Desk-Pal stays asleep until morning use, sunrise, or room lights return. Manual touchscreen/button wake remains available with its standard grace hold.

## Morning greeting

Under **Sensors → Sensor triggers**, enable **Greet once after sleep when radar sees someone**. Set a local start and cutoff (defaults 06:00–10:00) and optionally choose a Fuel Tracker integration. It uses the scene-lighting timezone. This setting is independent of the general sensor-reaction and person-returned switches, but the radar reader must be enabled on Hardware.

After a sleep episode within the previous 36 hours, one second of fresh radar reports inside the configured presence range during that window can wake the screen and queue a current-position wave with a greeting/date/fuel popup. The fuel value comes from the latest independently refreshed heartbeat, not from the last button press; cache age is shown, and missing/delayed results are identified. It makes no new producer or weather request. The popup stays until dismissed, with a low-lux wake grace period. A pending greeting expires at the cutoff; a popup already shown can still be dismissed afterward.

Once-per-day delivery and the preceding sleep time are retained privately in `morning_greeting_state.json`, so a renderer restart does not repeat the greeting. Sleep after an already-delivered greeting does not rearm it for that same local date. Reader outages and calibration captures do not count as presence. A simultaneous person-returned event is skipped when the morning greeting is queued. Radar presence is not personal identification, so a false target can still trigger the greeting. Generic installations start disabled; the personal Pi is enabled. The first physical morning trial passed on 12 October. Weather and configurable application sections are now available; clothing advice and optional spoken delivery remain follow-up work.

Mapping/threshold settings live in the ordinary configuration under the Sensors source. Hardware enable switches, axis calibration and reader options stay in `hardware_settings.json`. Full private backups retain the source's settings/mappings; ordinary integration-definition packages are intended for external applications.

Validation: deterministic sensor tests cover edge triggering, escalation, neutral rearming, calibrated axes, shake/cooldown, stale/disabled readings, capture suppression and presence/outage behavior. Targeting tests cover current-position resolution. Queue tests cover expiration before a rest transition. Live Pi checks loaded all eight frames, verified finite playback and preserved current-position/facing with stale scene/spot values. Temporary remote diagnostics were removed. Physical tilt interruption/resumption, mirroring and the 0.5-second cooldown were confirmed by the user. Sensors are now secured in holders and IMU calibration has been repeated. Morning greeting was physically confirmed on 12 October at 07:18 Brisbane time, including wake, popup and dismissal. Person-returned leave/return rehearsal remains pending.

### Generating another character

Both balance reactions have four frame-specific skeletons. Animation Grid reference downloads include them in the individual strip or the full character collection, together with the character reference, 4 FPS timing, play-once behaviour and movement instructions. Existing animation artwork is omitted. The reviewed source annotations are in `config/skeleton_annotations.json`; balance instructions are also retained in `config/balance_reference_notes.json`.

Talking and hello animations now also include reviewed skeleton guides and saved generation instructions in individual/full reference exports. Talking uses larger mouth shapes and per-frame torso anchors; the user confirmed the alignment correction looked better on 13 October. See [AI and speech](ai-and-speech.md).
