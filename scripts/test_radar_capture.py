"""Exercise diagnostic capture without a UART or real-time waits."""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from optional_hardware import HardwareMonitor


class CaptureTests(unittest.TestCase):
    def monitor(self, directory):
        monitor = HardwareMonitor.__new__(HardwareMonitor)
        monitor.path = Path(directory)/'hardware_settings.json'
        monitor.lock = threading.RLock()
        monitor.config = {'radar': {'enabled': True}}
        monitor.radar_capture = {'state': 'preparing', 'id': 1}
        monitor.radar_capture_frames = []
        return monitor

    def test_capture_preserves_frames_and_phase_order(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            clock = [0]
            def sleep(seconds):
                clock[0] += seconds
                if monitor.radar_capture['state'] == 'recording':
                    monitor.radar_capture_frames.append({'phase': monitor.radar_capture['phase'], 'raw_hex': 'aaff', 'targets': [{'slot': 2, 'x_mm': -400}]})
            with patch('optional_hardware.time.monotonic', side_effect=lambda: clock[0]), patch('optional_hardware.time.sleep', side_effect=sleep):
                monitor._capture_radar(1)
            report = json.loads(monitor.radar_capture_report())
            self.assertEqual(monitor.radar_capture['state'], 'complete')
            phases = list(dict.fromkeys(frame['phase'] for frame in report['frames']))
            self.assertEqual(phases, [step['phase'] for step in report['steps'][1:]])
            self.assertEqual(report['frames'][0]['targets'][0]['slot'], 2)
            self.assertEqual(report['frames'][0]['targets'][0]['x_mm'], -400)

    def test_cancel_keeps_previous_report(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = self.monitor(directory)
            target = Path(directory)/'radar_capture_latest.json'
            target.write_text('previous')
            monitor.capture_radar({'action': 'cancel'})
            monitor._capture_radar(1)
            self.assertEqual(target.read_text(), 'previous')
            self.assertEqual(monitor.radar_capture['state'], 'cancelled')


if __name__ == '__main__':
    unittest.main()
