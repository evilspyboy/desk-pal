"""Headless travel simulation; never mutates the running display/configuration."""
import os,sys,json,urllib.request,importlib.util
from copy import deepcopy
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
import pygame
from seed_scenes import seed
from scene_world import scene_id, activate_scene
pygame.display.init();pygame.display.set_mode((1,1))
spec=importlib.util.spec_from_file_location('travel_test_app',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
cfg=seed(json.load(urllib.request.urlopen('http://127.0.0.1:7777/api/config')))
activate_scene(cfg,'cozy_study')
a=m.DeskPalApp.__new__(m.DeskPalApp);a.cfg=deepcopy(cfg);a.char_dir='/home/admin/assets/characters/adventurer';a.raw_sprites={};a.sprite_cache={};a.configure_character(a.cfg)
a.trap=a.cfg['walkable_trapezoid'];a.obstacles=a.cfg['obstacles'];a.edit_mode=False;a.is_sleeping=False
a.char_x=a.char_y=0;a.char_x,a.char_y=a.clamp_to_walkable(650,650)
a.target_x,a.target_y=a.char_x,a.char_y;a.target_animation='idle';a.current_anim='idle';a.target_facing_left=None;a.pending_popup_modal=None;a.wander_timer=10;a.facing_left=False;a.anim_frame=0;a.anim_timer=0
a.load_scene_backgrounds=lambda:None;a.save_walkbox_config=lambda:None
for destination in ('resort_beach','apartment','cozy_study'):
    hops=a.request_scene_travel(destination);assert hops>=1
    visited=[scene_id(a.cfg)]
    for i in range(4000):
        a.update_autonomous_movement(1/30)
        assert a.floor_navigation().free((a.char_x,a.char_y))
        if scene_id(a.cfg)!=visited[-1]:visited.append(scene_id(a.cfg))
        if not a.scene_journey and not a.journey_arriving:break
    assert scene_id(a.cfg)==destination and not a.scene_journey and not a.journey_arriving,visited
    assert len(visited)==hops+1,visited
    print('Travelled:', ' -> '.join(visited))
assert a.cfg['interaction_spots']==cfg['interaction_spots'],'Study placements changed'
print('Both directions complete on real scene geometry; study placements preserved.')
pygame.quit()
