import sys, unittest, math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from prop_runtime import frame_index, validate_prop_config, prop_time_visible
class Props(unittest.TestCase):
 def test_time_visibility_and_validation(self):
  self.assertTrue(prop_time_visible({},1))
  self.assertTrue(prop_time_visible({'time_of_day':'day'},.49))
  self.assertFalse(prop_time_visible({'time_of_day':'day'},.5))
  self.assertTrue(prop_time_visible({'time_of_day':'night'},.5))
  self.assertFalse(prop_time_visible({'time_of_day':'night'},0))
  with self.assertRaises(ValueError):validate_prop_config({'props':[{'time_of_day':'bad'}]})
 def test_modes(self):
  a={'frames':['a','b','c'],'fps':1}
  self.assertEqual([frame_index(a,t) for t in range(7)],[0,1,2,0,1,2,0])
  a['playback_mode']='ping_pong';self.assertEqual([frame_index(a,t) for t in range(7)],[0,1,2,1,0,1,2])
  a['playback_mode']='once';self.assertEqual(frame_index(a,9),2)
  a.update(playback_mode='repeat',repeat_count=2);self.assertEqual(frame_index(a,3),0);self.assertEqual(frame_index(a,6),2)
  self.assertIsNone(frame_index({'frames':[]},0))
 def test_validation(self):
  c={'prop_animations':{'lamp':{'frames':['/assets/props/'+'a'*32+'.png']}},'props':[{'animation_id':'lamp','x':5,'y':8,'width':100}]}
  validate_prop_config(c)
  for valid_act in ('none', 'tv', 'overlay_popup', 'app_action', 'game_script', 'trigger_animation'):
   c['props'][0]['interaction'] = valid_act
   validate_prop_config(c)
  c['props'][0]['interaction'] = 'invalid_action'
  with self.assertRaises(ValueError):validate_prop_config(c)
  c['props'][0]['interaction'] = 'none'
  c['props'][0]['width']=float('nan')
  with self.assertRaises(ValueError):validate_prop_config(c)
  c['props']=[];c['prop_animations']['lamp']['frames']=['/assets/props/../../secret.png']
  with self.assertRaises(ValueError):validate_prop_config(c)
if __name__=='__main__':unittest.main()
