import copy
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from optional_hardware import DEFAULTS, HardwareMonitor, decode_frame


class HardwareTests(unittest.TestCase):
    def test_manufacturer_example(self):
        frame = bytes.fromhex('aaff0300 0e03 b186 1000 6801')+bytes(16)+bytes.fromhex('55cc')
        target = decode_frame(frame)[0]
        self.assertEqual((target['x_mm'], target['y_mm'], target['speed_cm_s']), (-782, 1713, -16))
        self.assertEqual(target['resolution_mm'], 360)
        self.assertEqual(decode_frame(bytes.fromhex('aaff0300')+bytes(24)+bytes.fromhex('55cc')), [])
        with self.assertRaises(ValueError):
            decode_frame(bytes(30))

    def test_invalid_settings_cannot_enable_devices(self):
        for bad in [{'radar': {'port': '/etc/passwd'}}, {'radar': {'model': 'hmmd'}},
                    {'speaker': {'enabled': 'yes'}}, {'unexpected': {}}]:
            with self.assertRaises(ValueError):
                HardwareMonitor.validate(bad)

    def test_separate_settings_and_audio_changes_preserve_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'hardware_settings.json'
            m = HardwareMonitor(path)
            self.assertFalse(path.exists())
            m.radar['frames'] = 123
            options = copy.deepcopy(DEFAULTS)
            options['speaker']['enabled'] = True
            m.configure(options)
            self.assertEqual(m.radar['frames'], 123)
            self.assertTrue(json.loads(path.read_text())['speaker']['enabled'])
            self.assertTrue(HardwareMonitor(path).config['speaker']['enabled'])

    def test_stale_positions_are_not_shown_as_live(self):
        with tempfile.TemporaryDirectory() as folder:
            m = HardwareMonitor(Path(folder)/'hardware.json')
            m.devices_at = time.monotonic()
            m.radar.update(state='receiving', last_frame=time.time()-5, targets=[{'slot': 1}])
            result = m.snapshot()
            self.assertEqual(result['radar']['state'], 'stale')
            self.assertEqual(result['radar']['targets'], [])

    def test_missing_serial_driver_does_not_break_core(self):
        with tempfile.TemporaryDirectory() as folder:
            m = HardwareMonitor(Path(folder)/'hardware.json')
            with patch.dict(sys.modules, {'serial': None}):
                m.read_radar()
            self.assertEqual(m.radar['state'], 'unavailable')
            self.assertTrue(m.radar['error'])

    def test_audio_requires_enable_and_bounded_level(self):
        with tempfile.TemporaryDirectory() as folder:
            m = HardwareMonitor(Path(folder)/'hardware.json')
            for kind, level in [('speaker', .25), ('microphone', .25), ('speaker', float('nan')),
                                ('speaker', 2), ('other', .25)]:
                with self.assertRaises(ValueError):
                    m.test(kind, level)

    def test_bh1750_modes_and_mtreg_validation(self):
        self.assertEqual(DEFAULTS['light']['mode'], 'high_res_2')
        self.assertEqual(DEFAULTS['light']['mtreg'], 254)
        valid = copy.deepcopy(DEFAULTS)
        valid['light']['mode'] = 'high_res_1'
        valid['light']['mtreg'] = 138
        validated = HardwareMonitor.validate(valid)
        self.assertEqual(validated['light']['mode'], 'high_res_1')
        self.assertEqual(validated['light']['mtreg'], 138)

        for bad in [{'light': {'mode': 'bad_mode'}}, {'light': {'mtreg': 20}}, {'light': {'mtreg': 300}}, {'light': {'mtreg': 'auto'}}]:
            with self.assertRaises(ValueError):
                HardwareMonitor.validate(bad)


if __name__ == '__main__':
    unittest.main()
