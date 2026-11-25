import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path('src').resolve()))
from integration_packages import export_integration,preview_integration,import_integration
class IntegrationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.conf=self.root/'config';self.conf.mkdir();self.assets=self.root/'assets';self.assets.mkdir()
  self.app={'id':'demo','name':'Demo','source_url':'http://private-address.local','source_enabled':True,'monitor_health':True,'switch_id':3,'settings':{'api_key':'private-secret'},'adapter':'json','poll_seconds':1800,'integration_events':[{'name':'done','example':{'api_key':'private-secret','summary':'personal payload','value':95}}],'actions':[{'id':'button','is_primary':True,'event':'status_check','scene':'study','animation':'typing','spot_id':'desk','target_mode':'specific','speech':'private message','conditions':[{'field':'price','op':'lt','value':80}]}]}
  self.cfg={'active_scene':'study','active_character':'hero','characters':{'hero':{'animations':{'typing':'type'}}},'animation_sequences':{'type':{}},'scenes':{'study':{'interaction_spots':[{'id':'desk','animation':'typing'}]}},'apps':[self.app,{'id':'other','settings':{'token':'keep'}}]};self.data=export_integration(self.cfg,'demo')
 def tearDown(self):self.temp.cleanup()
 def test_export_redacts_private_data(self):
  for text in (b'private-address',b'private-secret',b'personal payload',b'private message',b'switch_id'):self.assertNotIn(text,self.data)
  package=json.loads(self.data);self.assertEqual(package['application']['poll_seconds'],1800);self.assertEqual(package['events'][0]['example']['value'],0)
 def test_add_disconnected_and_preserve_others(self):
  review=preview_integration(self.data,self.cfg,'copy',True);self.assertEqual(review['missing'],[]);stored=[];import_integration(self.data,self.cfg,self.assets,self.conf,stored.append,review['digest'],review['state_digest'],'copy',True);cfg=stored[0];self.assertEqual(cfg['scenes'],self.cfg['scenes']);self.assertEqual(cfg['apps'][:2],self.cfg['apps']);app=cfg['apps'][2];self.assertFalse(app['source_enabled']);self.assertEqual(app['switch_id'],0);self.assertFalse(app['monitor_health'])
 def test_replace_preserves_local_settings(self):
  review=preview_integration(self.data,self.cfg,None,True);stored=[];import_integration(self.data,self.cfg,self.assets,self.conf,stored.append,review['digest'],review['state_digest'],None,True);app=stored[0]['apps'][0]
  for key in ('source_url','source_enabled','settings','switch_id','monitor_health'):self.assertEqual(app[key],self.app[key])
 def test_events_only_bypasses_missing_mapping_and_keeps_actions(self):
  cfg=copy.deepcopy(self.cfg);cfg['scenes']={};self.assertTrue(preview_integration(self.data,cfg,None,True)['missing']);review=preview_integration(self.data,cfg,None,False);self.assertEqual(review['missing'],[])
 def test_stale_settings_rejected(self):
  review=preview_integration(self.data,self.cfg,'copy');cfg=dict(self.cfg,changed=True);self.assertRaises(ValueError,import_integration,self.data,cfg,self.assets,self.conf,lambda c:None,review['digest'],review['state_digest'],'copy')
 def test_apply_failure_rolls_back(self):
  review=preview_integration(self.data,self.cfg,'copy');calls=[]
  def apply(cfg):
   calls.append(cfg)
   if len(cfg['apps'])>2:raise ValueError('fail')
  self.assertRaises(ValueError,import_integration,self.data,self.cfg,self.assets,self.conf,apply,review['digest'],review['state_digest'],'copy');self.assertEqual(calls[-1],self.cfg)
 def test_legacy_definition_populates_events(self):
  data=Path('examples/integration.example.json').read_bytes();review=preview_integration(data,self.cfg);self.assertEqual(len(review['events']),3);self.assertEqual(review['mode'],'add');self.assertEqual(review['missing'],[])
if __name__=='__main__':unittest.main()
