// Browser display of frames produced by the existing Pygame renderer in local mode.
let livePreviewTimer=null,livePreviewOpen=false;
async function openLivePreview(){
 try{
 const response=await fetch('/api/preview/status');if(!response.ok)throw Error('Start the local preview server first.');const capabilities=await response.json();if(!capabilities.enabled)throw Error('Live preview is available on the local PC installation.');
 document.getElementById('livePreviewPanel')?.remove();clearTimeout(livePreviewTimer);livePreviewOpen=true;
 const panel=document.createElement('div');panel.id='livePreviewPanel';panel.style.cssText='position:fixed;inset:0;background:#111e;z-index:2900;overflow:auto;padding:16px';document.body.append(panel);
 const add=(tag,text,parent=panel)=>{const n=document.createElement(tag);n.textContent=text;parent.append(n);return n;};
 const bar=add('div','');bar.style.cssText='display:flex;align-items:center;gap:10px;flex-wrap:wrap';add('strong','Local live preview',bar);add('span','Uses saved local settings. Save edits before previewing.',bar);
 const close=add('button','Return to editor',bar);close.className='btn';close.onclick=()=>{livePreviewOpen=false;clearTimeout(livePreviewTimer);panel.remove();};
 const status=add('p','Connecting to renderer...');const screen=add('img','');screen.alt='Live Desk-Pal screen';screen.style.cssText='display:block;width:min(100%,1280px);height:auto;aspect-ratio:16/9;background:black;cursor:pointer';
 const input=async(command)=>{const r=await fetch('/api/preview/input',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(command)});if(!r.ok)throw Error((await r.text()).replace(/<[^>]*>/g,' ').trim());};
 screen.onclick=async e=>{const rect=screen.getBoundingClientRect();try{await input({kind:'touch',x:Math.min(capabilities.width-1,Math.max(0,(e.clientX-rect.left)*capabilities.width/rect.width)),y:Math.min(capabilities.height-1,Math.max(0,(e.clientY-rect.top)*capabilities.height/rect.height))});}catch(error){status.textContent=error.message;}};
 let lost=0;const next=()=>{if(livePreviewOpen)livePreviewTimer=setTimeout(()=>screen.src='/api/preview/frame?t='+Date.now(),120);};screen.onload=()=>{lost=0;status.textContent='Live · tap the character to interact or dismiss a popup. Closing this view leaves the local renderer running.';next();};screen.onerror=()=>{lost++;status.textContent='Renderer unavailable. Check the local preview log.';if(lost<10)next();};screen.src='/api/preview/frame?t='+Date.now();
 const buttons=add('div','');buttons.style.cssText='display:flex;gap:8px;flex-wrap:wrap;margin:12px 0';
 const cfgResponse=await fetch('/api/config');if(!cfgResponse.ok)throw Error('Cannot read local settings');const cfg=await cfgResponse.json();
 for(let id=1;id<=5;id++){const assigned=(cfg.apps||[]).find(a=>a.switch_id===id);const b=add('button',id===1?'Sleep / wake':assigned?.name||'Button '+id,buttons);b.className='btn';b.onclick=async()=>{try{await input({kind:'switch',switch:id});}catch(error){status.textContent=error.message;}};}
 add('h3','Send a simulated event');add('p','These events go only to this local Desk-Pal. They do not query or run external applications.');
 const controls=add('div','');controls.style.cssText='display:flex;gap:8px;flex-wrap:wrap';const appChoice=add('select','',controls),eventChoice=add('select','',controls);
 const payload=add('textarea','');payload.style.cssText='display:block;width:min(100%,900px);height:110px;margin:8px 0';payload.setAttribute('aria-label','Simulated event JSON');
 for(const app of cfg.apps||[]){const option=add('option',app.name||app.id,appChoice);option.value=app.id;}
 const definitions=()=>{const app=(cfg.apps||[]).find(a=>a.id===appChoice.value);const events=new Map((app?.integration_events||[]).map(e=>[e.name,e]));for(const a of app?.actions||[])if(a.event&&!a.is_primary)events.set(a.event,events.get(a.event)||{name:a.event,label:a.label||a.event});events.set('heartbeat',events.get('heartbeat')||{name:'heartbeat',label:'Heartbeat'});return [...events.values()];};
 const updatePayload=()=>{const event=definitions().find(e=>e.name===eventChoice.value);payload.value=JSON.stringify({...event?.example,app_id:appChoice.value,event:eventChoice.value,status:'healthy',summary:'Local preview test: '+(event?.label||eventChoice.value)},null,2);};
 const updateEvents=()=>{eventChoice.replaceChildren();for(const event of definitions()){const option=add('option',event.label||event.name,eventChoice);option.value=event.name;}updatePayload();};appChoice.onchange=updateEvents;eventChoice.onchange=updatePayload;updateEvents();
 const send=add('button','Send test event');send.className='btn btn-primary';send.disabled=!(cfg.apps||[]).length;send.onclick=async()=>{try{const body=JSON.parse(payload.value);if(body.app_id!==appChoice.value||body.event!==eventChoice.value)throw Error('Keep app_id and event matched to the selections.');const r=await fetch(body.event==='heartbeat'?'/api/v1/heartbeat':'/api/v1/event',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw Error((await r.text()).replace(/<[^>]*>/g,' ').trim());status.textContent='Simulated event sent to the local queue.';}catch(error){status.textContent=error.message;}};
 }catch(error){alert(error.message);}
}
async function discoverLocalPreview(){
 try{const response=await fetch('/api/preview/status');if(!response.ok)return;const status=await response.json();if(!status.enabled)return;globalThis.deskpalLocalPreview=true;const b=document.getElementById('btnLivePreview');if(b)b.hidden=false;const save=document.getElementById('btnSave');if(save){save.textContent='Save locally';save.title='Save to the isolated PC installation';}const label=document.getElementById('statusMsg');if(label)label.textContent='Local installation · Pi settings are separate';}catch(error){}
}
discoverLocalPreview();
