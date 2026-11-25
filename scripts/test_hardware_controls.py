import sys,unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from gpio_hardware import ButtonController,validate_buttons
from optional_hardware import HardwareMonitor,LightSleepPolicy,DEFAULTS
from audio_output import playback_command
from light_schedule import evening_awake
class FakeButton:
 def __init__(self,pin,**kw):self.is_pressed=False;self.closed=False
 def close(self):self.closed=True
class Tests(unittest.TestCase):
 def test_gpio_test_blocks_actions_and_shutdown(self):
  actions=[];b=ButtonController(FakeButton,lambda n:actions.append(n),lambda:actions.append('shutdown'));b.configure({'pins':[{'id':6,'bcm':0}]},[])
  b.test(True);b.devices[6].when_pressed();b.devices[6].when_held();self.assertEqual(actions,[]);self.assertEqual(b.snapshot()['buttons'][0]['presses'],1)
  b.test(False);b.devices[6].when_pressed();b.devices[6].when_held();self.assertEqual(actions,[6,'shutdown'])
  old=b.devices[6];b.configure({'enabled':False,'pins':[]},[]);self.assertTrue(old.closed)
 def test_gpio_validation(self):
  for rows in [[{'id':2,'bcm':5},{'id':3,'bcm':5}],[{'id':2,'bcm':30}],[{'id':0,'bcm':5}]]:
   with self.assertRaises(ValueError):validate_buttons({'pins':rows})
  import copy
  settings=copy.deepcopy(DEFAULTS);settings['light']['enabled']=True;settings['buttons']['pins']=[{'id':2,'bcm':3}]
  with self.assertRaises(ValueError):HardwareMonitor.validate(settings)
 def test_evening_window_and_manual_sleep(self):
  light=dict(DEFAULTS['light'],enabled=True,idle_threshold_enabled=True,evening_awake_enabled=True,bedtime='22:00');loc={'timezone':'Australia/Brisbane'}
  self.assertTrue(evening_awake(light,loc,datetime(2026,10,11,20,tzinfo=ZoneInfo('Australia/Brisbane'))));self.assertFalse(evening_awake(light,loc,datetime(2026,10,11,23,tzinfo=ZoneInfo('Australia/Brisbane'))))
  light['bedtime']='01:00';self.assertTrue(evening_awake(light,loc,datetime(2026,10,12,0,30,tzinfo=ZoneInfo('Australia/Brisbane'))))
  p=LightSleepPolicy();reading={'state':'live','at':10,'lux':.2};self.assertIsNone(p.tick(light,reading,False,10,keep_awake=True));p.auto_sleep=True;self.assertEqual(p.tick(light,reading,True,10,keep_awake=True),'wake');self.assertIsNone(p.tick(light,reading,True,10,keep_awake=True))
 def test_usb_backend_uses_stable_node_name(self):
  from types import SimpleNamespace
  result=SimpleNamespace(stdout='[{"info":{"props":{"media.class":"Audio/Sink","node.name":"alsa_output.usb-speaker.analog-stereo"}}}]')
  with patch('audio_output.subprocess.run',return_value=result):self.assertEqual(playback_command('usb','tone.wav'),['pw-play','--target','alsa_output.usb-speaker.analog-stereo','tone.wav'])
if __name__=='__main__':unittest.main()
