# Hardware live view and calibration

Updated 12 October 2026. Open **Hardware** in Web Studio, or `http://YOUR-PI:7777/hardware`. Hardware is optional: device readers/tests can be enabled separately. Sensor reaction mappings live in **App & Action Studio → Sensors**, separately from reader settings.

## What is available

| Device | Live view / controls | Current status |
| --- | --- | --- |
| RD-03D radar | Target plot, trails, raw values, freshness, guided movement capture | Streaming and captures work; housed position/distance accuracy remains unverified |
| BH1750 light | Lux reading, observed range, optional dark sleep / bright wake | Physical sleep/wake confirmed |
| MPU6050 IMU | Calibrated 3D box, raw acceleration/gyro, guided mounting calibration | Guided calibration, preview and tilt reactions physically confirmed |
| Speaker | Saved USB / 3.5mm / system-default output and short test tone | USB speaker audibility physically confirmed |
| Physical buttons | Configurable BCM pins, labels and five-minute test mode | Physical button test confirmed by the builder on 11 October |
| USB microphone | 15-second level meter | Capture tested; no voice recognition or always-on listening |

Saved preferences are in `config/hardware_settings.json` beside the active room configuration. This includes reader switches, IMU mounting/neutral/bias and light policy. It is installation-specific and excluded from publication. Keep a separate private copy: the ordinary portable content/settings bundle does not yet include it. Content imports should not replace device calibration.

## Current personal wiring

These are the inspected installation's physical header pins, not BCM numbering. Check board labels rather than cable colours when reproducing it.

| Component | Pi connection |
| --- | --- |
| Touch Display 2 power | Physical 4: 5 V; physical 6: ground, using the builder's revised two-position connector |
| RD-03D power | Physical 2: 5 V; physical 9: ground |
| RD-03D UART | Radar TX → physical 10 / Pi RX; radar RX → physical 8 / Pi TX |
| BH1750 and MPU6050 power | Shared physical 1: 3.3 V; physical 14: ground |
| BH1750 and MPU6050 I²C | Shared physical 3: SDA; physical 5: SCL; bus 1, addresses 0x23 and 0x68 respectively |
| Mini microphone | USB |
| Current speaker | USB; earlier quiet speakers used the Pi 4 headphone jack |

The inspected radar cable uses black for 5 V, green for ground, white for TX and red for RX. This is not a general colour convention. The serial console is disabled and `/dev/serial0` is used at 256000 baud. Only one reader should own the port; disable/save the live radar reader before running a standalone UART bench test.

Mount sensors securely before final calibration. A loose IMU measures its own motion rather than the enclosure. Light exposure, nearby LEDs, radar angle and metal/display obstruction affect readings. Mounting pockets are fitted. The builder completed IMU calibration and radar guided capture again on 11 October after mounting. Check light exposure and radar accuracy in the final position.

## Guided IMU mounting calibration

The MPU6050 contains a three-axis accelerometer and three-axis gyroscope. Gravity supplies tilt; the gyroscope supplies relative turning. It has no compass and cannot determine an absolute heading.

1. Enable IMU readings and save; wait for live values.
2. Place the complete device in its normal position, with the sensor fixed to it. Start **Guided calibration**. An initial countdown gives time to pick up or position the unit.
3. Follow the large animated instruction: neutral, tilt left, tilt right, tilt the top toward you, tilt it away, turn left, then turn right. Make each movement once and hold; do not rock repeatedly.
4. Between movements, put it back in the starting position and let it settle. Matching tilt and stillness automatically start the next step; no Next button or fixed inter-step countdown is required. Return detection cannot verify the original table location or absolute compass direction.
5. Review the inferred mounting rotation, neutral offsets and gyro bias, then choose **Apply and save calibration**. Cancel leaves the existing calibration in place.

Neutral is sampled for approximately two seconds. Movement recording waits for motion, can finish early once a clear dominant rotation is captured, and has a bounded recording window. Small/mixed movements or unstable neutral readings can prompt a retry. The live 3D box is hidden while the graphical guide is active.

Each attempt's raw measurements are retained in `imu_capture_latest.json`, including failed runs. **Review saved capture** can recompute a proposal without repeating completed movements; starting a new neutral capture replaces the previous run. Apply is still required to change settings. Recalibrate after changing the sensor mount.

Guided inference learns a full mounting rotation, so a fixed angled sensor can spread one case movement across multiple sensor axes. Opposite movement pairs must agree and the three movement directions must remain distinct. The saved rotation is used by both the 3D preview and character reactions; legacy axis/sign calibration remains supported. Manual XYZ swaps/reversals have been replaced by guided inference. **Set current position as neutral** remains useful for a new resting angle. **Reset preview heading** only resets the visual session. Preview smoothing, gyro bias and a small stillness threshold reduce jitter. A roughly two-second window of stable acceleration and low, consistent residual gyro readings estimates a session-only rest bias to stop stationary heading accumulation. It preserves the saved calibration; very slow uniform turns can resemble bias without a compass. Set current position as neutral also resets preview heading, while Clear tilt offsets removes the resting tilt offsets rather than recalibrating the mounting. Duplicate/stale samples are not integrated. Relative heading can still drift. This is mounting/bias calibration, not a full accelerometer gain calibration.

## Light-triggered rest and screen-off

Enable light readings, then optionally **Enable idle light threshold**. Set:

- **Sleep below:** lux level that represents darkness in the actual enclosure.
- **Wake margin:** extra lux above that threshold needed to wake, preventing repeated toggling near the boundary.
- **Delay:** how long the condition must persist.
- **Stay awake after manual wake:** time to show information before dark sleep is allowed again; default 120 seconds.

In the **Radar** hardware section, enable **Stay awake while radar presence is detected**. Radar alone allows sleep after confirmed absence (30 seconds by default), only from the shared bedtime until sunrise, and wakes on presence. The Radar and Lux bedtime fields edit one saved value; changing either updates the other. Lux alone uses its light threshold. With both policies enabled, presence prevents sleep and lux decides when to sleep after absence. Presence is confirmed for one second. Automatic sleep can be woken by presence, including after bedtime; manual sleep remains asleep. Missing/stale radar readings and calibration captures never trigger absence-based sleep. False detections can still hold the display on.

Darkness uses the normal reachable sleep pose, entry transition and display-power-off flow. Brightness wakes only sleep initiated by the light policy; manual sleep remains manual. Touch/button and morning radar wake grant the full awake interval, even if lux briefly rises and falls. Information popups and other protected interactions prevent immediate sleep while being used. Missing/stale readings cause no sleep/wake action. Disabling the policy restores manual operation and wakes light-initiated sleep.

Sleep/wake has been physically confirmed. Collect daytime and lights-off values again after fixing the sensor in place; a shaded sensor or onboard LED can make a threshold misleading.

For a shaded sensor, enable **Ignore low lux from sunset until bedtime** and choose a local bedtime. Sunset uses the same latitude, longitude and timezone as scene lighting. This prevents low-lux sleep during that window and wakes light-initiated sleep; it does not undo manual sleep. The personal installation uses 22:00. Outside the window, the usual light threshold and manual-wake grace period apply.

## Physical button configuration and testing

Enable physical buttons, then add or remove rows with a button ID, **BCM GPIO number** and label. Save hardware settings before testing. IDs and GPIO pins must be unique. ID 1 retains sleep/wake and ID 6 retains held shutdown; other buttons can be assigned in App & Action Studio. Refresh the scene editor after adding button IDs. Removing a hardware row retains its application mappings. Enabled I²C/UART sensors reserve their bus pins.

**Start button test** shows live pressed state and press counts while suppressing physical button actions, including held shutdown. **Stop button test** restores normal actions; test mode also expires after five minutes. Keyboard and on-screen controls remain available. Driver/pin failures are displayed per button, so missing GPIO hardware does not prevent startup.

The BH1750 measures light reaching its mounting position, which may be much lower than the room's apparent brightness. In this enclosure, a sensor facing a side opening reports low lux even with room lights on. It should work well for light-based sleep/wake in a normally well-lit room when the mounting exposes it to that light. Choose thresholds from readings in the finished enclosure with the room lights on and off; do not copy another installation's lux thresholds. The sunset-to-bedtime override helps when evening lighting does not reach the sensor well.

## Radar view and guided movement capture

**Presence range** is a saved Radar setting, defaulting to 2 metres. Only reported distances strictly below that value count for wake, keep-awake, morning greeting and person-returned reactions. At or beyond the boundary, targets are ignored by these reactions but remain visible in the raw plot/table and calibration captures. Changing **Plot range** does not change the presence limit. Existing confirmation and absence grace still apply. This filters distant returns; it cannot distinguish a reflection from a person within the range.

From the shared bedtime until sunrise, radar presence cannot keep the display awake or wake it automatically. With lux sleep enabled, darkness below the configured threshold triggers sleep even if radar reports a target. Radar-only installations use bedtime sleep during this window. Manual screen/button wake retains the configured grace period, and an open information popup remains protected. After sunrise, normal radar wake/keep-awake behavior resumes. Targets outside the radar plot still exist in the raw data; the plot boundary is a display choice, not a reliable presence boundary.

**Stationary presence limitation:** in this installation, the RD-03D detected a seated user after standing up and sitting down, then stopped reporting any targets after the user remained still. Fresh valid frames continued arriving, so this was not just a hidden marker or a disconnected reader. A seated person can therefore disappear from the radar view without leaving the room. Movement can restore detection, but the reported position/distance may change. Treat zero targets as uncertain absence, not proof that the room is empty. Radar-only bedtime sleep now takes priority over presence until sunrise. Daytime wake/keep-awake still uses confirmed nearby reports and the configured absence grace; that grace does not guarantee detection of a motionless person. The cause and stationary detection reliability remain unverified.

The RD-03D streams continuously; Desk-Pal reads its frames rather than requesting each measurement. Three target slots are decoded. Slot numbers are not persistent person identities, and nearby people/reflections may merge or swap slots.

The facing-user view puts the radar at the top pointing down. **Mirror radar view** changes presentation, not raw coordinates. Raw tables and saved captures remain sensor-relative. The plot offers raw readings or approximately half-second averaging of fresh updates; stale/lost readings clear its history.

**Guided capture** gives graphical instructions and advances automatically while you stand away from the computer. It records centre/left/right movement nearby, then farther back, with return phases. The plot is hidden during capture so the instruction remains readable. Raw frames, phase labels and timestamps are saved in `radar_capture_latest.json` for download/review. Capturing does not apply a hardware calibration or change sensor settings.

A provisional corrected view provides an editable heading estimate and rejects large transient jumps before averaging. A candidate must remain consistent for 0.5 seconds before reacquisition. This changes only the browser plot. Stable reflections and gradual drift can pass; the current correction is not validated distance calibration. Compare against **Original sensor view** when troubleshooting. See the [capture review](radar-capture-review-2026-10-09-second.md) for evidence and limitations.

No software-reset/background-calibration command is sent. Physical-distance verification in the final housing remains necessary. Person-returned reactions use fresh target presence, not the preview correction; see [Sensor reactions](sensor-triggers.md).

Latest housed observation, 11 October: close-range tracking appears reasonable, but stepping farther away can produce a disproportionately distant marker. Target reassignment or reflections are possible explanations, not established causes. A continuous step-back capture comparing raw slots, coordinates and displayed positions is deferred until the builder is available. IMU calibration does not affect radar distance.

## Audio checks

Choose **USB speaker**, **3.5mm jack** or **System default**, adjust the 0–100% test-volume slider, then click **Save speaker settings**. Output and volume are restored when the page reloads. The selected output is saved for Desk-Pal without changing the operating system default. PipeWire is used when available, with ALSA fallback. Speaker tests play a brief tone without changing mixer volume; signal percentage is not perceived loudness. USB speaker audibility was physically confirmed on 11 October; the earlier headphone speakers were audible but quiet.

The saved speaker output and volume also control local Piper speech on **AI & Speech → Speech**. Speech is normalised and peak-limited before this master volume is applied; a beep and speech can still sound different at the same percentage. On 12 October, the current USB speaker played Piper successfully at the saved 90% setting. Increasing speech normalisation helped slightly, but the user still reported quiet playback. See [AI and speech](ai-and-speech.md) for retention, timing and remaining speech work.

The microphone meter measures audio briefly in memory and discards it. No recording is saved or uploaded. Useful microphone interaction is a near-term roadmap item; the current level meter is diagnostic only. Voice processing remains optional and separate from the core display. STT has not been enabled.

For standalone diagnostics use `scripts/check_optional_hardware.py` with `radar`, `microphone` or `speaker`. Disable the matching live reader first where necessary. Tone WAV files use managed temporary directories and are removed after testing. These bench commands do not reboot the Pi or enable character reactions.

## Reactions and touchscreen controls

Reader enablement and reaction enablement are independent. Configure mild/strong tilt, shake and opt-in person-returned mappings under **Sensors**. Current-position tilt/shake briefly interrupts ordinary movement, then resumes the same route; saved placements and greetings use the queue. Sleep, transitions, popups and attention have protection. See [Sensor reactions](sensor-triggers.md) for timing and limits.

Swipe down from the touchscreen's top edge for Keys, Edit, text size and the editor address. Clock and Exit remain visible over the scene. **Scene backgrounds** provides day/night header text colours. These display controls do not change sensor calibration.
