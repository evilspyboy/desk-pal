import runpy,copy
state=runpy.run_path('/home/admin/integration_validation/test_rest_handoff.py');a=state['a']
a.cfg['apps']=[{'id':'travel','suppressed_events':{'deal':True},'actions':[{'id':'deal','animation':'beach_dig','scene':'resort_beach','target_mode':'gesture'}]}];a.cfg['event_mappings']=[]
a.character_sequences['beach_dig']['idle_eligible']=True
choices=a.cycle_choices();assert 'beach_dig' in a.mapped_animation_roles();assert not any(c[2]=='beach_dig' and c[3] for c in choices)
a.cfg['apps']=[];assert any(c[2]=='beach_dig' and c[3] for c in a.cycle_choices())
a.character_sequences['beach_dig']['idle_eligible']=False;assert not any(c[2]=='beach_dig' and c[3] for c in a.cycle_choices())
a.cfg['apps']=[{'actions':[{'target_mode':'location','scene':'resort_beach','spot_id':'mid_beach'}]}];assert 'beach_dig' in a.mapped_animation_roles()
a.cfg['apps']=[{'actions':[{'target_mode':'any','scene':'resort_beach'}]}];assert 'bar_drink' in a.mapped_animation_roles()
a.cfg['apps']=[{'actions':[{'animation':'idle'}]}];assert 'idle_side' in a.mapped_animation_roles()
a.cfg['apps']=[];a.cfg['event_mappings']=[{'animation':'beach_dig'}];assert 'beach_dig' in a.mapped_animation_roles()
print('Mapped gestures, locations, any-selection, buttons/idle aliases and legacy mappings cannot run as idle; explicit disabled flags are retained.')
