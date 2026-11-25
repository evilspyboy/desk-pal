"""Exercise production touch methods without opening a display."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

tree = ast.parse(Path('src/deskpal_app.py').read_text(encoding='utf-8'))
methods = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
           and n.name in ('walk_from_touch', 'handle_touch_down')]
namespace = {'pygame': SimpleNamespace(Rect=lambda *a: SimpleNamespace(collidepoint=lambda p: False))}
exec(compile(ast.Module(body=methods, type_ignores=[]), 'touch', 'exec'), namespace)


class TouchTests(unittest.TestCase):
    def app(self):
        nav = SimpleNamespace(free=lambda p: p[1] >= 400,
                              route=lambda start, goal: [goal] if goal[0] < 900 else [])
        events = []
        app = SimpleNamespace(activity_queue=SimpleNamespace(active=None), char_x=500, char_y=500,
                              target_x=500, target_y=500, target_animation='seated_back',
                              target_spot_id='chair', target_playback_override={'playback_mode': 'loop'},
                              scene_journey=[{'old': True}], pending_idle_destination=('old', False),
                              floor_navigation=lambda: nav, audit_activity=lambda event, **kw: events.append((event, kw)),
                              clamp_to_walkable=lambda x, y: (x, max(y, 400)),
                              btn_exit_rect=SimpleNamespace(collidepoint=lambda p: False),
                              top_controls_open=False)
        app.events = events
        return app

    def test_idle_walk_clears_placement_and_old_journey(self):
        app = self.app()
        namespace['walk_from_touch'](app, (600, 450))
        self.assertEqual((app.target_x, app.target_y), (600, 450))
        self.assertEqual(app.target_animation, 'idle')
        self.assertIsNone(app.target_spot_id)
        self.assertIsNone(app.target_playback_override)
        self.assertEqual(app.scene_journey, [])
        self.assertIsNone(app.pending_idle_destination)
        self.assertEqual(app.events[-1][0], 'touch_walk_requested')

    def test_outside_tap_uses_nearest_floor(self):
        app = self.app()
        namespace['walk_from_touch'](app, (600, 200))
        self.assertEqual((app.target_x, app.target_y), (600, 400))

    def test_unreachable_tap_does_not_move(self):
        app = self.app()
        namespace['walk_from_touch'](app, (950, 500))
        self.assertEqual((app.target_x, app.target_y), (500, 500))
        self.assertEqual(app.target_spot_id, 'chair')

    def test_active_event_keeps_destination(self):
        app = self.app()
        app.activity_queue.active = ({'id': 'event'},)
        namespace['walk_from_touch'](app, (600, 450))
        self.assertEqual((app.target_x, app.target_y), (500, 500))
        self.assertEqual(app.events[-1][1]['reason'], 'application_action_active')

    def test_idle_character_tap_is_not_floor_tap(self):
        app = self.app()
        app.is_sleeping = app.edit_mode = app.show_shutdown_modal = False
        app.active_popup_modal = None
        app.character_touch_rect = SimpleNamespace(collidepoint=lambda p: True)
        app.activity_queue.acknowledge_attention = lambda a: False
        app.integration_attention = {}
        namespace['handle_touch_down'](app, (500, 200))
        self.assertEqual((app.target_x, app.target_y), (500, 500))


if __name__ == '__main__':
    unittest.main()
