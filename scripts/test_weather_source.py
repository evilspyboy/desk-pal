import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from weather_source import WeatherSource, ensure_weather_source, forecast, validate_weather
from morning_greeting import message, settings
from datetime import datetime

class WeatherTests(unittest.TestCase):
    def test_install_once_and_delete_is_respected(self):
        cfg={};ensure_weather_source(cfg);ensure_weather_source(cfg)
        self.assertEqual(len(cfg['apps']),1)
        cfg['apps']=[];ensure_weather_source(cfg);self.assertEqual(cfg['apps'],[])

    def test_daily_payload_and_units(self):
        data,text=forecast({'daily':{'time':['2026-10-12'],'temperature_2m_min':[15],
            'temperature_2m_max':[27],'precipitation_probability_max':[80],'wind_speed_10m_max':[30],'uv_index_max':[9]}})
        self.assertIn('15–27°C',text);self.assertIn('Rain 80%',text);self.assertEqual(data['time'],'2026-10-12')
        with self.assertRaises(ValueError):forecast({'daily':{}})

    def test_changed_forecast_emits_once_and_polling_is_bounded(self):
        cfg={};ensure_weather_source(cfg);source=cfg['apps'][0]
        receipts=[];events=[];tele={};worker=WeatherSource()
        app=SimpleNamespace(apps=cfg['apps'],cfg=cfg,app_telemetry=tele,receive_heartbeat=lambda h:receipts.append(h))
        def event(e):
            events.append(e);tele[source['id']]={'received_events':{'forecast_updated':{'data':e}}}
        app.receive_telemetry_event=event
        worker.signature=(source['id'],True,'{}');worker.next_poll=1e30
        result={'forecast':({'time':'2026-10-12','temperature_2m_min':15},'Test forecast')}
        worker.results.put((worker.signature,result));worker.tick(app)
        worker.results.put((worker.signature,result));worker.tick(app)
        self.assertEqual(len(receipts),2);self.assertEqual(len(events),1)
        source['poll_seconds']=1
        with self.assertRaises(ValueError):validate_weather(cfg)

    def test_configurable_greeting_and_wrong_day_weather(self):
        app=SimpleNamespace(apps=[{'id':'weather','adapter':'weather','name':'Weather'},{'id':'mail','name':'Mail'}],
            app_telemetry={'weather':{'received_events':{'heartbeat':{'data':{'time':'2026-10-12','summary':'Sunny'}}}},
            'mail':{'received_events':{'checked':{'data':{'counts':{'new':3}}}}}})
        options=settings({'sections':[{'app_id':'weather'},{'app_id':'mail','event':'checked','field':'counts.new'}]})
        text=message(app,options,datetime(2026,10,12,7));self.assertIn('Weather: Sunny',text);self.assertIn('Mail: 3',text)
        self.assertIn('unavailable',message(app,options,datetime(2026,10,13,7)))
        self.assertEqual(message(app,settings({'sections':[]}),datetime(2026,10,12,7)),'Good morning!\nMon 12 Oct')

if __name__=='__main__':unittest.main()
