"""Foreground depth/collision checks plus real alpha-mask rendering when pygame is available."""
import ast,math,pathlib,sys,unittest,os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT']='1'
try:import pygame
except ImportError:pygame=None
candidates = [arg for arg in sys.argv[1:] if arg.endswith('.py') and not arg.startswith('-') and 'test_' not in arg]
source = pathlib.Path(candidates[0]) if candidates else pathlib.Path(__file__).resolve().parents[1]/'src/deskpal_app.py'
tree=ast.parse(source.read_text(encoding='utf-8'))
names={'obstacle_points','point_in_polygon','foreground_depth','foreground_outlines','clip_vector_region','vector_leg_regions','clip_floor_to_screen','FloorNavigation','DeskPalApp'}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names],type_ignores=[]),str(source),'exec'))

class ForegroundTests(unittest.TestCase):
 def test_two_leg_vectors_keep_the_far_thigh_above_its_own_knee(self):
  o=self.object();o['id']='chair';fg=o['foreground'];fg['seated_spot_ids']=['seat'];fg['seated_roles']=['seated_back'];fg['parts']=[dict(id='seat',outline=[[0,0],[100,0],[100,100],[0,100]],seated_layer='front')]
  guide=dict(object_id='chair',part_id='seat',legs=[dict(points=[[.3,.3],[.7,.4],[.8,.9]]),dict(points=[[.3,.4],[.4,.6],[.45,.9]])])
  for flip in [False,True]:
   parts=foreground_outlines([o],50,80,'seated_back','seat',(0,0,100,100,flip),guide)
   x=60 if flip else 40
   self.assertFalse(any(point_in_polygon((x,50),p) for p in parts))
   self.assertTrue(any(point_in_polygon((x,70),p) for p in parts))
 def test_placement_vector_is_surface_specific_and_flips(self):
  o=self.object();o['id']='chair';fg=o['foreground'];fg['seated_spot_ids']=['seat'];fg['seated_roles']=['seated_back'];fg['parts']=[dict(id='seat',outline=fg['outline'],seated_layer='front')]
  guide=dict(object_id='chair',part_id='seat',points=[[.3,.3],[.5,.5],[.7,.9]])
  for flip in [False,True]:
   parts=foreground_outlines([o],50,80,'seated_back','seat',(0,0,100,100,flip),guide)
   self.assertFalse(any(point_in_polygon((50,20),p) for p in parts))
   self.assertTrue(any(point_in_polygon((50,60),p) for p in parts))
  guide['object_id']='other'
  self.assertTrue(any(point_in_polygon((50,20),p) for p in foreground_outlines([o],50,80,'seated_back','seat',(0,0,100,100),guide)))
 def test_vector_can_target_an_ordinary_foreground_outline(self):
  o=self.object();guide=dict(object_id='rack',part_id='outline',points=[[.3,.3],[.5,.5],[.7,.9]])
  parts=foreground_outlines([o],50,80,'inspect','location',(0,0,100,100),guide)
  self.assertFalse(any(point_in_polygon((50,20),p) for p in parts))
  self.assertTrue(any(point_in_polygon((50,60),p) for p in parts))
 def test_seat_body_split_follows_sprite_position_and_scale(self):
  o=self.object();fg=o['foreground'];fg['seated_spot_ids']=['seat'];fg['seated_roles']=['seated_back'];fg['parts']=[dict(outline=fg['outline'],seated_layer='front',seated_body_front_until=.72)]
  for bounds,hip,boot in [((0,0,100,80),(50,50),(50,65)),((0,20,100,50),(50,50),(50,65))]:
   parts=foreground_outlines([o],50,80,'seated_back','seat',bounds)
   self.assertFalse(any(point_in_polygon(hip,p) for p in parts))
   self.assertTrue(any(point_in_polygon(boot,p) for p in parts))
 def test_seat_front_edge_covers_boots_but_keeps_hips_visible(self):
  o=self.object();fg=o['foreground'];fg['seated_spot_ids']=['seat'];fg['seated_roles']=['seated_back','seated_back_get_up']
  fg['parts']=[dict(id='seat',outline=fg['outline'],seated_layer='front',seated_clip_line=[[20,50],[80,30]])]
  seated=foreground_outlines([o],50,80,'seated_back','seat')
  self.assertFalse(any(point_in_polygon((50,30),p) for p in seated))
  self.assertTrue(any(point_in_polygon((50,60),p) for p in seated))
  self.assertEqual(seated,foreground_outlines([o],50,80,'seated_back_get_up','seat'))
  self.assertTrue(any(point_in_polygon((50,30),p) for p in foreground_outlines([o],50,80,'walk','seat')))
 def test_backrest_and_seat_are_independent(self):
  o=self.object();fg=o['foreground'];fg['seated_spot_ids']=['seat'];fg['seated_roles']=['seated_back','seated_back_get_up']
  fg['parts']=[dict(id='backrest',outline=[[20,0],[80,0],[80,35],[20,35]],seated_layer='front'),dict(id='seat',outline=[[20,35],[80,35],[80,70],[20,70]],seated_layer='behind')]
  seated=foreground_outlines([o],50,80,'seated_back','seat')
  self.assertTrue(any(point_in_polygon((50,20),p) for p in seated))
  self.assertFalse(any(point_in_polygon((50,50),p) for p in seated))
  self.assertEqual(seated,foreground_outlines([o],50,80,'seated_back_get_up','seat'))
  for role,spot in [('walk','seat'),('seated_back','other')]:
   self.assertTrue(any(point_in_polygon((50,50),p) for p in foreground_outlines([o],50,80,role,spot)))
 def object(self):return dict(id='rack',x=20,y=70,w=60,h=30,foreground=dict(outline=[[20,0],[80,0],[80,70],[20,70]]))
 def test_depth_and_override(self):
  o=self.object();self.assertEqual(len(foreground_outlines([o],50,80)),1);self.assertEqual(foreground_outlines([o],50,100),[])
  o['foreground']['depth_y']=120;self.assertEqual(len(foreground_outlines([o],50,110)),1)
 def test_disabled_hiding_retains_collision(self):
  o=self.object();o['foreground']['enabled']=False;self.assertEqual(foreground_outlines([o],50,80),[])
  nav=FloorNavigation(dict(back_x_min=0,back_x_max=200,front_x_min=0,front_x_max=200,y_min=0,y_max=200),[o]);self.assertFalse(nav.free((50,80)))
 def test_rotated_footprint_side_changes_depth(self):
  o=self.object();o['points']=[[45,20],[90,30],[55,100],[10,80]]
  self.assertAlmostEqual(foreground_depth(o,75),60)
  self.assertAlmostEqual(foreground_depth(o,30),80+20*20/45)
  parts=foreground_outlines([o],75,70)
  self.assertTrue(parts)
  self.assertTrue(all(p[0]<=70 for part in parts for p in part))
  self.assertEqual(foreground_outlines([o],75,105),[])
 def test_seated_frame_masks_are_specific_to_pose_and_placement(self):
  o=self.object();o['foreground']['placement_masks']={'seat':dict(roles=['seated_back','seated_back_get_up'],outlines=[[[20,0],[25,0],[25,70],[20,70]],[[75,0],[80,0],[80,70],[75,70]]])}
  seated=foreground_outlines([o],50,80,'seated_back','seat')
  self.assertFalse(any(point_in_polygon((50,30),p) for p in seated))
  self.assertTrue(any(point_in_polygon((22,30),p) for p in seated))
  for role,spot in [('walk','seat'),('seated_back','different_seat')]:self.assertTrue(any(point_in_polygon((50,30),p) for p in foreground_outlines([o],50,80,role,spot)))
  self.assertEqual(seated,foreground_outlines([o],50,80,'seated_back_get_up','seat'))
 @unittest.skipUnless(pygame,'pygame required for actual RGBA mask check')
 def test_angled_shelf_and_always_front(self):
  o=self.object();o['points']=[[20,40],[80,40],[80,120],[20,60]]
  app=DeskPalApp.__new__(DeskPalApp);app.obstacles=[o];app.char_x=10;app.char_y=90
  sprite=pygame.Surface((100,100),pygame.SRCALPHA);sprite.fill((40,80,120,255))
  result=app.foreground_sprite(sprite,0,0)
  self.assertEqual(result.get_at((30,30)).a,255);self.assertEqual(result.get_at((70,30)).a,0)
  app.char_y=130;self.assertIs(app.foreground_sprite(sprite,0,0),sprite)
  o['foreground']['mode']='always_front';result=app.foreground_sprite(sprite,0,0)
  self.assertEqual(result.get_at((30,30)).a,0);self.assertEqual(result.get_at((70,30)).a,0)
  self.assertEqual(sprite.get_at((70,30)).a,255)
 @unittest.skipUnless(pygame,'pygame required for actual RGBA mask check')
 def test_mask_pixels_overlap_and_cached_sprite_preserved(self):
  app=DeskPalApp.__new__(DeskPalApp);app.obstacles=[self.object(),self.object()];app.char_x=50;app.char_y=80
  sprite=pygame.Surface((100,100),pygame.SRCALPHA);sprite.fill((40,80,120,255))
  result=app.foreground_sprite(sprite,0,0);self.assertEqual(result.get_at((50,30)).a,0);self.assertEqual(result.get_at((5,30)).a,255);self.assertEqual(sprite.get_at((50,30)).a,255)
  app.char_y=100;self.assertIs(app.foreground_sprite(sprite,0,0),sprite)
  app.char_y=80;self.assertIs(app.foreground_sprite(sprite,300,300),sprite)

if __name__=='__main__':unittest.main()

