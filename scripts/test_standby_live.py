"""Headless integration smoke test using the Pi's live character assets and scene."""
import os,sys,json,urllib.request,importlib.util
from unittest.mock import patch
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
import pygame
from scene_world import activate_scene
pygame.display.init();pygame.display.set_mode((1,1))
spec=importlib.util.spec_from_file_location('rest_test_app',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
cfg=json.load(urllib.request.urlopen('http://127.0.0.1:7777/api/config'))
test_scene=sys.argv[2] if len(sys.argv)>2 else 'cozy_study'
activate_scene(cfg,test_scene)
a=m.DeskPalApp.__new__(m.DeskPalApp);a.cfg=cfg;a.char_dir='/home/admin/assets/characters/adventurer';a.raw_sprites={};a.sprite_cache={};a.configure_character(cfg)
a.trap=cfg['walkable_trapezoid'];a.obstacles=cfg.get('obstacles',[]);a.edit_mode=False;a.is_sleeping=False
a.char_x,a.char_y=a.clamp_to_walkable((a.trap['back_x_min']+a.trap['back_x_max'])/2,(a.trap['y_min']+a.trap['y_max'])/2)
a.target_x,a.target_y=a.char_x,a.char_y;a.target_animation='idle';a.current_anim='idle';a.target_facing_left=None;a.pending_popup_modal=None;a.wander_timer=10;a.facing_left=False
clock=[0]
class FakePower:
 def __init__(self):self.is_off=False;self.calls=[]
 def set_sleeping(self,value):self.calls.append(value);self.is_off=value;return True
a.display_power=FakePower()
with patch.object(m.time,'monotonic',lambda:clock[0]):
 a.enter_standby()
 if test_scene=='video_store':
  assert a.target_animation=='idle'
  for i in range(60):clock[0]+=1/30;a.update_autonomous_movement(1/30)
  assert a.display_power.calls==[True],a.display_power.calls
  a.wake_from_standby();assert a.display_power.calls==[True,False]
  print('Scene without a resting placement powers off and wakes correctly.')
  pygame.quit();sys.exit(0)
 assert a.target_animation in ('sleeping','sitting_rest','deck_chair_rest','seated_back')
 for i in range(1800):
  clock[0]+=1/30;a.update_autonomous_movement(1/30)
  if getattr(a,'active_rest_role',None) and not getattr(a,'rest_transition',None):break
 assert getattr(a,'active_rest_role',None), 'Did not reach a valid rest placement'
 point=(a.char_x,a.char_y);role=a.active_rest_role
 for i in range(300):clock[0]+=1/30;a.update_autonomous_movement(1/30)
 assert point==(a.char_x,a.char_y) and a.active_rest_role==role
 assert a.display_power.calls==[True],a.display_power.calls
 a.wake_from_standby();clock[0]+=1/30;a.update_autonomous_movement(1/30);assert a.rest_transition['phase']=='exit'
 for i in range(120):
  clock[0]+=1/30;a.update_autonomous_movement(1/30)
  if a.active_rest_role is None:break
 assert a.active_rest_role is None and not a.is_sleeping
 assert a.display_power.calls==[True,False],a.display_power.calls
print('Live-asset standby: navigated to rest, held for 10 seconds, completed getting-up transition on wake.')
pygame.quit()
