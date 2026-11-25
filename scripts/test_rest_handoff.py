import sys,json,copy,os,importlib.util
from unittest.mock import patch
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
sys.path.insert(0,'/home/admin')
spec=importlib.util.spec_from_file_location('rest_candidate',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from activity_queue import ActivityQueue
from scene_world import activate_scene
cfg=json.load(open('/home/admin/config/room_config.json'));activate_scene(cfg,'cozy_study')
a=m.DeskPalApp.__new__(m.DeskPalApp);a.cfg=cfg;a.character_sequences={v.get('role',k.split(':')[-1]):dict(v,frames=v['frames']) for k,v in cfg['animation_sequences'].items() if v.get('character')=='adventurer_v1'}
a.trap=cfg['walkable_trapezoid'];a.obstacles=cfg['obstacles'];a.width=1280;a.height=720;a.edit_mode=False;a.is_sleeping=False;a.char_x=a.target_x=503.;a.char_y=a.target_y=563.;a.target_spot_id='desk_draws_far';a.target_animation='sitting_rest';a.current_anim='idle';a.wander_timer=1000.;a.target_facing_left=False;a.pending_popup_modal=None;a.scene_journey=[];a.journey_arriving=False;a.activity_queue=ActivityQueue();a.target_playback_override=None;a.audit_activity=lambda *args,**kw:None
clock=[100.]
with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):
 a.update_autonomous_movement(.05);assert a.rest_transition['phase']=='entry'
 clock[0]+=2;a.update_autonomous_movement(.05);assert a.active_rest_role=='sitting_rest'
 for i in range(1000):
  clock[0]+=.05;a.update_autonomous_movement(.05)
  assert not a.rest_transition and a.current_anim=='sitting_rest','Rest must remain seated for a 50-second idle dwell'
 args=({'animation':'inspect','source_event':'real_event'},'Test')
 a.activity_queue.enqueue(args);calls=[]
 def trigger(*args):calls.append(args);a.target_animation=a.current_anim='inspect'
 a.trigger_action=trigger
 a.activity_queue.tick(a,now=clock[0]);assert a.rest_transition['phase']=='exit'
 clock[0]+=2;a.update_autonomous_movement(.05)
 assert a.active_rest_role is None and a.rest_transition is None and a.target_animation!='sitting_rest','Must not immediately re-enter old sitting pose'
 a.activity_queue.tick(a,now=clock[0]);assert len(calls)==1 and not a.activity_queue.items
 print('Actual saved study rest: stays seated 50 seconds, gets up once, then starts queued action.')
# Wake-up exits also retire the previous sitting target.
a.target_animation='sitting_rest';a.active_rest_role='sitting_rest';a.active_rest_spot_id='desk_draws_far';a.begin_rest_transition('sitting_rest','exit');assert a.target_animation=='idle'
print('Rest exit retires old goal; queue and wake-up handoffs passed.')

