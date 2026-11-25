"""Render saved chair placements against live assets with old and seated-specific masks."""
import os,json,importlib.util
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy';os.environ['PYGAME_HIDE_SUPPORT_PROMPT']='1'
import pygame
from scene_world import activate_scene
pygame.display.init();pygame.display.set_mode((1,1))
def module(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
old=module('/home/admin/deskpal_app.py','old_chairs');new=module('/home/admin/chair_validation/deskpal_app.py','new_chairs')
c=json.load(open('/home/admin/chair_validation/config.json'));activate_scene(c,'resort_beach')
for label,m in [('before',old),('after',new)]:
 a=m.DeskPalApp.__new__(m.DeskPalApp);a.cfg=c;a.char_dir='/home/admin/assets/characters/adventurer';a.raw_sprites={};a.sprite_cache={};a.configure_character(c);a.trap=c['walkable_trapezoid'];a.obstacles=c['obstacles']
 bg=pygame.transform.scale(pygame.image.load('/home/admin/assets/themes/resort_beach/background_close.png'),(1280,720))
 key=a.character_sequences['seated_back']['frames'][0]
 for id in ['seated_back','seated_back_2']:
  spot=next(s for s in c['interaction_spots'] if s['id']==id);a.char_x=spot['x'];a.char_y=spot['y'];a.target_spot_id=id;a.current_anim='seated_back';a.rest_transition=None
  flip=spot.get('facing')=='left';sprite=a.get_perspective_sprite(key,a.char_y,flip);anchor=a.sprite_metrics[key].get('anchor_x',.5);anchor=1-anchor if flip else anchor;dx=a.char_x-sprite.get_width()*anchor;dy=a.char_y-sprite.get_height()
  masked=a.foreground_sprite(sprite,dx,dy);bg.blit(masked,(dx,dy))
  if label=='after':
   walking=m.foreground_outlines(a.obstacles,a.char_x,a.char_y,'walk',id)
   baseline=m.foreground_outlines(a.obstacles,a.char_x,a.char_y)
   assert walking==baseline,'Walking must retain full chair occlusion'
   assert m.foreground_outlines(a.obstacles,a.char_x,a.char_y,'seated_back_get_up',id)==m.foreground_outlines(a.obstacles,a.char_x,a.char_y,'seated_back',id)
 pygame.image.save(bg,'/home/admin/chair_validation/'+label+'.png')
print('Both saved chairs rendered; walking retains full masks and seating transitions use frame masks.')
pygame.quit()
