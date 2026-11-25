import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import ast, math, types, random
from pathlib import Path
source=Path('src/deskpal_app.py').read_text(encoding='utf-8');tree=ast.parse(source)
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DeskPalApp')
cls.body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('sequence_sprite_name','sequence_tick_limit','action_sequence','update_autonomous_movement','update_rest_transition','begin_rest_transition','rest_role_ready','idle_role_allowed','choose_idle_spots','enter_standby','wake_from_standby','mapped_animation_roles')]
clock=types.SimpleNamespace(value=0,monotonic=lambda:clock.value)
from scene_world import scene_id
ns={'math':math,'time':clock,'random':random,'scene_id':scene_id};exec(compile(ast.Module(body=[cls],type_ignores=[]),'app','exec'),ns);App=ns['DeskPalApp']
App.next_cycle_choice = lambda self, sleeping=False: (None, self.cfg.get('interaction_spots', [{}])[0], self.cfg.get('interaction_spots', [{}])[0].get('animation', 'sleeping'), False, True)
App.apply_cycle_choice = lambda self, choice, sleeping=False: (setattr(self, 'target_animation', choice[2] if choice else None), setattr(self, 'target_spot_id', choice[1].get('id') if choice and choice[1] else None))
App.select_next_idle = lambda self: (setattr(self, 'current_anim', 'idle'), setattr(self, 'target_x', getattr(self, 'pick_random_wander_point', lambda: (0, 0))()[0]))
App.audit_activity = lambda self, *a, **k: None
for mode,expected in [('once',[0,1,2,2,2,2,2]),('repeat',[0,1,2,0,1,2,2]),('loop',[0,1,2,0,1,2,0]),('ping_pong',[0,1,2,1,0,1,2])]:
 seq=dict(frames=[0,1,2],fps=4,playback_mode=mode,repeat_count=2)
 assert [App.sequence_sprite_name(seq,i) for i in range(7)]==expected
 assert App.sequence_sprite_name(dict(seq,frames=[0]),100)==0
app=App();app.edit_mode=False;app.char_x=app.char_y=app.target_x=app.target_y=0;app._route_goal=(0,0);app._route=[]
app.floor_navigation=lambda:types.SimpleNamespace(free=lambda p:True)
app.target_facing_left=None;app.target_animation='reach';app.current_anim='idle';app.pending_popup_modal=None;app.wander_timer=0
app.character_sequences={'reach':dict(frames=[0,1,2,3],fps=4,playback_mode='repeat',repeat_count=2)}
app.cfg={'interaction_spots':[],'pose_rules':{'idle':{'allow_open_floor':True}}};app.pick_random_wander_point=lambda:(10,10)
for t in (0,.5,1,1.99):
 clock.value=t;app.update_autonomous_movement(.1);assert app.current_anim=='reach';assert app.target_x==0
clock.value=2;app.update_autonomous_movement(.1);assert app.current_anim=='idle';assert app.target_x==10
print('Runtime once/repeat/loop/ping-pong boundaries, single frames and finite-action completion passed')
app.cfg['active_character']='v1';app.target_spot_id='one';app.target_playback_override=None
app.cfg['interaction_spots']=[{'id':'one','playback_overrides':{'v1':{'reach':{'playback_mode':'once'}}}},{'id':'two'},{'id':'three'}]
assert app.action_sequence('reach')['playback_mode']=='once'
app.target_spot_id='two';assert app.action_sequence('reach')['playback_mode']=='repeat'
app.target_spot_id='three';assert app.action_sequence('reach')['playback_mode']=='repeat'
app.target_spot_id='one';app.cfg['active_character']='v2';assert app.action_sequence('reach')['playback_mode']=='repeat'
assert app.character_sequences['reach']['playback_mode']=='repeat'
print('Location override isolated across three placements and characters; animation default unchanged')
# Rest entry and wake must finish before movement; eligibility is independent of bindings.
app=App();app.character_sequences={
 'sleeping':dict(frames=[0,1],fps=4,playback_mode='loop',idle_eligible=True,entry_transition='lie_down',exit_transition='stand_from_sleep'),
 'lie_down':dict(frames=[2,3],fps=4,transition_only=True),
 'stand_from_sleep':dict(frames=[4,5],fps=4,transition_only=True),
 'inspect':dict(frames=[6,7],fps=4,idle_eligible=False),
 'idle_side':dict(frames=[8],fps=4,playback_mode='loop',idle_eligible=True)}
app.cfg={'active_character':'v1','interaction_spots':[{'id':'rug','x':0,'y':0,'animation':'sleeping','animations':['inspect']}],'pose_rules':{'sleeping':{'valid_spots':['rug']}}}
app.edit_mode=False;app.char_x=app.char_y=app.target_x=app.target_y=0;app._route_goal=(0,0);app._route=[];app.pending_popup_modal=None;app.current_anim='idle';app.target_animation='idle';app.target_facing_left=None
app.floor_navigation=lambda:types.SimpleNamespace(free=lambda p:True);app.pick_random_wander_point=lambda:(20,20)
assert [r for _,r in app.choose_idle_spots()]==['sleeping']
clock.value=0;app.enter_standby();assert app.is_sleeping and app.target_animation=='sleeping'
app.update_autonomous_movement(.1);assert app.rest_transition['phase']=='entry'
clock.value=.49;app.update_autonomous_movement(.1);assert app.current_anim=='lie_down'
clock.value=.5;app.update_autonomous_movement(.1);assert app.active_rest_role=='sleeping'
clock.value=100;app.update_autonomous_movement(.1);assert app.char_x==0 and app.target_animation=='sleeping'
app.wake_from_standby();app.update_autonomous_movement(.1);assert app.rest_transition['phase']=='exit'
clock.value=100.49;app.update_autonomous_movement(.1);assert app.active_rest_role=='sleeping'
clock.value=100.5;app.update_autonomous_movement(.1);assert app.active_rest_role is None and app.current_anim=='idle'
# Missing transitions make a rest pose ineligible.
del app.character_sequences['stand_from_sleep'];assert not app.rest_role_ready('sleeping');assert not app.idle_role_allowed('sleeping')
print('Idle filtering, standby hold, entry/exit timing, wake and missing-transition protection passed')
