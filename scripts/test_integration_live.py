from pathlib import Path
import copy
import os,sys,json,tempfile,importlib.util
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
spec=importlib.util.spec_from_file_location('integration_app',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
from activity_queue import ActivityQueue
from integration_state import load_telemetry
with tempfile.TemporaryDirectory() as tmp:
 a=m.DeskPalApp.__new__(m.DeskPalApp);a.telemetry_path=str(Path(tmp)/'state.json');a.app_telemetry={};a.activity_queue=ActivityQueue();a.event_mappings=[];a.attention_seen={};a.integration_attention={};a.char_x=500;a.char_y=500
 a.apps=[{'id':'custom_app','name':'Custom','actions':[{'id':'ordinary','event':'*','animation':'inspect'},{'id':'cheap','event':'price','conditions':[{'field':'price','op':'lt','value':170}],'attention_needed':True,'animation':'wave_arms'}]}]
 a.receive_telemetry_event({'app_id':'custom_app','event':'price','price':160,'summary':'A real cheap price'})
 items=list(a.activity_queue.items);assert items[0][0]['id']=='cheap';assert items[1][0]['animation']=='wave_arms';assert a.integration_attention['custom_app']=='A real cheap price'
 assert items[0][0]['source_event']=='price'
 assert load_telemetry(a.telemetry_path)['custom_app']['summary']=='A real cheap price'
 a.receive_heartbeat({'app_id':'another_app','summary':'Ready','status':'healthy','ttl_seconds':600})
 assert load_telemetry(a.telemetry_path)['another_app']['ttl_seconds']==600
 a.apps.append({'id':'routine','name':'Routine','actions':[{'id':'status_check','animation':'inspect','display_mode':'popup_modal','speech':'{summary}'}]})
 a.receive_heartbeat({'app_id':'routine','status':'healthy','summary':'Real routine update'})
 queued=list(a.activity_queue.items)[-1];assert queued[1]=='Routine' and queued[0]['display_mode']=='none' and queued[0]['speech']==''
 assert queued[0]['source_event']=='heartbeat'
 a.apps.append({'id':'custom_travel','adapter':'travel_radar','suppress_duplicate_events':{'heartbeat':True},'name':'Travel','actions':[{'id':'status_check','animation':'inspect'}]})
 hb={'app_id':'custom_travel','status':'healthy','summary':'Same deals'}
 a.receive_heartbeat(hb);count=len(a.activity_queue.items);a.receive_heartbeat(hb);assert len(a.activity_queue.items)==count
 a.receive_heartbeat(dict(hb,summary='Changed deals'));assert len(a.activity_queue.items)==count+1
 ev={'app_id':'custom_travel','event':'flight_anomaly','summary':'A deal'}
 a.receive_telemetry_event(ev);count=len(a.activity_queue.items);a.receive_telemetry_event(ev);assert len(a.activity_queue.items)==count
 assert a.app_telemetry['custom_app']['received_events']['price']['data']['price']==160
 a.apps.append({'id':'muted','name':'Muted','suppressed_events':{'price':True,'heartbeat':True},'actions':[{'id':'status_check','animation':'inspect'},{'id':'price','event':'price','animation':'wave_arms','attention_needed':True}]})
 count=len(a.activity_queue.items)
 a.receive_telemetry_event({'app_id':'muted','event':'price','price':1,'summary':'Muted price','attention_needed':True})
 a.receive_heartbeat({'app_id':'muted','status':'error','summary':'Muted heartbeat'})
 assert len(a.activity_queue.items)==count and 'muted' not in a.integration_attention
 assert load_telemetry(a.telemetry_path)['muted']['received_events']['price']['count']==1
 a.integration_health_attention={'muted':'Stopped feed'};a.integration_attention['muted']='Stopped feed'
 a.receive_heartbeat({'app_id':'muted','status':'healthy','summary':'Suppressed but fresh'})
 assert 'muted' not in a.integration_attention
 a.apps[-1]['suppressed_events']['price']=False
 a.receive_telemetry_event({'app_id':'muted','event':'price','price':2,'summary':'Resumed price'})
 assert len(a.activity_queue.items)>count
 print('Live app methods persist event/heartbeat state, select matching value conditions, queue actions and retain attention details.')

# Saving only application settings must preserve the active trip and its target.
a=m.DeskPalApp.__new__(m.DeskPalApp)
a.cfg=m.load_config();m.ensure_world(a.cfg);m.sync_scene(a.cfg)
a.walk_frames=[];a.walk_fps=4;a.walk_ping_pong=False
a.configure_character=lambda cfg:None
a._init_fonts=lambda scale:setattr(a,'ui_font_scale',scale)
a.save_walkbox_config=lambda:None
a.char_x=500;a.char_y=500;a.target_x=700;a.target_y=600
a.scene_journey=['existing trip'];a.journey_arriving=True;a.status_msg='Real update'
apps=copy.deepcopy(a.cfg.get('apps',[]))
m.DeskPalApp.apply_remote_config(a,{'apps':apps})
assert a.scene_journey==['existing trip'] and a.journey_arriving
assert (a.target_x,a.target_y)==(700,600) and a.status_msg=='Real update'
m.DeskPalApp.apply_remote_config(a,copy.deepcopy(a.cfg))
assert a.scene_journey==['existing trip'] and (a.target_x,a.target_y)==(700,600)
print('Application-only and unchanged full-config saves preserve active travel and its target.')
# A broken first connection must not hide a valid alternative to the same scene.
trap={'points':[[0,0],[1280,0],[1280,720],[0,720]]}
start={'walkable_trapezoid':trap,'obstacles':[],'portals':[{'id':'exit','x':100,'y':100,'inside_x':120,'inside_y':100}]}
end={'walkable_trapezoid':trap,'obstacles':[],'portals':[{'id':'bad','x':-20,'y':100,'inside_x':20,'inside_y':100},{'id':'good','x':100,'y':100,'inside_x':120,'inside_y':100}]}
a=m.DeskPalApp.__new__(m.DeskPalApp);a.cfg={'active_scene':'start','scenes':{'start':start,'end':end},'walkable_trapezoid':trap,'obstacles':[],'scene_links':[{'a':{'scene':'start','portal':'exit'},'b':{'scene':'end','portal':'bad'}},{'a':{'scene':'start','portal':'exit'},'b':{'scene':'end','portal':'good'}}]};a.is_sleeping=False;a.scene_journey=[];a.char_x=200;a.char_y=200;a.target_next_portal=lambda:None
assert a.request_scene_travel('end')==1 and a.scene_journey[0]['to']['portal']=='good'
a.cfg['scene_links']=a.cfg['scene_links'][:1];a.scene_journey=[];a.pending_post_travel_action=None
try:a.trigger_action({'scene':'end','animation':'inspect'})
except ValueError:pass
else:raise AssertionError('Unreachable reaction must fail instead of playing in the current scene')
assert a.pending_post_travel_action is None
print('Scene travel uses valid alternatives and rejects unreachable mapped reactions.')
