"""Exercise new rear seated transitions against live assets without saving placements."""
import os,json,urllib.request,importlib.util
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy';os.environ['PYGAME_HIDE_SUPPORT_PROMPT']='1'
import pygame
from scene_world import activate_scene
pygame.display.init();pygame.display.set_mode((1,1))
spec=importlib.util.spec_from_file_location('seated_test_app','/home/admin/deskpal_app.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
original=json.load(urllib.request.urlopen('http://127.0.0.1:7777/api/config'))
for scene in ('resort_beach','apartment'):
 c=json.loads(json.dumps(original));activate_scene(c,scene)
 a=m.DeskPalApp.__new__(m.DeskPalApp);a.cfg=c;a.char_dir='/home/admin/assets/characters/adventurer';a.raw_sprites={};a.sprite_cache={};a.configure_character(c)
 assert a.rest_role_ready('seated_back') and a.idle_role_allowed('seated_back')
 assert not a.idle_role_allowed('seated_back_sit_down')
 a.trap=c['walkable_trapezoid'];a.obstacles=c['obstacles'];a.edit_mode=False;a.is_sleeping=False;a.width=1280;a.height=720
 p=c['scenes'][scene]['portals'][0];a.char_x=a.target_x=p['inside_x'];a.char_y=a.target_y=p['inside_y'];a.target_animation='seated_back';a.current_anim='walk';a.target_spot_id=None;a.target_facing_left=False;a.pending_popup_modal=None;a.wander_timer=100;a.facing_left=False;a.anim_frame=0;a.anim_timer=0
 assert a.floor_navigation().free((a.char_x,a.char_y));a.update_autonomous_movement(.01);assert a.rest_transition['role']=='seated_back_sit_down'
 a.rest_transition['started']-=3;a.update_autonomous_movement(.01);assert a.active_rest_role=='seated_back';assert a.current_anim=='seated_back'
 a.target_x+=20;a.target_animation='idle';a.update_autonomous_movement(.01);assert a.rest_transition['role']=='seated_back_get_up'
 a.rest_transition['started']-=3;a.update_autonomous_movement(.01);assert a.active_rest_role is None;assert a.current_anim=='walk'
 print(scene+': live frames loaded; sit, breathing rest, get-up and walking passed.')
pygame.quit()
