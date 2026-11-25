// Generic application setup and received-event mapping. No producer scripts run in the editor.
let appStudioSection='connection',integrationTelemetry={},integrationQueue={},integrationHistory=[],integrationMappingStatus={},integrationNew=false;
function integrationNode(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function integrationButton(text,fn){const b=integrationNode('button',text,'btn');b.onclick=fn;return b;}
function integrationField(card,label,node){const row=integrationNode('label',label+' ');row.style.cssText='display:flex;flex-direction:column;gap:5px;margin:10px 0';row.append(node);card.append(row);return node;}
function integrationInput(value,fn,type='text'){const n=document.createElement('input');n.type=type;n.value=value??'';n.onchange=()=>fn(n.value);return n;}
function integrationSelect(options,value,fn){const n=document.createElement('select');n.replaceChildren(...options.map(([v,label])=>new Option(label,v)));n.value=value;n.onchange=()=>fn(n.value);return n;}
async function refreshIntegrationStatus(){try{
 const replies=await Promise.all(['/api/telemetry','/api/activity_queue','/api/activity_history?heartbeat_receipts=0','/api/integrations/mapping_status'].map(url=>fetch(url)));
 if(replies.some(r=>!r.ok))throw Error('Cannot read live integration status');
 [integrationTelemetry,integrationQueue,integrationHistory,integrationMappingStatus]=await Promise.all(replies.map(r=>r.json()));
 if(appStudioModal.style.display!=='none')renderAppStudio();
}catch(e){const status=document.getElementById('integrationLiveStatus')||document.getElementById('statusMsg');if(status)status.textContent=e.message;}}
function integrationEventMappings(app,name){
 let normal=app.heartbeat_action_id??'__primary__';if(normal==='__primary__')normal=(app.actions||[]).find(a=>a.is_primary||a.id==='status_check')?.id;
 return (app.actions||[]).filter(a=>a.event===name||a.id===name||name==='heartbeat'&&a.id===normal);
}
function integrationEventGroups(app){
 const groups=new Map();
 for(const definition of integrationDefinitions(app)){
  const mappings=integrationEventMappings(app,definition.name),scenes=mappings.length?[...new Set(mappings.map(actionSceneId))]:[''];
  for(const scene of scenes){if(!groups.has(scene))groups.set(scene,[]);groups.get(scene).push({definition,mappings:mappings.filter(a=>actionSceneId(a)===scene)});}
 }
 return [...groups].sort(([a],[b])=>a?(b?(config.scenes?.[a]?.name||a).localeCompare(config.scenes?.[b]?.name||b):-1):1);
}
function integrationMappingSignature(action){return ['scene','target_scene','animation','spot_id','target_mode','x','y'].map(k=>action[k]??null);}
function integrationMappingCheck(app,action){
 const scene=actionSceneId(action),room=config.scenes?.[scene];if(!room)return {ok:false,reason:'Scene is missing'};
 if(room.enabled===false)return {ok:false,reason:'Scene is disabled'};
 const catalog=actionPoseCatalog(action),mode=action.target_mode||'specific';
 if(!['any','location'].includes(mode)&&!catalog[action.animation==='idle_side'?'idle':action.animation])return {ok:false,reason:'Character animation is missing'};
 if(['specific','location'].includes(mode)&&action.spot_id&&!(room.interaction_spots||[]).some(s=>s.id===action.spot_id))return {ok:false,reason:'Saved placement is missing'};
 const checked=integrationMappingStatus[app.id]?.[action.id];
 return checked&&JSON.stringify(checked.signature)===JSON.stringify(integrationMappingSignature(action))?checked:{ok:null,reason:'Save changes, then refresh live status to check the route'};
}
function integrationLastPlayback(app,action,event){
 const latest=[...integrationHistory].reverse().find(r=>['arrived','completed','failed'].includes(r.event)&&(r.app===app.id||r.app===app.name)&&r.source_event===event&&r.action===action.id);
 if(!latest)return null;
 const arrival=latest.activity_id&&integrationHistory.find(r=>r.event==='arrived'&&r.activity_id===latest.activity_id);
 return {...arrival,...latest,animation:latest.animation||arrival?.animation};
}
function integrationTimeAgo(timestamp){if(!timestamp)return 'Never received';const seconds=Math.max(0,Math.floor(Date.now()/1000-timestamp));return seconds<60?seconds+'s ago':seconds<3600?Math.floor(seconds/60)+'m ago':Math.floor(seconds/3600)+'h ago';}
function integrationQueuePhase(q){const phase={waiting_for_event:'Looping until the next event',waiting_for_interaction:'Attention — tap the sprite or press its application button',waiting_for_dismissal:'Button popup open — dismiss it to resume',travelling:'Travelling to reaction',playing:'Playing reaction',idle:'Idle'}[q.state]||'Idle';return q.paused?'Queue paused: '+(q.pause_reason==='sleep'?'screen asleep':'editor open'):phase;}
const integrationEventFilterState=new WeakMap();
function integrationFilteredEventGroups(app,state={}){
 const query=(state.query||'').trim().toLowerCase();
 return integrationEventGroups(app).filter(([scene])=>!state.scene||state.scene===scene).map(([scene,entries])=>[scene,entries.filter(({definition,mappings})=>{
  if(state.showSuppressed===false&&app.suppressed_events?.[definition.name]===true)return false;
  return !query||[definition.name,definition.label,config.scenes?.[scene]?.name,...mappings.flatMap(a=>[a.label,a.id,a.animation,a.spot_id])].filter(Boolean).join(' ').toLowerCase().includes(query);
 })]).filter(([,entries])=>entries.length);
}
function integrationPlacementPreview(action){
 const button=integrationButton('',()=>{selectedActionId=selectedActionId===action.id?'':action.id;redrawIntegrationEventPane();});button.title='Edit this scene and animation mapping';button.style.cssText='padding:0;border-radius:6px;overflow:hidden;width:180px;max-width:100%;flex-shrink:0';
 const canvas=document.createElement('canvas');canvas.width=480;canvas.height=270;canvas.style.cssText='width:100%;display:block;aspect-ratio:16/9';button.append(canvas);
 const ctx=canvas.getContext('2d'),sid=actionSceneId(action),room=actionSceneData(action),catalog=actionPoseCatalog(action),mode=action.target_mode||'specific';
 let placements=integrationPlacements(action).filter(p=>(mode!=='specific'&&mode!=='location'||!action.spot_id||p.spot.id===action.spot_id)&&(mode==='any'||mode==='location'||p.role===action.animation||(action.animation==='idle_side'&&p.role==='idle')));
 if(mode==='specific'&&!placements.length){const spot=(room.interaction_spots||[]).find(s=>s.id===action.spot_id)||{x:action.x,y:action.y};if(Number.isFinite(spot.x)&&Number.isFinite(spot.y)&&catalog[action.animation])placements=[{spot,role:action.animation}];}
 if(mode==='current'&&catalog[action.animation])placements=[{role:action.animation,spot:{x:640,y:600,facing:action.facing||'right'}}];
 const background=new Image(),images=new Map();
 const draw=()=>{ctx.fillStyle='#151321';ctx.fillRect(0,0,480,270);if(background.complete&&background.naturalWidth)ctx.drawImage(background,0,0,480,270);ctx.save();ctx.scale(480/1280,270/720);
  for(const p of placements){const frame=catalog[p.role],image=images.get(p);if(!frame)continue;const crop=frame.crop||[0,0,image?.naturalWidth||360,image?.naturalHeight||560];let h=floorPerspectiveHeight(room.walkable_trapezoid||config.walkable_trapezoid,p.spot.y);if(frame.reference_height)h*=crop[3]/frame.reference_height;const w=h*crop[2]/crop[3];
   if(image?.complete&&image.naturalWidth){ctx.save();ctx.translate(p.spot.x,p.spot.y-h);if(p.spot.facing==='left')ctx.scale(-1,1);ctx.drawImage(image,...crop,-w/2,0,w,h);ctx.restore();}
   ctx.strokeStyle='#00e5ff';ctx.lineWidth=5;ctx.beginPath();ctx.ellipse(p.spot.x,p.spot.y,22,10,0,0,Math.PI*2);ctx.stroke();
  }ctx.restore();};
 background.onload=draw;background.src='/assets/themes/'+encodeURIComponent(room.theme||sid)+'/'+encodeURIComponent(room.background||'background.jpg');
 for(const p of placements){const image=new Image();images.set(p,image);image.onload=draw;image.src=catalog[p.role].url;}draw();return button;
}

function prepareIntegrationPane(pane,app){
 if(integrationNew){renderNewIntegration(pane);return true;}
 const header=integrationNode('div',undefined,'editor-card');const title=integrationNode('h3',app.name||app.id);title.style.margin='0';header.append(title);
 const nav=integrationNode('div');nav.style.cssText='display:flex;gap:8px;flex-wrap:wrap;margin:12px 0';
 for(const [id,title]of (app.built_in==='sensors'?[['connection','1 · Sensor triggers'],['events','2 · Events & mappings']]:app.kind==='game'?[['connection','1 · 🎮 Game & Controls'],['events','2 · Events & mappings']]:[['connection','1 · Connection'],['events','2 · Events & mappings'],['button','3 · Physical button'],['dashboard','4 · 📊 5" Dashboard Modal']])){const b=integrationButton(title,()=>{appStudioSection=id;if(id==='events'||id==='dashboard')selectedActionId='';renderActionPane();});if(id===appStudioSection)b.classList.add('btn-primary');nav.append(b);}header.append(nav);
 const q=integrationQueue;header.append(integrationNode('small',integrationQueuePhase(q)+(q.active?' · '+q.active.app+' / '+q.active.action:'')+' · '+(q.pending?.length||0)+' waiting','integration-queue'));
 if(q.pending?.length){const waiting=document.createElement('details');waiting.append(integrationNode('summary','Waiting reactions (in playback order)'));const list=integrationNode('ol');for(const item of q.pending)list.append(integrationNode('li',item.app+' · '+(item.event||item.action)+(item.scene?' → '+(config.scenes?.[item.scene]?.name||item.scene):'')+(item.button?' · button priority':'')));waiting.append(list);header.append(waiting);} 
 if(q.last_error)header.append(integrationNode('p','Last action issue: '+q.last_error));
 const tools=integrationNode('div');tools.style.cssText='display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:8px';const refresh=integrationButton('Refresh live status',refreshIntegrationStatus);refresh.style.width='auto';tools.append(refresh);
 const logs=document.createElement('details');logs.append(integrationNode('summary','History & application ID'));logs.append(integrationNode('small','Application ID: '+app.id));const history=integrationNode('a','Download reactions & named events','btn');history.href='/api/activity_history?heartbeat_receipts=0';history.download='deskpal-reactions.json';logs.append(history);const fullHistory=integrationNode('a','Full history including heartbeats','btn');fullHistory.href='/api/activity_history';fullHistory.download='deskpal-activity-history.json';logs.append(fullHistory);tools.append(logs);header.append(tools);pane.append(header);
 if(appStudioSection==='connection'){if(app.built_in==='sensors')renderSensorSettings(pane,app);else if(app.kind==='game')renderGameSettings(pane,app);else renderIntegrationConnection(pane,app);return true;}
 if(appStudioSection==='events'){renderIntegrationEvents(pane,app);return true;}
 if(appStudioSection==='dashboard'){renderDashboardStudioTab(pane,app);return true;}
 renderIntegrationButton(pane,app);return true;
}
function renderSensorSettings(pane,app){
 const card=integrationNode('div',undefined,'editor-card');card.append(integrationNode('h3','Sensor triggers'));
 card.append(integrationNode('p','Enable hardware readers and calibrate mounting on the Hardware page first. Triggers use calibrated motion, fire on changes, and return to normal queued activity. No source URL, polling script or physical button is needed.'));
 const s=app.sensor_settings||={};integrationToggle(card,'Enable sensor reactions',!!s.enabled,v=>s.enabled=v);
 const link=integrationNode('a','Open Hardware calibration','btn');link.href='/hardware';link.target='_blank';card.append(link);
 for(const [key,label,def,min,max]of [['mild_degrees','Mild tilt (degrees)',12,3,60],['strong_degrees','Strong tilt (degrees)',28,5,85],['cooldown_seconds','Reaction cooldown (seconds)',.5,.5,120],['shake_g','Shake acceleration above/below normal gravity (g)',.45,.15,3]]){const input=integrationInput(s[key]??def,v=>s[key]=Math.max(min,Math.min(max,Number(v)||def)),'number');input.min=min;input.max=max;input.step=key==='shake_g'?.05:key==='cooldown_seconds'?.5:1;integrationField(card,label,input);}
 integrationToggle(card,'Enable person-returned greeting (radar)',!!s.presence_enabled,v=>s.presence_enabled=v);
 integrationField(card,'No person seen for at least (seconds)',integrationInput(s.absence_seconds??60,v=>s.absence_seconds=Math.max(5,Number(v)||60),'number'));
 card.append(integrationNode('small','Presence means a radar return, not a recognised person. False reflections may cause greetings. Calibration captures do not fire reactions; motion while sleeping or editing is not queued.'));

 const morning=config.morning_greeting||={enabled:false,start:'06:00',end:'10:00',fuel_app_id:''};
 card.append(integrationNode('h3','Morning greeting'));
 integrationToggle(card,'Greet once after sleep when radar sees someone',!!morning.enabled,v=>morning.enabled=v);
 integrationField(card,'Morning begins',integrationInput(morning.start||'06:00',v=>morning.start=v,'time'));
 integrationField(card,'Do not greet at or after',integrationInput(morning.end||'10:00',v=>morning.end=v,'time'));
 if(!Array.isArray(morning.sections)){const fuel=(config.apps||[]).find(a=>morning.fuel_app_id?a.id===morning.fuel_app_id:a.adapter==='fuel_tracker');morning.sections=fuel?[{app_id:fuel.id,event:'heartbeat',field:'summary'}]:[];}
 card.append(integrationNode('h4','Include in the morning briefing'));
 for(const source of (config.apps||[]).filter(a=>a.built_in!=='sensors')){
  const row=integrationNode('div',undefined,'editor-card');let section=morning.sections.find(s=>s.app_id===source.id);
  integrationToggle(row,source.name||source.id,!!section,v=>{if(v)morning.sections.push({app_id:source.id,event:'heartbeat',field:'summary'});else morning.sections=morning.sections.filter(s=>s.app_id!==source.id);renderActionPane();});
  if(section){integrationField(row,'Information from',integrationSelect(integrationDefinitions(source).map(d=>[d.name,d.label||d.name]),section.event||'heartbeat',v=>section.event=v));integrationField(row,'Information field',integrationInput(section.field||'summary',v=>section.field=v.trim()||'summary'));row.append(integrationNode('small','Use summary for readable text, or a JSON field path from the selected event. Fuel summary uses the current cached price.'));}
  card.append(row);
 }
 card.append(integrationNode('small','Uses the latest received information from the selected applications, with the scene lighting timezone. After sleep, one second of fresh radar presence can wake the display and show a greeting popup. Once per morning, never after the cutoff.'));
 card.append(integrationButton('Save sensor settings',saveConfigToPi),integrationButton('Choose reactions',()=>{appStudioSection='events';selectedActionId='';renderActionPane();}));pane.append(card);
}
function renderGameSettings(pane,app){
 const card=integrationNode('div',undefined,'editor-card');
 card.append(integrationNode('h3','🎮 Game & Controller Configuration'));
 card.append(integrationNode('p','Configure input schemes, cabinet bezels, and hardware switch overrides. When playing this mini-game, mapped switches control gameplay without triggering normal background application actions.'));
 integrationField(card,'Display name',integrationInput(app.name,v=>{app.name=v;renderAppList();}));
 const s=app.settings||={};
 s.controller||='buttons';
 s.bezel||='crt_monitor';
 s.on_screen_buttons||='auto';
 s.switch_left=Number(s.switch_left)||2;
 s.switch_right=Number(s.switch_right)||3;
 s.switch_action=Number(s.switch_action)||4;
 s.switch_exit=Number(s.switch_exit)||5;
 integrationField(card,'Input Controller Scheme',integrationSelect([
  ['buttons','Buttons (Physical Switches & On-Screen Touch)'],
  ['imu','MPU-6050 Accelerometer Tilt (Physical Case Tilt)'],
  ['radar','RD-03D Millimeter-Wave Radar (Lateral Body Position)'],
  ['touch','Direct Touchscreen Drag / Screen Only'],
  ['keyboard','Keyboard Only (Desktop Preview)'],
  ['auto','Auto (All Connected Hardware Active)']
 ],s.controller,v=>s.controller=v));
 integrationField(card,'Overlay Bezel / Frame Style',integrationSelect([
  ['crt_monitor','📺 1990s CRT Computer Monitor (Study Computer)'],
  ['arcade_cabinet','🕹️ Retro Arcade Cabinet (Video Store)'],
  ['handheld','📱 Handheld Console'],
  ['minimal','🔲 Minimal Frameless Window']
 ],s.bezel,v=>s.bezel=v));
 integrationField(card,'On-Screen Touch Buttons (◄, ►, ▲)',integrationSelect([
  ['auto','Auto (Show on touch / desktop preview)'],
  ['always','Always Show On-Screen Buttons'],
  ['never','Never Show (Physical Buttons Only)']
 ],s.on_screen_buttons,v=>s.on_screen_buttons=v));
 const hwBox=integrationNode('div',undefined,'editor-card');
 hwBox.style.cssText='background:#1b202c;border:1px solid #4a5568;border-radius:8px;padding:12px;margin:12px 0;';
 hwBox.innerHTML='<strong style="color:#e2e8f0;font-size:0.9rem;">🕹️ Physical Button Mapping & Override</strong><p style="margin:4px 0 8px 0;font-size:0.75rem;color:#a0aec0;">These switches control gameplay and are completely isolated from background apps while playing. Switches 1 (Sleep) and 6 (Power) remain protected.</p>';
 integrationField(hwBox,'Move Left Switch (ID)',integrationInput(s.switch_left,v=>s.switch_left=Number(v)||2,'number'));
 integrationField(hwBox,'Move Right Switch (ID)',integrationInput(s.switch_right,v=>s.switch_right=Number(v)||3,'number'));
 integrationField(hwBox,'Action / Launch / Restart Switch (ID)',integrationInput(s.switch_action,v=>s.switch_action=Number(v)||4,'number'));
 integrationField(hwBox,'Exit Game Switch (ID)',integrationInput(s.switch_exit,v=>s.switch_exit=Number(v)||5,'number'));
 card.append(hwBox);
 card.append(integrationButton('Save game settings',saveConfigToPi),integrationButton('View events & mappings',()=>{appStudioSection='events';renderActionPane();}));
 pane.append(card);
}

function renderIntegrationConnection(pane,app){
 const card=integrationNode('div',undefined,'editor-card'),tele=integrationTelemetry[app.id],age=tele?.last_seen?Math.max(0,Math.round(Date.now()/1000-tele.last_seen)):null;
 card.append(integrationNode('h3','Connection and normal updates'));const status=integrationNode('p',app.setup_pending?'Placeholder — not connected yet':tele?(tele.status||'Received')+' · Last update '+age+' seconds ago':'No update received yet');status.id='integrationLiveStatus';card.append(status);if(tele?.summary)card.append(integrationNode('p',tele.summary));
 integrationField(card,'Display name',integrationInput(app.name,v=>{app.name=v;renderAppList();}));
 const triggersVal = Array.isArray(app.voice_triggers) ? app.voice_triggers.join(', ') : (app.voice_triggers || '');
 integrationField(card, 'Voice command phrases (comma-separated)', integrationInput(triggersVal, v => {
   app.voice_triggers = v.split(',').map(s => s.trim()).filter(Boolean);
 }));
 if(app.built_in==='weather'){
  integrationToggle(card,'Enable weather updates',app.weather_enabled!==false,v=>app.weather_enabled=v);
  integrationField(card,'Refresh interval (seconds; minimum 900)',integrationInput(app.poll_seconds||3600,v=>app.poll_seconds=Math.max(900,Number(v)||3600),'number'));
  card.append(integrationNode('p','Open-Meteo forecast, using the latitude, longitude and timezone in scene day/night settings. No API key needed for personal non-commercial use. Updates run on this device and are cached; map Forecast changed to an animation in Events & mappings.'));
  const credit=integrationNode('a','Weather data: Open-Meteo');credit.href='https://open-meteo.com/';credit.target='_blank';card.append(credit);
  card.append(integrationButton('Save weather settings',saveConfigToPi),integrationButton('View events & mappings',()=>{appStudioSection='events';renderActionPane();}));pane.append(card);return;
 }
 integrationField(card,'Connection method',integrationSelect([['push','Application pushes events (Webhooks)'],['poll','Desk-Pal polls direct endpoint URL (REST API)']],app.source_enabled===true?'poll':'push',v=>{app.source_enabled=v==='poll';renderActionPane();}));
 integrationField(card,'Direct application endpoint URL',integrationInput(app.source_url||'',v=>app.source_url=v.trim(),'url'));
 if(app.source_enabled){
  integrationField(card,'API Key / Bearer Token (optional for Home Assistant / GitHub / Private APIs)',integrationInput(app.auth_token||'',v=>app.auth_token=v.trim()));
 }
 integrationField(card,'Source format',integrationSelect([['json','Generic JSON (Custom Fields)'],['system_monitor','🖥️ Pi System & Hardware Monitor'],['uptime_ping','📡 Network & Uptime Ping Monitor'],['home_assistant','🏠 Home Assistant Entity Relay'],['wellness_check','💧 Wellness & Hydration Tracker'],['fuel_tracker','Custom: Fuel Tracker QLD'],['travel_radar','Custom: Travel Radar Deals'],['bmcbf','Custom: BMCBF Crypto Tracker']],app.adapter||'json',v=>{app.adapter=v;renderActionPane();}));
 integrationField(card,'Poll interval (seconds)',integrationInput(app.poll_seconds||30,v=>app.poll_seconds=Math.max(5,Number(v)||30),'number'));
 integrationField(card,'Routine update maximum age after sleep (seconds; 0 keeps any age)',integrationInput(app.sleep_max_age_seconds??900,v=>app.sleep_max_age_seconds=Math.max(0,Number(v)||0),'number'));
 card.append(integrationNode('small','During sleep, keep the latest routine update per event. On wake, discard routine updates older than this limit. Important alerts are always kept.'));
 integrationField(card,'Summary field (JSON dot path)',integrationInput(app.summary_field||'summary',v=>app.summary_field=v));
 const monitor=document.createElement('input');monitor.type='checkbox';monitor.checked=app.monitor_health!==false;monitor.onchange=()=>app.monitor_health=monitor.checked;integrationField(card,'Warn when updates stop',monitor);
 integrationField(card,'Warn after seconds',integrationInput(app.stale_after_seconds||300,v=>app.stale_after_seconds=Math.max(60,Number(v)||300),'number'));
 integrationField(card,'Normal update reaction',integrationSelect([['__primary__','Use button/status reaction, without a popup'],['','Receive updates without an animation'],...(app.actions||[]).map(a=>[a.id,a.label||a.id])],app.heartbeat_action_id??'__primary__',v=>app.heartbeat_action_id=v));
 if(app.adapter==='fuel_tracker'){
  app.settings||={};
  integrationField(card,'Target postcode',integrationInput(app.settings.postcode||'4128',v=>app.settings.postcode=v.trim()));
  integrationField(card,'Fuel type',integrationSelect([['u98','Premium Unleaded 98 (U98)'],['u95','Premium Unleaded 95 (U95)'],['u91','Unleaded 91 (U91)'],['diesel','Diesel'],['e10','E10 Ethanol'],['pdsl','Premium Diesel']],app.settings.fuel_type||'u98',v=>app.settings.fuel_type=v));
  integrationField(card,'Search radius (km)',integrationInput(app.settings.radius_km||5,v=>app.settings.radius_km=Math.max(1,Number(v)||5),'number'));
 }
 if(app.adapter==='travel_radar'){app.settings||={};integrationField(card,'Origin airport',integrationInput(app.settings.origin||'BNE',v=>app.settings.origin=v));}
 if(app.adapter==='wellness_check'||app.id==='wellness_check'){renderWellnessConnectionSettings(card,app);}
 if(app.adapter==='calendar'||app.id==='calendar'){renderCalendarConnectionSettings(card,app);}
 const address=location.origin+'/api/v1/';card.append(integrationNode('p','Send JSON with app_id "'+app.id+'" to '+address+'heartbeat or '+address+'event. No source polling is required for applications that send updates directly.'));
 card.append(integrationButton('Save application',saveConfigToPi),integrationButton('View events & mappings',()=>{appStudioSection='events';renderActionPane();}),integrationButton('Delete application',deleteCurrentApp));pane.append(card);
}
function renderCalendarConnectionSettings(card,app){
 const s=app.settings||={};
 s.feed_url||='';
 s.poll_interval_minutes=Number(s.poll_interval_minutes)||15;
 const cSec=integrationNode('div',undefined,'editor-card');
 cSec.style.cssText='background:#191627;border:1px solid #a855f7;border-radius:8px;padding:14px;margin:14px 0;';
 const cHeader=integrationNode('div');
 cHeader.style.cssText='display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;border-bottom:1px solid rgba(168,85,247,0.3);padding-bottom:6px;';
 cHeader.innerHTML='<strong style="color:#d8b4fe;font-size:0.95rem;">📅 Private iCal / Calendar Feed</strong><span style="font-size:0.75rem;color:#a855f7;">Port 8097 Companion Microservice</span>';
 cSec.append(cHeader);
 const helpBox=integrationNode('div');
 helpBox.style.cssText='background:rgba(168,85,247,0.08);border:1px solid rgba(168,85,247,0.25);border-radius:6px;padding:10px 12px;margin-bottom:12px;font-size:0.8rem;color:#e9d5ff;line-height:1.45;';
 helpBox.innerHTML=\'<strong>How to get your private calendar link (No Google Cloud project needed):</strong><ol style="margin-left:18px;margin-top:4px;"><li>Open <a href="https://calendar.google.com" target="_blank" style="color:#38bdf8;text-decoration:underline;">Google Calendar</a> on your computer.</li><li>In the left sidebar, hover over your calendar, click <b>⋮ (Options)</b> &rarr; <b>Settings and sharing</b>.</li><li>Scroll down to <b>Integrate calendar</b> and copy the <b>Secret address in iCal format</b> (ends with <code>.ics</code>).</li><li>Paste that URL below and click <b>Save application</b>.</li></ol><div style="margin-top:4px;color:#94a3b8;font-size:0.75rem;">(Apple iCloud, Outlook, Fastmail, and Nextcloud private .ics links are also fully supported).</div>\';
 cSec.append(helpBox);
 const urlBox=integrationNode('div');urlBox.style.cssText=\'margin-bottom:12px;\';
 const urlInput=integrationInput(s.feed_url,v=>{s.feed_url=v.trim();});
 urlInput.placeholder=\'https://calendar.google.com/calendar/ical/.../basic.ics\';
 urlInput.style.fontFamily=\'monospace\';urlInput.style.fontSize=\'0.8rem\';
 integrationField(urlBox,\'Secret iCal Feed URL\',urlInput);
 cSec.append(urlBox);
 const intBox=integrationNode('div');intBox.style.cssText=\'display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;\';
 const intInput=integrationInput(s.poll_interval_minutes,v=>s.poll_interval_minutes=Math.max(5,Math.min(180,Number(v)||15)),\'number\');
 intInput.min=5;intInput.max=180;intInput.step=5;
 integrationField(intBox,\'Calendar sync interval (minutes)\',intInput);
 cSec.append(intBox);
 card.append(cSec);
}
function renderWellnessConnectionSettings(card,app){
 const s=app.settings||={};
 if(!Array.isArray(s.days_of_week))s.days_of_week=['mon','tue','wed','thu','fri'];
 s.start_time||='09:00';s.end_time||='17:00';
 s.interval_minutes=Number(s.interval_minutes)||45;
 s.absence_reset_minutes=Number(s.absence_reset_minutes)||30;
 s.voice_phrase||='Hey pal, time for a stretch and some water!';
 const wSec=integrationNode('div',undefined,'editor-card');
 wSec.style.cssText='background:#121826;border:1px solid #0284c7;border-radius:8px;padding:14px;margin:14px 0;';
 const wHeader=integrationNode('div');
 wHeader.style.cssText='display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;border-bottom:1px solid rgba(56,189,248,0.25);padding-bottom:6px;';
 wHeader.innerHTML='<strong style="color:#38bdf8;font-size:0.95rem;">💧 Wellness Schedule & Radar Policy</strong><span style="font-size:0.75rem;color:#94a3b8;">Port 8096 Companion Microservice</span>';
 wSec.append(wHeader);
 const daysRow=integrationNode('div');daysRow.style.cssText='margin-bottom:12px;';
 daysRow.append(integrationNode('label','Active Days of the Week: ','label-sub'));
 const pillsContainer=integrationNode('div');
 pillsContainer.style.cssText='display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;margin-bottom:8px;';
 const dayNames=[['mon','Mon'],['tue','Tue'],['wed','Wed'],['thu','Thu'],['fri','Fri'],['sat','Sat'],['sun','Sun']];
 const renderPills=()=>{
  pillsContainer.replaceChildren();
  dayNames.forEach(([code,label])=>{
   const active=s.days_of_week.includes(code);
   const pill=integrationNode('button',label,'btn');pill.type='button';
   pill.style.cssText=`font-size:0.78rem;padding:4px 10px;border-radius:6px;font-weight:700;cursor:pointer;transition:all 0.15s ease;${active?'background:#38bdf8;color:#0f172a;border:1px solid #38bdf8;':'background:#1e293b;color:#94a3b8;border:1px solid #334155;'}`;
   pill.onclick=e=>{e.preventDefault();if(active)s.days_of_week=s.days_of_week.filter(d=>d!==code);else s.days_of_week.push(code);renderPills();};
   pillsContainer.append(pill);
  });
 };
 renderPills();
 daysRow.append(pillsContainer);
 const presetsRow=integrationNode('div');presetsRow.style.cssText='display:flex;gap:8px;';
 const btnWeekdays=integrationNode('button','Mon–Fri (Workdays)','btn');btnWeekdays.type='button';
 btnWeekdays.style.cssText='font-size:0.72rem;padding:2px 8px;background:#0f172a;border:1px solid #334155;color:#cbd5e1;';
 btnWeekdays.onclick=e=>{e.preventDefault();s.days_of_week=['mon','tue','wed','thu','fri'];renderPills();};
 const btnAll=integrationNode('button','Every Day (Mon–Sun)','btn');btnAll.type='button';
 btnAll.style.cssText='font-size:0.72rem;padding:2px 8px;background:#0f172a;border:1px solid #334155;color:#cbd5e1;';
 btnAll.onclick=e=>{e.preventDefault();s.days_of_week=['mon','tue','wed','thu','fri','sat','sun'];renderPills();};
 presetsRow.append(btnWeekdays,btnAll);daysRow.append(presetsRow);wSec.append(daysRow);
 const timeGrid=integrationNode('div');timeGrid.style.cssText='display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;';
 const startBox=integrationNode('div');
 integrationField(startBox,'Active window starts (e.g. 09:00)',integrationInput(s.start_time,v=>s.start_time=v.trim()||'09:00','time'));
 const endBox=integrationNode('div');
 integrationField(endBox,'Active window ends (e.g. 17:00)',integrationInput(s.end_time,v=>s.end_time=v.trim()||'17:00','time'));
 timeGrid.append(startBox,endBox);wSec.append(timeGrid);
 const paramGrid=integrationNode('div');paramGrid.style.cssText='display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;';
 const intBox=integrationNode('div');
 const intInput=integrationInput(s.interval_minutes,v=>s.interval_minutes=Math.max(15,Math.min(180,Number(v)||45)),'number');
 intInput.min=15;intInput.max=180;intInput.step=5;
 integrationField(intBox,'Sitting reminder interval (minutes)',intInput);
 const absBox=integrationNode('div');
 const absInput=integrationInput(s.absence_reset_minutes,v=>s.absence_reset_minutes=Math.max(5,Math.min(120,Number(v)||30)),'number');
 absInput.min=5;absInput.max=120;absInput.step=5;
 integrationField(absBox,'Away break reset threshold (minutes)',absInput);
 paramGrid.append(intBox,absBox);wSec.append(paramGrid);
 wSec.append(integrationNode('small','If mmWave radar detects you away for the break threshold, the sitting timer resets automatically (natural break credited).','text-dim'));
 const voiceField=integrationField(wSec,'Piper TTS voice prompt phrase',integrationInput(s.voice_phrase,v=>s.voice_phrase=v.trim()||'Hey pal, time for a stretch and some water!'));
 voiceField.style.width='100%';
 card.append(wSec);
}
function integrationDefinitions(app){const observed=integrationTelemetry[app.id]?.received_events||{},defs=new Map((app.integration_events||[]).map(d=>[d.name,d]));for(const name of Object.keys(observed))if(!defs.has(name))defs.set(name,{name,label:name});for(const a of app.actions||[])if(a.event&&!(a.is_primary&&a.event==='status_check')&&!defs.has(a.event))defs.set(a.event,{name:a.event,label:a.label||a.event});if(app.built_in!=='sensors'&&!defs.has('heartbeat'))defs.set('heartbeat',{name:'heartbeat',label:'Normal update'});return [...defs.values()];}
function integrationReceiptStatus(observed,now=Date.now()/1000){const samples=(observed.recent_receipts||[]).filter(sample=>sample[0]>now-300&&sample[0]<=now);const suppressed=samples.filter(sample=>sample[1]!=='received').length;return samples.length+' received in last 5 min · '+suppressed+' suppressed in last 5 min · '+(observed.count||0)+' lifetime received'+(observed.last_suppression?' · latest suppressed ('+(observed.last_suppression==='duplicate'?'duplicate':'event disabled')+')':'');}
function integrationToggle(parent,label,checked,change){
 const input=document.createElement('input');input.type='checkbox';input.checked=checked;
 const row=integrationNode('label');row.style.cssText='display:inline-flex;align-items:center;gap:6px;cursor:pointer;margin:0';row.append(input,integrationNode('span',label));parent.append(row);input.onchange=()=>change(input.checked);return input;
}
function redrawIntegrationEventPane(){const pane=document.getElementById('actionMainPane'),top=pane?.scrollTop||0;renderActionPane();if(pane)pane.scrollTop=top;}
function integrationPlaybackSummary(action){
 const choices=integrationPlaybackChoices(action),modes=[...new Set(choices.map(sequence=>{const mode=playbackMode(sequence);return mode==='once'?'Play once':mode==='repeat'?'Play '+(sequence.repeat_count||2)+' times':mode==='ping_pong'?'Ping-pong':'Loop';}))];
 let text=modes.length?modes.join(' / '):'Animation default';
 if(choices.some(sequence=>['loop','ping_pong'].includes(playbackMode(sequence))))text+=Number(action.duration_seconds)>0?' · '+action.duration_seconds+' seconds':' · one cycle';
 if(action.attention_until_interaction)text='Until acknowledged';
 return text+' · '+({none:'No text',thought_bubble:'Message above character',popup_modal:'Popup'}[action.display_mode||'none']||'No text')+(action.conditions?.length?' · '+action.conditions.length+' conditions':'');
}
const integrationEventOptionsState=new WeakMap();
function integrationEventOptions(app,event){let events=integrationEventOptionsState.get(app);if(!events){events=new Map();integrationEventOptionsState.set(app,events);}return events;}
function renderIntegrationEvents(pane,app){
 const card=integrationNode('div',undefined,'editor-card');const heading=integrationNode('h3','Events & mappings');heading.style.margin='0 0 8px';card.append(heading,integrationNode('small','Click a scene preview to edit. Save your changes when finished.'));
 const state=integrationEventFilterState.get(app)||{query:'',scene:'',showSuppressed:true};integrationEventFilterState.set(app,state);
 const controls=integrationNode('div');controls.style.cssText='display:flex;gap:8px;align-items:center;flex-wrap:wrap';
 const search=document.createElement('input');search.type='search';search.id='integrationEventSearch';search.placeholder='Find an event, animation or location';search.value=state.query;search.style.minWidth='240px';search.oninput=()=>{state.query=search.value;const position=search.selectionStart;renderActionPane();const next=document.getElementById('integrationEventSearch');next?.focus();if(position!=null)next?.setSelectionRange(position,position);};controls.append(search);
 for(const [id,label]of [['','All scenes'],...integrationEventGroups(app).map(([id])=>[id||'__unmapped__',id?(config.scenes?.[id]?.name||id):'Unmapped'])]){const button=integrationButton(label,()=>{state.scene=id;renderActionPane();});if(state.scene===id)button.classList.add('btn-primary');controls.append(button);}
 const show=document.createElement('input');show.type='checkbox';show.checked=state.showSuppressed;show.onchange=()=>{state.showSuppressed=show.checked;renderActionPane();};const label=integrationNode('label','Show suppressed events ');label.append(show);controls.append(label);card.append(controls);
 const groups=integrationFilteredEventGroups(app,{...state,scene:state.scene==='__unmapped__'?'':state.scene}).filter(([scene])=>state.scene!=='__unmapped__'||!scene);
 if(!groups.length)card.append(integrationNode('p','No events match this view. Change the search, scene or suppressed-event filter.'));
 for(const [scene,entries]of groups){
  const section=integrationNode('section');section.style.cssText='margin:18px 0;border-top:2px solid #53526f;padding-top:10px';section.append(integrationNode('h3',scene?(config.scenes?.[scene]?.name||scene):'Events without a scene mapping'));
  for(const {definition,mappings}of entries){
   const observed=integrationTelemetry[app.id]?.received_events?.[definition.name],row=integrationNode('div',undefined,'editor-card'),muted=app.suppressed_events?.[definition.name]===true;
   const heading=integrationNode('div');heading.style.cssText='display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap';
   const title=integrationNode('h4',(definition.name==='heartbeat'?'Heartbeat':definition.label||definition.name)+(muted?' · suppressed':''));title.style.margin='0';heading.append(title,integrationNode('small',observed?'Received '+integrationTimeAgo(observed.last_seen):'Not received yet'));row.append(heading);
   const eventControls=integrationNode('div');eventControls.style.cssText='display:flex;gap:16px;flex-wrap:wrap;margin:10px 0';
   integrationToggle(eventControls,'Suppress event',muted,checked=>{app.suppressed_events||={};app.suppressed_events[definition.name]=checked;redrawIntegrationEventPane();});
   integrationToggle(eventControls,'Suppress duplicates',app.suppress_duplicate_events?.[definition.name]??definition.name!=='heartbeat',checked=>{app.suppress_duplicate_events||={};app.suppress_duplicate_events[definition.name]=checked;});row.append(eventControls);
   for(const action of mappings){
    const line=integrationNode('div');line.style.cssText='display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin:10px 0';line.append(integrationPlacementPreview(action));const description=integrationNode('div');description.style.cssText='flex:1;min-width:180px';
    const mode=action.target_mode||'specific',spot=actionSceneData(action).interaction_spots?.find(s=>s.id===action.spot_id);
    description.append(integrationNode('strong',action.label||action.id));const target=integrationNode('div',(['any','location'].includes(mode)?'Any matching animation':poseLabel(action.animation||'idle'))+' · '+(['any','gesture'].includes(mode)?'Any matching location':mode==='current'?'Where the character is':spot?.name||action.spot_id||'Saved coordinates'));target.style.margin='5px 0';description.append(target,integrationNode('small',integrationPlaybackSummary(action)));
    const attentionControls=integrationNode('div');attentionControls.style.cssText='display:flex;gap:12px;flex-wrap:wrap;margin:8px 0';
    integrationToggle(attentionControls,'Needs attention',!!action.attention_needed,checked=>{action.attention_needed=checked;});
    const latch=integrationToggle(attentionControls,'Until acknowledged',!!action.attention_until_interaction,checked=>{action.attention_until_interaction=checked;redrawIntegrationEventPane();});latch.title='Keep this reaction active until you tap the character or press this application’s button, then dismiss the details popup.';if(action.attention_until_interaction){const vToggle=integrationToggle(attentionControls,'Voice ladder',action.voice_escalation!==false,checked=>{action.voice_escalation=checked;});vToggle.title='Escalate voice reminders with TTS when user is present.';}description.append(attentionControls);
    const check=integrationMappingCheck(app,action),warning=integrationNode('div',(check.ok===false?'⚠ ':check.ok===true?'✓ ':'')+check.reason);warning.style.color=check.ok===false?'#ffad75':check.ok===true?'#99d895':'#b9bad1';description.append(warning);
    const playback=integrationLastPlayback(app,action,definition.name);if(playback)description.append(integrationNode('small',playback.event==='failed'?'Playback failed: '+(playback.error||playback.reason||'see activity history'):'Last played '+integrationTimeAgo(playback.timestamp)));
    const controls=integrationNode('div');controls.style.cssText='display:flex;gap:8px;flex-wrap:wrap';controls.append(integrationButton(selectedActionId===action.id?'Close mapping':'Edit mapping',()=>{selectedActionId=selectedActionId===action.id?'':action.id;redrawIntegrationEventPane();}));if(!action.is_primary){const remove=integrationButton('Delete mapping',()=>removeIntegrationMapping(app,action));remove.classList.add('btn-danger');controls.append(remove);}description.append(controls);line.append(description);row.append(line);
    if(selectedActionId===action.id){renderIntegrationTarget(row,action);renderIntegrationPlayback(row,action);const options=document.createElement('details');options.append(integrationNode('summary','More options · conditions ('+(action.conditions||[]).length+')'));appendIntegrationControls(options,app,action,false);row.append(options,integrationButton('Save mapping',saveConfigToPi));}
   }
   const settings=document.createElement('details'),openOptions=integrationEventOptions(app,definition.name);settings.open=!!openOptions.get(definition.name);settings.ontoggle=()=>openOptions.set(definition.name,settings.open);settings.append(integrationNode('summary','More options · received values'));
   settings.append(integrationNode('p',observed?integrationReceiptStatus(observed):'Defined; not received yet'),integrationNode('small','Suppression skips playback while retaining health updates and the saved mapping. A new task run ID counts as a new occurrence.'));
   const payload=observed?.data||definition.example;if(payload){const pre=integrationNode('pre',JSON.stringify(payload,null,2));pre.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere';settings.append(pre);}row.append(settings,integrationButton(mappings.length?'Add conditional mapping':'Map this event',()=>addIntegrationMapping(app,definition)));section.append(row);
  }card.append(section);
 }
 card.append(integrationButton('Save event settings',saveConfigToPi),integrationButton('Add custom event mapping',()=>{const name=prompt('Incoming event name');if(name?.trim())addIntegrationMapping(app,{name:name.trim(),label:name.trim()});}));pane.append(card);
}

function removeIntegrationMapping(app,action){
 if(action.is_primary||!app.actions.includes(action))return;
 if(!confirm('Delete mapping "'+(action.label||action.id)+'"? Its scene, animation, location and conditions will be removed from this application.'))return;
 app.actions=app.actions.filter(a=>a!==action);if(selectedActionId===action.id)selectedActionId='';renderActionPane();
}
function addIntegrationMapping(app,definition){
 const base=definition.name.replace(/[^a-zA-Z0-9_]/g,'_')||'event';let id=base,n=2;while(app.actions.some(a=>a.id===id))id=base+'_'+n++;
 const source=app.actions.find(a=>a.is_primary||a.id==='status_check')||{};const a=JSON.parse(JSON.stringify(source));delete a.is_primary;delete a.switch_id;Object.assign(a,{id,event:definition.name,label:definition.label||definition.name,speech:'',display_mode:'none',conditions:[]});if(app.built_in==='sensors'){a.target_mode='current';a.hide_label=true;a.animation=definition.name==='person_returned'?'wave_arms':definition.name==='shake'||definition.name.endsWith('_strong')?'balance_strong':'balance_mild';a.duration_seconds=0;delete a.facing;if(definition.name.startsWith('tilt_left'))a.facing='right';if(definition.name.startsWith('tilt_right'))a.facing='left';}app.actions.push(a);selectedActionId=id;appStudioSection='events';renderActionPane();
}
function integrationPlacements(action){
 const room=actionSceneData(action),catalog=actionPoseCatalog(action);
 return (room.interaction_spots||[]).flatMap(spot=>[...new Set([spot.animation,...(spot.animations||[])])].filter(role=>role&&catalog[role]&&!role.startsWith('walk')&&!catalog[role].transition_only&&(!room.pose_rules?.[role]?.valid_spots||room.pose_rules[role].valid_spots.includes(spot.id))).map(role=>({spot,role})));
}
function renderIntegrationTargetDropdowns(card,action){
 const redraw=()=>renderActionPane();
 integrationField(card,'Scene',integrationSelect(Object.entries(config.scenes||{}).filter(([,s])=>s.enabled!==false).map(([id,s])=>[id,s.name||id]),actionSceneId(action),v=>{action.scene=v;delete action.target_scene;delete action.spot_id;action.target_mode='any';delete action.x;delete action.y;redraw();}));
 const placements=integrationPlacements(action),roles=[...new Set(placements.map(p=>p.role))],catalog=actionPoseCatalog(action),any=['any','location'].includes(action.target_mode);
 integrationField(card,'Animation',integrationSelect([['','Any placed animation'],...roles.map(role=>[role,catalog[role]?.name||role]),...(!any&&action.animation&&!roles.includes(action.animation)?[[action.animation,action.animation+' (no saved placement)']]:[])],any?'':action.animation||'',v=>{action.animation=v;action.target_mode=v?'gesture':'any';delete action.spot_id;delete action.x;delete action.y;redraw();}));
 const spots=[...new Map(placements.filter(p=>any||p.role===action.animation).map(p=>[p.spot.id,p.spot])).values()];
 integrationField(card,'Location',integrationSelect([['','Any matching location'],...spots.map(s=>[s.id,s.name||s.id]),...(action.spot_id&&!spots.some(s=>s.id===action.spot_id)?[[action.spot_id,action.spot_id+' (not placed for this animation)']]:[])],action.spot_id||'',v=>{const spot=spots.find(s=>s.id===v);if(spot){action.spot_id=v;action.x=spot.x;action.y=spot.y;action.facing=spot.facing||'right';action.target_mode=any?'location':'specific';}else{delete action.spot_id;delete action.x;delete action.y;action.target_mode=any?'any':'gesture';}redraw();}));
 if(!placements.length)card.append(integrationNode('p','No animations are placed in this scene yet. Place them in the Pose Stager first.'));
}
function renderDashboardDesignerMarkup(container, app, act) {
  if (!act.dashboard) {
    act.dashboard = {
      hero_value: '',
      hero_subhead: '',
      badge: '',
      badge_color: '#2ecc71',
      tiles: []
    };
  }
  const dash = act.dashboard;
  if (!Array.isArray(dash.tiles)) dash.tiles = [];
  const modalLayout = act.modal_layout || (app.id === 'wellness_check' ? 'wellness' : 'dashboard');
  const isWellness = (modalLayout === 'wellness');
  const isDash = (modalLayout === 'dashboard');

  const prevHero = dash.hero_value || (app.id === 'fuel_tracker' ? '179.9¢/L' : (app.id === 'bmcbf' ? 'ONLINE' : (app.id === 'store_orders' ? '3 Orders' : 'OK')));
  const prevBadge = dash.badge || (app.id === 'fuel_tracker' ? 'BUY NOW' : (app.id === 'bmcbf' ? 'HEALTHY' : (app.id === 'store_orders' ? 'NEW' : 'ACTIVE')));
  const prevSub = dash.hero_subhead || (app.id === 'fuel_tracker' ? 'Costco North Lakes' : (app.id === 'bmcbf' ? 'All systems nominal' : (app.id === 'store_orders' ? 'Awaiting packaging' : 'Status check')));
  const prevTiles = dash.tiles.length ? dash.tiles : (app.id === 'fuel_tracker' ? [
    { label: 'AREA AVG', value: '262.0¢' },
    { label: 'TREND', value: 'Rising 48h' },
    { label: 'DISTANCE', value: '1.1km' }
  ] : [
    { label: app.id === 'bmcbf' ? 'STATUS' : 'Metric 1', value: app.id === 'bmcbf' ? 'Online' : '100%' },
    { label: app.id === 'bmcbf' ? 'TASKS' : 'Metric 2', value: app.id === 'bmcbf' ? 'Nominal' : 'Normal' }
  ]);
  const prevBadgeColor = dash.badge_color || '#2ecc71';

  container.innerHTML = `
    <div style="margin-top:6px;">
      <div class="field-group" style="margin-bottom:10px;">
        <label style="font-weight:700; color:var(--accent);">Popup Card Layout (Optimized for 5" 1280x720 Screen)</label>
        <div class="btn-toggle-group" style="max-width:560px;">
          ${(app.id === 'wellness_check' || modalLayout === 'wellness') ? `
            <div class="btn-toggle ${isWellness ? 'active-modal' : ''}" onclick="updateActionField('modal_layout', 'wellness')">🧘 Dual-Panel Wellness Card</div>
          ` : ''}
          <div class="btn-toggle ${isDash ? 'active-modal' : ''}" onclick="updateActionField('modal_layout', 'dashboard')">📊 5" Dashboard Card (High-Vis)</div>
          <div class="btn-toggle ${modalLayout === 'classic' ? 'active' : ''}" onclick="updateActionField('modal_layout', 'classic')">📄 Classic Text Paragraph</div>
        </div>
      </div>

      ${isWellness ? `
        <div class="dash-designer-container">
          <!-- Controls Column -->
          <div class="dash-designer-controls">
            <div style="background:rgba(56,189,248,0.1); border:1px solid #38bdf8; border-radius:8px; padding:10px 12px; margin-bottom:12px;">
              <div style="font-weight:700; color:#38bdf8; font-size:0.88rem; margin-bottom:4px;">🧘 5" Dual-Panel Graphic Wellness Card</div>
              <div style="font-size:0.75rem; color:#b4c8dc; line-height:1.4;">Displays the real 30/70 split layout with pixel-art water glass, animated stretching sprite, metric 20-20-20 eye advice (6 metres for 20 seconds), and an interactive touch slider rail (15m–120m).</div>
            </div>

            <div class="form-row-2">
              <div class="field-group">
                <label>Hydration Action Prompt</label>
                <input type="text" value="${esc(act.wellness?.hydration_text || 'Drink Water')}" placeholder="Drink Water"
                       onchange="act.wellness=act.wellness||{};act.wellness.hydration_text=this.value;saveConfigToPi();renderActionPane();">
              </div>
              <div class="field-group">
                <label>Stretch Activity Title</label>
                <input type="text" value="${esc(act.wellness?.stretch_title || 'Stand Up & Move')}" placeholder="Stand Up & Move"
                       onchange="act.wellness=act.wellness||{};act.wellness.stretch_title=this.value;saveConfigToPi();renderActionPane();">
              </div>
            </div>

            <div class="form-row-2">
              <div class="field-group">
                <label>Stretch Activity Advice</label>
                <input type="text" value="${esc(act.wellness?.stretch_subhead || 'Roll shoulders & stretch arms')}" placeholder="Roll shoulders & stretch arms"
                       onchange="act.wellness=act.wellness||{};act.wellness.stretch_subhead=this.value;saveConfigToPi();renderActionPane();">
              </div>
              <div class="field-group">
                <label>Eye Health Rule (Metric)</label>
                <input type="text" value="Look 6 metres away (20s)" disabled style="opacity:0.8;">
              </div>
            </div>

            <div class="field-group" style="margin-top:4px;">
              <label>Voice Escalation Reminder Phrase</label>
              <input type="text" value="${esc(act.voice_phrase || app.settings?.voice_phrase || 'Hey pal, time for a stretch and some water!')}" placeholder="Hey pal, time for a stretch and some water!"
                     onchange="updateActionField('voice_phrase', this.value)">
            </div>

            <div style="font-size:0.75rem; color:#94a3b8; margin-top:8px;">
              Active days (e.g. Mon–Fri) and active hours (e.g. 09:00–17:00) are configured under the <a href="javascript:void(0)" onclick="appStudioSection='connection';renderAppStudio();" style="color:#38bdf8; text-decoration:underline;">Connection</a> section.
            </div>
          </div>

          <!-- 5-Inch Bezel Live Preview Column -->
          <div class="dash-preview-wrap">
            <div class="dash-preview-label">
              <span>5-Inch Display Preview</span>
              <span style="font-size:0.65rem; color:var(--text-dim);">1280 × 720</span>
            </div>
            <div class="dash-preview-bezel">
              <div class="dash-preview-card" style="border-color:#38bdf8; background:#161926; padding:10px 12px; gap:8px;">
                <!-- Header -->
                <div class="dash-preview-hdr" style="border-bottom:1px solid rgba(56,189,248,0.2);">
                  <span class="dash-preview-title" style="color:#38bdf8; font-size:0.8rem; letter-spacing:1px;">${esc(app.name || 'WELLNESS & HYDRATION').toUpperCase()}</span>
                  <span class="dash-preview-clock" style="color:#8b9bb4; font-size:0.7rem;">10:45 AM</span>
                </div>

                <!-- Dual Panels Row -->
                <div style="display:flex; gap:10px; align-items:stretch;">
                  <!-- Panel 1: Hydration (32%) -->
                  <div style="flex:0 0 32%; background:#1c2333; border:1px solid #38bdf8; border-radius:8px; padding:8px 6px; display:flex; flex-direction:column; align-items:center; justify-content:space-between; text-align:center; min-height:130px;">
                    <span style="font-size:0.6rem; font-weight:800; padding:2px 8px; border-radius:10px; background:#143c5f; border:1px solid #38bdf8; color:#fff; letter-spacing:0.5px;">HYDRATION</span>
                    <div style="margin:4px 0; display:flex; align-items:center; justify-content:center; height:54px;">
                      <img src="/assets/props/wellness_glass.png" alt="Water Glass" style="max-height:50px; max-width:44px; object-fit:contain; image-rendering:pixelated;" onerror="this.outerHTML='<span style=\\'font-size:2rem;\\'>🥛</span>'">
                    </div>
                    <div style="font-size:0.75rem; font-weight:700; color:#fff;">${esc(act.wellness?.hydration_text || 'Drink Water')}</div>
                  </div>

                  <!-- Panel 2: Stretch & Rest (68%) -->
                  <div style="flex:1; background:#1c2333; border:1px solid #6ad73c; border-radius:8px; padding:8px 10px; display:flex; flex-direction:column; justify-content:space-between; min-height:130px;">
                    <div style="display:flex; justify-content:flex-start;">
                      <span style="font-size:0.6rem; font-weight:800; padding:2px 8px; border-radius:10px; background:#194123; border:1px solid #6ad73c; color:#fff; letter-spacing:0.5px;">STRETCH &amp; REST</span>
                    </div>
                    <div style="display:flex; gap:10px; align-items:center; margin-top:4px;">
                      <div style="flex:0 0 50px; display:flex; align-items:center; justify-content:center; height:58px;">
                        <img src="/assets/characters/adventurer/wellness_stretch_0.png" alt="Stretch" style="max-height:56px; max-width:48px; object-fit:contain; image-rendering:pixelated;" onerror="this.outerHTML='<span style=\\'font-size:2rem;\\'>🧘</span>'">
                      </div>
                      <div style="flex:1; display:flex; flex-direction:column;">
                        <div style="font-size:0.88rem; font-weight:800; color:#fff; line-height:1.15;">${esc(act.wellness?.stretch_title || 'Stand Up & Move')}</div>
                        <div style="font-size:0.68rem; color:#b4c8dc; margin-top:2px;">${esc(act.wellness?.stretch_subhead || 'Roll shoulders & stretch arms')}</div>
                        <div style="font-size:0.66rem; font-weight:700; color:#38bdf8; margin-top:4px;">20-20-20 Rule (Metric):</div>
                        <div style="font-size:0.66rem; font-weight:700; color:#6ad73c;">Look 6 metres away (20s)</div>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- Touch Slider Rail Preview -->
                <div style="background:#141724; border:1px solid #2a334a; border-radius:6px; padding:4px 8px; margin-top:2px;">
                  <div style="display:flex; justify-content:space-between; font-size:0.62rem; font-weight:700; color:#38bdf8; margin-bottom:3px;">
                    <span>NEXT REMINDER IN: 45 MIN</span>
                    <span style="color:#8b9bb4;">15m – 120m</span>
                  </div>
                  <div style="position:relative; height:8px; background:#1c2333; border:1px solid #3a4466; border-radius:4px; overflow:hidden;">
                    <div style="width:35%; height:100%; background:#38bdf8; border-radius:4px;"></div>
                  </div>
                </div>

                <!-- Dismiss line -->
                <div class="dash-preview-dismiss" style="color:#8b9bb4; font-size:0.62rem; margin-top:1px;">[ TAP SCREEN TO DISMISS ]</div>
              </div>
            </div>
            <div style="margin-top:8px; display:flex; justify-content:center;">
              <button class="btn btn-accent" style="font-size:0.78rem; padding:4px 12px; font-weight:bold;" onclick="testCurrentActionOnPi()">
                ▶ Test on Pi Display
              </button>
            </div>
          </div>
        </div>
      ` : isDash ? `
        <div class="dash-designer-container">
          <!-- Controls Column -->
          <div class="dash-designer-controls">
            <div class="form-row-2">
              <div class="field-group">
                <label>Hero Metric (Big Stat)</label>
                <input type="text" placeholder="e.g. 179.9¢/L or {badge}" value="${esc(dash.hero_value || '')}"
                       oninput="updateActionDashboardField('hero_value', this.value, true)"
                       onchange="updateActionDashboardField('hero_value', this.value)">
              </div>
              <div class="field-group">
                <label>Action Badge Pill</label>
                <input type="text" placeholder="e.g. BUY NOW or WAIT" value="${esc(dash.badge || '')}"
                       oninput="updateActionDashboardField('badge', this.value, true)"
                       onchange="updateActionDashboardField('badge', this.value)">
              </div>
            </div>

            <div class="form-row-2">
              <div class="field-group">
                <label>Badge Color</label>
                <div style="display:flex; align-items:center; gap:8px;">
                  <div class="dash-color-preset ${dash.badge_color==='#2ecc71'?'active':''}" style="background:#2ecc71;" title="Green (Buy/OK)" onclick="updateActionDashboardField('badge_color', '#2ecc71')"></div>
                  <div class="dash-color-preset ${dash.badge_color==='#e74c3c'?'active':''}" style="background:#e74c3c;" title="Red (Wait/Alert)" onclick="updateActionDashboardField('badge_color', '#e74c3c')"></div>
                  <div class="dash-color-preset ${dash.badge_color==='#3498db'?'active':''}" style="background:#3498db;" title="Blue (Notice/Info)" onclick="updateActionDashboardField('badge_color', '#3498db')"></div>
                  <div class="dash-color-preset ${dash.badge_color==='#f39c12'?'active':''}" style="background:#f39c12;" title="Amber (Warning)" onclick="updateActionDashboardField('badge_color', '#f39c12')"></div>
                  <div class="dash-color-preset ${dash.badge_color==='#00e5ff'?'active':''}" style="background:#00e5ff;" title="Cyan (Special)" onclick="updateActionDashboardField('badge_color', '#00e5ff')"></div>
                  <input type="color" value="${dash.badge_color || '#2ecc71'}" style="width:32px; height:24px; padding:0; border:none; cursor:pointer;"
                         onchange="updateActionDashboardField('badge_color', this.value)">
                </div>
              </div>
              <div class="field-group">
                <label>Context Subhead</label>
                <input type="text" placeholder="e.g. Costco North Lakes" value="${esc(dash.hero_subhead || '')}"
                       oninput="updateActionDashboardField('hero_subhead', this.value, true)"
                       onchange="updateActionDashboardField('hero_subhead', this.value)">
              </div>
            </div>

            <div class="field-group" style="margin-top:4px;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                <label style="margin:0;">Glanceable Metric Tiles (Max 4)</label>
                ${dash.tiles.length < 4 ? `<button class="btn btn-sm" style="padding:2px 8px; font-size:0.75rem;" onclick="addActionDashboardTile()">+ Add Tile</button>` : ''}
              </div>
              ${dash.tiles.map((t, idx) => `
                <div class="dash-tile-row">
                  <input type="text" style="flex:1;" placeholder="Label (e.g. Avg)" value="${esc(t.label || '')}"
                         onchange="updateActionDashboardTile(${idx}, 'label', this.value)">
                  <input type="text" style="flex:1;" placeholder="Value (e.g. 194.2¢)" value="${esc(t.value || '')}"
                         onchange="updateActionDashboardTile(${idx}, 'value', this.value)">
                  <button class="btn btn-danger" style="padding:2px 6px; font-size:0.75rem;" onclick="removeActionDashboardTile(${idx})">✖</button>
                </div>
              `).join('')}
              ${!dash.tiles.length ? `<div style="font-size:0.72rem; color:var(--text-dim); font-style:italic;">No custom tiles added (auto-summary metrics will be displayed if available).</div>` : ''}
            </div>
          </div>

          <!-- 5-Inch Bezel Live Preview Column -->
          <div class="dash-preview-wrap">
            <div class="dash-preview-label">
              <span>5-Inch Display Preview</span>
              <span style="font-size:0.65rem; color:var(--text-dim);">1280 × 720</span>
            </div>
            <div class="dash-preview-bezel">
              <div class="dash-preview-card" style="border-color:${esc(prevBadgeColor)};">
                <div class="dash-preview-hdr">
                  <span class="dash-preview-title">${esc(app.name || app.id).toUpperCase()}</span>
                  <span class="dash-preview-clock">10:45 AM</span>
                </div>
                <div class="dash-preview-hero-row">
                  <span class="dash-preview-hero-val" id="dashPrevHeroVal">${esc(prevHero)}</span>
                  <span class="dash-preview-badge-pill" id="dashPrevBadgePill" style="background:${esc(prevBadgeColor)};">${esc(prevBadge)}</span>
                </div>
                <div class="dash-preview-subhead" id="dashPrevSubhead">${esc(prevSub)}</div>
                <div class="dash-preview-tiles" id="dashPrevTiles">
                  ${prevTiles.slice(0, 4).map(t => `
                    <div class="dash-preview-tile-chip">
                      <span class="dash-preview-tile-label">${esc(t.label || 'METRIC')}</span>
                      <span class="dash-preview-tile-val">${esc(t.value || '--')}</span>
                    </div>
                  `).join('')}
                </div>
                <div class="dash-preview-dismiss">[ TAP TO DISMISS ]</div>
              </div>
            </div>
            <div style="margin-top:8px; display:flex; justify-content:center;">
              <button class="btn btn-accent" style="font-size:0.78rem; padding:4px 12px; font-weight:bold;" onclick="testCurrentActionOnPi()">
                ▶ Test on Pi Display
              </button>
            </div>
          </div>
        </div>
      ` : `
        <div style="font-size:0.75rem; color:var(--text-dim); padding:8px 0;">
          Classic layout displays multi-line telemetry speech text in standard sized font.
        </div>
      `}
    </div>
  `;
}

function renderDashboardStudioTab(pane, app) {
  const card = integrationNode('div', undefined, 'editor-card');
  const h = integrationNode('h3', '📊 5" Dashboard Modal Designer');
  h.style.color = 'var(--accent)';
  const p = integrationNode('p', 'Design high-visibility dashboard cards for your 5-inch 1280x720 display. Features glanceable hero statistics, action pills, context subhead, and compact metric tiles.');
  card.append(h, p);

  if (!app.actions || !app.actions.length) {
    card.append(integrationNode('p', 'No actions or event mappings configured for this application yet.'));
    card.append(integrationButton('+ Create 5" Dashboard Popup Modal', () => {
      if(!app.actions) app.actions = [];
      const act = {
        id: 'status_check',
        label: (app.name || app.id) + ' Status',
        event: 'status_check',
        is_primary: true,
        display_mode: 'popup_modal',
        target_mode: 'specific',
        scene: currentSceneId(),
        animation: app.id === 'deskpal_weather' ? 'window_look' : 'inspect',
        spot_id: app.id === 'deskpal_weather' ? 'window' : '',
        speech: '{summary}',
        dashboard: {
          hero_value: app.id === 'deskpal_weather' ? '24°C' : 'OK',
          hero_subhead: app.id === 'deskpal_weather' ? 'Sunny · Rain 0%' : 'Status check',
          badge: app.id === 'deskpal_weather' ? 'FINE' : 'ACTIVE',
          badge_color: '#2ecc71',
          tiles: app.id === 'deskpal_weather' ? [
            { label: 'MIN / MAX', value: '16° / 26°' },
            { label: 'RAIN', value: '0%' },
            { label: 'UV INDEX', value: '6 (Mod)' },
            { label: 'WIND', value: '15 km/h' }
          ] : [
            { label: 'STATUS', value: 'Nominal' },
            { label: 'MODE', value: 'Ready' }
          ]
        }
      };
      app.actions.push(act);
      selectedActionId = act.id;
      saveConfigToPi();
      renderActionPane();
    }));
    pane.append(card);
    return;
  }

  let act = app.actions.find(a => a.id === selectedActionId);
  if (!act) {
    act = app.actions.find(a => a.is_primary || a.id === 'status_check' || a.display_mode === 'popup_modal') || app.actions[0];
    selectedActionId = act.id;
  }

  const selRow = document.createElement('div');
  selRow.style.cssText = 'display:flex; align-items:center; gap:12px; margin-bottom:14px; flex-wrap:wrap;';
  selRow.innerHTML = `
    <label style="font-weight:700; color:var(--accent);">Action / Event to Design:</label>
    <select id="dashActionSelector" style="background:#141120; color:#fff; border:1px solid var(--accent); padding:6px 12px; border-radius:6px; font-weight:600; min-width:240px;" onchange="selectedActionId=this.value; renderActionPane();">
      ${app.actions.map(a => `<option value="${esc(a.id)}" ${a.id === act.id ? 'selected' : ''}>${esc(a.label || a.id)} (${esc(a.event || 'default')})${a.display_mode==='popup_modal'?' · [Popup Active]':''}</option>`).join('')}
    </select>
  `;
  card.append(selRow);

  if (act.display_mode !== 'popup_modal') {
    const notice = document.createElement('div');
    notice.style.cssText = 'background:rgba(240,160,80,0.15); border:1px solid var(--accent); border-radius:6px; padding:10px 14px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;';
    notice.innerHTML = `
      <span style="font-size:0.85rem; color:#ffd090;">⚠️ This action is currently set to <b>${act.display_mode === 'thought_bubble' ? '💭 Thought Bubble' : (act.display_mode || 'No text')}</b>. Enable Popup Modal to show this dashboard on the 5" screen when triggered.</span>
      <button class="btn btn-primary" style="padding:4px 12px; font-size:0.8rem;" onclick="updateActionField('display_mode', 'popup_modal');">Enable 5" Popup Modal</button>
    `;
    card.append(notice);
  }

  const designerWrap = document.createElement('div');
  renderDashboardDesignerMarkup(designerWrap, app, act);
  card.append(designerWrap);

  const bottomBar = document.createElement('div');
  bottomBar.style.cssText = 'display:flex; justify-content:space-between; align-items:center; margin-top:16px; padding-top:12px; border-top:1px solid var(--border);';
  bottomBar.innerHTML = `
    <button class="btn btn-accent" style="font-weight:700; font-size:0.85rem; padding:6px 16px;" onclick="testCurrentActionOnPi()">▶ Test on Pi Display (1280x720)</button>
    <button class="btn btn-primary" style="font-weight:700; font-size:0.85rem; padding:6px 16px;" onclick="saveConfigToPi()">💾 Save Dashboard Settings</button>
  `;
  card.append(bottomBar);

  pane.append(card);
}

function renderIntegrationPlayback(card,action){
 integrationField(card,'Text display',integrationSelect([['none','No text'],['thought_bubble','Message above character'],['popup_modal','Status popup (5" Dashboard)']],action.display_mode||'none',v=>{action.display_mode=v;renderActionPane();}));
 if(action.display_mode!=='none'){
  integrationField(card,'Message',integrationInput(action.speech??'{summary}',v=>action.speech=v));
  integrationField(card,'Show with message',integrationSelect([['message_only','Message only'],['message_and_label','Message + application label']],action.message_label_mode||'message_and_label',v=>action.message_label_mode=v));
 }
 if(action.display_mode==='popup_modal'){
  const dashBox=document.createElement('div');
  dashBox.style.cssText='margin-top:12px;padding:12px;background:rgba(0,0,0,0.3);border:1px solid var(--accent);border-radius:8px;';
  const app=config.apps?config.apps.find(a=>a.id===selectedAppId):null;
  if(app)renderDashboardDesignerMarkup(dashBox,app,action);
  card.append(dashBox);
 }
}
function integrationPlaybackChoices(action){
 const room=actionSceneData(action),bindings=config.characters?.[config.active_character]?.animations||{},mode=action.target_mode||'specific';
 const choices=integrationPlacements(action).filter(p=>(!['specific','location'].includes(mode)||!action.spot_id||p.spot.id===action.spot_id)&&(!['specific','gesture'].includes(mode)||p.role===action.animation));
 const sequenceFor=(role,spot)=>{const sequence=config.animation_sequences?.[bindings[role==='idle'?'idle_side':role]||bindings[role]];if(!sequence)return null;return {...sequence,...spot?.playback_overrides?.[config.active_character]?.[role]};};
 if(mode==='current')return [sequenceFor(action.animation)].filter(Boolean);
 if(mode==='specific')return [sequenceFor(action.animation,room.interaction_spots?.find(s=>s.id===action.spot_id))].filter(Boolean);
 return choices.map(p=>sequenceFor(p.role,p.spot)).filter(Boolean);
}
function renderIntegrationLoopDuration(card,action){
 const sequences=integrationPlaybackChoices(action),looping=sequences.some(s=>['loop','ping_pong'].includes(playbackMode(s)));
 if(looping){const line=integrationNode('div');line.style.cssText='display:flex;align-items:center;gap:8px;flex-wrap:wrap';const input=integrationInput(action.duration_seconds??0,v=>action.duration_seconds=Math.max(0,Math.min(120,Number(v)||0)),'number');input.min=0;input.max=120;input.style.width='75px';integrationField(line,'Loop duration override (seconds; 0 = one cycle)',input);line.append(integrationNode('span',sequences.some(s=>!['loop','ping_pong'].includes(playbackMode(s)))?'Applies only when the chosen placement loops. Finite animations finish normally.':'Milestone events play one complete cycle by default; an override repeats for the chosen time.'));card.append(line);}
 else if(sequences.length)card.append(integrationNode('p','Playback: '+(sequences.length===1?(playbackMode(sequences[0])==='once'?'play once':'play '+(sequences[0].repeat_count||2)+' times'):'configured finite playback')+' — finishes before the next event.'));
}
const integrationPickerState=new WeakMap();
function selectIntegrationPlacement(action,scene,placement){
 const {spot,role}=placement;Object.assign(action,{scene,animation:role,spot_id:spot.id,x:spot.x,y:spot.y,facing:spot.facing||'right',target_mode:'specific'});delete action.target_scene;
}
function renderIntegrationTarget(card,action){
 const atCurrent=action.target_mode==='current';
 const targets=integrationNode('div');targets.style.cssText='display:flex;gap:8px;margin:10px 0';
 const here=integrationButton('Where the character is',()=>{action.target_mode='current';for(const key of ['scene','target_scene','spot_id','x','y','target_prop'])delete action[key];renderActionPane();});if(atCurrent)here.classList.add('btn-primary');
 const placed=integrationButton('Saved scene / location',()=>{action.target_mode='gesture';action.scene=currentSceneId();renderActionPane();});if(!atCurrent)placed.classList.add('btn-primary');targets.append(here,placed);card.append(targets);
 if(atCurrent){const catalog=actionPoseCatalog({scene:currentSceneId()});integrationField(card,'Animation here',integrationSelect(Object.keys(catalog).filter(role=>!role.startsWith('walk')).map(role=>[role,poseLabel(role)]),action.animation||'',v=>{action.animation=v;renderActionPane();}));integrationField(card,'Facing / mirror',integrationSelect([['','Keep the character’s facing'],['left','Left · mirrored'],['right','Right · original']],action.facing||'',v=>{if(v)action.facing=v;else delete action.facing;renderActionPane();}));card.append(integrationNode('p','Uses the character’s position and scene when this reaction starts. No saved placement is required.'));renderIntegrationLoopDuration(card,action);return;}
 const state=integrationPickerState.get(action)||{scene:actionSceneId(action),filter:''};integrationPickerState.set(action,state);
 const scenes=Object.entries(config.scenes||{}).filter(([,s])=>s.enabled!==false);
 if(!scenes.some(([id])=>id===state.scene))state.scene=scenes[0]?.[0]||actionSceneId(action);
 const tray=integrationNode('div');tray.style.cssText='display:flex;gap:8px;overflow:auto;margin:10px 0';
 const background=(id,room)=>'/assets/themes/'+encodeURIComponent(room.theme||id)+'/'+encodeURIComponent(room.background||'background.jpg');
 for(const [id,room]of scenes){const button=integrationButton('',()=>{state.scene=id;state.filter='';renderActionPane();});button.style.cssText='min-width:125px;width:125px;flex-shrink:0;display:flex;flex-direction:column;white-space:normal;padding:4px;border:2px solid '+(id===state.scene?'#ffb34d':'#555');const img=document.createElement('img');img.src=background(id,room);img.style.cssText='width:100%;aspect-ratio:16/9;object-fit:cover;display:block';button.append(img,integrationNode('span',room.name||id));tray.append(button);}card.append(tray);
 const probe={scene:state.scene},room=actionSceneData(probe),catalog=actionPoseCatalog(probe),placements=integrationPlacements(probe),roles=[...new Set(placements.map(p=>p.role))];
 integrationField(card,'Show gestures',integrationSelect([['','All placed gestures'],...roles.map(role=>[role,poseLabel(role)])],state.filter,v=>{state.filter=v;renderActionPane();}));
 const shown=placements.filter(p=>!state.filter||p.role===state.filter);
 const selected=placements.find(p=>actionSceneId(action)===state.scene&&p.spot.id===action.spot_id&&p.role===action.animation);
 card.append(integrationNode('p','Click a character or its location button to choose it. Browsing scenes and filtering does not change the saved mapping.'));
 const canvas=document.createElement('canvas');canvas.width=1280;canvas.height=720;canvas.style.cssText='width:100%;display:block;aspect-ratio:16/9;background:#141120;border-radius:6px;cursor:pointer';canvas.setAttribute('aria-label','Saved gesture placements in '+(config.scenes?.[state.scene]?.name||state.scene));card.append(canvas);
 const ctx=canvas.getContext('2d'),bg=new Image(),images=new Map(),hits=[];
 const draw=()=>{
  ctx.clearRect(0,0,1280,720);if(bg.complete&&bg.naturalWidth)ctx.drawImage(bg,0,0,1280,720);hits.length=0;
  for(const [i,p]of shown.entries()){
   const frame=catalog[p.role],img=images.get(p),crop=frame?.crop||[0,0,img?.naturalWidth||360,img?.naturalHeight||560];
   let h=floorPerspectiveHeight(room.walkable_trapezoid||config.walkable_trapezoid,p.spot.y);if(frame?.reference_height)h*=crop[3]/frame.reference_height;const w=h*crop[2]/crop[3],x=p.spot.x-w/2,y=p.spot.y-h;
   ctx.save();ctx.globalAlpha=selected===p?1:.7;if(img?.complete&&img.naturalWidth){ctx.translate(p.spot.x,y);if(p.spot.facing!=='right')ctx.scale(-1,1);ctx.drawImage(img,...crop,-w/2,0,w,h);}ctx.restore();
   ctx.strokeStyle=selected===p?'#ffdd00':'#00d8ee';ctx.lineWidth=4;ctx.beginPath();ctx.ellipse(p.spot.x,p.spot.y,22,10,0,0,Math.PI*2);ctx.stroke();
   ctx.fillStyle='#171525';ctx.fillRect(p.spot.x-18,p.spot.y-37,36,24);ctx.fillStyle='white';ctx.font='bold 20px sans-serif';ctx.textAlign='center';ctx.fillText(String(i+1),p.spot.x,p.spot.y-18);
   hits.push({p,x,y,w,h});
  }
 };
 bg.onload=draw;bg.src=background(state.scene,config.scenes?.[state.scene]||{});
 for(const p of shown){const img=new Image();img.onload=draw;img.src=catalog[p.role].url;images.set(p,img);}draw();
 canvas.onclick=e=>{const rect=canvas.getBoundingClientRect(),x=(e.clientX-rect.left)*1280/rect.width,y=(e.clientY-rect.top)*720/rect.height;const hit=[...hits].reverse().find(h=>x>=h.x&&x<=h.x+h.w&&y>=h.y&&y<=h.y+h.h+12);if(hit){selectIntegrationPlacement(action,state.scene,hit.p);renderActionPane();}};
 const choices=integrationNode('div');choices.style.cssText='display:flex;gap:6px;flex-wrap:wrap;margin:8px 0';
 shown.forEach((p,i)=>{const b=integrationButton((i+1)+'. '+poseLabel(p.role)+' · '+(p.spot.name||p.spot.id),()=>{selectIntegrationPlacement(action,state.scene,p);renderActionPane();});if(selected===p)b.classList.add('btn-primary');choices.append(b);});card.append(choices);
 if(!shown.length)card.append(integrationNode('p','No saved placements here. Add gestures in the Pose Stager.'));
 card.append(integrationButton(state.filter?'Use this gesture at any matching location':'Use any shown gesture and location',()=>{action.scene=state.scene;delete action.target_scene;delete action.spot_id;delete action.x;delete action.y;action.target_mode=state.filter?'gesture':'any';if(state.filter)action.animation=state.filter;renderActionPane();}));
 if(action.spot_id)card.append(integrationButton('Use any gesture at selected location',()=>{action.target_mode='location';renderActionPane();}));
 const sceneName=config.scenes?.[actionSceneId(action)]?.name||actionSceneId(action),spot=actionSceneData(action).interaction_spots?.find(s=>s.id===action.spot_id),mode=action.target_mode||'specific';
 card.append(integrationNode('p','Mapping: '+sceneName+' → '+(['any','location'].includes(mode)?'any matching gesture':poseLabel(action.animation||'idle'))+' → '+(['any','gesture'].includes(mode)?'any matching location':spot?.name||action.spot_id||'saved coordinates')));
 renderIntegrationLoopDuration(card,action);
}
function renderIntegrationButton(pane,app){
 const card=integrationNode('div',undefined,'editor-card');card.append(integrationNode('h3','Physical button response'));
 integrationField(card,'Hardware button',integrationSelect([['0','No hardware button'],...['2','3','4','5'].map(n=>[n,'Button '+n])],String(app.switch_id||0),v=>updateAppProperty('switch_id',Number(v))));
 if(!app.actions) app.actions = [];
 let action=(app.actions||[]).find(a=>a.is_primary||(selectedActionId&&a.id===selectedActionId)||a.id==='status_check') || app.actions[0];
 if(app.actions.length > 0){
  if(app.actions.length > 1){
   integrationField(card,'Action triggered by button',integrationSelect(
    app.actions.map(a=>[a.id,(a.label||a.id)+(a.is_primary?' ★ [Active Button Action]':'')]),
    action?.id||'',
    v=>{
     app.actions.forEach(a=>{a.is_primary=(a.id===v);});
     selectedActionId=v;
     renderActionPane();
    }
   ));
  }
  if(action){
   selectedActionId=action.id;
   renderIntegrationTarget(card,action);
   renderIntegrationPlayback(card,action);
  }
 } else {
  card.append(integrationNode('p','No button response action is configured for this application yet.'));
  card.append(integrationButton('+ Create Button Action & 5" Dashboard Popup',()=>{
   const act={
    id:'status_check',
    label:(app.name||app.id)+' Status',
    event:'status_check',
    is_primary:true,
    display_mode:'popup_modal',
    target_mode:'specific',
    scene:currentSceneId(),
    animation:app.id==='deskpal_weather'?'window_look':'inspect',
    spot_id:app.id==='deskpal_weather'?'window':'',
    speech:'{summary}',
    dashboard:{
     hero_value:app.id==='deskpal_weather'?'24°C':'OK',
     hero_subhead:app.id==='deskpal_weather'?'Sunny · Rain 0%':'Status check',
     badge:app.id==='deskpal_weather'?'FINE':'ACTIVE',
     badge_color:'#2ecc71',
     tiles:app.id==='deskpal_weather'?[
      {label:'MIN / MAX',value:'16° / 26°'},
      {label:'RAIN',value:'0%'},
      {label:'UV INDEX',value:'6 (Mod)'},
      {label:'WIND',value:'15 km/h'}
     ]:[
      {label:'STATUS',value:'Nominal'},
      {label:'MODE',value:'Ready'}
     ]
    }
   };
   app.actions.push(act);
   selectedActionId=act.id;
   saveConfigToPi();
   renderActionPane();
  }));
 }
 card.append(integrationButton('Save button settings',saveConfigToPi));pane.append(card);
}
function integrationPlacementUsers(cfg,scene,spot,role){
 return (cfg.apps||[]).flatMap(app=>(app.actions||[]).filter(action=>{
  const targetScene=action.scene||action.target_scene;if(targetScene&&targetScene!==scene)return false;
  const mode=action.target_mode||'specific';
  if(mode==='current')return false;
  if(mode==='any')return true;
  if(mode==='location')return action.spot_id===spot.id;
  if((action.animation==='idle'?'idle_side':action.animation)!==(role==='idle'?'idle_side':role))return false;
  if(mode==='gesture')return true;
  return action.spot_id===spot.id||(!action.spot_id&&action.x===spot.x&&action.y===spot.y);
 }).map(action=>(app.name||app.id)+' / '+(action.label||action.id)));
}
function integrationAnimationUsers(cfg,role){
 const normalized=role==='idle'?'idle_side':role;
 return [...new Set((cfg.apps||[]).flatMap(app=>(app.actions||[]).filter(action=>{
  if(!['any','location'].includes(action.target_mode))return (action.animation==='idle'?'idle_side':action.animation)===normalized;
  return Object.entries(cfg.scenes||{}).some(([scene,room])=>(!action.scene&&!action.target_scene||scene===(action.scene||action.target_scene))&&(room.interaction_spots||[]).some(spot=>(action.target_mode!=='location'||spot.id===action.spot_id)&&[spot.animation,...spot.animations||[]].some(r=>(r==='idle'?'idle_side':r)===normalized)));
 }).map(action=>(app.name||app.id)+' / '+(action.label||action.id))))];
}
let eligibilitySaveQueue=Promise.resolve();
function saveAnimationEligibility(sequence,key,value){
 sequence[key]=value;
 const id=Object.keys(config.animation_sequences||{}).find(id=>config.animation_sequences[id]===sequence);
 eligibilitySaveQueue=eligibilitySaveQueue.catch(()=>{}).then(async()=>{
  const res=await fetch('/api/config');if(!res.ok)throw Error('Could not read saved animation settings');
  const cfg=await res.json();if(!cfg.animation_sequences?.[id])throw Error('Animation no longer exists');
  cfg.animation_sequences[id][key]=value;
  const saved=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({animation_sequences:cfg.animation_sequences})});
  if(!saved.ok)throw Error('Could not save animation choice');
  document.getElementById('statusMsg').textContent='Animation choice saved to Pi.';
 }).catch(e=>{document.getElementById('statusMsg').textContent='Animation choice NOT saved: '+e.message;});
 renderUnusedIdleRefresh();
}
function renderUnusedIdle(pane){
 const card=integrationNode('div',undefined,'editor-card');card.append(integrationNode('h3','Unused animations & idle'),integrationNode('p','Saved locations not covered by any application event or button mapping appear first. Flexible “any” mappings count as using every matching placement. Mapped animations are reserved for their application events and buttons, across all scenes. Only unmapped animations enabled for idle can run when the event queue is empty. Checkbox changes save immediately.'));
 card.append(integrationNode('p','Character: '+(config.active_character||'none')),integrationNode('p','Sleep cycles through reachable resting placements across connected scenes. It settles there before turning the screen off, then gets up from that spot on wake. Incoming reactions wait in the queue while asleep.'));
 const groups=new Map();
 for(const [scene,room]of Object.entries(config.scenes||{})){
  if(room.enabled===false)continue;
  for(const placement of integrationPlacements({scene})){
   const {spot,role}=placement,bindings=config.characters?.[config.active_character]?.animations||{},sequence=config.animation_sequences?.[bindings[role==='idle'?'idle_side':role]||bindings[role]];
   if(!groups.has(role))groups.set(role,{role,sequence,placements:[]});
   groups.get(role).placements.push({scene,room,spot,users:integrationPlacementUsers(config,scene,spot,role)});
  }
 }
 const sorted=[...groups.values()].sort((a,b)=>Number(b.placements.some(p=>!p.users.length))-Number(a.placements.some(p=>!p.users.length))||a.role.localeCompare(b.role));
 for(const group of sorted){
  const row=integrationNode('div',undefined,'editor-card'),unused=group.placements.filter(p=>!p.users.length),sequence=group.sequence;
  row.append(integrationNode('h4',poseLabel(group.role)+' — '+unused.length+' unused / '+group.placements.length+' locations'));
  const check=document.createElement('input');check.type='checkbox';const reserved=integrationAnimationUsers(config,group.role);check.checked=!reserved.length&&(sequence?.idle_eligible??group.role.startsWith('idle'));check.disabled=!sequence||!!reserved.length;check.onchange=()=>saveAnimationEligibility(sequence,'idle_eligible',check.checked);integrationField(row,'Use while idle / no events',check);
  const sleep=document.createElement('input');sleep.type='checkbox';sleep.checked=sequence?.standby_eligible??['sleeping','sitting_rest','seated_back','deck_chair_rest'].includes(group.role);sleep.disabled=!sequence;sleep.onchange=()=>saveAnimationEligibility(sequence,'standby_eligible',sleep.checked);integrationField(row,'Use for sleep button',sleep);
  if(reserved.length)row.append(integrationNode('p','Reserved for applications; excluded from idle: '+reserved.join(', ')));
  if(!sequence)row.append(integrationNode('p','Save an animation sequence in the Animation Grid before enabling idle playback.'));
  for(const p of unused)row.append(integrationNode('p',(p.room.name||p.scene)+' → '+(p.spot.name||p.spot.id)+' (unused)'));
  const used=group.placements.filter(p=>p.users.length);if(used.length){const detail=document.createElement('details');detail.append(integrationNode('summary','Mapped locations ('+used.length+')'));for(const p of used)detail.append(integrationNode('p',(p.room.name||p.scene)+' → '+(p.spot.name||p.spot.id)+' · '+p.users.join(', ')));row.append(detail);}
  card.append(row);
 }
 if(!sorted.length)card.append(integrationNode('p','No saved animation placements for this character. Add placements in the Pose Stager.'));
 card.append(integrationButton('Save idle & sleep choices',saveConfigToPi));pane.append(card);
}
function renderUnusedIdleRefresh(){const pane=document.getElementById('actionMainPane');pane.replaceChildren();renderUnusedIdle(pane);}
function buildIntegrationApplication(definition,existing,scene,animation){
 if(definition.schema_version!==1||!definition.application||!Array.isArray(definition.events))throw Error('Use a version 1 Desk-Pal integration definition with application and events.');
 const input=definition.application,id=String(input.id||'');if(!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(id)||existing.some(a=>a.id===id))throw Error('Application ID must be unique and contain letters, numbers, underscores or hyphens.');
 if(definition.events.length>100)throw Error('Use at most 100 event definitions.');
 const adapter=String(input.adapter||(id==='wellness_check'?'wellness_check':(id==='fuel_tracker'?'fuel_tracker':'json')));
 const isWellness=adapter==='wellness_check',isFuel=adapter==='fuel_tracker',isSys=adapter==='system_monitor',isUptime=adapter==='uptime_ping',isHass=adapter==='home_assistant';
 const app={
  id,
  name:String(input.name||id),
  adapter:['system_monitor','uptime_ping','home_assistant','push'].includes(adapter)?'json':adapter,
  source_url:String(input.source_url||''),
  source_enabled:adapter==='push'?false:!!input.source_enabled,
  poll_seconds:isWellness?15:Math.max(5,Number(input.poll_seconds)||30),
  summary_field:String(input.summary_field||'summary'),
  monitor_health:input.monitor_health!==false,
  heartbeat_action_id:'__primary__',
  switch_id:0,
  color:isWellness?[56,189,248]:(isSys?[139,92,246]:(isUptime?[16,185,129]:(isHass?[3,169,244]:(isFuel?[247,37,133]:[0,229,255])))),
  actions:isWellness?[
    {id:'status_check',label:'Status / button response',event:'status_check',is_primary:true,scene,animation,target_mode:'any',duration_seconds:0,speech:'{summary}',display_mode:'popup_modal',modal_layout:'wellness'},
    {id:'wellness_reminder',label:'Wellness check reminder',event:'wellness_reminder',is_primary:false,scene,animation,target_mode:'any',duration_seconds:0,speech:'{wellness_message}',display_mode:'popup_modal',modal_layout:'wellness'}
  ]:[
    {id:'status_check',label:'Status / button response',event:'status_check',is_primary:true,scene,animation,target_mode:'any',duration_seconds:0,speech:'{summary}',display_mode:'popup_modal',modal_layout:input.modal_layout||'dashboard',dashboard:isSys?{hero_value:'{badge}',hero_subhead:'Raspberry Pi CPU Temp',badge:'STATUS'}:(isUptime?{hero_value:'{badge}',hero_subhead:'Ping Latency',badge:'ONLINE'}:(isHass?{hero_value:'{badge}',hero_subhead:'Home Assistant',badge:'HASS'}:undefined))}
  ],
  integration_events:[]
 };
 if(isWellness){
  app.settings={
    days_of_week:input.settings?.days_of_week||['mon','tue','wed','thu','fri'],
    start_time:input.settings?.start_time||'09:00',
    end_time:input.settings?.end_time||'17:00',
    interval_minutes:Number(input.settings?.interval_minutes)||45,
    absence_reset_minutes:Number(input.settings?.absence_reset_minutes)||30,
    voice_phrase:input.settings?.voice_phrase||'Hey pal, time for a stretch and some water!'
  };
  if(!definition.events.length){
    app.integration_events.push(
      {name:'wellness_reminder',label:'Wellness reminder notification'},
      {name:'water_goal_reached',label:'Hydration goal achieved'}
    );
  }
 }
 if(isFuel){
  app.settings={
    postcode:input.settings?.postcode||'4128',
    fuel_type:input.settings?.fuel_type||'u98',
    radius_km:Number(input.settings?.radius_km)||5
  };
 }
 for(const event of definition.events){
  if(!event||typeof event.name!=='string'||!event.name.trim()||event.name.length>80)throw Error('Each event needs a name of 1–80 characters.');
  if(app.integration_events.some(d=>d.name===event.name))throw Error('Event names must be unique.');
  app.integration_events.push({name:event.name,label:String(event.label||event.name),example:event.example&&typeof event.example==='object'?event.example:undefined});
 }
 return app;
}
async function importIntegrationFile(file){await openIntegrationPackagePanel(file);}
function showAddIntegration(){integrationNew=true;renderNewIntegration(document.getElementById('actionMainPane'));}
function renderNewIntegration(pane){
 pane.replaceChildren();const card=integrationNode('div',undefined,'editor-card');card.append(integrationNode('h3','Add application'),integrationNode('p','Import an integration definition, select an active companion script running on the Pi, or enter the details manually.'));
 const compBox=document.createElement('div');compBox.style.cssText='background:#181424;border:1px solid #f72585;border-radius:8px;padding:12px;margin:12px 0';compBox.innerHTML='<strong style="color:#f72585;font-size:0.85rem">⚡ Companion Scripts on Pi:</strong><div style="font-size:0.75rem;color:var(--text-dim);margin:3px 0 8px">Click to pre-fill connection settings from a local companion service:</div>';
 fetch('/api/services').then(r=>r.json()).then(data=>{const svcs=data.services||[];if(!svcs.length){compBox.remove();return;}const row=document.createElement('div');row.style.cssText='display:flex;gap:8px;flex-wrap:wrap';svcs.forEach(s=>{const btn=document.createElement('button');btn.className='btn';btn.type='button';btn.style.cssText='font-size:0.75rem;padding:4px 10px;background:#241f35;border:1px solid #f72585;color:#fff;cursor:pointer;display:flex;align-items:center;gap:6px';btn.innerHTML=`<span>⚡</span> <b>${s.name}</b> <span style="color:#00e5ff">(${s.port?':'+s.port:'push'})</span>`;btn.onclick=(e)=>{e.preventDefault();name.value=s.name;id.value=s.id;id.dataset.edited='1';url.value=s.port?`http://127.0.0.1:${s.port}/status`:'';if(s.id==='wellness_check'||s.port===8096)adapterSel.value='wellness_check';else if(s.id==='calendar'||s.port===8097)adapterSel.value='calendar';else if(s.id==='system_monitor'||s.port===8092)adapterSel.value='system_monitor';else if(s.id==='uptime_ping'||s.port===8093)adapterSel.value='uptime_ping';else if(s.id==='home_assistant'||s.port===8094)adapterSel.value='home_assistant';else if(s.id==='fuel_tracker')adapterSel.value='fuel_tracker';else if(s.id==='travel_radar'||s.id==='flight_radar'||s.port===8095)adapterSel.value='travel_radar';else adapterSel.value='json';};row.append(btn);});compBox.append(row);}).catch(()=>{compBox.remove();});card.append(compBox);
 const file=document.createElement('input');file.type='file';file.accept='.json,application/json';file.onchange=()=>importIntegrationFile(file.files[0]);integrationField(card,'Import integration file',file);
 const name=integrationInput('',()=>{}),id=integrationInput('',()=>{}),url=integrationInput('',()=>{},'url');name.oninput=()=>{if(!id.dataset.edited)id.value=name.value.toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'');};id.oninput=()=>id.dataset.edited='1';
 const adapterSel=integrationSelect([
   ['json','🌐 Generic REST API (Direct HTTP Polling)'],
   ['push','⚡ Webhook Receiver (Push to /api/v1/event)'],
   ['calendar','📅 Calendar & Daily Agenda (Port 8097)'],
   ['system_monitor','🖥️ Pi System & Hardware Monitor (Port 8092)'],
   ['uptime_ping','📡 Network & Uptime Ping Monitor (Port 8093)'],
   ['home_assistant','🏠 Home Assistant Entity Relay (Port 8094)'],
   ['wellness_check','💧 Desk Wellness & Hydration (Built-in Port 8096)'],
   ['fuel_tracker','⛽ Custom Relay: Fuel Tracker QLD'],
   ['travel_radar','✈️ Custom Relay: Travel Radar Deals'],
   ['bmcbf','🪙 Custom Relay: BMCBF Crypto Tracker']
 ],'json',v=>{
  if(v==='calendar'){name.value='Calendar & Agenda';id.value='calendar';url.value='http://127.0.0.1:8097/status';}else if(v==='wellness_check'){if(!name.value||name.value==='Fuel Tracker QLD'||name.value==='Travel Radar')name.value='Wellness & Hydration';if(!id.dataset.edited||id.value==='fuel_tracker'||id.value==='travel_radar')id.value='wellness_check';if(!url.value||url.value.includes(':8090')||url.value.includes(':8095'))url.value='http://127.0.0.1:8096/status';}
  else if(v==='system_monitor'){name.value='Pi System Monitor';id.value='system_monitor';url.value='http://127.0.0.1:8092/status';}
  else if(v==='uptime_ping'){name.value='Network Uptime';id.value='uptime_ping';url.value='http://127.0.0.1:8093/status';}
  else if(v==='home_assistant'){name.value='Home Assistant';id.value='home_assistant';url.value='http://127.0.0.1:8094/status';}
  else if(v==='fuel_tracker'){if(!name.value||name.value==='Wellness & Hydration'||name.value==='Travel Radar')name.value='Fuel Tracker QLD';if(!id.dataset.edited||id.value==='wellness_check'||id.value==='travel_radar')id.value='fuel_tracker';if(!url.value||url.value.includes(':8096')||url.value.includes(':8095'))url.value='http://127.0.0.1:8090/fuel';}
  else if(v==='travel_radar'){if(!name.value||name.value==='Wellness & Hydration'||name.value==='Fuel Tracker QLD')name.value='Travel Radar';if(!id.dataset.edited||id.value==='wellness_check'||id.value==='fuel_tracker')id.value='travel_radar';if(!url.value||url.value.includes(':8096')||url.value.includes(':8090'))url.value='http://127.0.0.1:8095/status';}
  else if(v==='push'){if(!name.value)name.value='Custom Webhook Receiver';if(!id.value)id.value='custom_webhook';url.value='';}
 });
 integrationField(card,'Application name',name);integrationField(card,'Application ID sent in events',id);integrationField(card,'Source format / Archetype',adapterSel);integrationField(card,'Optional JSON source URL',url);
 card.append(integrationButton('Add application',()=>{try{if(!name.value.trim())throw Error('Enter an application name.');const roles=Object.keys(characterPoseCatalog(config,spriteTags)),app=buildIntegrationApplication({schema_version:1,application:{id:id.value,name:name.value.trim(),adapter:adapterSel.value,source_url:url.value,source_enabled:adapterSel.value==='push'?false:!!url.value},events:[]},config.apps||[],currentSceneId(),roles.includes('idle_side')?'idle_side':roles[0]||'idle');config.apps||=[];config.apps.push(app);selectedAppId=app.id;selectedActionId='status_check';integrationNew=false;appStudioSection='connection';renderAppStudio();}catch(e){alert(e.message);}}),integrationButton('Cancel',()=>{integrationNew=false;renderAppStudio();}));pane.append(card);
}

async function openIntegrationPackagePanel(initialFile=null){
 document.getElementById('integrationPackagePanel')?.remove();
 const panel=integrationNode('div');panel.id='integrationPackagePanel';panel.style.cssText='position:fixed;inset:0;background:#000a;z-index:3000;display:flex;align-items:center;justify-content:center';
 const card=integrationNode('div');card.style.cssText='background:#211e30;color:#eee;width:850px;max-width:94vw;max-height:90vh;overflow:auto;padding:22px;border:1px solid #76728a;border-radius:8px';panel.append(card);document.body.append(panel);
 const add=(tag,text,parent=card)=>{const node=integrationNode(tag,text);parent.append(node);return node;};
 add('h2','Integration packages');add('p','Export event definitions, preferences and optional mappings. Connection URLs, credentials, private adapter settings, hardware assignments and received payloads are excluded. Save editor changes first.');
 card.append(integrationButton('Close',()=>panel.remove()));const tray=add('div','');tray.style.cssText='display:flex;gap:12px;flex-wrap:wrap';let saved=null;
 const status=add('p','Loading saved applications...');
 try{const response=await fetch('/api/config');if(!response.ok)throw Error('Could not read saved applications');saved=await response.json();for(const app of saved.apps||[]){const tile=add('div','',tray);tile.style.cssText='border:1px solid #666;padding:12px;width:180px';add('strong',app.name||app.id,tile);add('p',(app.integration_events?.length||0)+' defined events · '+(app.actions?.length||0)+' mappings',tile);const link=add('a','Export integration',tile);link.className='btn';link.href='/api/integration-packages/download?application='+encodeURIComponent(app.id);link.download=app.id+'-integration.json';}status.textContent='Select an integration definition or package to preview.';}catch(error){status.textContent=error.message;}
 add('h3','Import integration');const input=add('input','');input.type='file';input.accept='.json,application/json';let file=initialFile;if(file)add('p','Selected: '+file.name);
 add('p','Destination application ID: leave blank to use the file ID, or enter a new ID to add a copy.');const target=add('input','');target.placeholder='e.g. example_app';
 const mappingLabel=add('label','');const mappingCheck=document.createElement('input');mappingCheck.type='checkbox';mappingLabel.append(mappingCheck,document.createTextNode(' Include scene / animation / location mappings (replaces mappings for an existing application).'));
 const preview=add('button','Preview integration');const review=add('div','');const confirmLabel=add('label','');const confirmCheck=document.createElement('input');confirmCheck.type='checkbox';confirmLabel.append(confirmCheck,document.createTextNode(' Import the application and settings shown in this preview.'));confirmLabel.hidden=true;const apply=add('button','Import reviewed integration');apply.disabled=true;let details=null,query='';
 const invalidate=()=>{details=null;confirmCheck.checked=false;apply.disabled=true;confirmLabel.hidden=true;review.replaceChildren();};input.onchange=()=>{file=input.files[0];invalidate();};target.oninput=invalidate;mappingCheck.onchange=invalidate;confirmCheck.onchange=()=>apply.disabled=!confirmCheck.checked||!details||details.missing.length>0;
 const request=async(path,args)=>{const response=await fetch('/api/integration-packages/'+path+'?'+args,{method:'POST',headers:{'Content-Type':'application/json','X-Deskpal-Restore':'confirmed'},body:file});if(!response.ok)throw Error((await response.text()).replace(/<[^>]*>/g,' ').trim());return response.json();};
 preview.onclick=async()=>{invalidate();if(!file||file.size>1024*1024){status.textContent='Choose an integration JSON file smaller than 1 MB.';return;}preview.disabled=true;input.disabled=true;target.disabled=true;mappingCheck.disabled=true;status.textContent='Checking integration and mappings...';query='target='+encodeURIComponent(target.value.trim())+'&mappings='+(mappingCheck.checked?'1':'0');try{details=await request('preview',query);add('h3',(details.mode==='replace'?'Update saved application: ':'Add application: ')+details.name+' ('+details.target_application+')',review);const events=add('div','',review);events.style.cssText='display:flex;gap:6px;flex-wrap:wrap';for(const e of details.events){const chip=add('span',e.label+' · '+e.name,events);chip.style.cssText='padding:6px;background:#38344a;border-radius:5px';}if(details.include_mappings){const maps=add('div','',review);maps.style.cssText='display:flex;gap:8px;flex-wrap:wrap';for(const mapping of details.mappings){const tile=add('div','',maps);tile.style.cssText='padding:10px;border:1px solid #666;width:220px';const scene=mapping.scene||mapping.target_scene,room=saved?.scenes?.[scene];if(room){const image=add('img','',tile);image.src='/assets/themes/'+encodeURIComponent(room.theme||scene)+'/'+(room.background||'background.jpg');image.alt=room.name||scene;image.style.width='100%';}add('strong',mapping.label||mapping.id,tile);add('p',(scene||'Any scene')+' → '+(mapping.animation||'Any animation')+' → '+(mapping.spot_id||'Any matching location'),tile);}}const preferences=add('details','',review);add('summary','Imported preferences',preferences);add('pre',JSON.stringify(details.preferences,null,2),preferences).style.cssText='white-space:pre-wrap;overflow-wrap:anywhere';if(details.include_mappings){const settings=add('details','',review);add('summary','Mapping conditions and playback settings',settings);add('pre',JSON.stringify(details.mappings,null,2),settings).style.cssText='white-space:pre-wrap;overflow-wrap:anywhere';}for(const note of details.notes)add('p',note,review);for(const missing of details.missing)add('p','Cannot import mappings: '+missing,review).style.color='#ffad75';confirmLabel.hidden=false;status.textContent='Preview ready. Nothing has changed. Importing saves to the Pi; unsaved editor changes are not included.';}catch(error){status.textContent=error.message;}preview.disabled=false;input.disabled=false;target.disabled=false;mappingCheck.disabled=false;};
 apply.onclick=async()=>{if(!details||!confirmCheck.checked||details.missing.length)return;apply.disabled=true;preview.disabled=true;input.disabled=true;target.disabled=true;mappingCheck.disabled=true;status.textContent='Saving recovery backup and importing integration...';try{const result=await request('import',query+'&digest='+encodeURIComponent(details.digest)+'&state='+encodeURIComponent(details.state_digest));status.textContent='Integration imported. Reload the editor to configure its connection, events and button. A recovery backup was saved.';const link=add('a','Download recovery backup');link.href='/api/backups/recovery?name='+encodeURIComponent(result.recovery_backup);card.append(integrationButton('Reload editor',()=>location.reload()));}catch(error){status.textContent=error.message;preview.disabled=false;input.disabled=false;target.disabled=false;mappingCheck.disabled=false;}details=null;};
}
