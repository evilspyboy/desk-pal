"""Load actual Pi character assets and check perspective scaling in each scene."""
import os,json,urllib.request,importlib.util
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy';os.environ['PYGAME_HIDE_SUPPORT_PROMPT']='1'
import pygame
from scene_world import activate_scene
pygame.display.init();pygame.display.set_mode((1,1))
spec=importlib.util.spec_from_file_location('perspective_test_app','/home/admin/deskpal_app.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
c=json.load(urllib.request.urlopen('http://127.0.0.1:7777/api/config'))
for id in c['scenes']:
 activate_scene(c,id);a=m.DeskPalApp.__new__(m.DeskPalApp);a.cfg=c;a.char_dir='/home/admin/assets/characters/adventurer';a.raw_sprites={};a.sprite_cache={};a.configure_character(c);a.trap=c['walkable_trapezoid']
 key=a.character_sequences['idle_side']['frames'][0]
 for y in [300,420,500,620,720]:
  surface=a.get_perspective_sprite(key,y,False);expected=int(m.floor_perspective_height(a.trap,y));ref=a.sprite_metrics.get(key,{}).get('reference_height')
  if ref:expected*=a.raw_sprites[key].get_height()/ref
  expected=max(4,int(expected//4)*4);assert surface.get_height()==expected,(id,y,surface.get_height(),expected)
 print(id+': actual sprite sizes match polygon-based perspective calibration.')
pygame.quit()
