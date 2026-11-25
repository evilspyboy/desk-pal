import runpy
from unittest.mock import patch
state=runpy.run_path('/home/admin/integration_validation/test_world_idle.py');a=state['a'];m=state['m'];clock=[8000.]
with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):
 for cycle in range(8):
  a.enter_standby();wanted=a.standby_choice
  for i in range(5000):
   clock[0]+=.1;a.update_autonomous_movement(.1)
   if a.display_power.is_off:break
  assert a.display_power.is_off, 'Must finish requested sleep journey'
  assert a.cfg['active_scene']==wanted[0] and a.current_anim==wanted[2] and a.target_spot_id==wanted[1]['id'], 'Never power off at an unrelated standing pose'
  a.wake_from_standby();assert a.rest_transition['phase']=='exit'
  clock[0]+=.1;a.update_autonomous_movement(.1)
  a.enter_standby();assert a.pending_standby_choice, 'Rapid sleep during get-up must wait'
  wanted=a.standby_choice
  for i in range(5000):
   clock[0]+=.1;a.update_autonomous_movement(.1)
   if a.display_power.is_off:break
  assert a.display_power.is_off and a.current_anim==wanted[2] and a.target_spot_id==wanted[1]['id']
  a.wake_from_standby();clock[0]+=2;a.update_autonomous_movement(.1)
print('Eight repeated wake/sleep cycles, including presses during get-up, reach the chosen rest before powering off.')
