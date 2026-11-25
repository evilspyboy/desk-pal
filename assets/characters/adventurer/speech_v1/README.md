# Speech and welcome-back sprites

Generated with the built-in imagegen tool on 13 October 2026, using the existing adventurer_v1 front-facing standing sprite as the character reference. `talking` has four mouth poses at 6 FPS. `wave_hello` uses three same-hand poses at 4 FPS, with the second pose repeated to close the loop; the fourth generated pose changed hands and is excluded.

The generated sheets are retained for provenance. `prepare_speech_sprites.py` splits them and aligns the boot centre/baseline without resizing or recolouring pixels. Frame PNGs, crop data, reviewed skeleton joint guides and generation notes are in `manifest.json`. These are ordinary character-owned Animation Grid sequences, not idle or standby candidates by default.

Talking also uses reviewed per-frame anchors to compensate for the generated torso's horizontal drift: 0, +2, +4 and +4 pixels on the shared canvas. Foot-centre alignment alone produced a visible sideways movement in the physical test; torso registration supersedes it for the talking loop. No scene placement coordinates were changed.

Generation prompt summary: preserve the supplied front-facing character, costume, head size, palette and full-body alignment; four transparent equal-cell pixel-art frames. Talking changes only the mouth, then was edited to make the open-mouth poses larger and more legible at small display sizes. Hello uses a calm, single raised hand with small wrist motion and the other arm relaxed. No props, text or backdrop. The two-handed attention wave remains a separate existing sequence.
