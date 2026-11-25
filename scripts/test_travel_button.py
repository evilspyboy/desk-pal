import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from satellite_travel import TravelRadarSatellite

class Button(unittest.TestCase):
 def test_true_threshold_and_entire_feed_not_only_first_four(self):
  agent=TravelRadarSatellite();sent=[];agent.post_deskpal=lambda kind,payload:sent.append((kind,payload)) or True
  deals=[{'destination':'Below','flightDeal':50.4,'flightNormal':100}]*4 + [{'destination':'Exactly','flightDeal':50,'flightNormal':100},{'destination':'Higher','flightDeal':40,'flightNormal':100}]
  with patch('satellite_travel.requests.get') as get:
   get.return_value.status_code=200;get.return_value.json.return_value={'opportunities':deals}
   agent.check_deals_and_relay()
   summary=sent[0][1]['button_summary']
   self.assertNotIn('Below',summary);self.assertIn('Exactly',summary);self.assertIn('Higher',summary)
   get.return_value.json.return_value={'opportunities':deals[:4]};sent.clear();agent.check_deals_and_relay()
   self.assertIn('No cached flights',sent[0][1]['button_summary'])
   get.return_value.json.return_value={'opportunities':[]};sent.clear();agent.check_deals_and_relay()
   self.assertIn('50% or more',sent[0][1]['button_summary'])
if __name__=='__main__':unittest.main()
