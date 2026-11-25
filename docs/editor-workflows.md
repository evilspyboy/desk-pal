# Scene and animation workflows

## Scenes and connections

Open the scene map to select a room. Drag between entry/exit dots to connect rooms; clicking two dots also works. Select a connection to remove it. Travel can pass through an intermediate room.

Use **Add a scene** with a name and PNG/JPEG background. Adjust its floor, blocked areas, entry paths and placements, then save. Disable a scene from its map card to exclude it from travel and action targets while retaining its settings. At least one scene must remain enabled.

Keep both ends of each entry path on the walkable floor. Red entry paths need adjustment. Blocked areas must leave a connected route to the entry.

## Foreground objects

Trace the visible object and its ground footprint. Footprint mode lets the character pass in front or behind according to its feet position and the footprint's front edge. Use always-front mode for plants or rocks at the edge of the image that should always cover the character.

## Characters and references

Select or add a character in the Animation Grid. Upload its reference image and PNG frames. Uploaded frames are tagged to that character. Reference exports contain the selected character reference and skeleton guides rather than existing animation artwork. A new character can use a saved skeleton template from the template selector.

Frame crops also apply to the skeleton editor: joint positions remain stored against the full source image, while the editor shows the selected frame.

## Placements and playback

Pose placements belong to their scene. Select a placement to move, update or delete it. Multiple placements can share an animation. Playback defaults belong to the animation; a placement can override playback independently.

Move the staged sprite and click **Save position**. This updates the selected location or creates one when none is selected, and confirms the coordinates after saving to the Pi. Use **Add another location** explicitly for an extra placement. A `*` beside a pose in the stager dropdown means it has at least one location in the current scene; the marker updates when locations are added or removed.

The beach has deck-chair rest with sit/get-up transitions, a one-shot coconut drink and a digging sequence that repeats twice. These animations are restricted to the beach. Review the new artwork in motion for any remaining colour or alignment differences.

## Props and computer screens

Enable **View props** to open the scene prop panel. The Animation Grid has a separate Props section for PNG frames and playback. Add a library prop to the scene, then move, scale or rotate it and choose its depth and trigger. The built-in terminal screen effect uses four editable corners and can be linked to a typing placement; its lines animate once the character has arrived and is typing. Props can be disabled or deleted. See [image-props.md](image-props.md).

## Application action targets

Select the destination scene first. An action can target a specific animation and placement, a gesture at any valid placement, any matching gesture at one placement, or any valid gesture and placement. Flexible targets are resolved when the event arrives, respecting character, scene and reachable locations. Disabled scenes are excluded.

## Standby

Standby selects a reachable sleeping, sitting, rear-reclining or deck-chair placement, completes the settling transition and powers down the panel. A room without a resting placement powers down with the character stationary. Waking restores the panel before the getting-up transition.

The rear-reclining `seated_back` animation is shared by the beach and apartment. Place it behind a chair or couch back; the object outline provides the overlap. Sit-down/get-up sequences are transition-only and are played automatically. Existing side deck-chair animation remains available.

Beach chairs have exactly two independent surface masks: **Backrest** and **Seat**. In Foreground objects, select a chair and choose either surface under **Outline to edit**; adjust its points and save objects. At the linked seated placement, both backrest and seat masks cover overlapping character pixels, including boots behind the seat and sit/get-up transitions. Walking uses both surfaces with normal footprint depth. Ground blocks and saved pose positions are separate and unchanged.



For a saved pose placement, the floating placement controls include **Add vector offset**. Choose its mask surface, then drag the magenta Hip, Knee and Foot handles. The dotted line through the knee separates the seated body from the hanging legs for that surface. Moving the Knee changes the layer boundary; moving the Foot changes its angle. Hip marks the body's alignment. **Save vector offset** persists it; **Remove vector offset** followed by Save removes it. Guides can be hidden while retaining their effect. Coordinates are stored relative to the cropped sprite, so the guide follows movement, perspective scale and left/right flipping. Overrides are local to scene, placement, character and pose; other placements keep their previous overlap. The left beach chair guide was physically adjusted and accepted by the user; preserve it. The right-chair seated placement was removed because its sprite angle was unsuitable.

Use **Add second leg guide** when the pose has knees at different depths. Near and Far guides have independent draggable handles (magenta and green). Each leg's nearest-knee region uses its own knee-to-foot layer boundary. Existing first-guide points are retained. Save with **Save vector offset**.

### Animation availability and transitions

Load a saved animation in Animation Grid. Under **Where and how this animation is used**, leave **Available in all scenes** checked or select the scene thumbnails where it is valid. Restrictions do not delete existing placements.

Set **Before: sit/lie down** and **After: get up** to the character's matching transition animations. Resting animations need both transitions for idle and sleep use. Mark the transition sequences themselves **Transition only** to keep them out of ordinary pose choices. **May be used for the sleep button** controls standby eligibility; **May be used while idle** controls normal idle eligibility.

Use **Save animation** to save these settings along with the animation frames. Loading a sequence restores its saved settings. No scenes, placements or event mappings are reset by this editor update.

Reference-sheet controls are grouped under **Download generation references**. These downloads do not save animation changes; use **Save animation** first when changes should be retained.
