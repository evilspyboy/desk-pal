import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from morning_greeting import MorningGreeting, message, settings, update
from unittest.mock import patch


class MorningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.policy = MorningGreeting(Path(self.temp.name)/'morning.json')
        self.now = datetime(2026, 10, 12, 7, tzinfo=ZoneInfo('Australia/Brisbane'))
        self.options = settings({'enabled': True})

    def radar(self, at, present=True):
        return dict(state='receiving', _monotonic_at=at, last_frame=at, targets=[{}] if present else [])

    def test_requires_sleep_fresh_presence_and_persists_once(self):
        self.assertFalse(self.policy.ready(self.options,self.now,self.radar(1),1))
        self.policy.slept(self.now-timedelta(hours=8))
        self.assertFalse(self.policy.ready(self.options,self.now,self.radar(1),1))
        self.assertTrue(self.policy.ready(self.options,self.now,self.radar(2.1),2.1))
        self.policy.greeted(self.now)
        restored=MorningGreeting(self.policy.path)
        restored.slept(self.now)
        self.assertFalse(restored.ready(self.options,self.now,self.radar(3),3))

    def test_cutoff_absence_outage_calibration_and_repeated_frame(self):
        self.policy.slept(self.now-timedelta(hours=8))
        self.assertFalse(self.policy.ready(self.options,self.now,self.radar(1),1))
        self.assertFalse(self.policy.ready(self.options,self.now,self.radar(1),1.8))
        self.assertFalse(self.policy.ready(self.options,self.now,self.radar(2,False),2))
        self.assertFalse(self.policy.ready(self.options,self.now,self.radar(3),3,blocked=True))
        self.assertFalse(self.policy.ready(self.options,self.now,self.radar(3),5))
        self.assertFalse(self.policy.ready(self.options,self.now.replace(hour=10),self.radar(6),6))

    def test_price_uses_new_heartbeat_not_old_button_or_event(self):
        app=SimpleNamespace(apps=[{'id':'fuel','adapter':'fuel_tracker'}],app_telemetry={'fuel':{'summary':'Old button 300', 'received_events':{'fuel_drop':{'data':{'price':280}},'heartbeat':{'data':{'price':210.5,'station':'Test station','fuel_type':'u98','cached_at':self.now.timestamp()-1800}}}}})
        text=message(app,self.options,self.now)
        self.assertIn('210.5¢/L',text)
        self.assertIn('30 min ago',text)
        self.assertNotIn('300',text)
        app.app_telemetry={}
        self.assertIn('awaiting a price',message(app,self.options,self.now))

    def test_settings_reject_invalid_window(self):
        for value in [{'start':'11:00'},{'end':'25:00'},{'enabled':'yes'}]:
            with self.assertRaises(ValueError):settings(value)

    def test_wakes_queues_popup_once_and_grants_dark_wake_grace(self):
        self.policy.slept(self.now-timedelta(hours=8))
        queued=[];grace=[]
        app=SimpleNamespace(cfg={'morning_greeting':self.options}, morning_greeting=self.policy,
            apps=[],app_telemetry={},edit_mode=False,is_sleeping=True,
            active_popup_modal=None,pending_popup_modal=None,
            light_sleep_policy=SimpleNamespace(manual=lambda t:grace.append(t)),
            queue_action=lambda *a,**k:queued.append((a,k)),audit_activity=lambda *a,**k:None)
        app.wake_from_standby=lambda **k:setattr(app,'is_sleeping',False)
        with patch('morning_greeting.local_now',return_value=self.now),patch('morning_greeting.time.monotonic',return_value=1):
            self.assertFalse(update(app,self.radar(1)))
        with patch('morning_greeting.local_now',return_value=self.now),patch('morning_greeting.time.monotonic',return_value=2.1):
            self.assertTrue(update(app,self.radar(2.1)))
            self.assertFalse(update(app,self.radar(2.2)))
        self.assertFalse(app.is_sleeping);self.assertEqual(len(queued),1);self.assertEqual(len(grace),1)
        self.assertTrue(queued[0][0][0]['_hold_popup_until_dismissed'])


if __name__=='__main__':unittest.main()
