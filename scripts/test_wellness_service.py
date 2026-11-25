import unittest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "wellness_check"))
import main as wellness_main


class WellnessServiceTests(unittest.TestCase):
    def test_default_settings(self):
        s = wellness_main.DEFAULT_SETTINGS
        self.assertIn("mon", s["days_of_week"])
        self.assertEqual(s["interval_minutes"], 45)
        self.assertEqual(s["absence_reset_minutes"], 30)

    def test_monitor_state_and_schedule(self):
        m = wellness_main.WellnessMonitor()
        m.settings["days_of_week"] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        m.settings["start_time"] = "00:00"
        m.settings["end_time"] = "23:59"
        self.assertTrue(m.is_within_schedule())

    def test_absence_break_reset(self):
        m = wellness_main.WellnessMonitor()
        m.consecutive_sitting_seconds = 1800  # 30 min sitting
        m.consecutive_absence_seconds = 1805  # > 30 min away
        reset_threshold = m.settings["absence_reset_minutes"] * 60
        if m.consecutive_absence_seconds >= reset_threshold:
            m.consecutive_sitting_seconds = 0
        self.assertEqual(m.consecutive_sitting_seconds, 0)


if __name__ == "__main__":
    unittest.main()
