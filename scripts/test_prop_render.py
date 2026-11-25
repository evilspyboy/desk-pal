import os,sys,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
try:
    import pygame
except ImportError:
    print("Skipping test_prop_render: pygame not installed")
    sys.exit(0)
from prop_runtime import draw_props, prop_is_active, warp_screen
pygame.init();pygame.display.set_mode((1,1))
url='/assets/props/'+'a'*32+'.png';image=pygame.Surface((10,10),pygame.SRCALPHA);image.fill((255,0,0,255))
p={'id':'lamp','animation_id':'lamp','x':50,'y':50,'width':20,'layer':'depth','depth_y':60,'trigger':'always'}
a=SimpleNamespace(cfg={'active_scene':'test','prop_animations':{'lamp':{'frames':[url],'fps':4}},'props':[p]},char_y=40,char_x=50,target_x=50,target_y=40,current_anim='idle',is_sleeping=False,screen=pygame.Surface((100,100),pygame.SRCALPHA))
with patch.object(pygame.image,'load',return_value=image):
 draw_props(a,False);assert a.screen.get_at((50,50)).a==0
 draw_props(a,True);assert a.screen.get_at((50,50)).r==255
 p['time_of_day']='night';a.lighting_night_amount=0;a.screen.fill((0,0,0,0));draw_props(a,True)
 assert a.screen.get_at((50,50)).a==0 and ('test','lamp') not in a._image_prop_state
 a.lighting_night_amount=1;draw_props(a,True);assert a.screen.get_at((50,50)).r==255
 p['time_of_day']='both'
 p['trigger']='typing';draw_props(a,True);assert not a._image_prop_state[('test','lamp')]['active']
 p['typing_spot_id']='desk';a.target_spot_id='desk';a.current_anim='typing';draw_props(a,True);assert a._image_prop_state[('test','lamp')]['active']
 p['trigger']='action';a.active_prop_overlays={'lamp':{'start_time':time.time(),'duration':10}};draw_props(a,True);assert a._image_prop_state[('test','lamp')]['active']
 a.is_sleeping=True;draw_props(a,True);assert not a._image_prop_state[('test','lamp')]['active']
a.is_sleeping=False;p.update(trigger='pose',pose_spot_id='couch',pose_animation='seated_back',hide_when_inactive=True,animation_ids=['lamp','other'])
a.cfg['prop_animations']['other']={'frames':[url],'fps':4};a.current_anim='seated_back';a.target_spot_id='couch'
assert prop_is_active(a,p);a.char_x=45;assert not prop_is_active(a,p);a.char_x=50
a.current_anim='seated_back_enter';assert not prop_is_active(a,p);a.current_anim='seated_back'
a.active_rest_role='seated_back';a.active_rest_spot_id='couch';a.current_anim='idle';a.target_spot_id='next_destination'
assert prop_is_active(a,p), 'A settled couch pose must use its actual rest placement'
a.rest_transition={'phase':'exit'};assert not prop_is_active(a,p)
a.rest_transition=None;a.active_rest_spot_id='another_chair';assert not prop_is_active(a,p)
a.active_rest_spot_id='couch';a.is_sleeping=True;assert not prop_is_active(a,p)
a.is_sleeping=False;a.active_rest_role=None;a.target_spot_id='couch';a.current_anim='seated_back'
with patch.object(pygame.image,'load',return_value=image), patch('prop_runtime.random.choice',side_effect=['other','lamp']) as choose:
 draw_props(a,True);assert a._image_prop_state[('test','lamp')]['animation_id']=='other'
 draw_props(a,True);assert choose.call_count==1
 a.current_anim='idle';a.screen.fill((0,0,0,0));draw_props(a,True);assert a.screen.get_at((50,50)).a==0
 a.current_anim='seated_back';draw_props(a,True);assert choose.call_count==2;assert a._image_prop_state[('test','lamp')]['animation_id']=='lamp'
projected,origin=warp_screen(image,[[10,10],[30,12],[28,30],[12,28]])
assert origin==(10,10) and projected.get_at((10,10)).r==255 and projected.get_at((0,19)).a==0
print('Pose arrival, random selection once per activation, hidden inactive state and screen projection passed.')
print('Prop alpha rendering, depth layers, typing/action triggers and standby passed.');pygame.quit()
