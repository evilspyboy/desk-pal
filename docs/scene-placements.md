# Scene placements and travel

Use the **Scene** dropdown above the scene image to switch backgrounds for editing. **Save to Pi** saves the selected scene and displays it. Each scene owns its floor, blocks, props, pose rules and gesture placements; character animations are shared.

**+ Entry / Exit** works like Add Block: it immediately creates an Exit handle and a connected Inside handle on free floor. Drag either handle to adjust the path, or drag the connecting line to move both together. The inspector lets you rename, delete or link it in the map. The connecting line must remain on walkable floor without crossing blocks. On departure the character walks to Inside, then follows the line to Exit; on arrival it follows the same line inward.

**Scene map** shows scene thumbnails and their entry/exit nodes. Drag between nodes (or click two nodes) to connect them; select a connection to remove it. Use the scene card's editor button to edit entry/exit paths in the regular scene editor. Deleting an entry removes its links. Links work in both directions.

**Walk to scene** saves the editor state and navigates through the shortest walkable chain of linked entry points. Travel follows the saved connections among enabled scenes; the current content includes study, video store, beach and apartment. Resting characters get up before walking; telemetry does not interrupt travel and standby cancels it. Newly added scenes start with empty gesture placements; existing personal scenes retain their saved placements. Entry markers are editable thresholds, not automatically detected doors.

`scenes[id]` stores theme/background, geometry, placements and portals. `scene_links` pairs `{scene, portal}` endpoints. `active_scene` selects the room. The top-level values and legacy `scene_placements` remain compatibility projections. Study calibration and poses are preserved during migration.

The video-store shelf has a blocked ground footprint. Animated props and beach digging are implemented; see [image props](image-props.md) and [editor workflows](editor-workflows.md). Background source prompts: `assets/themes/GENERATED_SCENES.md`.

## Compatibility notes

`scene_placements[active_scene || theme || "cozy_study"]` stores the scene's
`interaction_spots` and `pose_rules`. Animation sequences remain shared character
assets. Legacy locations migrate only to the current scene. A new scene starts
with empty placements, even when another scene uses the same character/gesture.

The existing top-level `interaction_spots` and `pose_rules` are a compatibility
projection of the current scene for the display engine. The editor activates the
scene after reading configuration and synchronizes that projection on save.
The scene selector synchronizes before switching, activates the new scene and
loads its background and geometry. The display engine loads scene-specific backgrounds.

The Pose Stager draws every allowed placement of the selected gesture. The selected
copy uses the draft drag position until Save position is used; other copies use their
saved positions. Each badge selects its copy. Its × removes only the pose/location
association and saves; the shared location remains available to other gestures.
Overlapping badges stack so colocated placements remain selectable. Global location
deletion remains a separate, explicitly labeled action.
