# Foreground objects

Open **Foreground objects** in the web editor. Existing red blocks are listed, so a floor block can become a foreground object without adding a second obstacle.

1. Select an existing block or **Add object**, then give it a name.
2. **Edit ground footprint**: place the red quad around the object's base. This blocks walking and pose placement. The footprint is usually much smaller than the visible object.
3. **Trace / replace outline**: click around the visible silhouette of the rack, chair, plant, etc. Click **Finish outline** or the first point to close it. **Undo last point** corrects tracing mistakes; **Done / cancel** discards an unfinished trace.
4. **Adjust outline points** lets you drag existing silhouette vertices. Outline editing does not move the original background artwork.
5. Choose **Use ground footprint (walk around)** for shelves and chairs. Leave depth blank to use the footprint's sloping front edge. Depth is checked across the character's width, so an angled shelf can hide only the part behind it. A custom Y value gives a flat boundary. Choose **Always in front (screen-edge objects)** for plants and rocks at the very front of the scene.
6. Check the result in the Pose Stager and **Save objects to Pi**.

Objects are per scene. Collision remains active if visual hiding is unchecked. The same mask applies to walking, idle and gesture frames in the display runtime. The renderer clears only covered sprite pixels: original backgrounds, day/night shading and existing app overlays remain intact. Separate movable prop images/animations are available through View props and Animation Grid → Props; this feature handles objects already painted into the background. See [image props](image-props.md).

Stored as `obstacles[].foreground = {outline: [[x,y], ...], enabled: true, mode: "footprint" | "always_front", depth_y?: number}`. Missing mode retains footprint behaviour and existing depth overrides. The regular obstacle quad is the linked navigation footprint. Traced outlines may be concave; footprints remain convex.

Tests: `test_foreground_editor.cjs` and `test_foreground_objects.py`. The Python test includes actual pygame alpha masking when pygame is available, including overlapping objects and preservation of cached sprite frames.
