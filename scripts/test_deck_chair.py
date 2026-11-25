import json,ast,math,sys,runpy,types
c=json.load(open('scratch/props_work/screen_config.json'));print('rule',c['scenes']['cozy_study']['pose_rules'].get('sitting_rest'))
tree=ast.parse(open('src/deskpal_app.py',encoding='utf-8').read());names={'obstacle_points','point_in_polygon','clip_floor_to_screen','FloorNavigation'};ns={'math':math};exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names],type_ignores=[]),'nav','exec'),ns)
s=c['scenes']['resort_beach'];nav=ns['FloorNavigation'](s['walkable_trapezoid'],s['obstacles']);print('Chair approach valid',nav.free((965,422)));assert nav.free((965,422))
g=runpy.run_path('scripts/test_playback_modes.py');App=g['App'];g['ns']['scene_id']=lambda cfg:cfg.get('active_scene');a=App.__new__(App);a.cfg={'active_scene':'resort_beach'};a.target_animation=None;a.char_x=a.char_y=a.target_x=a.target_y=0
a.character_sequences={'deck_chair_rest':dict(frames=[0,1],fps=4,idle_eligible=True,allowed_scenes=['resort_beach'],entry_transition='down',exit_transition='up'),'down':dict(frames=[0,1],fps=4),'up':dict(frames=[1,0],fps=4)}
assert a.rest_role_ready('deck_chair_rest');assert a.idle_role_allowed('deck_chair_rest');a.cfg['active_scene']='cozy_study';assert not a.idle_role_allowed('deck_chair_rest')
a.cfg['active_scene']='resort_beach';assert a.begin_rest_transition('deck_chair_rest','entry');g['clock'].value+=1;a.update_rest_transition();assert a.active_rest_role=='deck_chair_rest';assert a.begin_rest_transition('deck_chair_rest','exit');g['clock'].value+=1;a.update_rest_transition();assert a.active_rest_role is None
print('Beach-only eligibility and generic chair entry/exit checks passed.')
