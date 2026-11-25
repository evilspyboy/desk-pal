import sys
from pathlib import Path
import unittest
from datetime import datetime, timezone, timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from scene_lighting import lighting_state


class LightingTests(unittest.TestCase):
    def state(self, month, hour, minute=0):
        return lighting_state(now=datetime(2026,month,2,hour,minute,tzinfo=timezone(timedelta(hours=10))))

    def test_brisbane_day_night_and_season(self):
        self.assertEqual(self.state(10,0)['night'],1)
        self.assertEqual(self.state(10,12)['night'],0)
        self.assertGreater(self.state(6,12)['sunrise'],self.state(12,12)['sunrise'])
        self.assertLess(self.state(6,12)['sunset'],self.state(12,12)['sunset'])

    def test_sunrise_blends_smoothly(self):
        minute=round(self.state(10,12)['sunrise']*60)
        before=self.state(10,(minute-15)//60,(minute-15)%60)
        middle=self.state(10,minute//60,minute%60)
        after=self.state(10,(minute+15)//60,(minute+15)%60)
        self.assertGreater(before['night'],middle['night'])
        self.assertGreater(middle['night'],after['night'])
        self.assertAlmostEqual(middle['night'],.5,delta=.02)

    def test_location_and_timezone_are_respected(self):
        utc=datetime(2026,10,2,2,tzinfo=timezone.utc)
        local=utc.astimezone(timezone(timedelta(hours=10)))
        self.assertEqual(lighting_state(now=utc)['night'],lighting_state(now=local)['night'])
        polar=lighting_state({'latitude':89,'longitude':0},datetime(2026,6,21,12,tzinfo=timezone.utc))
        self.assertEqual(polar['night'],0)

    def test_named_timezone_uses_location_date_and_dst(self):
        from scene_lighting import lighting_details
        settings = {'latitude': 40.71, 'longitude': -74.01, 'timezone': 'America/New_York'}
        winter = lighting_details(settings, datetime(2026,1,2,2,tzinfo=timezone.utc))
        summer = lighting_details(settings, datetime(2026,7,2,2,tzinfo=timezone.utc))
        self.assertTrue(winter['local_time'].startswith('2026-01-01T21:'))
        self.assertTrue(winter['local_time'].endswith('-05:00'))
        self.assertTrue(summer['local_time'].endswith('-04:00'))
        local = datetime.fromisoformat(summer['local_time'])
        self.assertEqual(lighting_state(settings, local)['night'], lighting_state(settings, datetime(2026,7,2,2,tzinfo=timezone.utc))['night'])
        brisbane = lighting_state({'timezone':'Australia/Brisbane'}, datetime(2026,10,3,10,tzinfo=timezone.utc))
        london = lighting_state({'latitude':51.5,'longitude':-.12,'timezone':'Europe/London'}, datetime(2026,10,3,10,tzinfo=timezone.utc))
        self.assertEqual(brisbane['night'], 1)
        self.assertEqual(london['night'], 0)

    def test_invalid_location_rejected(self):
        from scene_lighting import validate_lighting
        for settings in ({'latitude':91}, {'longitude':181}, {'latitude':float('nan')}, {'longitude':True}, {'timezone':'Not/AZone'}, {'timezone':123}):
            with self.assertRaises(ValueError):
                validate_lighting(settings)
        validate_lighting({})
        validate_lighting({'latitude':-27.47,'longitude':153.03,'timezone':'Australia/Brisbane'})


if __name__=='__main__':unittest.main()
