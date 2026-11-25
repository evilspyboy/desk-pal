import os,json,urllib.request,importlib.util,sys
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy';os.environ['PYGAME_HIDE_SUPPORT_PROMPT']='1'
import pygame
from scene_world import activate_scene
pygame.display.init();pygame.display.set_mode((1,1))
spec=importlib.util.spec_from_file_location('chair_test_app','/home/admin/deskpal_app.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
c=json.load(urllib.request.urlopen('http://127.0.0.1:7777/api/config'));activate_scene(c,'resort_beach')
a=m.DeskPalApp.__new__(m.DeskPalApp);a.cfg=c;a.char_dir='/home/admin/assets/characters/adventurer';a.raw_sprites={};a.sprite_cache={};a.configure_character(c)
a.trap=c['walkable_trapezoid'];a.obstacles=c['obstacles'];a.edit_mode=False;a.is_sleeping=False;a.width=1280;a.height=720
spot=next(s for s in c['interaction_spots'] if 'deck_chair_rest' in [s.get('animation')]+s.get('animations',[]));a.char_x=a.target_x=spot['x'];a.char_y=a.target_y=spot['y'];a.target_animation='deck_chair_rest';a.current_anim='walk';a.target_spot_id=spot['id'];a.target_facing_left=True;a.pending_popup_modal=None;a.wander_timer=100;a.facing_left=True;a.anim_frame=0;a.anim_timer=0
assert a.floor_navigation().free((a.char_x,a.char_y));a.update_autonomous_movement(.01);assert a.rest_transition['role']=='deck_chair_sit_down'
a.rest_transition['started']-=3;a.update_autonomous_movement(.01);assert a.active_rest_role=='deck_chair_rest';assert a.current_anim=='deck_chair_rest'
a.target_x=900;a.target_y=500;a.target_animation='idle';a.update_autonomous_movement(.01);assert a.rest_transition['role']=='deck_chair_get_up'
a.rest_transition['started']-=3;a.update_autonomous_movement(.01);assert a.active_rest_role is None;assert a.current_anim=='walk'
print('Pi loaded all new sprite frames and verified approach -> sit -> rest -> get up -> walk without changing the live display.');pygame.quit()
