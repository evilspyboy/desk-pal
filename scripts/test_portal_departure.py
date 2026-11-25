import ast,math,pathlib,types
tree=ast.parse(pathlib.Path('src/deskpal_app.py').read_text(encoding='utf-8'))
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DeskPalApp')
cls.body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('target_next_portal','advance_scene_journey')]
p={'x':10,'y':20,'inside_x':90,'inside_y':100}
ns={'math':math,'portal':lambda cfg,end:p};exec(compile(ast.Module(body=[cls],type_ignores=[]),'portal_test','exec'),ns)
a=ns['DeskPalApp']();a.cfg={};a.scene_journey=[{'from':{},'to':{}}]
a.target_next_portal();assert (a.target_x,a.target_y)==(90,100)
a.char_x,a.char_y=90,100;assert a.advance_scene_journey();assert (a.target_x,a.target_y)==(10,20) and a.journey_exiting
a.target_next_portal();a.char_x,a.char_y=40,40;assert not a.advance_scene_journey();assert a.scene_journey==[]
print('Departure visits the inside point before the exit; interrupted paths cannot teleport scenes.')
