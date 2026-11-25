import sys,unittest,ast,time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path('src').resolve()))
from activity_queue import ActivityQueue
class AttentionTests(unittest.TestCase):
 def test_attention_waits_and_acknowledgement_holds_original_popup(self):
  q=ActivityQueue();events=[]
  a=SimpleNamespace(is_sleeping=False,edit_mode=False,scene_journey=[],journey_arriving=False,current_anim='wave_arms',target_animation='wave_arms',char_x=0,char_y=0,target_x=0,target_y=0,rest_transition=None,wander_timer=0,action_sequence=lambda role:{'frames':['a','b'],'fps':4,'playback_mode':'once'},sequence_tick_limit=lambda seq:2,audit_activity=lambda event,**kw:events.append(event),integration_attention={'fuel':'Original alert'},cfg={'interaction_spots':[]},character_sequences={'wave_arms':{'frames':['a','b'],'fps':4,'playback_mode':'once'}},activity_queue=q)
  action={'id':'drop','_source_app_id':'fuel','_attention_waiting':True};q.active=(action,'Fuel',(1,2,3),'Original price drop',['original detail'],None);q.started=0;q.arrived=0;q.dwell=1
  q.tick(a,1000);self.assertIsNotNone(q.active);self.assertFalse(q.acknowledge_attention(a,'another'))
  candidates=[arg for arg in sys.argv[1:] if arg.endswith('.py') and not arg.startswith('-') and 'test_' not in arg]
  src_path=candidates[0] if candidates else 'src/deskpal_app.py'
  tree=ast.parse(Path(src_path).read_text());method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='action_sequence');ns={};exec(compile(ast.Module(body=[method],type_ignores=[]),'action_sequence','exec'),ns)
  self.assertEqual(ns['action_sequence'](a,'wave_arms')['playback_mode'],'loop');self.assertEqual(a.character_sequences['wave_arms']['playback_mode'],'once')
  a.switches=[{'id':2,'app_id':'fuel'}];a.switch_press_times={};a.active_popup_modal=None;handler=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_handle_switch_pressed');handlers={'time':time};exec(compile(ast.Module(body=[handler],type_ignores=[]),'switch','exec'),handlers);handlers['_handle_switch_pressed'](a,2);self.assertTrue(action['_attention_acknowledged']);self.assertEqual(a.active_popup_modal['summary'],'Original price drop');self.assertEqual(a.target_animation,'idle');q.tick(a,1001);self.assertIsNotNone(q.active)
  q.dismiss_popup(a);q.tick(a,1002);self.assertIsNone(q.active);self.assertIn('attention_acknowledged',events)
  # Touch the sprite, hold the original popup, then dismiss it through the
  # production touch handler and verify the next queued event starts.
  action={'id':'touch-drop','_source_app_id':'fuel','_attention_waiting':True}
  q.active=(action,'Fuel',(1,2,3),'Original touch alert',[],None);q.started=q.arrived=1003;q.dwell=1
  a.active_popup_modal=None;a.character_touch_rect=SimpleNamespace(collidepoint=lambda pos:pos==(10,10))
  a.popup_page_buttons=[]
  touch=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='handle_touch_down')
  touch_ns={'pygame':SimpleNamespace(Rect=lambda *args:SimpleNamespace(collidepoint=lambda pos:False)), 'time':time}
  exec(compile(ast.Module(body=[touch],type_ignores=[]),'touch','exec'),touch_ns)
  q.tick(a,1200);self.assertIsNotNone(q.active)
  touch_ns['handle_touch_down'](a,(10,10))
  self.assertEqual(a.active_popup_modal['summary'],'Original touch alert')
  q.tick(a,1300);self.assertIsNotNone(q.active)
  next_action=({'id':'next','animation':'inspect'},'Next',(1,2,3),'Next event',[],None)
  q.enqueue(next_action);a.trigger_action=lambda *args:setattr(a,'target_animation',args[0]['animation'])
  touch_ns['handle_touch_down'](a,(50,50));q.tick(a,1301)
  self.assertEqual(q.active[0]['id'],'next');self.assertIsNone(a.active_popup_modal)
if __name__=='__main__':unittest.main(argv=[sys.argv[0]])

