// Editor-only lighting preview; changing it never changes the Pi's solar clock.
let editorLightingPreview='day',editorNightImage=new Image(),editorNightLoaded=false;
function sceneAssetUrl(scene,filename){return '/assets/themes/'+encodeURIComponent(scene.theme||currentSceneId())+'/'+encodeURIComponent(filename);}
function loadEditorNightBackground(){
 editorNightLoaded=false;const scene=config.scenes[currentSceneId()];const image=new Image();editorNightImage=image;
 image.onload=()=>{if(editorNightImage===image){editorNightLoaded=true;render();}};
 image.onerror=()=>{if(editorNightImage===image){editorNightLoaded=false;render();}};
 image.src=sceneAssetUrl(scene,scene.background_night||'background_night.jpg');
}
function setEditorLightingPreview(value){editorLightingPreview=value;render();}
function drawEditorNight(){
 if(editorLightingPreview!=='night')return;
 if(editorNightLoaded){ctx.drawImage(editorNightImage,0,0,1280,720);return;}
 const theme=config.theme||currentSceneId();ctx.save();ctx.globalCompositeOperation='multiply';
 ctx.fillStyle=theme==='resort_beach'?'rgb(80,100,145)':'rgb(140,145,180)';ctx.fillRect(0,0,1280,720);
 const openings={video_store:[[[0,0],[101,39],[101,533],[0,656]]],apartment:[[[563,32],[646,33],[645,98],[564,97]],[[665,32],[747,30],[747,97],[665,97]],[[564,105],[645,105],[645,163],[564,163]],[[665,105],[746,104],[746,162],[665,164]],[[564,172],[645,172],[645,229],[563,229]],[[665,172],[746,171],[746,229],[665,230]],[[1137,26],[1279,0],[1279,407],[1138,382]]]}[theme]||[];
 ctx.fillStyle='rgb(65,85,145)';for(const polygon of openings){ctx.beginPath();polygon.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.closePath();ctx.fill();}ctx.restore();
}
function propVisibleInEditor(prop){return (prop.time_of_day||'both')==='both'||prop.time_of_day===editorLightingPreview;}
async function uploadSceneBackground(id,file,variant){
 if(file.size>12000000)throw Error('Choose a PNG or JPEG smaller than 12 MB');
 const image_b64=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Could not read image'));reader.readAsDataURL(file);});
 const scene=config.scenes?.[id];const response=await fetch('/api/scenes/background',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scene_id:id,theme:scene?.theme,variant,image_b64})});
 if(!response.ok)throw Error('Background upload failed. Use PNG/JPEG up to 20 megapixels.');return response.json();
}
function openSceneBackgrounds(){
 const old=document.getElementById('sceneBackgroundPanel');if(old)old.remove();const id=currentSceneId(),scene=config.scenes[id];
 const panel=document.createElement('div');panel.id='sceneBackgroundPanel';panel.style='position:fixed;inset:0;background:#000a;z-index:6100;display:flex;align-items:center;justify-content:center';
 const box=document.createElement('div');box.style='background:var(--surface);padding:22px;border:1px solid var(--border);border-radius:12px;width:min(660px,90vw)';panel.append(box);
 const heading=document.createElement('h2');heading.textContent=scene.name+' — backgrounds';box.append(heading);
 const status=document.createElement('p');status.setAttribute('role','status');
 for(const variant of ['day','night']){
  const row=document.createElement('div');row.style='display:inline-block;width:48%;vertical-align:top';box.append(row);
  const label=document.createElement('strong');label.textContent=variant==='day'?'Daytime':'Nighttime';row.append(label);
  const img=document.createElement('img');img.style='width:95%;aspect-ratio:16/9;object-fit:contain;background:#151321';img.alt=label.textContent+' background';img.src=sceneAssetUrl(scene,scene[variant==='day'?'background':'background_night']||(variant==='day'?'background.jpg':'background_night.jpg'));row.append(img);
  const input=document.createElement('input');input.type='file';input.accept='image/png,image/jpeg';input.setAttribute('aria-label','Upload '+label.textContent+' background');row.append(input);
  input.onchange=async()=>{const file=input.files[0];if(!file)return;input.disabled=true;save.disabled=true;status.textContent='Uploading…';try{const asset=await uploadSceneBackground(id,file,variant);Object.assign(scene,asset);img.src=sceneAssetUrl(scene,asset[variant==='day'?'background':'background_night']);loadImages();status.textContent='Image staged. Save to Pi to apply it. Layout and placements are kept.';}catch(e){status.textContent=e.message;}finally{input.disabled=false;save.disabled=false;input.value='';}};
 }
 const note=document.createElement('p');note.textContent='Use matching 1280×720 compositions so your floor, masks and placements fit both images. Without a night image, the Pi derives night lighting from daytime artwork.';box.append(note,status);
 const save=document.createElement('button');save.className='btn btn-primary';save.textContent='Save to Pi';save.onclick=async()=>{save.disabled=true;try{status.textContent=await saveConfigToPi()?'Backgrounds and editor changes saved.':'Save failed; changes remain in the editor.';}finally{save.disabled=false;}};
 const close=document.createElement('button');close.className='btn';close.textContent='Close';close.onclick=()=>panel.remove();box.append(save,close);document.body.append(panel);
}
