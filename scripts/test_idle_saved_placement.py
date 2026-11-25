from pathlib import Path
import ast,sys,urllib.request
root=Path.cwd();source=(root/'src/deskpal_app.py').read_text(encoding='utf8');tree=ast.parse(source)
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DeskPalApp')
names={'cycle_choices','next_cycle_choice','apply_cycle_choice'}
mini=ast.Module(body=[ast.ClassDef(name='Probe',bases=[],keywords=[],body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names],decorator_list=[])],type_ignores=[])
ns={'scene_id':lambda cfg:cfg['active_scene']};exec(compile(ast.fix_missing_locations(mini),'<idle regression>','exec'),ns)
a=ns['Probe']();a.cfg={'active_scene':'study','scenes':{'study':{'pose_rules':{'idle_side':{'allow_open_floor':True}},'interaction_spots':[{'id':'mailbox','animation':'mailbox_interact'}]}}};a.character_sequences={'idle_side':{'idle_eligible':True},'mailbox_interact':{'idle_eligible':False},'seated_back':{'idle_eligible':True}};a.mapped_animation_roles=lambda:set();a.rest_role_ready=lambda role:True;a.cycle_choice_reachable=lambda c:True
assert a.cycle_choices()==[];assert a.next_cycle_choice() is None
a.char_x,a.char_y=1020,707;a.audit_activity=lambda *args,**kwargs:None;a.apply_cycle_choice(None);assert a.target_animation is None and a.idle_waiting
spot={'id':'couch','animation':'seated_back','x':400,'y':500};a.cfg['scenes']['study']['interaction_spots'].append(spot)
assert a.next_cycle_choice()[1] is spot
print('Idle regressions passed: open floor excluded; no invented placement; saved couch selected.')

