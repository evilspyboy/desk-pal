# Remaining Adventurer 1 gestures

> Artwork/provenance record. Runtime selection, crops, anchors and placements come from saved configuration; this record is not the current deployment or task list. See the [documentation index](../../../../docs/index.md).


Generated with the built-in image generator, using the established side, rear and front Adventurer 1 idle sprites as identity references. Eight transparent source PNGs are saved in `raw/`; every actual prompt is in `prompts.json`.

- `window_look`: back facing camera, hands on hips, breathing.
- `lean_globe`: side view leaning forward to examine something at desk height.
- `wave_arms`: front view with raised arms waving for attention.
- `ponder`: side view, hand at chin, small thinking/breathing movement.

Each loop has two generated source frames, held in editable slots at 4 FPS. These remain draft loops with minor generated differences. Ground crop, anchor and reference height are in `manifest.json`. Window look and waving do not mirror when the scene's facing setting changes. Mailbox interaction uses a copy of the Pi's current table-height reach sequence, preserving its timing and frame settings; no redundant images are generated for it.

The Pose Stager and action selector now use the active character's validated sequence bindings or explicitly matching tagged legacy sprites. They no longer fall back to untagged or other-character images. Unavailable existing action choices remain visibly marked instead of silently changing saved mappings. The retired Puppet Poser UI is removed; its original assets/config and the Animation Grid wireframe are retained.

Locations have distinct Add and Update actions. Adding never overwrites an existing ID, even with the same name. A gesture can have several `pose_rules[role].valid_spots`, and a location can have several `animations`, alongside its existing default `animation`. Selecting a location and updating it with another gesture adds that association. Existing location IDs and action links remain stable; linked actions resolve current location coordinates.

Future log-input selection can build on these associations: a fixed gesture with any valid location; a fixed location with any compatible gesture; or any compatible gesture/location pair. The future selection policy UI is not implemented in this change. Existing event mappings retain their behavior.
