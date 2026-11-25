# Inspect colour review

> Artwork/provenance record. Runtime selection, crops, anchors and placements come from saved configuration; this record is not the current deployment or task list. See the [documentation index](../../../../docs/index.md).


The original alternate frame is brighter than the master, particularly in the
teal coat and brown boots. Two built-in image-generator edits were evaluated:
`raw/inspect_1_colour_v2.png` and `raw/inspect_1_colour_v3.png`.
Neither is deployed: the first retains brighter boots; the second over-darkens
them and slightly alters the body. The Pi still uses the original Inspect frames.

The user explicitly authorized direct pixel-preserving colour correction.
`scripts/match_inspect_colours.py` fits a smooth RGB correction from corresponding
stationary body and head pixels, using the original first frame and rejecting
outliers caused by pose differences. This preserves shade gradients and lens highlights.
It changes only RGB in the original second frame; dimensions, alpha, silhouette,
pose and pixel positions remain identical. The selected output is
`raw/inspect_1_colour_matched.png`. Measurements are in
`inspect_colour_metrics.json`. The generated candidates above are not selected.

The built-in generation prompts are recorded in `inspect_colour_prompts.json`;
the final correction uses deterministic Python/Pillow/NumPy, as requested.
