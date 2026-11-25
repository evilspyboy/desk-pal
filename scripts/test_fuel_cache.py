import sys,tempfile,unittest,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path('src').resolve()))
from satellite_fueltracker import FuelTrackerSatellite
class CacheTest(unittest.TestCase):
 def test_changed_cheapest_station_at_same_price_is_one_real_update(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'state.json';agent=FuelTrackerSatellite(state_path=path)
   source={'last_poll_time':'first','last_predictions_time':'prediction','status':'healthy'};agent.source_status=lambda:source
   sent=[];agent.post_deskpal=lambda kind,payload:sent.append((kind,payload)) or True
   response={'query':{'fuel_id':8},'cheapest_station':{'price_cents':200,'name':'Station A'},'summary':'Current best station'}
   class Reply:
    def raise_for_status(self):pass
    def json(self):return copy.deepcopy(response)
   with patch('satellite_fueltracker.requests.get',return_value=Reply()):
    agent.check_status_and_relay()
    source['last_poll_time']='second';response['cheapest_station']['name']='Station B';agent.next_query=0
    agent.check_status_and_relay();agent.check_status_and_relay()
    events=[v for k,v in sent if k=='event'];self.assertEqual([v['event'] for v in events],['fuel_update']);self.assertEqual(events[0]['station'],'Station B')
    restarted=FuelTrackerSatellite(state_path=path);restarted.source_status=lambda:source;restarted.post_deskpal=agent.post_deskpal
    restarted.check_status_and_relay();self.assertEqual(len([v for k,v in sent if k=='event']),1)
    source['last_poll_time']='third';response['cheapest_station']={'price_cents':195,'name':'Station C'};restarted.next_query=0;restarted.check_status_and_relay()
    alert=[v for k,v in sent if k=='event'][-1];self.assertEqual(alert['event'],'fuel_drop');self.assertIn('Cheapest nearby fuel fell',alert['summary']);self.assertIn('Station C',alert['summary'])

 def test_cache_occurrences_and_restart(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'state.json';agent=FuelTrackerSatellite(state_path=path);source={'last_poll_time':'a','last_predictions_time':'p','status':'healthy'};agent.source_status=lambda:source
   sent=[];agent.post_deskpal=lambda kind,payload:sent.append((kind,payload)) or True
   response={'query':{'fuel_id':8},'cheapest_station':{'price_cents':200,'name':'Station'},'summary':'Actual price','forecast':{'trend':'stable'}}
   class Reply:
    def raise_for_status(self):pass
    def json(self):return copy.deepcopy(response)
   with patch('satellite_fueltracker.requests.get',return_value=Reply()) as get:
    agent.check_status_and_relay();agent.check_status_and_relay();self.assertEqual(get.call_count,1);self.assertFalse(any(k=='event' for k,v in sent))
    source['last_poll_time']='b';response['cheapest_station']['price_cents']=195;agent.next_query=0;agent.check_status_and_relay();self.assertEqual([v['event'] for k,v in sent if k=='event'],['fuel_drop'])
    restarted=FuelTrackerSatellite(state_path=path);restarted.source_status=lambda:source;restarted.post_deskpal=agent.post_deskpal;restarted.check_status_and_relay();self.assertEqual(get.call_count,2)
    source['last_predictions_time']='q';response['forecast']={'trend':'rising'};restarted.next_query=0;restarted.check_status_and_relay();self.assertEqual([v['event'] for k,v in sent if k=='event'],['fuel_drop','fuel_prediction'])
if __name__=='__main__':unittest.main()

