import runpy,sys
from unittest.mock import patch
state=runpy.run_path('/home/admin/integration_validation/test_rest_handoff.py');a=state['a'];m=state['m'];clock=[1000.]
a.rest_transition=None;a.active_rest_role=None;a.active_rest_spot_id=None;a.current_anim='idle';a.target_animation='idle';a.activity_queue=state['ActivityQueue']();a.trigger_action=m.DeskPalApp.trigger_action.__get__(a);a.cfg['pose_rules']={};a.target_spot_id=None;a.wander_timer=0;a._idle_cursors={};a.apps=[]
spot={'id':'desk_draws_far','x':503,'y':563,'facing':'right'}
a.choose_idle_spots=lambda:[(spot,'sitting_rest'),(spot,'ponder')]
a.cycle_choices=lambda:[('cozy_study',spot,'sitting_rest',True,True),('cozy_study',spot,'ponder',True,False)]
a.character_sequences['ponder']={'frames':['p0','p1'],'fps':4,'playback_mode':'once'}
with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):
 a.select_next_idle();assert a.target_animation=='sitting_rest'
 a.update_autonomous_movement(.05);clock[0]+=2;a.update_autonomous_movement(.05)
 for i in range(600):
  clock[0]+=.1;a.activity_queue.tick(a,now=clock[0]);a.update_autonomous_movement(.1)
  assert a.current_anim=='sitting_rest' and not a.rest_transition,'Idle must hold for 60 seconds'
 a.activity_queue.enqueue(({'animation':'inspect','playback_override':{'playback_mode':'once'},'display_mode':'none'},'Test'))
 for i in range(100):
  clock[0]+=.05;a.activity_queue.tick(a,now=clock[0]);a.update_autonomous_movement(.05)
  if a.activity_queue.completed==1 and a.idle_waiting and a.target_animation=='ponder':break
 assert a.activity_queue.completed==1 and a.target_animation=='ponder','Completed event must advance to second idle pose'
 a.update_autonomous_movement(.05);a.gesture_sprite_name('ponder')
 clock[0]+=90;a.update_autonomous_movement(.1)
 assert a.target_animation=='ponder' and a.current_anim=='ponder' and a.gesture_sprite_name('ponder')=='p1','Play-once idle must hold final frame'
 a.activity_queue.enqueue(({'animation':'inspect','playback_override':{'playback_mode':'once'},'display_mode':'none'},'Test'))
 for i in range(100):
  clock[0]+=.05;a.activity_queue.tick(a,now=clock[0]);a.update_autonomous_movement(.05)
  if a.activity_queue.completed==2 and a.idle_waiting:break
 assert a.target_animation=='sitting_rest','Progression must wrap around after the next event'
print('Idle holds until events; real queue interrupts, finite event completes, next idle advances and once holds final frame; cycle wraps.')

