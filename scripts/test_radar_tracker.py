import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from radar_tracker import RadarTracker
from radar_awake import presence_reading


class RadarTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tracker = RadarTracker(
            jump_threshold_mm=600,
            jump_confirm_seconds=0.5,
            hold_dropout_seconds=2.5,
            smoothing_alpha=0.3
        )

    def test_steady_tracking_with_small_jitter(self):
        # Target at ~450mm with small micro-jitter
        t1 = self.tracker.update([{'slot': 1, 'x_mm': 100, 'y_mm': 450, 'speed_cm_s': 0}], now=1.0)
        self.assertEqual(len(t1), 1)
        self.assertEqual(t1[0]['tracking_status'], 'initial')

        t2 = self.tracker.update([{'slot': 1, 'x_mm': 105, 'y_mm': 455, 'speed_cm_s': 0}], now=1.1)
        self.assertEqual(len(t2), 1)
        self.assertEqual(t2[0]['tracking_status'], 'tracking')
        self.assertTrue(440 <= t2[0]['distance_mm'] <= 480)

    def test_transient_jump_spike_rejection(self):
        # User at 1.15m desk position
        desk_target = {'slot': 1, 'x_mm': -300, 'y_mm': 1150, 'speed_cm_s': 0}
        self.tracker.update([desk_target], now=1.0)

        # Frame 2: sudden jump to 3.4m (wall/multipath reflection spike)
        jump_target = {'slot': 1, 'x_mm': -250, 'y_mm': 3435, 'speed_cm_s': -51}
        f2 = self.tracker.update([jump_target], now=1.05)
        self.assertEqual(len(f2), 1)
        self.assertEqual(f2[0]['tracking_status'], 'jump_hold')
        # Target must be held at desk position, NOT 3.4m
        self.assertLess(f2[0]['distance_mm'], 1500)

        # Frame 3: spike persists for 100ms (<500ms confirm threshold)
        f3 = self.tracker.update([jump_target], now=1.15)
        self.assertEqual(f3[0]['tracking_status'], 'jump_hold')
        self.assertLess(f3[0]['distance_mm'], 1500)

        # Frame 4: spike vanishes, radar back at desk position
        f4 = self.tracker.update([{'slot': 1, 'x_mm': -295, 'y_mm': 1155, 'speed_cm_s': 0}], now=1.25)
        self.assertEqual(f4[0]['tracking_status'], 'tracking')
        self.assertLess(f4[0]['distance_mm'], 1500)

    def test_presence_reading_never_drops_during_transient_jump(self):
        # Ensure presence_reading (presence_range_m=2.0) does NOT drop to 0 during jump spike
        desk_target = {'slot': 1, 'x_mm': -300, 'y_mm': 1150, 'speed_cm_s': 0, 'distance_mm': 1188}
        jump_target = {'slot': 1, 'x_mm': -250, 'y_mm': 3435, 'speed_cm_s': -51, 'distance_mm': 3444}

        self.tracker.update([desk_target], now=1.0)
        # Spike occurs
        stabilized = self.tracker.update([jump_target], now=1.1)
        radar_feed = {'state': 'receiving', 'targets': stabilized}

        presence = presence_reading(radar_feed, range_m=2.0)
        self.assertEqual(len(presence['targets']), 1, "Presence dropped to 0 during reflection jump!")
        self.assertLess(presence['targets'][0]['distance_mm'], 2000)

    def test_sustained_relocation_is_accepted(self):
        # User starts at 1.0m
        self.tracker.update([{'slot': 1, 'x_mm': 0, 'y_mm': 1000, 'speed_cm_s': 0}], now=1.0)

        # User steps back to 2.2m and holds it
        new_pos = {'slot': 1, 'x_mm': 0, 'y_mm': 2200, 'speed_cm_s': 0}
        # First 0.4s: treated as pending jump
        self.tracker.update([new_pos], now=1.1)
        self.tracker.update([new_pos], now=1.3)
        res = self.tracker.update([new_pos], now=1.4)
        self.assertEqual(res[0]['tracking_status'], 'jump_hold')

        # At >=0.5s: confirmed relocation
        res_confirmed = self.tracker.update([new_pos], now=1.65)
        self.assertEqual(res_confirmed[0]['tracking_status'], 'reacquired')
        self.assertEqual(res_confirmed[0]['y_mm'], 2200)

    def test_seated_micro_dropout_hold(self):
        # User seated at 500mm
        self.tracker.update([{'slot': 1, 'x_mm': 100, 'y_mm': 500, 'speed_cm_s': 0}], now=1.0)

        # Doppler returns drop below threshold: empty frames for 1.8 seconds
        for t in [1.2, 1.5, 1.8, 2.2, 2.6]:
            res = self.tracker.update([], now=t)
            self.assertEqual(len(res), 1, f"Failed hold at t={t}")
            self.assertEqual(res[0]['tracking_status'], 'dropout_hold')
            self.assertEqual(res[0]['speed_cm_s'], 0)

        # User moves slightly at t=2.7s
        res_moved = self.tracker.update([{'slot': 1, 'x_mm': 110, 'y_mm': 510, 'speed_cm_s': 10}], now=2.7)
        self.assertEqual(len(res_moved), 1)
        self.assertEqual(res_moved[0]['tracking_status'], 'tracking')

    def test_true_departure_clears_targets_after_hold_expires(self):
        # User seated at 500mm
        self.tracker.update([{'slot': 1, 'x_mm': 100, 'y_mm': 500, 'speed_cm_s': 0}], now=1.0)

        # User walks away; no targets for 3.0s (>2.5s hold)
        res = self.tracker.update([], now=3.6)
        self.assertEqual(res, [], "Targets must be empty after hold interval expires")
        self.assertEqual(len(self.tracker.tracks), 0)


if __name__ == '__main__':
    unittest.main()
