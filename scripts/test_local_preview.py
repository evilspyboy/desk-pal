import json,sys,tempfile,unittest,threading,time
from pathlib import Path
sys.path[:0]=[str(Path('src').resolve()),str(Path('scripts').resolve())]
from local_preview import PreviewBridge,PreviewDisplayPower
from run_local_preview import prepare_installation,ROOT
from backup_packages import export_backup
class PreviewTests(unittest.TestCase):
 def test_graphics_calls_execute_on_renderer_thread(self):
  bridge=PreviewBridge();result=[];renderer=threading.get_ident()
  worker=threading.Thread(target=lambda:result.append(bridge.call(threading.get_ident)));worker.start()
  deadline=time.monotonic()+2
  while bridge.calls.empty() and time.monotonic()<deadline:time.sleep(.001)
  bridge.tick_inputs(object());worker.join(2);self.assertEqual(result,[renderer])
 def test_inputs_are_validated_and_run_on_tick(self):
  bridge=PreviewBridge();calls=[]
  class App:
   def on_switch_pressed(self,n):calls.append(('button',n))
   def handle_touch_down(self,p):calls.append(('touch',p))
   def handle_touch_up(self):calls.append(('up',))
  bridge.enqueue({'kind':'switch','switch':2},1280,720);bridge.enqueue({'kind':'touch','x':10,'y':20},1280,720);self.assertEqual(calls,[]);bridge.tick_inputs(App());self.assertEqual(calls,[('button',2),('touch',(10,20)),('up',)])
  for command in ({'kind':'switch','switch':6},{'kind':'touch','x':1280,'y':2},{'kind':'touch','x':float('nan'),'y':2}):self.assertRaises(ValueError,bridge.enqueue,command,1280,720)
 def test_power_is_simulated(self):
  power=PreviewDisplayPower();power.set_sleeping(True);self.assertTrue(power.is_off);power.set_sleeping(False);self.assertFalse(power.is_off)
 def test_install_and_relaunch_preserve_local_settings(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);assets=root/'original/assets';assets.mkdir(parents=True);conf=root/'original/config';conf.mkdir();cfg={'active_scene':'study','active_character':'hero','scenes':{'study':{}},'characters':{'hero':{}},'animation_sequences':{},'apps':[{'id':'app','source_enabled':True,'monitor_health':True}]};backup=root/'backup.zip';backup.write_bytes(export_backup(cfg,assets,conf));original=backup.read_bytes();installation=root/'preview';prepare_installation(installation,backup);file=installation/'config/room_config.json';local=json.loads(file.read_text());self.assertFalse(local['apps'][0]['source_enabled']);self.assertFalse(local['apps'][0]['monitor_health']);local['edited']=True;file.write_text(json.dumps(local));prepare_installation(installation,backup);self.assertTrue(json.loads(file.read_text())['edited']);self.assertEqual(backup.read_bytes(),original)
 def test_repository_cannot_be_used_as_data_directory(self):self.assertRaises(ValueError,prepare_installation,ROOT)
if __name__=='__main__':unittest.main()
