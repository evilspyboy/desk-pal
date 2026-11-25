"""Exercise real touch handlers without launching the display or hardware."""
import ast
from pathlib import Path
from types import SimpleNamespace

tree = ast.parse(Path('src/deskpal_app.py').read_text(encoding='utf-8'))
names = {'handle_touch_down', 'handle_touch_motion', 'handle_touch_up'}
methods = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in names]
class Rect:
    def __init__(self, x, y, w, h): self.bounds = x, y, w, h
    def collidepoint(self, pos):
        x, y, w, h = self.bounds
        return x <= pos[0] < x+w and y <= pos[1] < y+h
ns = {'pygame': SimpleNamespace(Rect=Rect)}
exec(compile(ast.Module(body=methods, type_ignores=[]), '<touch handlers>', 'exec'), ns)
a = SimpleNamespace(tv_viewer=None, activity_queue=None, is_sleeping=False,
    active_popup_modal=None, show_shutdown_modal=False, edit_mode=False,
    top_controls_open=False, top_swipe_start=None, running=True,
    btn_exit_rect=Rect(1170,12,95,44), btn_edit_rect=Rect(108,80,85,44),
    btn_keys_rect=Rect(16,80,85,44), btn_font_rect=Rect(200,80,110,44),
    keys_pinned=False, show_quick_keys=False)
down=lambda p: ns['handle_touch_down'](a,p)
motion=lambda p: ns['handle_touch_motion'](a,p)
up=lambda: ns['handle_touch_up'](a)
down((30,20)); motion((30,54)); assert not a.top_controls_open
motion((30,60)); assert a.top_controls_open
up(); assert a.top_swipe_start is None
down((30,95)); assert a.keys_pinned and a.show_quick_keys
down((400,200)); assert not a.top_controls_open
down((30,20)); motion((100,50)); assert not a.top_controls_open
up()
down((30,20)); motion((30,70)); up()
down((120,95)); assert a.edit_mode and not a.top_controls_open
a.edit_mode=False
down((1200,30)); assert not a.running
print('Passed swipe threshold/direction, keys, outside dismissal, edit and permanent Exit.')
