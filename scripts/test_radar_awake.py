import sys
import unittest
from unittest.mock import patch
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from radar_awake import RadarAwakePolicy, sleep_inputs, presence_keeps_awake, presence_reading
from optional_hardware import HardwareMonitor, LightSleepPolicy
from light_schedule import bedtime_window

class PresenceAwakeTests(unittest.TestCase):
    def test_presence_bubble_excludes_boundary_invalid_and_far_targets(self):
        raw=dict(state='receiving',targets=[{'slot':1,'distance_mm':1999},
            {'slot':2,'distance_mm':2000},{'slot':3,'distance_mm':3500},
            {'distance_mm':float('nan')},{'distance_mm':0},{}])
        self.assertEqual([t['slot'] for t in presence_reading(raw)['targets']],[1])
        self.assertEqual(len(raw['targets']),6)
        self.assertEqual([t['slot'] for t in presence_reading(raw,4)['targets']],[1,2,3])

    def test_distant_target_does_not_confirm_presence(self):
        p=RadarAwakePolicy()
        for now in (1,3,10):
            raw=self.radar(now);raw['targets']=[{'distance_mm':2500}]
            self.assertFalse(p.tick(True,presence_reading(raw),now))
        self.assertIsNone(p.last_present)
        for now in (11,12.1):
            raw=self.radar(now);raw['targets']=[{'distance_mm':500}]
            awake=p.tick(True,presence_reading(raw),now)
        self.assertTrue(awake)

    def test_presence_range_validation(self):
        self.assertEqual(HardwareMonitor.validate({})['radar']['presence_range_m'],2)
        for value in (0,9,True,float('nan')):
            with self.assertRaises(ValueError):HardwareMonitor.validate({'radar':{'presence_range_m':value}})

    def test_bedtime_presence_keeps_awake_and_sleeps_on_absence_until_morning(self):
        options=HardwareMonitor.validate({'light':{'enabled':True,'idle_threshold_enabled':True,'presence_awake_enabled':True}})['light']
        p=LightSleepPolicy()
        # While awake at night (working late), presence keeps it awake
        self.assertTrue(presence_keeps_awake(True, night=True, sleeping=False))
        # Once asleep at night, presence does not wake it
        self.assertFalse(presence_keeps_awake(True, night=True, sleeping=True))
        # Daytime presence can wake it
        self.assertTrue(presence_keeps_awake(True, night=False, sleeping=True))
        # Absence never keeps awake
        self.assertFalse(presence_keeps_awake(False, night=True, sleeping=False))

        reading=lambda n:dict(state='live',at=n,lux=0)

        # Working at desk past bedtime: presence keeps Desk-Pal awake
        self.assertIsNone(p.tick(options,reading(1),False,1,keep_awake=presence_keeps_awake(True,night=True,sleeping=False)))
        self.assertIsNone(p.tick(options,reading(6),False,6,keep_awake=presence_keeps_awake(True,night=True,sleeping=False)))

        # User leaves desk at night: keep_awake becomes False, triggers sleep
        p.tick(options,reading(7),False,7,keep_awake=presence_keeps_awake(False,night=True,sleeping=False))
        self.assertEqual(p.tick(options,reading(12),False,12,keep_awake=presence_keeps_awake(False,night=True,sleeping=False)),'sleep')

        # Desk-Pal is now asleep. Night presence does not wake it
        self.assertIsNone(p.tick(options,reading(13),True,13,keep_awake=presence_keeps_awake(True,night=True,sleeping=True)))

        # Manual wake still works
        p.manual(14)
        self.assertIsNone(p.tick(options,reading(15),False,15,keep_awake=False))
        self.assertIsNone(p.tick(options,reading(134),False,134,keep_awake=False))
        self.assertEqual(p.tick(options,reading(139),False,139,keep_awake=False),'sleep')

    def test_radar_only_bedtime_can_sleep_despite_false_target(self):
        options=HardwareMonitor.validate({'light':{'presence_awake_enabled':True}})['light']
        policy=RadarAwakePolicy()
        cfg,reading=sleep_inputs(options,{},policy,False,10,night=True,bedtime_priority=True,sleeping=False)
        p=LightSleepPolicy()
        self.assertEqual(p.tick(cfg,reading,False,10),'sleep')
        cfg,reading=sleep_inputs(options,{},policy,True,11,night=False,bedtime_priority=False,sleeping=True)
        self.assertEqual(p.tick(cfg,reading,True,11,keep_awake=True),'wake')

    def test_shared_bedtime_window_and_daytime_absence(self):
        options=HardwareMonitor.validate({'light':{'presence_awake_enabled':True,'bedtime':'22:00'}})['light']
        with patch('light_schedule.local_now',side_effect=lambda cfg,now:now), patch('light_schedule.lighting_state',return_value={'sunrise':6}):
            for hour,minute,expected in [(21,59,False),(22,0,True),(1,0,True),(6,0,False),(12,0,False)]:
                self.assertEqual(bedtime_window(options,{},datetime(2026,10,12,hour,minute)),expected)
        radar=RadarAwakePolicy();radar.sleep_ready=True
        cfg,reading=sleep_inputs(options,{},radar,False,100,night=False)
        self.assertIsNone(LightSleepPolicy().tick(cfg,reading,False,100))

    def test_radar_only_sleep_wake_and_missing_sensor(self):
        options=HardwareMonitor.validate({'light':{'presence_awake_enabled':True}})['light']
        radar=RadarAwakePolicy(); light=LightSleepPolicy()
        def tick(now, targets=False, state='receiving', sleeping=False):
            reading=self.radar(now,targets);reading['state']=state
            awake=radar.tick(True,reading,now,30)
            cfg,lux=sleep_inputs(options,{},radar,awake,now)
            return light.tick(cfg,lux,sleeping,now,keep_awake=awake)
        self.assertIsNone(tick(1))
        self.assertIsNone(tick(20))
        self.assertEqual(tick(31),'sleep')
        self.assertIsNone(tick(32,True,sleeping=True))
        self.assertEqual(tick(33.1,True,sleeping=True),'wake')
        self.assertIsNone(tick(70,state='disabled'))
        self.assertIsNone(tick(100,state='disabled'))
        light.manual(101)
        self.assertIsNone(tick(102))
        self.assertIsNone(tick(132))

    def test_lux_policy_remains_independent(self):
        options=HardwareMonitor.validate({'light':{'enabled':True,'idle_threshold_enabled':True}})['light']
        reading=dict(state='live',at=1,lux=0)
        self.assertEqual(sleep_inputs(options,reading,RadarAwakePolicy(),False,1),(options,reading))

    def radar(self, now, targets=True):
        return dict(state='receiving',last_frame=now,_monotonic_at=now,targets=[{}] if targets else [])

    def test_presence_confirmation_absence_grace_and_freshness(self):
        p=RadarAwakePolicy()
        self.assertFalse(p.tick(True,self.radar(1),1))
        self.assertTrue(p.tick(True,self.radar(2.1),2.1))
        self.assertTrue(p.tick(True,self.radar(10,False),10))
        self.assertFalse(p.tick(True,self.radar(33,False),33))
        p.tick(True,self.radar(40),40)
        self.assertTrue(p.tick(True,self.radar(41.1),41.1))
        self.assertFalse(p.tick(True,self.radar(41.1),43))

    def test_disable_capture_and_duplicate_frame_do_not_establish_presence(self):
        p=RadarAwakePolicy();p.tick(True,self.radar(1),1)
        self.assertFalse(p.tick(True,self.radar(1),1.9))
        self.assertFalse(p.tick(True,self.radar(2),2,calibrating=True))
        self.assertFalse(p.tick(False,self.radar(4),4))

    def test_presence_wakes_only_light_sleep_and_vetoes_dark_sleep(self):
        options=HardwareMonitor.validate({'light':{'enabled':True,'idle_threshold_enabled':True}})['light']
        p=LightSleepPolicy();reading=lambda n:dict(state='live',at=n,lux=0)
        p.tick(options,reading(0),False,0)
        self.assertIsNone(p.tick(options,reading(5),False,5,keep_awake=True))
        p.tick(options,reading(6),False,6)
        self.assertEqual(p.tick(options,reading(11),False,11),'sleep')
        self.assertEqual(p.tick(options,reading(12),True,12,keep_awake=True),'wake')
        p.manual(13)
        self.assertIsNone(p.tick(options,reading(14),True,14,keep_awake=True))

    def test_bright_flash_does_not_shorten_manual_wake_grace(self):
        options=HardwareMonitor.validate({'light':{'enabled':True,'idle_threshold_enabled':True}})['light']
        p=LightSleepPolicy();p.tick(options,dict(state='live',at=0,lux=0),False,0);p.manual(1)
        p.tick(options,dict(state='live',at=2,lux=100),False,2)
        self.assertIsNone(p.tick(options,dict(state='live',at=20,lux=0),False,20))
        self.assertIsNone(p.tick(options,dict(state='live',at=121,lux=0),False,121))
        self.assertEqual(p.tick(options,dict(state='live',at=126,lux=0),False,126),'sleep')

if __name__=='__main__':unittest.main()
