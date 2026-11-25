const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('src/web_studio.html','utf8');
const data=JSON.parse(fs.readFileSync('config/skeleton_annotations.json'));
const cfg=JSON.parse(fs.readFileSync('scratch/skeleton_work/config.json'));
const tags={...JSON.parse(fs.readFileSync('scratch/skeleton_work/tags.json')),...JSON.parse(fs.readFileSync('config/sprite_tags.json'))};
const balance=Object.fromEntries(['balance_mild','balance_strong'].map(role=>[role,{name:role,role,character:'adventurer_v1',fps:4,playback_mode:'once',frames:Array.from({length:4},(_,i)=>({url:'/assets/characters/adventurer/sensor_v1/'+role+'_'+i+'.png',reference_height:680,anchor_x:.5}))}]));
for(const [role,seq] of Object.entries(balance)){cfg.animation_sequences['adventurer_v1:'+role]=seq;for(const f of seq.frames)tags[f.url]={...tags[f.url],variant:'adventurer_v1'};}
for(const [url,skeleton] of Object.entries(data))tags[url]={...tags[url],skeleton};
const context={spriteTags:tags};vm.createContext(context);
vm.runInContext(html.slice(html.indexOf("function playbackMode("),html.indexOf("function animateStagedPose(")),context);
vm.runInContext(html.slice(html.indexOf('// Frame-specific skeleton guides.'),html.indexOf('\nsetupSkeletonEditor();')),context);
assert.equal(Object.keys(data).length,65);
for(const [url,skeleton] of Object.entries(data)){assert(context.validSkeleton(skeleton),url);assert(tags[url].variant==='adventurer_v1');}
const image={naturalWidth:1086,naturalHeight:1448};
const p=context.skeletonPoint([.5,.5],image,[200,100,600,1360],20,30,.5);
assert.deepEqual(Array.from(p),[191.5,342]); // Cropped preview must subtract the source crop origin.
const a={url:'a'},b={url:'b'};
const runs=context.compactReferenceFrames([a,a,b,b,b,a]);
assert.deepEqual(Array.from(runs,r=>[r.frame.url,r.count,r.start,r.end]),[['a',2,1,2],['b',3,3,5],['a',1,6,6]]);
assert.equal(context.compactReferenceFrames([a,{...a,crop:[1,2,3,4]}]).length,2);
assert.equal(context.referenceSequences({animation_sequences:{a:{character:'other',frames:[a]},b:{character:'v1',role:'walk',fps:4,frames:[a]},c:{character:'v1',role:'walk_side',fps:4,frames:[a]}}},'v1').length,1);
const sequences=context.referenceSequences(cfg,'adventurer_v1');
for(const seq of sequences)for(const f of seq.frames)assert(context.validSkeleton(context.frameSkeleton(f)),f.url);
assert.notDeepEqual(data[Object.keys(data)[0]].joints,data[Object.keys(data)[1]].joints);
let calls=[];const ctx=new Proxy({},{get:(o,k)=>o[k]||((...a)=>calls.push([k,...a])),set:(o,k,v)=>(o[k]=v,true)});
context.drawFrameSkeleton(ctx,Object.values(data)[0],image,[0,0,1086,1448],0,0,.2);
assert(calls.some(c=>c[0]==='setLineDash'&&c[1].length));assert.equal(calls.filter(c=>c[0]==='arc').length,17);
console.log('Validated 65 skeletons, all saved sequence coverage, crop coordinates, inferred bones, hold compaction and character filtering.');

const exporter=html.slice(html.indexOf("async function exportAnimationReference"));
assert(!exporter.includes("drawImage(im,"));
assert(exporter.includes("drawImage(refImg,"));
assert(!exporter.includes("\u00e2\u20ac"));
for(const [mode,expected] of Object.entries({once:[0,1,2,2,2,2,2],repeat:[0,1,2,0,1,2,2],loop:[0,1,2,0,1,2,0],ping_pong:[0,1,2,1,0,1,2]})){
 const seq={frames:[{},{},{}],fps:4,playback_mode:mode,repeat_count:2};
 assert.deepEqual([0,250,500,750,1000,1250,1500].map(t=>context.stagedFrameIndex(seq,t)),expected);
}
console.log('Editor playback modes agree with runtime boundary checks');

for(const role of ["balance_mild","balance_strong"]){assert(vm.runInContext("REFERENCE_NOTES["+JSON.stringify(role)+"]",context).includes("Four-frame"));}
// Exercise the actual export function for a single strip and the full collection.
(async()=>{
 const elements={animStatusMsg:{},animCharacterTag:{value:'adventurer_v1'},animSequenceName:{value:'balance_mild'},animRole:{value:'balance_mild'},animReferenceNotes:{value:''},referenceSheetDownload:{},referenceSheetImage:{},referenceSheetModal:{style:{}}};
 let rendered=[],artwork=[];
 const draw=new Proxy({measureText:t=>({width:String(t).length*9}),fillText:()=>{},drawImage:im=>artwork.push(im.url)},{get:(o,k)=>o[k]||(()=>{})});
 Object.assign(context,{document:{getElementById:id=>elements[id],createElement:()=>({getContext:()=>draw,toBlob:cb=>cb({})})},fetch:async url=>({ok:true,json:async()=>url.endsWith('sprite_tags')?tags:cfg}),animFps:4,animPingPong:false,animationPlaybackSettings:()=>({playback_mode:'once'}),getFilledFrames:()=>balance.balance_mild.frames,characterReference:()=>({url:'reference'}),loadReferenceImage:async url=>({url,naturalWidth:800,naturalHeight:720}),referenceFrameRect:()=>({crop:[0,0,800,720],x:0,y:0,scale:1}),drawFrameSkeleton:(_ctx,sk)=>rendered.push(sk),closeReferenceSheet:()=>{},URL:{createObjectURL:()=> 'blob:reference'}});
 for(const all of [false,true]){
  rendered=[];artwork=[];await context.exportAnimationReference(all);
  assert(elements.animStatusMsg.textContent.startsWith('Reference sheet ready'),elements.animStatusMsg.textContent);
  assert.deepEqual(artwork,['reference']);
  for(const f of balance.balance_mild.frames)assert(rendered.includes(tags[f.url].skeleton));
  if(all)for(const f of balance.balance_strong.frames)assert(rendered.includes(tags[f.url].skeleton));
  else assert.equal(rendered.length,4);
 }
 console.log('Single and full-character export paths include balance guides and only the character reference artwork.');
})().catch(e=>{console.error(e);process.exitCode=1;});
