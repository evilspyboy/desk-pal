# Deck-chair animation

> Artwork/provenance record. Runtime selection, crops, anchors and placements come from saved configuration; this record is not the current deployment or task list. See the [documentation index](../../../../docs/index.md).


Generated using the built-in image-generation tool. Original character references: `../walk/walk_0.png` and `../poses/v1_stand_side_0.png`.

The selected sheet is `deck_chair_sheet.png`; `deck_chair_0.png` through `deck_chair_5.png` are lossless copies used with per-frame crops and independently editable skeleton tags. No existing character assets were overwritten. The Pi configuration contains the crop, scale, anchor, skeleton, beach-only eligibility and transition bindings.

The initial generation requested a six-frame transparent sprite sheet of the exact adventurer: stand, lower, perch, sit, recline and breathe; side-facing right, consistent palette and proportions, no chair or background. The layout pass added room around the sprites to prevent clipped boots.

Final correction prompt (verbatim):

> Edit target Image1: remove ALL colored glow, haze, gradients, shadows and background pixels around the six characters. Output MUST have completely transparent pixels outside the characters' exact crisp silhouettes, with no glow at all. Keep all six full bodies, exact six-cell layout, positions, poses and sizes of Image1. Supporting Image2 is original character palette/pixel-art reference: match its dark muted teal coat, white shirt, blond hair, dark trousers, brown boots and chunky crisp pixel-art rendering. Do not introduce glow, soft shadows or lights. Do not crop any boots. No scenery, text, chairs, frames, backgrounds. Six isolated character sprites on true alpha transparency. Top left stand, top middle lowering, top right perched, bottom left sitting, bottom middle reclined, bottom right same reclined breathing.

Validation: rendered against the beach using the actual crop/anchor metrics; checked the approach point against floor and obstacles; Pi headless test loaded all frames and exercised sit, rest, get up and walking away. Transparent RGB colors visible in the generator preview do not appear in the alpha-composited scene.
