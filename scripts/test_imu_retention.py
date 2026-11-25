import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from optional_hardware import HardwareMonitor


class RetentionTests(unittest.TestCase):
    def test_steps_and_errors_survive_a_new_monitor(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor = HardwareMonitor.__new__(HardwareMonitor)
            monitor.path = Path(directory)/'hardware_settings.json'
            phases = ['neutral', 'left', 'right', 'forward', 'back', 'turn_left', 'turn_right']
            raw = [(0, [0, 0, 1], [1, 2, 3]), (1, [0, .1, .9], [4, 5, 6])]
            for i, phase in enumerate(phases):
                monitor.imu_capture = dict(id=i, state='complete', phase=phase, integral=[1, 2, 3])
                monitor._retain_imu_capture(phase, [0, 0, 0], raw)
            other = HardwareMonitor.__new__(HardwareMonitor)
            other.path = monitor.path
            report = json.loads(other.imu_capture_report())
            self.assertTrue(report['complete'])
            self.assertEqual(len(report['steps']), 7)
            self.assertEqual(report['steps']['left']['raw_samples'][1]['gyro_dps'], [4, 5, 6])
            monitor.imu_capture = dict(id=10, state='error', phase='turn_right', error='test')
            monitor._retain_imu_capture('turn_right', [0, 0, 0], raw)
            report = json.loads(other.imu_capture_report())
            self.assertFalse(report['complete'])
            self.assertEqual(len(report['attempts']), 8)
            monitor.imu_capture = dict(id=11, state='complete', phase='neutral')
            monitor._retain_imu_capture('neutral', [0, 0, 0], raw)
            self.assertEqual(list(json.loads(other.imu_capture_report())['steps']), ['neutral'])


if __name__ == '__main__':
    unittest.main()
