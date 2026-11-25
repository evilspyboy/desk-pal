import runpy
from unittest.mock import patch
state=runpy.run_path('/home/admin/integration_validation/test_rest_handoff.py');a=state['a'];m=state['m'];clock=[2000.]
a.activity_queue=state['ActivityQueue']();a.rest_transition=None;a.active_rest_role=None;a.active_rest_spot_id=None;a.current_anim='idle';a.target_animation='idle';a.target_spot_id=None;a._idle_cursors={};a.wander_timer=0;a.apps=[]
left={'id':'desk_draws_far','x':503,'y':563,'facing':'right'};right={'id':'hearth_rug','x':669,'y':596,'facing':'left'}
a.choose_idle_spots=lambda:[(left,'sitting_rest'),(left,'inspect'),(right,'sleeping')]
a.choose_standby_spots=lambda:[(left,'sitting_rest'),(right,'sleeping')]
a.cycle_choices=lambda:[('cozy_study',left,'sitting_rest',True,True),('cozy_study',left,'inspect',True,False),('cozy_study',right,'sleeping',True,True)]
a.cfg['pose_rules']={}
class Power:
 is_off=False
 error=''
 def set_sleeping(self, value):self.is_off=value;return True
a.display_power=Power();a.anim_timer=0.;a.anim_frame=0;a.motion_direction='side';a.current_walk_sequence=lambda:{'fps':4}
with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):
 a.select_next_idle();assert a.target_spot_id=='desk_draws_far'
 a.enter_standby();assert a.target_spot_id=='hearth_rug' and a.target_animation=='sleeping','Sleep must take next allowed cycle choice, skipping inspect even though nearest is the previous seat'
 for i in range(300):
  clock[0]+=.1;a.update_autonomous_movement(.1)
  if a.display_power.is_off:break
 assert a.display_power.is_off and a.active_rest_role=='sleeping' and a.active_rest_spot_id=='hearth_rug','Sleep must arrive, enter rest, then power off'
 a.wake_from_standby();assert not a.display_power.is_off and a.rest_transition['phase']=='exit' and a.rest_transition['spot_id']=='hearth_rug'
 clock[0]+=2;a.update_autonomous_movement(.1)
 a.enter_standby();assert a.target_spot_id=='desk_draws_far','Next sleep request must wrap shared cycle'
 a.cycle_choices=lambda:[];a.enter_standby();assert a.target_animation=='idle' and (a.target_x,a.target_y)==(a.char_x,a.char_y)
print('Sleep shares idle cursor, skips ineligible poses, reaches next rest, powers off, wakes at same spot, wraps and retains fallback.')

