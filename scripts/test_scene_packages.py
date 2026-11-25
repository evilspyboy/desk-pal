import copy,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path('src').resolve()))
from scene_packages import export_scene,preview_scene,import_scene

class SceneTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.assets=self.root/'assets';self.conf=self.root/'config';self.conf.mkdir();(self.assets/'themes/study').mkdir(parents=True);(self.assets/'themes/study/background.jpg').write_bytes(b'background')
  self.cfg={'active_scene':'study','active_character':'hero','scenes':{'study':{'theme':'study','background':'background.jpg','interaction_spots':[{'id':'desk','animation':'typing'}],'props':[]}},'characters':{'hero':{'animations':{'typing':'type'}}},'animation_sequences':{'type':{}},'apps':[{'id':'app','actions':[]}],'scene_links':[]}
  self.data=export_scene(self.cfg,'study',self.assets)
 def tearDown(self):self.tmp.cleanup()
 def review(self,cfg=None):return preview_scene(self.data,cfg or self.cfg,self.assets,self.conf,'copy')
 def test_add_preserves_existing_settings(self):
  review=self.review();self.assertEqual(review['missing'],[]);stored=[];import_scene(self.data,self.cfg,self.assets,self.conf,stored.append,review['digest'],review['state_digest'],'copy');self.assertEqual(stored[0]['apps'],self.cfg['apps']);self.assertEqual(stored[0]['scenes']['study'],self.cfg['scenes']['study']);self.assertEqual(stored[0]['characters'],self.cfg['characters']);self.assertTrue((self.assets/'themes/imported_copy/background.jpg').exists())
 def test_missing_animation_blocks_import(self):
  cfg=copy.deepcopy(self.cfg);cfg['characters']['hero']['animations']={};self.assertTrue(self.review(cfg)['missing'])
 def test_stale_settings_rejected(self):
  review=self.review();cfg=dict(self.cfg,new_setting=True);self.assertRaises(ValueError,import_scene,self.data,cfg,self.assets,self.conf,lambda c:None,review['digest'],review['state_digest'],'copy')
 def test_failed_apply_removes_added_assets(self):
  review=self.review()
  def apply(cfg):
   if 'copy' in cfg['scenes']:raise ValueError('failure')
  self.assertRaises(ValueError,import_scene,self.data,self.cfg,self.assets,self.conf,apply,review['digest'],review['state_digest'],'copy');self.assertFalse((self.assets/'themes/imported_copy/background.jpg').exists())
if __name__=='__main__':unittest.main()
