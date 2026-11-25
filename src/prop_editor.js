// Image prop library and scene placements. Metadata is independent of character sequences.
let selectedImageProp='',propLibraryId='',gridActivePropId='',propPreviewPlaying=true,propPreviewStarted=performance.now(),propPreviewElapsed=0,propDrag=null;
const propImages=new Map();

function propFrameIndex(seq,elapsed){
 const n=seq.frames?.length||0;if(!n)return -1;let t=Math.max(0,Math.floor(elapsed*Math.max(1,Math.min(60,Number(seq.fps)||4))));
 if(seq.playback_mode==='once')return Math.min(t,n-1);
 if(seq.playback_mode==='repeat'&&t>=n*Math.max(1,Number(seq.repeat_count)||1))return n-1;
 if(seq.playback_mode==='ping_pong'&&n>1){t%=2*n-2;return t<n?t:2*n-2-t;}return t%n;
}
function propImage(url){if(!propImages.has(url)){const img=typeof Image!=='undefined'?new Image():{};if(img.onload&&typeof render==='function')img.onload=()=>render();img.src=url;propImages.set(url,img);}return propImages.get(url);}
function imageProp(){return (typeof config!=='undefined'?(config.props||[]):[]).find(p=>p.id===selectedImageProp);}
function propTime(){return (propPreviewPlaying?performance.now()-propPreviewStarted:propPreviewElapsed)/1000;}
function togglePropPlayback(){if(propPreviewPlaying)propPreviewElapsed=performance.now()-propPreviewStarted;else propPreviewStarted=performance.now()-propPreviewElapsed;propPreviewPlaying=!propPreviewPlaying;const b=typeof document!=='undefined'?document.getElementById('propPlay'):null;if(b)b.textContent=propPreviewPlaying?'Pause':'Play';if(typeof render==='function')render();}
function restartPropPreview(){propPreviewElapsed=0;propPreviewStarted=performance.now();if(typeof render==='function')render();}

function getAllSceneProps(cfg=(typeof config!=='undefined'?config:{})){
 const list=[];const seen=new Set();const curScene=cfg?.active_scene||'current';
 for(const p of (cfg?.props||[])){
  const key=`${curScene}:${p.id}`;if(!seen.has(key)){seen.add(key);const sceneName=cfg?.scenes?.[curScene]?.name||curScene;list.push({...p,sceneId:curScene,sceneName});}
 }
 for(const [sId,s] of Object.entries(cfg?.scenes||{})){
  for(const p of (s.props||[])){
   const key=`${sId}:${p.id}`;if(!seen.has(key)){seen.add(key);list.push({...p,sceneId:sId,sceneName:s.name||sId});}
  }
 }
 return list;
}

function refreshImageProps(){
 if(typeof document==='undefined')return;
 const select=document.getElementById('imagePropPlacement');
 const allProps=config.props||[];
 if(select){
  select.replaceChildren(new Option('Select a placed prop ('+allProps.length+' in scene)',''),...allProps.map(p=>{
   const tag=p.interaction==='tv'?' [📺 TV Easter Egg]':(p.screen_quad?' [🖥️ Screen]':' [🖼️ Prop]');
   return new Option((p.label||p.id)+tag,p.id);
  }));
  if(selectedImageProp&&!allProps.some(p=>p.id===selectedImageProp))selectedImageProp=allProps[0]?.id||'';
  select.value=selectedImageProp;
 }
 const library=document.getElementById('imagePropLibrary');
 if(library)library.replaceChildren(...Object.entries(config.prop_animations||{}).map(([id,a])=>new Option(a.name||id,id)));
 const p=imageProp();
 const fields=document.getElementById('imagePropFields');
 if(fields)fields.hidden=!p;
 if(!p)return;
 for(const key of ['width','rotation','layer','trigger','depth_y']){const el=document.getElementById('ip_'+key);if(el)el.value=p[key]??(key==='depth_y'?p.y:'');}
 const tod=document.getElementById('ip_time_of_day');if(tod)tod.value=p.time_of_day||'both';
 const interaction=p.interaction||'none';
 const act=document.getElementById('ip_interaction');if(act)act.value=interaction;
 const tvNotice=document.getElementById('ip_tv_notice');if(tvNotice)tvNotice.hidden=(interaction!=='tv');
 const tapAnimFields=document.getElementById('ip_tap_anim_fields');if(tapAnimFields)tapAnimFields.hidden=(interaction!=='trigger_animation');
 const tapAnimSelect=document.getElementById('ip_tap_animation');
 if(tapAnimSelect){
  tapAnimSelect.replaceChildren(new Option('Choose animation to trigger on tap',''),...Object.entries(config.prop_animations||{}).map(([id,a])=>new Option(a.name||id,id)));
  tapAnimSelect.value=p.tap_animation||p.animation_id||'';
 }
 const appActionFields=document.getElementById('ip_app_action_fields');if(appActionFields)appActionFields.hidden=(interaction!=='app_action');
 const appSelect=document.getElementById('ip_app_id');
 const apps=config.integrations||[];
 if(appSelect){
  appSelect.replaceChildren(new Option('Select Application...',''),...apps.map(app=>new Option(app.name||app.id,app.id)));
  appSelect.value=p.app_id||(apps[0]?.id||'');
 }
 refreshPropAppActions();
 const gameScriptFields=document.getElementById('ip_game_script_fields');if(gameScriptFields)gameScriptFields.hidden=(interaction!=='game_script');
 const gameSelect=document.getElementById('ip_game_id');if(gameSelect)gameSelect.value=p.game_id||'retro_tv';
 const spots=document.getElementById('ip_typing_spot_id');if(spots){spots.replaceChildren(new Option('Choose typing location',''),...(config.interaction_spots||[]).filter(s=>s.animation==='typing'||s.animations?.includes('typing')).map(s=>new Option(s.name||s.id,s.id)));spots.value=p.typing_spot_id||'';}
 const poseSpots=document.getElementById('ip_pose_spot_id');if(poseSpots){poseSpots.replaceChildren(new Option('Choose pose location',''),...(config.interaction_spots||[]).map(s=>new Option(s.name||s.id,s.id)));poseSpots.value=p.pose_spot_id||'';}
 refreshPropPoseRoles();
 const poseAnim=document.getElementById('ip_pose_animation');if(poseAnim)poseAnim.value=p.pose_animation||'';
 const poseFields=document.getElementById('ip_pose_fields');if(poseFields)poseFields.hidden=p.trigger!=='pose';
 if(spots)spots.hidden=p.trigger!=='typing';
 const screenHint=document.getElementById('ip_screen_hint');if(screenHint)screenHint.hidden=!p.screen_quad;
 const tray=document.getElementById('ip_animation_choices');
 if(tray){
  tray.replaceChildren();
  const activeChoices=p.animation_ids||(p.animation_id?[p.animation_id]:[]);
  for(const [id,a] of Object.entries(config.prop_animations||{})){
   const label=document.createElement('label');label.style='display:block';
   const check=document.createElement('input');check.type='checkbox';check.checked=activeChoices.includes(id);
   check.onchange=()=>{
    const choices=p.animation_ids||(p.animation_id?[p.animation_id]:[]);
    p.animation_ids=check.checked?[...new Set([...choices,id])]:choices.filter(x=>x!==id);
    if(!p.animation_ids.length&&p.animation_id)p.animation_ids=[p.animation_id];
    if(p.animation_ids.length)p.animation_id=p.animation_ids[0];
    refreshImageProps();restartPropPreview();
   };
   label.append(check,document.createTextNode(' '+a.name));tray.append(label);
  }
 }
 const hideInactive=document.getElementById('ip_hide_when_inactive');if(hideInactive)hideInactive.checked=!!p.hide_when_inactive;
 const labelInput=document.getElementById('ip_label');if(labelInput)labelInput.value=p.label||'';
}

function updateImageProp(){
 const p=imageProp();if(!p)return;
 for(const k of ['width','rotation','depth_y']){const el=document.getElementById('ip_'+k);if(el){const n=Number(el.value);if(Number.isFinite(n))p[k]=k==='width'?Math.max(4,Math.min(1280,n)):n;}}
 for(const k of ['label','layer','trigger','typing_spot_id','pose_spot_id','pose_animation','time_of_day','interaction','tap_animation','app_id','action_id','game_id']){const el=document.getElementById('ip_'+k);if(el)p[k]=el.value;}
 const hideInactive=document.getElementById('ip_hide_when_inactive');if(hideInactive)p.hide_when_inactive=hideInactive.checked;
 refreshImageProps();if(typeof render==='function')render();
}
function refreshPropAppActions(){
 if(typeof document==='undefined')return;
 const p=imageProp();
 const appId=document.getElementById('ip_app_id')?.value||p?.app_id;
 const actionSelect=document.getElementById('ip_action_id');if(!actionSelect)return;
 const app=(config.integrations||[]).find(a=>a.id===appId);
 const actions=app?.actions||[];
 actionSelect.replaceChildren(new Option('Select Action...',''),...actions.map(act=>new Option(act.label||act.id||act.event,act.id||act.event)));
 actionSelect.value=p?.action_id||(actions[0]?.id||actions[0]?.event||'');
}
function refreshPropPoseRoles(){
 if(typeof document==='undefined')return;
 const p=imageProp(),spot=(config.interaction_spots||[]).find(s=>s.id===document.getElementById('ip_pose_spot_id')?.value),roles=[...new Set([spot?.animation,...(spot?.animations||[])].filter(Boolean))];
 const select=document.getElementById('ip_pose_animation');if(select){select.replaceChildren(new Option('Choose animation',''),...roles.map(r=>new Option(r,r)));select.value=p?.pose_animation||'';}
}
function changePropPoseSpot(){const p=imageProp();if(!p)return;p.pose_spot_id=document.getElementById('ip_pose_spot_id').value;p.pose_animation='';refreshImageProps();if(typeof render==='function')render();}
function fitImagePropScreen(){const p=imageProp();if(!p)return;if(p.screen_quad){delete p.screen_quad;}else{const img=propImage(config.prop_animations[p.animation_id].frames[0]),w=p.width||120,h=w*(img.naturalHeight||90)/(img.naturalWidth||120);p.screen_quad=[[p.x-w/2,p.y-h/2],[p.x+w/2,p.y-h/2],[p.x+w/2,p.y+h/2],[p.x-w/2,p.y+h/2]].map(q=>[Math.max(0,Math.min(1280,q[0])),Math.max(0,Math.min(720,q[1]))]);}refreshImageProps();if(typeof render==='function')render();}

function moveImageProp(x,y){
 const p=imageProp(),d=propDrag;if(!p||!d)return;
 if(d.mode==='corner'){p.screen_quad[d.corner]=[Math.max(0,Math.min(1280,x)),Math.max(0,Math.min(720,y))];}
 else if(d.mode==='screen_move'){const dx=Math.max(-Math.min(...d.quad.map(q=>q[0])),Math.min(1280-Math.max(...d.quad.map(q=>q[0])),x-d.x)),dy=Math.max(-Math.min(...d.quad.map(q=>q[1])),Math.min(720-Math.max(...d.quad.map(q=>q[1])),y-d.y));p.screen_quad=d.quad.map(q=>[q[0]+dx,q[1]+dy]);}
 else if(d.mode==='move'){p.x=Math.max(0,Math.min(1280,d.px+x-d.x));p.y=Math.max(0,Math.min(720,d.py+y-d.y));}
 else if(d.mode==='rotate')p.rotation=Math.round(Math.atan2(y-p.y,x-p.x)*180/Math.PI+90);
 else p.width=Math.round(Math.max(4,Math.min(1280,d.width*Math.hypot(x-p.x,y-p.y)/Math.max(1,d.distance))));
 refreshImageProps();if(typeof render==='function')render();
}

function addImageProp(){if(typeof document==='undefined')return;const id=document.getElementById('imagePropLibrary')?.value,a=config.prop_animations?.[id];if(!a){openPropLibrary();return;}const p={id:'prop_'+Date.now().toString(36),label:a.name,animation_id:id,x:640,y:360,width:120,rotation:0,layer:'depth',depth_y:420,trigger:'always',enabled:true};config.props||=[];config.props.push(p);selectedImageProp=p.id;refreshImageProps();restartPropPreview();}
function deleteImageProp(){const p=imageProp();if(!p||(typeof confirm==='function'&&!confirm('Remove this prop placement? The library animation will remain.')))return;config.props=(config.props||[]).filter(x=>x!==p);selectedImageProp='';refreshImageProps();if(typeof render==='function')render();}

function drawPropScreen(img,q,roundness=0){
 if(typeof document==='undefined')return;
 if(roundness){const c=document.createElement('canvas');c.width=img.naturalWidth;c.height=img.naturalHeight;const g=c.getContext('2d');g.beginPath();g.roundRect(0,0,c.width,c.height,Math.min(c.width,c.height)*roundness);g.clip();g.drawImage(img,0,0);c.naturalWidth=c.width;c.naturalHeight=c.height;img=c;}
 const uv=[[0,0],[img.naturalWidth,0],[img.naturalWidth,img.naturalHeight],[0,img.naturalHeight]];
 for(const ids of [[0,1,2],[0,2,3]]){const [a,b,c]=ids.map(i=>q[i]),[u,v,w]=ids.map(i=>uv[i]),den=(v[0]-u[0])*(w[1]-u[1])-(w[0]-u[0])*(v[1]-u[1]);
 const xx=((b[0]-a[0])*(w[1]-u[1])-(c[0]-a[0])*(v[1]-u[1]))/den,xy=((c[0]-a[0])*(v[0]-u[0])-(b[0]-a[0])*(w[0]-u[0]))/den;
 const yx=((b[1]-a[1])*(w[1]-u[1])-(c[1]-a[1])*(v[1]-u[1]))/den,yy=((c[1]-a[1])*(v[0]-u[0])-(b[1]-a[1])*(w[0]-u[0]))/den;
 ctx.save();ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.lineTo(...c);ctx.closePath();ctx.clip();ctx.transform(xx,yx,xy,yy,a[0]-xx*u[0]-xy*u[1],a[1]-yx*u[0]-yy*u[1]);ctx.drawImage(img,0,0);ctx.restore();}
}

function drawImageProps(front){
 if(typeof ctx==='undefined')return;
 for(const p of (typeof config!=='undefined'?(config.props||[]):[])){
  if(typeof propsView!=='undefined'&&!propsView&&p.hide_when_inactive)continue;
  const choices=p.animation_ids?.length?p.animation_ids:[p.animation_id],seq=config.prop_animations?.[choices[(typeof propsView!=='undefined'&&propsView)?Math.floor(propTime()/8)%choices.length:0]];
  if(!seq||p.enabled===false||(typeof propVisibleInEditor==='function'&&!propVisibleInEditor(p)))continue;
  const isFront=p.layer==='front'||(p.layer==='depth'&&(p.depth_y??p.y)>(typeof stagedChar!=='undefined'?stagedChar.y:0));
  if(isFront!==front)continue;
  const index=propFrameIndex(seq,(typeof propsView!=='undefined'&&propsView)?propTime():0),img=propImage(seq.frames[index]);
  if(!img?.complete||!img.naturalWidth)continue;
  if(p.screen_quad){
   drawPropScreen(img,p.screen_quad,p.screen_roundness||0);
   if(typeof propsView!=='undefined'&&propsView&&p.id===selectedImageProp){
    ctx.save();ctx.strokeStyle='#d69cff';ctx.fillStyle='#d69cff';ctx.lineWidth=2/(typeof zoom!=='undefined'?zoom:1);
    ctx.beginPath();p.screen_quad.forEach((q,i)=>i?ctx.lineTo(...q):ctx.moveTo(...q));ctx.closePath();ctx.stroke();
    for(const q of p.screen_quad){ctx.beginPath();ctx.arc(...q,5/(typeof zoom!=='undefined'?zoom:1),0,2*Math.PI);ctx.fill();}
    ctx.restore();
   }
   continue;
  }
  const w=p.width||120,h=w*img.naturalHeight/img.naturalWidth;
  ctx.save();ctx.translate(p.x,p.y);ctx.rotate((p.rotation||0)*Math.PI/180);ctx.drawImage(img,-w/2,-h/2,w,h);
  if(typeof propsView!=='undefined'&&propsView&&p.id===selectedImageProp){
   ctx.strokeStyle='#d69cff';ctx.lineWidth=2/(typeof zoom!=='undefined'?zoom:1);ctx.strokeRect(-w/2,-h/2,w,h);
   ctx.fillStyle='#d69cff';ctx.fillRect(w/2-5/(typeof zoom!=='undefined'?zoom:1),h/2-5/(typeof zoom!=='undefined'?zoom:1),10/(typeof zoom!=='undefined'?zoom:1),10/(typeof zoom!=='undefined'?zoom:1));
   ctx.beginPath();ctx.moveTo(0,-h/2);ctx.lineTo(0,-h/2-25/(typeof zoom!=='undefined'?zoom:1));ctx.stroke();
   ctx.beginPath();ctx.arc(0,-h/2-25/(typeof zoom!=='undefined'?zoom:1),6/(typeof zoom!=='undefined'?zoom:1),0,Math.PI*2);ctx.fill();
  }
  ctx.restore();
 }
}

function imagePropPointerDown(x,y){
 if(typeof propsView==='undefined'||!propsView||(typeof screenEffectEditing!=='undefined'&&screenEffectEditing))return false;
 for(const p of [...(typeof config!=='undefined'?(config.props||[]):[])].reverse()){
  if(p.enabled===false||(typeof propVisibleInEditor==='function'&&!propVisibleInEditor(p)))continue;
  const choices=p.animation_ids?.length?p.animation_ids:[p.animation_id],seq=config.prop_animations?.[choices[(typeof propsView!=='undefined'&&propsView)?Math.floor(propTime()/8)%choices.length:0]];
  if(!seq)continue;
  const img=propImage(seq.frames[propFrameIndex(seq,propTime())]);if(!img?.naturalWidth)continue;
  if(p.screen_quad){
   const z=(typeof zoom!=='undefined'?zoom:1);
   const corner=p.id===selectedImageProp?p.screen_quad.findIndex(q=>Math.hypot(x-q[0],y-q[1])<12/z):-1;
   const inside=x>=Math.min(...p.screen_quad.map(q=>q[0]))&&x<=Math.max(...p.screen_quad.map(q=>q[0]))&&y>=Math.min(...p.screen_quad.map(q=>q[1]))&&y<=Math.max(...p.screen_quad.map(q=>q[1]));
   if(corner>=0||inside){
    selectedImageProp=p.id;
    propDrag={mode:corner>=0?'corner':'screen_move',corner,x,y,quad:p.screen_quad.map(q=>[...q])};
    refreshImageProps();if(typeof render==='function')render();return true;
   }
   continue;
  }
  const angle=-(p.rotation||0)*Math.PI/180,dx=x-p.x,dy=y-p.y,lx=dx*Math.cos(angle)-dy*Math.sin(angle),ly=dx*Math.sin(angle)+dy*Math.cos(angle);
  const w=p.width||120,h=w*img.naturalHeight/img.naturalWidth;
  const z=(typeof zoom!=='undefined'?zoom:1);
  const selected=p.id===selectedImageProp,rotate=selected&&Math.hypot(lx,ly+h/2+25/z)<12/z,scale=selected&&Math.hypot(lx-w/2,ly-h/2)<12/z;
  if(rotate||scale||(Math.abs(lx)<=w/2&&Math.abs(ly)<=h/2)){
   selectedImageProp=p.id;
   propDrag={mode:rotate?'rotate':scale?'scale':'move',x,y,px:p.x,py:p.y,width:w,distance:Math.hypot(dx,dy)};
   refreshImageProps();if(typeof render==='function')render();return true;
  }
 }
 return false;
}

function openPropLibrary(){if(typeof openAnimGrid==='function')openAnimGrid();showAnimationLibrary('props');}
function showAnimationLibrary(kind){
 if(typeof document==='undefined')return;
 const layout=document.querySelector('#animGridModal .animgrid-layout');if(layout)layout.style.display=kind==='props'?'none':'';
 const panel=document.getElementById('propLibraryPanel');if(panel)panel.hidden=kind!=='props';
 const tabChars=document.getElementById('tabAnimCharacters'),tabProps=document.getElementById('tabAnimProps');
 if(tabChars&&tabProps){
  tabChars.style.background=kind==='props'?'#242030':'#4a2574';tabChars.style.borderColor=kind==='props'?'#443c53':'#9b5de5';
  tabProps.style.background=kind==='props'?'#4a2574':'#242030';tabProps.style.borderColor=kind==='props'?'#9b5de5':'#443c53';
 }
 if(kind==='props')renderPropLibrary();
}

function selectGridProp(propId){
 gridActivePropId=propId;
 const all=getAllSceneProps();
 const p=all.find(x=>x.id===propId)||all[0];
 if(p){
  gridActivePropId=p.id;
  const animIds=p.animation_ids?.length?p.animation_ids:(p.animation_id?[p.animation_id]:[]);
  if(animIds.length&&!animIds.includes(propLibraryId))propLibraryId=animIds[0];
 }
 renderPropLibrary();restartPropPreview();
}

function cycleGridTvChannel(delta){
 const all=getAllSceneProps();
 const p=all.find(x=>x.id===gridActivePropId)||all[0];if(!p)return;
 const animIds=p.animation_ids?.length?p.animation_ids:(p.animation_id?[p.animation_id]:[]);
 if(!animIds.length)return;
 let idx=animIds.indexOf(propLibraryId);
 if(idx<0)idx=0;
 idx=(idx+delta+animIds.length)%animIds.length;
 propLibraryId=animIds[idx];
 renderPropLibrary();restartPropPreview();
}

function reorderPropAnimation(propId,aId,delta){
 const all=getAllSceneProps();
 const p=all.find(x=>x.id===propId);if(!p)return;
 const anims=[...(p.animation_ids?.length?p.animation_ids:(p.animation_id?[p.animation_id]:[]))];
 const idx=anims.indexOf(aId);if(idx<0)return;
 const target=idx+delta;
 if(target>=0&&target<anims.length){
  [anims[idx],anims[target]]=[anims[target],anims[idx]];
  p.animation_ids=anims;
  if(p.animation_ids.length)p.animation_id=p.animation_ids[0];
  if(config.scenes?.[p.sceneId]?.props){const sp=config.scenes[p.sceneId].props.find(x=>x.id===p.id);if(sp){sp.animation_ids=anims;sp.animation_id=anims[0];}}
  if(config.props){const cp=config.props.find(x=>x.id===p.id);if(cp){cp.animation_ids=anims;cp.animation_id=anims[0];}}
  renderPropLibrary();refreshImageProps();restartPropPreview();
 }
}

function togglePropAnimationAssign(propId,aId,add){
 const all=getAllSceneProps();
 const p=all.find(x=>x.id===propId);if(!p)return;
 let anims=[...(p.animation_ids?.length?p.animation_ids:(p.animation_id?[p.animation_id]:[]))];
 if(add){if(!anims.includes(aId))anims.push(aId);}
 else{anims=anims.filter(x=>x!==aId);}
 p.animation_ids=anims;
 if(anims.length){
  if(!anims.includes(p.animation_id))p.animation_id=anims[0];
 }else{
  delete p.animation_id;
 }
 if(config.scenes?.[p.sceneId]?.props){const sp=config.scenes[p.sceneId].props.find(x=>x.id===p.id);if(sp){sp.animation_ids=anims;sp.animation_id=anims[0]||'';}}
 if(config.props){const cp=config.props.find(x=>x.id===p.id);if(cp){cp.animation_ids=anims;cp.animation_id=anims[0]||'';}}
 if(anims.length&&!anims.includes(propLibraryId))propLibraryId=anims[0];
 renderPropLibrary();refreshImageProps();restartPropPreview();
}

function newAnimationForGridProp(propId){
 const name=prompt('New animation / TV channel name:');if(!name?.trim())return;
 config.prop_animations||={};
 const newId='prop_anim_'+Date.now().toString(36);
 config.prop_animations[newId]={name:name.trim(),frames:[],fps:4,playback_mode:'loop',repeat_count:1};
 const all=getAllSceneProps();
 const p=all.find(x=>x.id===propId);
 if(p){
  p.animation_ids=[...(p.animation_ids?.length?p.animation_ids:(p.animation_id?[p.animation_id]:[])),newId];
  if(!p.animation_id)p.animation_id=newId;
  if(config.scenes?.[p.sceneId]?.props){const sp=config.scenes[p.sceneId].props.find(x=>x.id===p.id);if(sp){sp.animation_ids=p.animation_ids;sp.animation_id=p.animation_ids[0];}}
  if(config.props){const cp=config.props.find(x=>x.id===p.id);if(cp){cp.animation_ids=p.animation_ids;cp.animation_id=p.animation_ids[0];}}
 }
 propLibraryId=newId;
 renderPropLibrary();refreshImageProps();restartPropPreview();
}

function setGridPropField(propId, field, value){
 const all=getAllSceneProps();
 const p=all.find(x=>x.id===propId);
 if(!p)return;
 p[field]=value;
 if(config.scenes?.[p.sceneId]?.props){
  const sp=config.scenes[p.sceneId].props.find(x=>x.id===p.id);
  if(sp)sp[field]=value;
 }
 if(config.props){
  const cp=config.props.find(x=>x.id===p.id);
  if(cp)cp[field]=value;
 }
 renderGridPropDetails();
 refreshImageProps();
 if(typeof render==='function')render();
}

function renderGridPropDetails(){
 if(typeof document==='undefined')return;
 const container=document.getElementById('gridPropActiveDetails');if(!container)return;
 const all=getAllSceneProps();
 const p=all.find(x=>x.id===gridActivePropId)||all[0];
 if(!p){container.innerHTML='<div style="color:#aaa;padding:12px;font-size:0.85rem;">No placed props found in any scene.</div>';return;}
 gridActivePropId=p.id;
 const interaction=p.interaction||'none';
 const isTV=interaction==='tv'||interaction==='overlay_popup';
 const isAnim=interaction==='trigger_animation';
 const isApp=interaction==='app_action';
 const isGame=interaction==='game_script';

 let interactionBadge='🚶 Walk & Inspect';
 if(isTV)interactionBadge='📺 Overlay Viewer';
 else if(isAnim)interactionBadge='🎬 Animation Burst';
 else if(isApp)interactionBadge='⚡ App Action';
 else if(isGame)interactionBadge='🎮 Game / Script';

 const typeIcon=isTV?'📺':(isGame?'🎮':(isApp?'⚡':(p.screen_quad?'🖥️':'🖼️')));
 const typeName=isTV?'TV Overlay Screen':(isGame?'Game Prop':(isApp?'App Trigger Prop':(p.screen_quad?'Screen Monitor':'Prop Object')));
 const badgeBg=isTV?'#4a2574':(isGame?'#591a75':(isApp?'#1b4d24':(p.screen_quad?'#1e3a5f':'#332b40')));
 const badgeCol=isTV?'#ffd166':(isGame?'#e0aaff':(isApp?'#a3e635':(p.screen_quad?'#70d6ff':'#ddd')));
 let triggerDesc='Always active';
 if(p.trigger==='pose')triggerDesc='Active when sitting on couch / pose';
 else if(p.trigger==='typing')triggerDesc='Active when typing at desk';
 else if(p.trigger==='action')triggerDesc='Application action trigger';

 const animChoices=p.animation_ids||(p.animation_id?[p.animation_id]:[]);
 
 // All library animations not currently assigned to this prop
 const allLibraryAnims=Object.entries(config.prop_animations||{});
 const unassignedAnims=allLibraryAnims.filter(([id])=>!animChoices.includes(id));

 // On-Tap subcontrols based on mode
 let onTapSubcontrols='';
 if(isAnim){
  const animOptions=Object.entries(config.prop_animations||{}).map(([id,a])=>`<option value="${id}" ${(p.tap_animation||p.animation_id)===id?'selected':''}>${a.name||id}</option>`).join('');
  onTapSubcontrols=`
   <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:8px;">
     <span style="font-size:0.78rem;color:#98c1d9;font-weight:600;">Animation to Trigger:</span>
     <select style="background:#151c28;color:#98c1d9;border:1px solid #3d5a80;padding:4px 8px;border-radius:4px;font-size:0.78rem;" onchange="setGridPropField('${p.id}','tap_animation',this.value)">
       ${animOptions||'<option disabled>No animations in library</option>'}
     </select>
   </div>
  `;
 }else if(isApp){
  const apps=config.integrations||[];
  const curAppId=p.app_id||(apps[0]?.id||'');
  const curApp=apps.find(a=>a.id===curAppId);
  const actions=curApp?.actions||[];
  const appOptions=apps.map(a=>`<option value="${a.id}" ${curAppId===a.id?'selected':''}>${a.name||a.id}</option>`).join('');
  const actionOptions=actions.map(act=>`<option value="${act.id||act.event}" ${(p.action_id)===(act.id||act.event)?'selected':''}>${act.label||act.id||act.event}</option>`).join('');
  onTapSubcontrols=`
   <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:8px;">
     <span style="font-size:0.78rem;color:#a3e635;font-weight:600;">Application:</span>
     <select style="background:#182418;color:#a3e635;border:1px solid #406840;padding:4px 8px;border-radius:4px;font-size:0.78rem;" onchange="setGridPropField('${p.id}','app_id',this.value)">
       ${appOptions||'<option disabled>No applications registered</option>'}
     </select>
     <span style="font-size:0.78rem;color:#a3e635;font-weight:600;">Action:</span>
     <select style="background:#182418;color:#a3e635;border:1px solid #406840;padding:4px 8px;border-radius:4px;font-size:0.78rem;" onchange="setGridPropField('${p.id}','action_id',this.value)">
       ${actionOptions||'<option value="tap">Default tap</option>'}
     </select>
   </div>
  `;
 }else if(isGame){
  const curGame=p.game_id||'retro_tv';
  onTapSubcontrols=`
   <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:8px;">
     <span style="font-size:0.78rem;color:#e0aaff;font-weight:600;">Game Script:</span>
     <select style="background:#24162a;color:#e0aaff;border:1px solid #8338ec;padding:4px 8px;border-radius:4px;font-size:0.78rem;" onchange="setGridPropField('${p.id}','game_id',this.value)">
       <option value="retro_tv" ${curGame==='retro_tv'?'selected':''}>📺 Retro TV Channels & Static (Built-in)</option>
       <option value="snake" ${curGame==='snake'?'selected':''}>🐍 Retro Snake Mini-Game</option>
       <option value="custom" ${curGame==='custom'?'selected':''}>⚙️ Custom Overlay Script</option>
     </select>
   </div>
  `;
 }

 let onTapSectionHtml=`
  <div style="background:#191524;border:1px solid #4a3e62;border-radius:6px;padding:10px;margin:10px 0;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;flex-wrap:wrap;gap:6px;">
      <div style="display:flex;align-items:center;gap:6px;">
        <span style="font-weight:700;color:#ffd166;font-size:0.85rem;">👆 On-Tap Interaction:</span>
        <span style="background:${badgeBg};color:${badgeCol};font-size:0.68rem;padding:1px 6px;border-radius:3px;font-weight:600;">${interactionBadge}</span>
      </div>
      <span style="font-size:0.72rem;color:#aaa;">When tapped on Desk-Pal screen</span>
    </div>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
      <select style="background:#262035;color:#fff;border:1px solid #6b558c;padding:4px 8px;border-radius:4px;font-size:0.8rem;font-weight:600;" onchange="setGridPropField('${p.id}','interaction',this.value)">
        <option value="none" ${interaction==='none'?'selected':''}>🚶 None (Floor walk / inspect)</option>
        <option value="tv" ${isTV?'selected':''}>📺 Open Overlay Viewer (CRT TV / Monitor)</option>
        <option value="trigger_animation" ${isAnim?'selected':''}>🎬 Trigger In-Scene Animation Burst</option>
        <option value="app_action" ${isApp?'selected':''}>⚡ Trigger Application Action...</option>
        <option value="game_script" ${isGame?'selected':''}>🎮 Launch Mini-Game / Script...</option>
      </select>
    </div>
    ${onTapSubcontrols}
  </div>
 `;

 // TV Channel live switcher preview
 let tvPlayerHtml='';
 if(isTV&&animChoices.length){
  const curIdx=Math.max(0,animChoices.indexOf(propLibraryId));
  const chName=config.prop_animations?.[propLibraryId]?.name||propLibraryId||'Static';
  tvPlayerHtml=`
   <div style="background:#201a2e;border:1px solid #795290;border-radius:6px;padding:10px;margin:10px 0;">
     <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;flex-wrap:wrap;gap:4px;">
       <span style="font-weight:bold;color:#ffd166;font-size:0.85rem;">📺 TV Live Channel Switcher</span>
       <span style="font-size:0.75rem;color:#ddd;">Channel <b>${curIdx+1}</b> of <b>${animChoices.length}</b></span>
     </div>
     <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
       <div style="display:flex;gap:6px;">
         <button class="btn" style="padding:4px 10px;font-size:0.75rem;" onclick="cycleGridTvChannel(-1)">◀ Prev Channel</button>
         <button class="btn" style="padding:4px 10px;font-size:0.75rem;" onclick="cycleGridTvChannel(1)">Next Channel ▶</button>
       </div>
       <span style="font-size:0.8rem;color:#00e5ff;font-weight:600;">Active Channel: ${chName}</span>
     </div>
   </div>
  `;
 }

 // Assigned animations card grid
 let animListHtml='';
 if(!animChoices.length){
  animListHtml=`
   <div style="background:#241d24;border:1px dashed #7a5060;border-radius:6px;padding:14px;margin:10px 0;text-align:center;">
     <div style="font-weight:bold;color:#ff9e9e;font-size:0.88rem;margin-bottom:4px;">⚠️ No animations assigned to this prop yet.</div>
     <div style="font-size:0.78rem;color:#ccc;">Choose an existing animation from the library below, or create and upload new frames for this prop!</div>
   </div>
  `;
 }else{
  animListHtml=`
   <div style="margin-top:10px;">
     <div style="font-weight:700;color:#fff;font-size:0.85rem;margin-bottom:6px;">
       🎬 Currently Assigned ${isTV?'TV Channels':'Animations'} (${animChoices.length} active):
     </div>
     <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(260px, 1fr));gap:8px;">
  `;
  for(let i=0;i<animChoices.length;i++){
   const aId=animChoices[i];
   const a=config.prop_animations?.[aId];
   const isEditing=(aId===propLibraryId);
   const borderCol=isEditing?'#00e5ff':'#443c53';
   const bgCol=isEditing?'#2e2640':'#1e1a2b';
   const chLabel=isTV?`Ch ${i+1}`:`Anim ${i+1}`;
   const cleanName=(a?.name||aId).replace(/^TV\s*[-—–]\s*/i,'');
   const framesCount=a?.frames?.length||0;
   const fps=a?.fps||4;

   animListHtml+=`
     <div style="background:${bgCol};border:1px solid ${borderCol};border-radius:6px;padding:8px;display:flex;flex-direction:column;justify-content:space-between;gap:6px;">
       <div style="display:flex;justify-content:space-between;align-items:flex-start;">
         <div style="display:flex;align-items:center;gap:6px;">
           <span style="background:${isTV?'#4a2574':'#2b3b55'};color:#ffd166;font-size:0.68rem;padding:1px 5px;border-radius:3px;font-weight:bold;">${chLabel}</span>
           <span style="font-size:0.82rem;font-weight:600;color:#fff;" title="${aId}">${cleanName}</span>
         </div>
         ${isEditing?'<span style="font-size:0.65rem;color:#00e5ff;font-weight:bold;">EDITING</span>':''}
       </div>
       <div style="font-size:0.72rem;color:#aaa;">
         ${framesCount} frames · ${fps} FPS · ${a?.playback_mode||'loop'}
       </div>
       <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px;">
         <button class="btn" style="padding:2px 8px;font-size:0.7rem;background:${isEditing?'#00e5ff':'#39334a'};color:${isEditing?'#000':'#fff'};font-weight:${isEditing?'bold':'normal'};" onclick="propLibraryId='${aId}';renderPropLibrary();restartPropPreview();">
           ${isEditing?'✓ In Sequencer Below':'▶ Edit Frames Below'}
         </button>
         <div style="display:flex;gap:3px;">
           <button class="btn" style="padding:1px 5px;font-size:0.68rem;" title="Move earlier" onclick="reorderPropAnimation('${p.id}','${aId}',-1)" ${i===0?'disabled':''}>▲</button>
           <button class="btn" style="padding:1px 5px;font-size:0.68rem;" title="Move later" onclick="reorderPropAnimation('${p.id}','${aId}',1)" ${i===animChoices.length-1?'disabled':''}>▼</button>
           <button class="btn" style="padding:1px 5px;font-size:0.68rem;color:#ff8585;" title="Remove from this prop" onclick="togglePropAnimationAssign('${p.id}','${aId}',false)">✕</button>
         </div>
       </div>
     </div>
   `;
  }
  animListHtml+=`</div></div>`;
 }

 // Add or change animations controls
 let addOptionsHtml=unassignedAnims.map(([id,a])=>`<option value="${id}">${a.name||id}</option>`).join('');
 let addSectionHtml=`
  <div style="background:#1c1828;border:1px solid #4a3e62;border-radius:6px;padding:10px;margin-top:12px;">
    <div style="font-weight:700;color:#ffd166;font-size:0.85rem;margin-bottom:8px;">
      ➕ Add or Change Animations for "${p.label||p.id}":
    </div>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px;">
      <span style="font-size:0.78rem;color:#ccc;">Attach Existing Animation:</span>
      <select id="gridAddAnimChoice" style="background:#282335;color:#fff;border:1px solid #5a4f6e;padding:4px 8px;border-radius:4px;font-size:0.8rem;min-width:180px;">
        ${addOptionsHtml||'<option disabled>All library animations already attached</option>'}
      </select>
      <button class="btn" style="padding:4px 10px;font-size:0.75rem;background:#4a2574;color:#ffd166;" onclick="const s=document.getElementById('gridAddAnimChoice');if(s&&s.value)togglePropAnimationAssign('${p.id}',s.value,true);" ${!unassignedAnims.length?'disabled':''}>
        + Attach to this Prop
      </button>
      <span style="font-size:0.75rem;color:#888;">— OR —</span>
      <button class="btn" style="padding:4px 10px;font-size:0.75rem;background:#2e7d32;color:#fff;" onclick="newAnimationForGridProp('${p.id}')">
        ✨ Create New Animation for this Prop
      </button>
    </div>

    <!-- Quick Checklist of All Library Animations -->
    <details style="margin-top:6px;font-size:0.78rem;">
      <summary style="color:#aaa;cursor:pointer;font-weight:600;">☑️ Quick Checklist of All Library Animations (Tick to include/exclude)</summary>
      <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(220px, 1fr));gap:6px;margin-top:6px;max-height:160px;overflow-y:auto;background:#15121e;padding:8px;border-radius:4px;">
        ${allLibraryAnims.map(([id,a])=>{
          const isChecked=animChoices.includes(id);
          return `<label style="display:flex;align-items:center;gap:6px;cursor:pointer;color:${isChecked?'#00e5ff':'#bbb'};">
            <input type="checkbox" ${isChecked?'checked':''} onchange="togglePropAnimationAssign('${p.id}','${id}',this.checked)">
            <span>${a.name||id}</span>
          </label>`;
        }).join('')}
      </div>
    </details>
  </div>
 `;

 container.innerHTML=`
  <div style="background:#262035;border:1px solid #483d5c;border-radius:8px;padding:12px;">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:8px;">
      <div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <span style="font-weight:700;color:#fff;font-size:1.05rem;">${typeIcon} ${p.label||p.id}</span>
          <span style="background:${badgeBg};color:${badgeCol};font-size:0.7rem;padding:2px 8px;border-radius:4px;font-weight:bold;">${typeName}</span>
          <span style="background:#1b2838;color:#70d6ff;font-size:0.7rem;padding:2px 8px;border-radius:4px;">📍 Scene: <b>${p.sceneName}</b></span>
        </div>
        <div style="font-size:0.75rem;color:#bbb;margin-top:4px;">⚙️ Trigger: <span style="color:#eee;">${triggerDesc}</span></div>
      </div>
    </div>
    ${onTapSectionHtml}
    ${tvPlayerHtml}
    ${animListHtml}
    ${addSectionHtml}
  </div>
 `;
}

function renderPlacedPropsOverview(){
 if(typeof document==='undefined')return;
 const tabs=document.getElementById('propSelectorTabs');
 const allPlaced=getAllSceneProps();
 if(tabs){
  tabs.replaceChildren();
  for(const p of allPlaced){
   const isTV=p.interaction==='tv';
   const typeIcon=isTV?'📺':(p.screen_quad?'🖥️':'🖼️');
   const isSelected=(p.id===gridActivePropId);
   const animCount=(p.animation_ids?.length||(p.animation_id?1:0));
   const btn=document.createElement('button');
   btn.className='btn';
   btn.style=`background:${isSelected?'#5a2b8e':'#221d2e'};border:2px solid ${isSelected?'#ffd166':'#443c53'};padding:8px 12px;border-radius:6px;text-align:left;cursor:pointer;display:inline-flex;flex-direction:column;gap:2px;`;
   btn.innerHTML=`
     <div style="font-weight:bold;color:${isSelected?'#ffd166':'#fff'};font-size:0.88rem;">${typeIcon} ${p.label||p.id}</div>
     <div style="font-size:0.72rem;color:${isSelected?'#fff':'#aaa'};">${p.sceneName} · <b>${animCount}</b> ${isTV?'channels':'animations'}</div>
   `;
   btn.onclick=()=>selectGridProp(p.id);
   tabs.append(btn);
  }
 }
 const grid=document.getElementById('placedPropsOverviewGrid');if(!grid)return;
 grid.replaceChildren();
 const countEl=document.getElementById('placedPropsCount');if(countEl)countEl.textContent=allPlaced.length;
 if(!allPlaced.length){
  grid.innerHTML='<div style="color:#aaa;font-size:0.85rem;grid-column:1/-1;">No props placed in any scene.</div>';return;
 }
 for(const p of allPlaced){
  const card=document.createElement('div');
  const isTV=p.interaction==='tv';
  card.style='background:#242030;border:1px solid '+(isTV?'#9b5de5':'#443c53')+';border-radius:8px;padding:12px;';
  const typeIcon=isTV?'📺':(p.screen_quad?'🖥️':'🖼️');
  const typeName=isTV?'TV Easter Egg':(p.screen_quad?'Screen Monitor':'Prop Object');
  const badgeBg=isTV?'#4a2574':(p.screen_quad?'#1e3a5f':'#332b40');
  const badgeCol=isTV?'#ffd166':(p.screen_quad?'#70d6ff':'#ddd');
  let triggerDesc='Always active';
  if(p.trigger==='pose')triggerDesc='Active when sitting on couch / pose';
  else if(p.trigger==='typing')triggerDesc='Active when typing at desk';
  else if(p.trigger==='action')triggerDesc='Application action trigger';
  let chInfo='';
  if(isTV){
   const n=(p.animation_ids||[p.animation_id]).filter(Boolean).length;
   chInfo=`<div style="font-size:0.75rem;color:#ffd166;margin-top:4px;">📺 TV Channels: <b>${n}</b> shows active</div>`;
  }
  card.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
    <span style="font-weight:700;color:#fff;font-size:0.95rem;">${typeIcon} ${p.label||p.id}</span>
    <span style="background:${badgeBg};color:${badgeCol};font-size:0.68rem;padding:2px 6px;border-radius:4px;font-weight:bold;">${typeName}</span>
  </div>
  <div style="font-size:0.75rem;color:#aaa;margin-bottom:4px;">📍 Scene: <b style="color:#00e5ff;">${p.sceneName}</b></div>
  <div style="font-size:0.75rem;color:#aaa;">⚙️ Trigger: <span style="color:#ddd;">${triggerDesc}</span></div>
  ${chInfo}
  <div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap;">
    <button class="btn" style="padding:4px 8px;font-size:0.72rem;background:#4a2574;color:#ffd166;" onclick="selectGridProp('${p.id}');">Select &amp; View Animations</button>
  </div>`;
  grid.append(card);
 }
}

function renderPropLibrary(){
 if(typeof document==='undefined')return;
 config.prop_animations||={};
 const allProps=getAllSceneProps();
 if(!gridActivePropId&&allProps.length){
  // default to TV if present or first prop
  const tvProp=allProps.find(p=>p.interaction==='tv'||p.animation_ids?.length);
  gridActivePropId=tvProp?.id||allProps[0].id;
 }
 const propSelect=document.getElementById('gridPropSelect');
 if(propSelect){
  propSelect.replaceChildren(...allProps.map(p=>{
   const tag=p.interaction==='tv'?' [📺 TV Easter Egg]':(p.screen_quad?' [🖥️ Screen]':' [🖼️ Prop]');
   return new Option((p.label||p.id)+tag+' ('+p.sceneName+')',p.id);
  }));
  propSelect.value=gridActivePropId;
 }
 renderGridPropDetails();
 renderPlacedPropsOverview();
 const select=document.getElementById('propSequence');
 if(select){
  select.replaceChildren(...Object.entries(config.prop_animations).map(([id,a])=>{
   let prefix=id.startsWith('tv_')?'📺 TV Channel — ':(id.includes('water')?'🌊 Prop — ':'🖼️ Prop — ');
   let cleanName=(a.name||id).replace(/^TV\s*[-—–]\s*/i,'');
   return new Option(prefix+cleanName,id);
  }));
  if(!config.prop_animations[propLibraryId])propLibraryId=Object.keys(config.prop_animations)[0]||'';
  select.value=propLibraryId;
 }
 const a=config.prop_animations[propLibraryId];
 const titleEl=document.getElementById('currentEditingAnimTitle');
 if(titleEl)titleEl.textContent=a?(a.name||propLibraryId):'None selected';
 const fields=document.getElementById('propSequenceFields');
 if(fields)fields.hidden=!a;
 if(!a)return;
 for(const k of ['name','fps','playback_mode','repeat_count']){const el=document.getElementById('pa_'+k);if(el)el.value=a[k]??1;}
 const countReadout=document.getElementById('propFrameCountReadout');
 if(countReadout)countReadout.textContent=a.frames?.length||0;
 const tray=document.getElementById('propFrameTray');
 if(tray){
  tray.replaceChildren();
  a.frames.forEach((url,i)=>{
   const card=document.createElement('div');card.style='display:inline-flex;flex-direction:column;width:115px;margin:6px;padding:6px;background:#393448;border-radius:4px;';
   const img=document.createElement('img');img.src=url;img.style='width:100px;height:100px;object-fit:contain;background:repeating-conic-gradient(#555 0% 25%,#333 0% 50%) 0/16px 16px;border-radius:4px;';
   card.append(img);
   const label=document.createElement('span');label.style='font-size:0.75rem;color:#eee;margin:3px 0;';label.textContent='Frame '+(i+1);
   card.append(label);
   for(const [text,action] of [['←',()=>{if(i>0)[a.frames[i-1],a.frames[i]]=[a.frames[i],a.frames[i-1]];}],['→',()=>{if(i<a.frames.length-1)[a.frames[i+1],a.frames[i]]=[a.frames[i],a.frames[i+1]];}],['Remove',()=>a.frames.splice(i,1)]]){
    const b=document.createElement('button');b.className='btn';b.style='padding:1px 4px;font-size:0.68rem;margin-top:2px;';b.textContent=text;
    b.onclick=()=>{action();renderPropLibrary();restartPropPreview();};
    card.append(b);
   }
   tray.append(card);
  });
 }
}

function newPropAnimation(){const name=prompt('Prop animation name');if(!name?.trim())return;config.prop_animations||={};propLibraryId='prop_anim_'+Date.now().toString(36);config.prop_animations[propLibraryId]={name:name.trim(),frames:[],fps:4,playback_mode:'loop',repeat_count:1};renderPropLibrary();refreshImageProps();}
function updatePropAnimation(){const a=config.prop_animations[propLibraryId];if(!a)return;a.name=document.getElementById('pa_name').value;a.fps=Math.max(1,Math.min(60,Number(document.getElementById('pa_fps').value)||4));a.playback_mode=document.getElementById('pa_playback_mode').value;a.repeat_count=Math.max(1,Math.min(1000,Number(document.getElementById('pa_repeat_count').value)||1));refreshImageProps();renderPropLibrary();restartPropPreview();}
async function uploadPropFrames(input){const a=config.prop_animations?.[propLibraryId];if(!a)return;const status=document.getElementById('propLibraryStatus');input.disabled=true;try{for(const file of [...input.files].sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true}))){if(file.size>12000000)throw Error('Each PNG must be under 12 MB');const image_b64=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=()=>reject(Error('Could not read image'));r.readAsDataURL(file);});const r=await fetch('/api/props/frame',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image_b64})});if(!r.ok)throw Error('Could not upload '+file.name);a.frames.push((await r.json()).url);renderPropLibrary();}status.textContent='Frames uploaded in filename order. Save to Pi to keep the sequence.';}catch(e){status.textContent=e.message;}finally{input.disabled=false;input.value='';}}
async function savePropLibrary(){document.getElementById('propLibraryStatus').textContent=await saveConfigToPi()?'Prop library and placements saved to Pi.':'Save failed; changes remain in editor.';}
function drawPropLibraryPreview(){
 const panel=document.getElementById('propLibraryPanel');if(!panel||panel.hidden||document.getElementById('animGridModal').style.display==='none')return;
 const c=document.getElementById('propLibraryPreview'),g=c.getContext('2d');g.clearRect(0,0,c.width,c.height);const a=config?.prop_animations?.[propLibraryId];if(!a?.frames?.length)return;
 const img=propImage(a.frames[propFrameIndex(a,propTime())]);if(!img?.naturalWidth)return;const scale=Math.min(220/img.naturalWidth,160/img.naturalHeight);g.imageSmoothingEnabled=false;g.drawImage(img,(240-img.naturalWidth*scale)/2,(180-img.naturalHeight*scale)/2,img.naturalWidth*scale,img.naturalHeight*scale);
}
function deletePropAnimation(){
 if(!propLibraryId)return;const used=[...(config.props||[]),...Object.values(config.scenes||{}).flatMap(s=>s.props||[])].some(p=>(p.animation_ids||[p.animation_id]).includes(propLibraryId));
 if(used){document.getElementById('propLibraryStatus').textContent='Remove this prop’s placements from all scenes before deleting its library entry.';return;}
 if(!confirm('Delete this prop animation from the library?'))return;delete config.prop_animations[propLibraryId];propLibraryId='';renderPropLibrary();refreshImageProps();
}
