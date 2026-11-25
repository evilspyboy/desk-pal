import sys,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path('src').resolve()))
from satellite_travel import TravelRadarSatellite
with tempfile.TemporaryDirectory() as tmp:
 path=Path(tmp)/'travel.json';deal={'id':'same-id','destination':'Test','flightDeal':50,'flightNormal':100,'dates':'test'};sent=[]
 def send(kind,payload):sent.append(kind);return True
 with patch('satellite_travel.requests.get') as get:
  get.return_value.status_code=200;get.return_value.json.side_effect=lambda:{'opportunities':[deal]}
  a=TravelRadarSatellite(state_path=path);a.post_deskpal=send;a.check_deals_and_relay();assert sent==['heartbeat']
  deal['flightDeal']=40;a.check_deals_and_relay();assert sent.count('event')==1
  b=TravelRadarSatellite(state_path=path);b.post_deskpal=send;b.check_deals_and_relay();assert sent.count('event')==1
  deal['flightDeal']=30;b.post_deskpal=lambda *args:False;b.check_deals_and_relay();b.post_deskpal=send;b.check_deals_and_relay();assert sent.count('event')==2
print('Travel baselines existing deals, persists delivered changes across restarts, and retries failed delivery.')
