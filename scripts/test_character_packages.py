import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path('src').resolve()))
from character_packages import export_character,preview_character,import_character,pack,read_package
class CharacterTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.assets=self.root/'assets';self.conf=self.root/'config';self.conf.mkdir();(self.assets/'characters/adventurer').mkdir(parents=True);(self.assets/'characters/adventurer/frame.png').write_bytes(b'art')
  self.url='/assets/characters/adventurer/frame.png';(self.conf/'sprite_tags.json').write_text(json.dumps({self.url:{'variant':'hero','skeleton':{'joints':{'head':[.5,.1]}}}}))
  self.cfg={'active_character':'hero','active_scene':'study','characters':{'hero':{'reference_sprite':{'url':self.url},'animations':{'walk':'walk'}}},'animation_sequences':{'walk':{'character':'hero','fps':4,'playback_mode':'ping_pong','frames':[{'url':self.url,'crop':[0,0,10,20]}]}},'scenes':{'study':{}},'apps':[{'id':'app'}],'scene_placements':{'study':{'edited':True}}}
  self.data=export_character(self.cfg,'hero',self.assets,self.conf)
 def tearDown(self):self.temp.cleanup()
 def review(self):return preview_character(self.data,self.cfg,self.assets,self.conf,'copy')
 def test_import_preserves_settings_and_remaps_content(self):
  review=self.review();self.assertEqual(review['missing'],[]);stored=[];import_character(self.data,self.cfg,self.assets,self.conf,stored.append,review['digest'],review['state_digest'],'copy');cfg=stored[0]
  for key in ('apps','scenes','scene_placements','active_character'):self.assertEqual(cfg[key],self.cfg[key])
  seq=cfg['animation_sequences'][cfg['characters']['copy']['animations']['walk']];self.assertEqual(seq['playback_mode'],'ping_pong');self.assertEqual(seq['frames'][0]['crop'],[0,0,10,20]);tags=json.loads((self.conf/'sprite_tags.json').read_text());self.assertEqual(tags[seq['frames'][0]['url']]['variant'],'copy');self.assertEqual(tags[self.url]['variant'],'hero')
 def test_stale_auxiliary_rejected(self):
  review=self.review();(self.conf/'sprite_tags.json').write_text('{}');self.assertRaises(ValueError,import_character,self.data,self.cfg,self.assets,self.conf,lambda cfg:None,review['digest'],review['state_digest'],'copy')
 def test_apply_failure_rolls_back_tags_and_art(self):
  review=self.review();old=(self.conf/'sprite_tags.json').read_bytes()
  def apply(cfg):
   if 'copy' in cfg['characters']:raise ValueError('reject')
  self.assertRaises(ValueError,import_character,self.data,self.cfg,self.assets,self.conf,apply,review['digest'],review['state_digest'],'copy');self.assertEqual((self.conf/'sprite_tags.json').read_bytes(),old);self.assertFalse((self.assets/'characters/adventurer/imported/copy/frame.png').exists())
 def test_foreign_frame_is_blocked(self):
  payload,files=read_package(self.data);payload['tags'][self.url]['variant']='other';bad=pack(payload,files);self.assertRaises(ValueError,preview_character,bad,self.cfg,self.assets,self.conf,'copy')
 def test_replacement_cannot_remove_roles(self):
  payload,files=read_package(self.data);payload['character']['animations']={};review=preview_character(pack(payload,files),self.cfg,self.assets,self.conf,'hero');self.assertTrue(review['missing'])
if __name__=='__main__':unittest.main()
