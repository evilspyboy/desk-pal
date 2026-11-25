import runpy
from unittest.mock import patch
state=runpy.run_path('/home/admin/integration_validation/test_rest_handoff.py');a=state['a'];m=state['m'];clock=[4000.]
from scene_world import activate_scene
activate_scene(a.cfg,'video_store');a.trap=a.cfg['walkable_trapezoid'];a.obstacles=a.cfg['obstacles'];a.props=a.cfg['props'];a._floor_signature=None;a._route_goal=None;a.char_x,a.char_y=a.floor_navigation().nearest((640,600));a.target_x,a.target_y=a.char_x,a.char_y;a.rest_transition=None;a.active_rest_role=None;a.active_rest_spot_id=None;a.target_animation='idle';a.current_anim='idle';a.activity_queue=state['ActivityQueue']();a.anim_timer=0.;a.anim_frame=0;a.current_walk_sequence=lambda:{'fps':4};a.load_scene_backgrounds=lambda:None;a.save_walkbox_config=lambda:None;a.apps=[]
class Power:
 is_off=False
 error=''
 def set_sleeping(self, value):self.is_off=value;return True
a.display_power=Power()
with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):
 choice=a.next_cycle_choice(sleeping=True);assert choice[0]!='video_store' and choice[4] and choice[1] is not None,'VHS screen must find another reachable scene for rest'
 a._idle_world_cursor=0;a.enter_standby();destination=a.pending_idle_destination[0][0];role=a.pending_idle_destination[0][2];spot=a.pending_idle_destination[0][1]['id'];assert a.scene_journey and not a.display_power.is_off
 for i in range(4000):
  clock[0]+=.1;a.update_autonomous_movement(.1)
  if a.display_power.is_off:break
 assert a.display_power.is_off and a.cfg['active_scene']==destination and a.target_spot_id==spot and a.current_anim==role,'Must traverse connections, settle into target and then power off'
 print('VHS sleep travelled to',destination,spot,role,'and powered off after settling.')
 a.wake_from_standby();assert not a.display_power.is_off and a.rest_transition['spot_id']==spot and a.rest_transition['phase']=='exit'
 clock[0]+=2;a.update_autonomous_movement(.1)
 activate_scene(a.cfg,'video_store');a.trap=a.cfg['walkable_trapezoid'];a.obstacles=a.cfg['obstacles'];a._floor_signature=None;a.char_x,a.char_y=a.floor_navigation().nearest((640,600));a.target_x,a.target_y=a.char_x,a.char_y;a._idle_world_cursor=0;a.scene_journey=[];a.journey_arriving=False;a.active_rest_role=None;a.rest_transition=None
 a.select_next_idle();assert a.pending_idle_destination and a.scene_journey and a.idle_waiting
 for i in range(4000):
  clock[0]+=.1;a.update_autonomous_movement(.1)
  if not a.pending_idle_destination and not a.scene_journey and not a.journey_arriving and a.current_anim!='walk' and not a.rest_transition:break
 assert a.cfg['active_scene']!='video_store' and a.idle_waiting and not a.display_power.is_off
 print('Idle also traverses scene connections and waits at its selected pose; wake-up uses the same rest spot.')
