# Day and night artwork and props

Every scene follows the shared sunrise/sunset location configured under **Day / night settings**. The **Preview: Day / Night** selector above the canvas is editor-only: it never changes the Pi clock or solar settings.

## Scene backgrounds

Open **Scene backgrounds** beside the scene selector to upload or replace daytime and nighttime artwork for the current scene. The two images should have the same composition and preferably be 1280×720, so existing floor points, obstacles, foreground masks and pose placements still align. PNG/JPEG uploads support up to 12 MB and 20 megapixels. New scene creation in **Scene map** also accepts an optional nighttime background.

Uploads stage new image files without overwriting old artwork. Click **Save to Pi** to save backgrounds and other pending editor changes; closing the panel leaves those changes staged. Saving new artwork for the displayed scene reloads its background without resetting the character's current action or placements. Without a nighttime image, the renderer derives night shading from the daytime artwork; existing default night files remain supported.

Scene packages and normal content backups carry the uploaded images and scene metadata. Day/night images share one layout and one set of placements.

## Prop placements

Turn on **View props**, select a placed image prop or built-in typing monitor, and set **Visible** to **Day and night**, **Day only**, or **Night only**. This applies to that placement, independently of the library animation and its normal activation trigger. Save to Pi to keep the setting. Existing placements default to both and are unchanged.

Switch the editor preview between day and night to check placement visibility while playing the prop. On the Pi, the switch occurs halfway through the existing dawn/dusk blend. A prop outside its selected period is completely hidden, including any inactive frame, and begins fresh when visible again and its trigger is active. Sleep and pose/application triggers continue to apply. Props are not automatically darkened: illuminated screens can remain bright. Separate day-only and night-only placements can use different animations in the same location.

Validation: upload validation, day/night thresholds, image and built-in monitor rendering, preview controls and existing editor regression checks passed locally; image prop rendering also passed on the deployed Pi. Saved settings were preserved during deployment.

Configuration: scene `background` / `background_night`; placement `time_of_day` (`both`, `day`, `night`). No existing artwork, geometry or saved placements are changed when these controls are introduced.

