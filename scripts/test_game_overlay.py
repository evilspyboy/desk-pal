"""
Comprehensive Unit Tests for Game Controller Adapter, GameBezel, and GameOverlay.
Verifies input isolation, switch overriding, touch handling, and bezel layouts headlessly.
"""

import os
import sys
import unittest

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_dir = os.path.join(repo_root, "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame

from games.controller import GameControllerAdapter, GameInputState
from games.bezel import GameBezel
from games.overlay import GameOverlay
from games.breakout import BreakoutGame


class MockApp:
    def __init__(self):
        self.width = 1280
        self.height = 720
        self.cfg = {
            "apps": [
                {
                    "id": "breakout",
                    "name": "Breakout Arcade",
                    "kind": "game",
                    "settings": {
                        "controller": "buttons",
                        "bezel": "crt_monitor",
                        "switch_left": 2,
                        "switch_right": 3,
                        "switch_action": 4,
                        "switch_exit": 5,
                    },
                }
            ]
        }
        self.active_game_overlay = None
        self.activity_audits = []

    def audit_activity(self, event, **kwargs):
        self.activity_audits.append((event, kwargs))


class TestGameControllerAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = GameControllerAdapter({
            "controller": "buttons",
            "switch_left": 2,
            "switch_right": 3,
            "switch_action": 4,
            "switch_exit": 5,
        })

    def test_switch_overrides_and_isolation(self):
        # Switches 2, 3, 4, 5 MUST return True to override normal app triggers
        self.assertTrue(self.adapter.handle_switch(2))  # Left
        self.assertTrue(self.adapter.handle_switch(3))  # Right
        self.assertTrue(self.adapter.handle_switch(4))  # Action
        self.assertTrue(self.adapter.handle_switch(5))  # Exit

        # System switches 1 (Sleep) and 6 (Power) must NOT be captured
        self.assertFalse(self.adapter.handle_switch(1))
        self.assertFalse(self.adapter.handle_switch(6))

    def test_switch_movement_pulse(self):
        self.adapter.handle_switch(2)  # Tap Left
        state = self.adapter.poll(dt=0.016)
        self.assertEqual(state.axis_x, -1.0)

        self.adapter.handle_switch(3)  # Tap Right
        state = self.adapter.poll(dt=0.016)
        self.assertEqual(state.axis_x, 1.0)

    def test_touch_controls(self):
        self.adapter.handle_touch_control("left")
        state = self.adapter.poll(dt=0.016)
        self.assertEqual(state.axis_x, -1.0)

        self.adapter.handle_touch_control("right")
        state = self.adapter.poll(dt=0.016)
        self.assertEqual(state.axis_x, 1.0)

        self.adapter.handle_touch_control("release")
        state = self.adapter.poll(dt=0.016)
        self.assertEqual(state.axis_x, 0.0)

        self.adapter.handle_touch_control("action")
        state = self.adapter.poll(dt=0.016)
        self.assertTrue(state.action)


class TestGameBezel(unittest.TestCase):
    def test_crt_monitor_layout(self):
        bezel = GameBezel(bezel_type="crt_monitor")
        cab, view = bezel.compute_layout(1280, 720)

        self.assertGreater(cab.width, view.width)
        self.assertGreater(cab.height, view.height)
        self.assertTrue(cab.contains(view))

    def test_arcade_cabinet_layout(self):
        bezel = GameBezel(bezel_type="arcade_cabinet")
        cab, view = bezel.compute_layout(1280, 720)

        self.assertTrue(cab.contains(view))
        self.assertGreater(view.width, 400)
        self.assertGreater(view.height, 300)


class TestGameOverlay(unittest.TestCase):
    def setUp(self):
        self.app = MockApp()
        self.overlay = GameOverlay(self.app, game_id="breakout", bezel_type="crt_monitor")
        self.app.active_game_overlay = self.overlay

    def test_initialization(self):
        self.assertIsInstance(self.overlay.game, BreakoutGame)
        self.assertIsInstance(self.overlay.bezel, GameBezel)
        self.assertIsInstance(self.overlay.controller, GameControllerAdapter)
        self.assertEqual(self.overlay.bezel.bezel_type, "crt_monitor")

    def test_switch_dispatch_and_exit(self):
        # Switch 2 (Left) moves paddle
        self.assertTrue(self.overlay.handle_switch(self.app, 2))
        self.overlay.update(self.app, dt=0.016)

        # Switch 5 (Exit) cleanly closes overlay
        self.assertTrue(self.overlay.handle_switch(self.app, 5))
        self.assertIsNone(self.app.active_game_overlay)

    def test_touch_down_close(self):
        # Compute layout
        screen = pygame.Surface((1280, 720)) if pygame else None
        if screen:
            self.overlay.bezel.draw(screen, self.app, self.overlay.game_surf, show_touch_buttons=True)
            exit_pos = self.overlay.bezel.btn_exit_rect.center
            handled = self.overlay.handle_touch_down(self.app, exit_pos)
            self.assertTrue(handled)
            self.assertIsNone(self.app.active_game_overlay)


if __name__ == "__main__":
    unittest.main()
