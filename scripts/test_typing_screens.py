import ast,math,pathlib,types,unittest
import sys
sys.path.insert(0,str(pathlib.Path('src').resolve()))
s=ast.parse(pathlib.Path('src/deskpal_app.py').read_text(encoding='utf-8'));cls=next(n for n in s.body if isinstance(n,ast.ClassDef) and n.name=='DeskPalApp');fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='draw_typing_screens')
lines=[];ns={'math':math,'time':types.SimpleNamespace(monotonic=lambda:1),'pygame':types.SimpleNamespace(draw=types.SimpleNamespace(line=lambda *args:lines.append(args)))}
exec(compile(ast.Module(body=[fn],type_ignores=[]),'screen','exec'),ns)
a=types.SimpleNamespace(current_anim='typing',target_x=364,target_y=620,char_x=364,char_y=620,target_spot_id='desk',cfg={'interaction_spots':[{'id':'desk','x':364,'y':620}]},props=[{'typing_spot_id':'desk','screen_quad':[[196,300],[249,298],[251,359],[197,366]]}],screen=None)
ns['draw_typing_screens'](a);assert len(lines)>=6
a.props[0]['time_of_day']='night';lines.clear();ns['draw_typing_screens'](a);assert not lines
a.lighting_night_amount=1;ns['draw_typing_screens'](a);assert len(lines)>=6
a.props[0]['time_of_day']='both'
for field,value in [('current_anim','walk'),('target_spot_id','elsewhere'),('target_x',400),('is_sleeping',True)]:
 old=getattr(a,field,None);setattr(a,field,value);lines.clear();ns['draw_typing_screens'](a);assert not lines,field;setattr(a,field,old)
print('Screen follows typing arrival, placement and standby; all checks passed.')
