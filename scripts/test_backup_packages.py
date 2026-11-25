import sys,tempfile,json,zipfile,io,unittest
from pathlib import Path
sys.path.insert(0,str(Path('src').resolve()))
from backup_packages import export_backup,preview_backup,restore_backup,unpack
class BackupTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.assets=self.root/'assets';self.conf=self.root/'config';self.conf.mkdir();(self.assets/'themes/study').mkdir(parents=True);(self.assets/'themes/study/background.jpg').write_bytes(b'background');(self.assets/'characters').mkdir();(self.assets/'characters/frame.png').write_bytes(b'frame')
  self.cfg={'active_scene':'study','active_character':'hero','scenes':{'study':{}},'characters':{'hero':{}},'animation_sequences':{'idle':{'frames':['/assets/characters/frame.png']}},'apps':[{'id':'test','access_token':'private','actions':[]}],'value':'saved'}
 def tearDown(self):self.temp.cleanup()
 def test_roundtrip_and_local_secrets(self):
  data=export_backup(self.cfg,self.assets,self.conf);self.assertNotIn(b'private',unpack(data)[2]['config/room_config.json']);current=dict(self.cfg,value='different');review=preview_backup(data,current,self.assets,self.conf);self.assertEqual(review['missing'],[]);stored=[];result=restore_backup(data,current,self.assets,self.conf,stored.append,review['digest'],review['state_digest']);self.assertEqual(stored[0]['value'],'saved');self.assertEqual(stored[0]['apps'][0]['access_token'],'private');self.assertTrue((self.conf/'backups'/result['recovery_backup']).exists())
 def test_changed_preview_is_rejected(self):
  data=export_backup(self.cfg,self.assets,self.conf);review=preview_backup(data,self.cfg,self.assets,self.conf);(self.assets/'characters/frame.png').write_bytes(b'edited');self.assertRaises(ValueError,restore_backup,data,self.cfg,self.assets,self.conf,lambda c:None,review['digest'],review['state_digest'])
 def test_failed_apply_rolls_back_files(self):
  data=export_backup(self.cfg,self.assets,self.conf);frame=self.assets/'characters/frame.png';frame.write_bytes(b'edited');current=dict(self.cfg,value='different');review=preview_backup(data,current,self.assets,self.conf)
  def apply(c):
   if c['value']=='saved':raise ValueError('Rejected settings')
  self.assertRaises(ValueError,restore_backup,data,current,self.assets,self.conf,apply,review['digest'],review['state_digest']);self.assertEqual(frame.read_bytes(),b'edited')
 def test_unsafe_path_rejected(self):
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:z.writestr('../escape.py',b'bad')
  self.assertRaises(ValueError,unpack,out.getvalue())
if __name__=='__main__':unittest.main()
