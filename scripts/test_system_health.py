import sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from system_health import ConnectivityMonitor,update_notifications,settings,probe
from activity_queue import ActivityQueue

class Tests(unittest.TestCase):
 def test_debounce_and_recovery(self):
  samples=iter([False,False,False,True,False,True,True])
  monitor=ConnectivityMonitor(lambda:dict(reachable=next(samples),route_available=True))
  self.assertEqual(monitor.sample()['status'],'checking');self.assertEqual(monitor.sample()['status'],'checking')
  incident=monitor.sample()['incident'];self.assertTrue(incident)
  for _ in range(3):self.assertEqual(monitor.sample()['incident'],incident)
  self.assertEqual(monitor.sample()['status'],'online')
 def app(self,mode):
  m=ConnectivityMonitor();m.result.update(status='offline',incident='one',route_available=True)
  q=ActivityQueue();a=SimpleNamespace(cfg={'system_health':{'alert_mode':mode}},connectivity_monitor=m,activity_queue=q,integration_attention={},char_x=1,char_y=2,active_popup_modal=None)
  a.queue_action=lambda action,*args,**kwargs:q.enqueue((action,args[0],args[1],args[2],None,None))
  return a
 def test_no_duplicates_once_and_acknowledged(self):
  for mode in ('once','until_acknowledged'):
   a=self.app(mode);update_notifications(a);update_notifications(a);self.assertEqual(len(a.activity_queue.items),1)
   action=a.activity_queue.items.popleft()[0];self.assertEqual(action['attention_until_interaction'],mode!='once')
   update_notifications(a);self.assertEqual(len(a.activity_queue.items),0)
 def test_restored_mode_repeats_after_popup_only_and_recovery(self):
  a=self.app('until_restored')
  with patch('system_health.time.monotonic',return_value=0):update_notifications(a)
  a.activity_queue.items.clear();a.active_popup_modal={'title':'original'}
  with patch('system_health.time.monotonic',return_value=20):update_notifications(a)
  self.assertFalse(a.activity_queue.items);a.active_popup_modal=None
  with patch('system_health.time.monotonic',return_value=20):update_notifications(a)
  self.assertEqual(len(a.activity_queue.items),1)
  a.connectivity_monitor.result.update(status='online',incident=None);update_notifications(a)
  a.activity_queue.remove_suppressed(a);self.assertFalse(a.activity_queue.items)
 def test_disable_clears_only_health_incident(self):
  a=self.app('until_acknowledged');update_notifications(a)
  a.activity_queue.enqueue(({'id':'real'},'Fuel',None,'Original alert',None,None));a.integration_attention['fuel']='original'
  a.cfg['system_health']['enabled']=False;update_notifications(a);a.activity_queue.remove_suppressed(a)
  self.assertEqual(len(a.activity_queue.items),1);self.assertEqual(a.integration_attention,{'fuel':'original'})
 def test_settings_invalid(self):
  for cfg in ({'interval_seconds':0},{'interval_seconds':float('nan')},{'alert_mode':'bad'},{'enabled':'false'}):
   with self.assertRaises(ValueError):settings(cfg)
 def test_recovery_stops_active_warning_preserves_real_work(self):
  a=self.app('until_acknowledged');update_notifications(a)
  a.activity_queue.active=a.activity_queue.items.popleft()
  a.active_popup_modal={'title':'Pi connectivity'}
  a.activity_queue.enqueue(({'id':'real-order'},'Stores',None,'Real order',None,None))
  a.connectivity_monitor.result.update(status='online',incident=None)
  update_notifications(a);a.activity_queue.remove_suppressed(a)
  self.assertIsNone(a.activity_queue.active);self.assertIsNone(a.active_popup_modal)
  self.assertEqual(a.activity_queue.items[0][0]['id'],'real-order')
 def test_independent_endpoints(self):
  with patch('system_health.socket.create_connection',side_effect=[OSError(),SimpleNamespace(__enter__=lambda s:s,__exit__=lambda *a:None)]) as connect:
   # MagicMock supplies context-manager methods for the successful endpoint.
   from unittest.mock import MagicMock
   connect.side_effect=[OSError(),MagicMock()]
   self.assertTrue(probe()['reachable']);self.assertEqual(connect.call_count,2)
if __name__=='__main__':unittest.main()
