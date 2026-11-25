async function openSystemHealth(){
 const response=await fetch('/api/config');if(!response.ok)return alert('Could not load system health settings');
 const saved=await response.json(),cfg=saved.system_health||{};
 const overlay=document.createElement('div');overlay.id='systemHealthPanel';overlay.style.cssText='position:fixed;inset:0;background:#0009;z-index:6500;display:flex;align-items:center;justify-content:center';
 const card=document.createElement('div');card.style.cssText='background:#25253c;color:#eee;padding:22px;width:440px;max-width:90vw;border-radius:10px';overlay.append(card);
 const add=(tag,text)=>{const node=document.createElement(tag);node.textContent=text||'';if(tag==='button'){node.className='btn';node.style.cssText='margin:8px 6px 0 0;padding:8px 12px';}card.append(node);return node;};
 add('h2','Pi connectivity');add('p','Background checks continue while notifications are displayed. Three failed checks trigger an alert; two successful checks clear it.');
 const label=add('label','Enable connectivity monitoring '),enabled=document.createElement('input');enabled.type='checkbox';enabled.checked=cfg.enabled!==false;label.append(enabled);
 const modeLabel=add('label','Alert behaviour '),mode=document.createElement('select');modeLabel.append(mode);
 for(const [value,text]of [['once','Notify once'],['until_acknowledged','Until acknowledged'],['until_restored','Until connection restored']])mode.add(new Option(text,value));mode.value=cfg.alert_mode||'until_acknowledged';
 modeLabel.style.cssText='display:block;margin:14px 0';
 add('p','Until restored resumes the alert after its popup is dismissed while the outage continues. Normal events remain queued. Sleep still works.');
 const secondsLabel=add('label','Check interval (seconds) '),seconds=document.createElement('input');seconds.type='number';seconds.min=15;seconds.max=3600;seconds.required=true;seconds.value=cfg.interval_seconds||30;secondsLabel.append(seconds);
 const status=add('p');status.setAttribute('role','status');
 const refresh=async()=>{try{const r=await fetch('/api/system-health');const state=await r.json();status.textContent='Status: '+(state.enabled===false?'disabled':state.status)+(state.checked_at?' · last check '+new Date(state.checked_at*1000).toLocaleTimeString():'');}catch(error){status.textContent='Unable to read connectivity status';}};
 add('button','Refresh status').onclick=refresh;
 add('button','Save settings').onclick=async()=>{if(!seconds.checkValidity()){status.textContent='Choose 15–3600 seconds';return;}const system_health={enabled:enabled.checked,alert_mode:mode.value,interval_seconds:Number(seconds.value)};try{const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({system_health})});if(!r.ok)throw Error('Could not save settings');config.system_health=system_health;status.textContent='Saved';}catch(error){status.textContent=error.message;}};
 add('button','Close').onclick=()=>overlay.remove();document.body.append(overlay);await refresh();
}
