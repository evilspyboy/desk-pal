import sys,unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from integration_state import load_telemetry,save_telemetry,summary_for,button_summary_for,conditions_match,normal_update_action,record_received,suppress_successive_duplicate
from activity_queue import ActivityQueue
class Integration(unittest.TestCase):
 def test_button_uses_status_not_latest_event_and_keeps_its_age(self):
  tele={'summary':'New order!', 'last_seen':999}
  record_received(tele,'heartbeat',{'summary':'Three orders', 'button_summary':'3 awaiting shipment','ttl_seconds':60},100)
  record_received(tele,'store_order',{'summary':'New order!'},999)
  self.assertEqual(button_summary_for(tele,'Store',120),'3 awaiting shipment')
  self.assertIn('awaiting a new response',button_summary_for(tele,'Store',1000))
  self.assertEqual(button_summary_for({'summary':'Legacy','last_seen':100},'Store',120),'Legacy')
 def test_recovered_feed_discards_old_stopped_feed_reaction(self):
  app=SimpleNamespace(apps=[],app_telemetry={'one':{'last_seen':101}})
  q=ActivityQueue();q.enqueue(({'_source_app_id':'one','_health_seen':100},'One'))
  q.enqueue(({'_source_app_id':'one','_important':True},'One'))
  q.remove_suppressed(app);self.assertEqual(len(q.items),1);self.assertTrue(q.items[0][0]['_important'])
 def test_suppression_removes_old_queued_and_active_events_but_keeps_buttons(self):
  app=SimpleNamespace(apps=[{'id':'one','name':'One','suppressed_events':{'heartbeat':True}}],char_x=1,char_y=2)
  q=ActivityQueue();q.active=({'_source_app_id':'one','source_event':'heartbeat'},'One')
  q.enqueue(({'source_event':'heartbeat'},'One'))
  q.enqueue(({'_source_app_id':'one','source_event':'store_order'},'One'))
  q.enqueue(({'_source_app_id':'one','source_event':'heartbeat','_button_action':True},'One'))
  q.remove_suppressed(app)
  self.assertIsNone(q.active);self.assertEqual(len(q.items),2)
  self.assertEqual((app.target_x,app.target_y),(1,2));self.assertEqual(app.scene_journey,[])
 def test_sleep_compacts_routines_and_preserves_alerts(self):
  q=ActivityQueue();logs=[];app=SimpleNamespace(audit_activity=lambda event,**fields:logs.append((event,fields)))
  def item(event,stamp,important=False,age=100):
   return ({'_source_app_id':'one','source_event':event,'_received_at':stamp,'_important':important,'_sleep_max_age_seconds':age},'One')
  q.enqueue(item('heartbeat',100));q.enqueue(item('heartbeat',150));q.enqueue(item('price',100,True))
  q.defer_for_standby(app);self.assertEqual(len(q.items),2)
  q.enqueue(item('heartbeat',200),app);q.enqueue(item('mail',100,age=0),app)
  q.compact_sleep_queue(app,waking=True,now=350)
  self.assertEqual([args[0]['source_event'] for args in q.items],['price','mail'])
  self.assertTrue(any(fields['reason']=='stale_after_sleep' for event,fields in logs))
  q.resume_from_standby(app);self.assertFalse(q.sleeping)
 def test_recent_receipts_expire_and_keep_lifetime_totals(self):
  tele={};record_received(tele,'heartbeat',{},100)
  record_received(tele,'heartbeat',{},200,suppression='duplicate')
  record_received(tele,'heartbeat',{},401,suppression='event')
  received=tele['received_events']['heartbeat']
  self.assertEqual(received['count'],3);self.assertEqual(received['suppressed_count'],2)
  self.assertEqual(received['recent_receipts'],[[200,'duplicate'],[401,'event']])
 def test_button_priority_holds_popup_until_dismissed(self):
  calls=[];a=SimpleNamespace(is_sleeping=False,edit_mode=False,char_x=0,char_y=0,target_x=0,target_y=0,scene_journey=[],journey_arriving=False,rest_transition=None,target_animation='inspect',current_anim='inspect',wander_timer=0,action_sequence=lambda _: {'fps':2},sequence_tick_limit=lambda _:4,trigger_action=lambda *args:calls.append(args[1]))
  q=ActivityQueue();q.enqueue(({'id':'feed1'},'Feed1'));q.enqueue(({'id':'feed2'},'Feed2'));q.tick(a,0)
  q.enqueue_priority(a,({'id':'button','_button_action':True,'_hold_popup_until_dismissed':True},'Button'));q.tick(a,1);q.tick(a,2);q.tick(a,500)
  self.assertEqual(calls,['Feed1','Button']);self.assertEqual(q.completed,0)
  self.assertEqual(q.snapshot()['state'],'waiting_for_dismissal')
  q.dismiss_popup(a);q.tick(a,501);self.assertEqual(calls,['Feed1','Button','Feed1']);self.assertEqual(q.items[0][1],'Feed2')
 def test_standby_defers_current_turn_before_later_events(self):
  q=ActivityQueue();q.active=({'id':'first'},'First');q.enqueue(({'id':'second'},'Second'))
  q.defer_for_standby(SimpleNamespace());self.assertIsNone(q.active)
  self.assertEqual([a[0]['id'] for a in q.items],['first','second'])
 def test_duplicate_setting_and_real_repeated_task(self):
  previous={'summary':'No mail','task_id':'run1','polled_at':1}
  current=dict(previous,polled_at=2)
  self.assertTrue(suppress_successive_duplicate({},'mail_check',previous,current))
  self.assertFalse(suppress_successive_duplicate({},'heartbeat',previous,current))
  self.assertTrue(suppress_successive_duplicate({'suppress_duplicate_events':{'heartbeat':True}},'heartbeat',previous,current))
  self.assertFalse(suppress_successive_duplicate({'suppress_duplicate_events':{'mail_check':False}},'mail_check',previous,current))
  self.assertFalse(suppress_successive_duplicate({},'mail_check',previous,dict(current,task_id='run2')))
  self.assertFalse(suppress_successive_duplicate({},'mail_check',None,current))
 def test_milestone_loop_finishes_without_a_following_event(self):
  import math
  for mode,seconds in [('loop',2),('ping_pong',3)]:
   calls=[];a=SimpleNamespace(is_sleeping=False,edit_mode=False,char_x=0,char_y=0,target_x=0,target_y=0,scene_journey=[],journey_arriving=False,rest_transition=None,target_animation='inspect',current_anim='inspect',wander_timer=0,action_sequence=lambda _: {'fps':2,'frames':[1,2,3,4],'playback_mode':mode},sequence_tick_limit=lambda _:math.inf,trigger_action=lambda *args:calls.append(args[1]))
   q=ActivityQueue();q.enqueue(({'duration_seconds':0},'first'));q.tick(a,0);q.tick(a,1);q.tick(a,1+seconds-.01);self.assertEqual(q.completed,0);q.tick(a,1+seconds);self.assertEqual(q.completed,1);self.assertIsNone(q.active)
 def test_loop_override_and_attention_hold_remain_supported(self):
  import math
  a=SimpleNamespace(is_sleeping=False,edit_mode=False,char_x=0,char_y=0,target_x=0,target_y=0,scene_journey=[],journey_arriving=False,rest_transition=None,target_animation='wave',current_anim='wave',wander_timer=0,action_sequence=lambda _: {'fps':2,'frames':[1,2],'playback_mode':'loop'},sequence_tick_limit=lambda _:math.inf,trigger_action=lambda *args:None)
  q=ActivityQueue();q.enqueue(({'duration_seconds':5},'timed'));q.tick(a,0);q.tick(a,1);q.tick(a,5);self.assertEqual(q.completed,0);q.tick(a,6);self.assertEqual(q.completed,1)
  q.enqueue(({'_attention_waiting':True},'alert'));q.tick(a,7);q.tick(a,8);q.tick(a,1000);self.assertIsNotNone(q.active);self.assertEqual(q.completed,1)
 def test_duration_override_does_not_shorten_finite_animation(self):
  a=SimpleNamespace(is_sleeping=False,edit_mode=False,char_x=0,char_y=0,target_x=0,target_y=0,scene_journey=[],journey_arriving=False,rest_transition=None,target_animation='inspect',current_anim='inspect',wander_timer=0,action_sequence=lambda _: {'fps':2},sequence_tick_limit=lambda _:12,trigger_action=lambda *args:None)
  q=ActivityQueue();q.enqueue(({'duration_seconds':1},'finite'));q.tick(a,0);q.tick(a,1);q.tick(a,2);self.assertEqual(q.completed,0);q.tick(a,7);self.assertEqual(q.completed,1)
 def test_routine_updates_are_quiet_and_configurable(self):
  action={'id':'status_check','speech':'{summary}','display_mode':'popup_modal','animation':'inspect'};app={'actions':[action]}
  quiet=normal_update_action(app);self.assertEqual(quiet['display_mode'],'none');self.assertEqual(quiet['speech'],'');self.assertEqual(action['display_mode'],'popup_modal')
  app['heartbeat_action_id']='';self.assertIsNone(normal_update_action(app))
 def test_event_fields_survive_heartbeats(self):
  tele={};record_received(tele,'price',{'price':160},10);record_received(tele,'heartbeat',{'status':'healthy'},11)
  self.assertEqual(tele['received_events']['price']['data']['price'],160)
  record_received(tele,'price',{'price':155},12);self.assertEqual(tele['received_events']['price']['count'],2)
 def test_pause_does_not_expire_active_turn_and_manual_travel_holds_events(self):
  calls=[];a=SimpleNamespace(is_sleeping=False,edit_mode=False,char_x=0,char_y=0,target_x=0,target_y=0,scene_journey=['manual'],journey_arriving=False,rest_transition=None,target_animation='inspect',current_anim='inspect',wander_timer=0,action_sequence=lambda _: {'fps':2},sequence_tick_limit=lambda _:4,trigger_action=lambda *args:calls.append(args[1]))
  q=ActivityQueue();q.enqueue(({},'first'));q.enqueue(({},'second'));q.tick(a,0);self.assertEqual(len(q.items),2)
  a.scene_journey=[];q.tick(a,1);q.tick(a,2);a.edit_mode=True;q.tick(a,3);q.tick(a,100);a.edit_mode=False;q.tick(a,101);self.assertEqual(calls,['first']);q.tick(a,102);self.assertEqual(calls,['first','second']);self.assertEqual(q.snapshot()['completed'],1)
 def test_persistence_and_age(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'telemetry.json';data={'app':{'summary':'Real response','last_seen':100,'ttl_seconds':300}}
   save_telemetry(p,data);self.assertEqual(load_telemetry(p),data)
   self.assertEqual(summary_for(data['app'],'App',200),'Real response');self.assertIn('awaiting a new response',summary_for(data['app'],'App',1000))
   self.assertIn('No update received',summary_for({},'App',200))
 def test_conditions(self):
  action={'conditions':[{'field':'data.price','op':'lt','value':'170'},{'field':'important','op':'eq','value':'true'}]}
  self.assertTrue(conditions_match(action,{'data':{'price':165},'important':True}));self.assertFalse(conditions_match(action,{'data':{'price':190},'important':True}));self.assertFalse(conditions_match(action,{}))
 def test_fifo_and_travel(self):
  calls=[];a=SimpleNamespace(is_sleeping=False,edit_mode=False,char_x=0,char_y=0,target_x=0,target_y=0,scene_journey=[],journey_arriving=False,rest_transition=None,target_animation='inspect',current_anim='inspect',wander_timer=0,action_sequence=lambda _: {'fps':2},sequence_tick_limit=lambda _:4,trigger_action=lambda *args:calls.append(args[1]))
  q=ActivityQueue();q.enqueue(({},'first'));q.enqueue(({},'second'));q.tick(a,0);self.assertEqual(calls,['first']);a.scene_journey=['travel'];q.tick(a,20);self.assertEqual(calls,['first']);a.scene_journey=[];q.tick(a,21);q.tick(a,22);self.assertEqual(calls,['first']);q.tick(a,23);self.assertEqual(calls,['first','second'])
 def test_standby_holds_queue(self):
  a=SimpleNamespace(is_sleeping=True,edit_mode=False);q=ActivityQueue();q.enqueue(({},'app'));q.tick(a,0);self.assertEqual(len(q.items),1)
 def test_stale_sensor_reaction_does_not_exit_rest(self):
  import time
  calls=[];a=SimpleNamespace(is_sleeping=False,edit_mode=False,scene_journey=[],journey_arriving=False,rest_transition=None,active_rest_role='seated_back',begin_rest_transition=lambda *args:calls.append(args))
  q=ActivityQueue();q.enqueue(({'_sensor_event':True,'_received_at':time.time()-10},'Sensors'));q.tick(a,0)
  self.assertEqual(calls,[]);self.assertFalse(q.items);self.assertIsNone(q.active)
if __name__=='__main__':unittest.main()
