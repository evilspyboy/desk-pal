# Floor editing outside the background

The editor canvas is a viewport onto scene coordinates. The background and walkable floor are bounded to 1280×720. Zoom and right-button panning transform the entire scene together. Wheel zoom stays anchored under the pointer with sidebar/header offsets accounted for.

Floor handles are labelled P1, P2, etc. Drag a handle to move it. Shift-click an edge to insert a point; Alt-click a point to remove it (at least three must remain). Dragging beyond an image edge immediately clips the floor and adds editable intersection vertices; crossing a corner includes the image corner when it falls within the floor. Clipping is mandatory, with no opt-out. A continuous drag retains its original corner even as new boundary vertices appear.

Older off-image floors are clipped when opened in the editor and when constructed by the runtime navigation solver. The runtime rejects any destination beyond the image regardless of saved geometry. Saving the editor persists the clipped scene polygons. Character depth calibration remains unchanged.

Floors support 3–32 points and must remain convex, matching the navigation solver. Crossed edges and inward notches are rejected; use blocked areas for internal obstacles. Front/back perspective calibration stays independent of trimming the floor. Save to Pi persists the polygon separately for each scene.

The optional `walkable_trapezoid.points` array holds the polygon. Existing four-corner configurations remain compatible. The runtime, native editor overlay, pose placement bounds, portal validity and pathfinding use the polygon when present. Background images are unchanged.

Tests: `scripts/test_floor_editor.cjs` covers fitting off-image points, coordinate round trips, wheel anchoring, clipping, extra vertices and pose bounds. `scripts/test_floor_navigation.py` includes multi-sided and off-image runtime routes and invalid geometry cases.
