import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
if (ROOT / 'scratch/local_preview_deps').is_dir():
    sys.path.insert(0, str(ROOT / 'scratch/local_preview_deps'))

from desktop_mode import DesktopDisplayPower, DesktopWindow
from audio_output import playback_command


class DesktopModeTests(unittest.TestCase):
    def test_desktop_display_power_simulates_standby(self):
        power = DesktopDisplayPower()
        self.assertFalse(power.is_off)
        self.assertIsNone(power.error)

        success = power.set_sleeping(True)
        self.assertTrue(success)
        self.assertTrue(power.is_off)
        self.assertIsNone(power.error)

        success = power.set_sleeping(False)
        self.assertTrue(success)
        self.assertFalse(power.is_off)
        self.assertIsNone(power.error)

    def test_viewport_geometry_exact_aspect(self):
        # 1280x720 native
        ox, oy, tw, th, scale = DesktopWindow.get_viewport_geometry(1280, 720)
        self.assertEqual((ox, oy, tw, th, scale), (0, 0, 1280, 720, 1.0))

        # 960x540 (0.75x)
        ox, oy, tw, th, scale = DesktopWindow.get_viewport_geometry(960, 540)
        self.assertEqual((ox, oy, tw, th), (0, 0, 960, 540))
        self.assertAlmostEqual(scale, 0.75)

        # 640x360 (0.5x)
        ox, oy, tw, th, scale = DesktopWindow.get_viewport_geometry(640, 360)
        self.assertEqual((ox, oy, tw, th), (0, 0, 640, 360))
        self.assertAlmostEqual(scale, 0.5)

    def test_viewport_geometry_letterboxing_and_pillarboxing(self):
        # Wider than 16:9 (pillarboxed on left and right)
        ox, oy, tw, th, scale = DesktopWindow.get_viewport_geometry(1200, 540)
        self.assertGreater(ox, 0)
        self.assertEqual(oy, 0)
        self.assertEqual(th, 540)
        self.assertEqual(tw, 960)

        # Taller than 16:9 (letterboxed on top and bottom)
        ox, oy, tw, th, scale = DesktopWindow.get_viewport_geometry(960, 700)
        self.assertEqual(ox, 0)
        self.assertGreater(oy, 0)
        self.assertEqual(tw, 960)
        self.assertEqual(th, 540)

    def test_map_input_pos_scaling(self):
        # In 640x360 window, center click (320, 180) maps to canvas center (640, 360)
        cx, cy = DesktopWindow.map_input_pos((320, 180), (640, 360))
        self.assertEqual((cx, cy), (640, 360))

        # In 960x540 window, (0, 0) maps to (0, 0)
        cx, cy = DesktopWindow.map_input_pos((0, 0), (960, 540))
        self.assertEqual((cx, cy), (0, 0))

        # Bottom right
        cx, cy = DesktopWindow.map_input_pos((959, 539), (960, 540))
        self.assertEqual((cx, cy), (1278, 718))

    def test_map_input_pos_bounds_clamping(self):
        # Click in black letterbox bar outside canvas
        cx, cy = DesktopWindow.map_input_pos((-50, -50), (960, 540))
        self.assertEqual((cx, cy), (0, 0))

        cx, cy = DesktopWindow.map_input_pos((2000, 2000), (960, 540))
        self.assertEqual((cx, cy), (1279, 719))

    def test_playback_command_validity(self):
        cmd = playback_command('default', 'dummy.wav')
        self.assertIsInstance(cmd, list)
        self.assertTrue(len(cmd) > 0)

    def test_desktop_shutdown_exits_cleanly(self):
        try:
            import pygame
        except ImportError:
            self.skipTest("pygame not available")
        from deskpal_app import DeskPalApp
        app = DeskPalApp.__new__(DeskPalApp)
        app.local_preview = False
        app.desktop_mode = True
        app.running = True

        app.perform_shutdown()
        self.assertFalse(app.running)


if __name__ == '__main__':
    unittest.main()
