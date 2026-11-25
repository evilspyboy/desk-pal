import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from optional_hardware import LightSleepPolicy,HardwareMonitor

class LightSleepTests(unittest.TestCase):
    def setUp(self):
        self.policy=LightSleepPolicy()
        self.options=HardwareMonitor.validate({'light':{'enabled':True,'idle_threshold_enabled':True}})['light']
    def tick(self,now,lux=1,sleeping=False,blocked=False):
        return self.policy.tick(self.options,{'state':'live','lux':lux,'at':now},sleeping,now,blocked)
    def test_dark_debounce_and_bright_wake(self):
        self.assertIsNone(self.tick(10));self.assertEqual(self.tick(15),'sleep')
        self.assertIsNone(self.tick(16,lux=6,sleeping=True))
        self.assertIsNone(self.tick(20,lux=8,sleeping=True));self.assertEqual(self.tick(25,lux=8,sleeping=True),'wake')
    def test_manual_wake_has_grace_period(self):
        self.tick(10);self.policy.manual(11)
        self.assertIsNone(self.tick(130));self.assertIsNone(self.tick(131));self.assertEqual(self.tick(136),'sleep')
    def test_manual_sleep_is_not_woken_by_light(self):
        self.tick(10);self.policy.manual(11)
        self.assertIsNone(self.tick(12,lux=100,sleeping=True));self.assertIsNone(self.tick(200,lux=100,sleeping=True))
    def test_manual_sleep_arms_in_dark_and_wakes_on_morning_light(self):
        self.tick(10);self.policy.manual(11)
        # Sleeping in dark arms auto_sleep:
        self.assertIsNone(self.tick(12,lux=0,sleeping=True))
        # Morning light arrives:
        self.assertIsNone(self.tick(13,lux=50,sleeping=True))
        self.assertEqual(self.tick(20,lux=50,sleeping=True),'wake')
    def test_popup_blocks_sleep_after_grace(self):
        self.tick(10);self.policy.manual(11)
        self.assertIsNone(self.tick(200,blocked=True));self.assertIsNone(self.tick(300,blocked=True))
        self.assertIsNone(self.tick(301));self.assertEqual(self.tick(306),'sleep')
    def test_stale_or_missing_readings_never_trigger(self):
        self.tick(10)
        self.assertIsNone(self.policy.tick(self.options,{'state':'live','lux':0,'at':10},False,20))
        self.assertIsNone(self.policy.tick(self.options,{'state':'unavailable'},False,30))
        self.assertIsNone(self.tick(31));self.assertEqual(self.tick(36),'sleep')
    def test_disabling_only_wakes_automatic_sleep(self):
        self.tick(10);self.tick(15)
        self.options['idle_threshold_enabled']=False
        self.assertEqual(self.tick(16,sleeping=True),'wake')
        self.assertIsNone(self.tick(17,sleeping=True))
    def test_invalid_threshold_values_rejected(self):
        for value in (float('nan'),-1,'dark',True):
            with self.assertRaises(ValueError):HardwareMonitor.validate({'light':{'sleep_below_lux':value}})

if __name__=='__main__':unittest.main()
