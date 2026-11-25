# Animation playback

Animation Grid > Playback sets the animation default: `once`, `repeat` (1-1000 complete plays), `loop`, or `ping_pong`. Save with Save animation. Legacy sequences without a mode retain their former loop/ping-pong behaviour. Existing reach/kneel/mailbox gestures were migrated to play once.

Finite actions finish every requested frame before autonomous movement selects its next action. Their last frame is held for its full frame duration. Loop and ping-pong continue until the current action is ended or replaced by the scheduler or a new event. Ping-pong does not duplicate endpoints. Editor previews hold the final frame after finite playback; pressing Play restarts the preview. Stager previews use the same frame timing.

Ordinary application events are milestones: a looping animation with no duration override plays one full cycle and completes. A positive loop-time override supplies a bounded dwell. Idle loops can continue until the next event; attention and connectivity-outage holds follow their own interaction/recovery rules. The same sequence can therefore loop continuously in a preview but finish after one cycle when used for a normal event.

Select a placed sprite in the scene to see its floating playback panel. `Default *` displays the animation's inherited mode. Any other choice overrides only that character and pose at that location. Use Save placement playback to persist; selecting Default removes the override. A location must exist and be linked to the pose before it can have an override. Other copies retain their own settings.

Overrides live at `scene_placements[scene].interaction_spots[].playback_overrides[character][pose]`. The active-scene compatibility projection exposes them to the Pi at `interaction_spots`. Animation defaults use `playback_mode` and `repeat_count`; `ping_pong` remains a compatibility field. Grid reference exports describe playback mode as well as frame holds.

Validation: test_playback_modes.py checks each mode, single frames, exact completion boundaries, and isolation across three locations and multiple characters. test_animation_references.cjs checks matching editor timing. Existing Pi tests (8 character/animation checks and 9 navigation checks) passed. Browser checks verified the floating control, repeat count, inherited default, and play-once grid selection.
