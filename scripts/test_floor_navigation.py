"""Geometry and movement regression tests, without launching the display or GPIO."""
import ast
import heapq
import json
import math
import pathlib
import random
import sys
import time
import unittest

candidates = [arg for arg in sys.argv[1:] if arg.endswith('.py') and not arg.startswith('-') and 'test_' not in arg]
source = pathlib.Path(candidates[0]) if candidates else pathlib.Path(__file__).resolve().parents[1]/'src/deskpal_app.py'
tree = ast.parse(source.read_text(encoding='utf-8'))
names = {'obstacle_points', 'set_obstacle_bounds', 'point_in_polygon', 'segment_intersection', 'valid_floor_points', 'clip_floor_to_screen','FloorNavigation', 'DeskPalApp'}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names], type_ignores=[]), str(source), 'exec'))

TRAP = dict(y_min=0, y_max=200, back_x_min=50, back_x_max=250, front_x_min=0, front_x_max=300)

class FloorTests(unittest.TestCase):
    def test_polygon_extra_edges_and_offscreen_floor(self):
        points=[[-200,100],[100,0],[1200,0],[1500,100],[1500,720],[-200,720]]
        self.assertTrue(valid_floor_points(points))
        nav=FloorNavigation(dict(TRAP,points=points),[])
        self.assertFalse(nav.free((-100,300)))
        self.assertFalse(nav.free((-150,0)))
        self.assertFalse(nav.free((1400,600)))
        self.assertTrue(all(0<=x<=1280 and 0<=y<=720 for x,y in nav.floor))
        self.check_route(nav,(5,300),(1275,600))

    def test_legacy_floor_is_clipped_and_empty_floor_has_no_route(self):
        nav=FloorNavigation(dict(y_min=-100,y_max=950,back_x_min=-500,back_x_max=1700,front_x_min=-500,front_x_max=1700),[])
        self.assertTrue(nav.free((0,0)))
        self.assertFalse(nav.free((640,721)))
        self.assertFalse(nav.free((-1,360)))
        self.assertEqual(nav.nearest((1400,400)),(1280,400))
        outside=FloorNavigation(dict(TRAP,points=[[1400,0],[1500,0],[1500,100],[1400,100]]),[])
        self.assertEqual(outside.floor,[])
        self.assertFalse(outside.free((1450,50)))
        self.assertIsNone(outside.nearest((640,360)))

    def test_invalid_polygon_rejected(self):
        self.assertFalse(valid_floor_points([[0,0],[200,200],[0,200],[200,0]]))
        self.assertFalse(valid_floor_points([[0,0],[200,0],[100,50],[200,200],[0,200]]))
        self.assertFalse(valid_floor_points([[0,0],[200,0],[float('nan'),200]]))

    def check_route(self, nav, start, end):
        route = nav.route(start, end)
        self.assertTrue(route)
        self.assertEqual(route[-1], end)
        for a, b in zip([start]+route, route):
            self.assertTrue(nav.clear(a, b))
            for i in range(101):
                self.assertTrue(nav.free((a[0]+(b[0]-a[0])*i/100, a[1]+(b[1]-a[1])*i/100)))
        return route

    def test_trapezoid_sloping_boundary(self):
        self.check_route(FloorNavigation(TRAP, []), (51, 1), (2, 199))

    def test_rectangle_detour(self):
        nav = FloorNavigation(TRAP, [dict(x=120, y=60, w=50, h=80)])
        self.assertFalse(nav.clear((80, 100), (220, 100)))
        self.assertGreater(len(self.check_route(nav, (80, 100), (220, 100))), 1)

    def test_polygon_footprint_not_bounding_box(self):
        nav = FloorNavigation(TRAP, [dict(points=[[130,60],[160,60],[190,140],[100,140]])])
        self.assertTrue(nav.free((105, 65)))
        self.assertFalse(nav.free((145, 100)))
        self.check_route(nav, (80,100), (220,100))

    def test_overlapping_obstacles(self):
        nav = FloorNavigation(TRAP, [dict(x=100,y=60,w=70,h=60),dict(x=140,y=100,w=60,h=55)])
        self.check_route(nav, (75,100), (225,130))
        self.assertTrue(nav.free(nav.nearest((150,110))))

    def test_wall_disconnects_floor(self):
        nav = FloorNavigation(TRAP, [dict(x=140,y=-10,w=20,h=220)])
        self.assertEqual(nav.route((80,100),(220,100)), [])

    def test_fully_blocked_floor(self):
        nav = FloorNavigation(TRAP, [dict(x=-10,y=-10,w=400,h=300)])
        self.assertIsNone(nav.nearest((150,100)))

    def test_projection_never_pushes_outside_floor(self):
        nav = FloorNavigation(TRAP, [dict(x=0,y=100,w=100,h=100)])
        for p in [(-100,150),(20,180),(150,-50),(500,400)]:
            self.assertTrue(nav.free(nav.nearest(p)))

    def test_movement_checks_every_step_and_reaches_goal(self):
        app = DeskPalApp.__new__(DeskPalApp)
        app.trap = TRAP
        app.obstacles = [dict(points=[[130,60],[160,60],[190,140],[100,140]])]
        app.edit_mode = False
        app.char_x, app.char_y = 80,100
        app.target_x, app.target_y = 220,100
        app.anim_timer = 0
        app.anim_frame = 0
        app.walk_fps = 4
        app.walk_frames = []
        app.walk_ping_pong = False
        app.wander_timer = 999
        app.target_facing_left = app.target_animation = app.pending_popup_modal = None
        nav = app.floor_navigation()
        for _ in range(180):
            previous = (app.char_x, app.char_y)
            app.update_autonomous_movement(1/30)
            self.assertTrue(nav.clear(previous,(app.char_x,app.char_y)))
        self.assertAlmostEqual(app.char_x,220)
        self.assertAlmostEqual(app.char_y,100)

    def test_native_resize_preserves_shape(self):
        obs = dict(x=0,y=0,w=100,h=50,points=[[20,0],[80,0],[100,50],[0,50]])
        set_obstacle_bounds(obs,x=10,w=200)
        self.assertEqual(obs['points'],[[50,0],[170,0],[210,50],[10,50]])

if __name__ == '__main__':
    unittest.main()
