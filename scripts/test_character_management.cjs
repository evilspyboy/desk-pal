const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('src/web_studio.html','utf8');const elements={animCharacterTag:{value:'v2'},animStatusMsg:{}};let posts=0;
const context={document:{getElementById:id=>elements[id]||={}},confirm:()=>false,fetch:async(route,opts)=>{if(opts)posts++;return {ok:true,json:async()=>route.endsWith('sprite_tags')?{x:{variant:'v2'}}:{characters:{v2:{}},animation_sequences:{}}};}};
vm.createContext(context);vm.runInContext(html.slice(html.indexOf('// Character catalogue and management.'),html.indexOf('function refreshSavedAnimations()')),context);
const cfg={active_character:'v2',characters:{empty:{animations:{}},v2:{animations:{walk:'two'}},v1:{animations:{walk:'one'}}},animation_sequences:{one:{character:'v1'},two:{character:'v2'},tagless:{character:'third'}},reference_sprite:{url:'b'},scene_placements:{room:{locations:[1,2]}}};
const tags={a:{variant:'v1',skeleton:{version:1}},b:{variant:'v2',skeleton:{version:1},crop:[1,2,3,4]},c:{variant:'tags_only'}};
assert.deepEqual(Array.from(context.animationCharacterIds(cfg,tags)),['empty','tags_only','third','v1','v2']);
context.removeCharacterData(cfg,tags,'v2');assert(!cfg.characters.v2);assert(!cfg.animation_sequences.two);assert(cfg.animation_sequences.one);assert.equal(tags.b.variant,undefined);assert(tags.b.skeleton);assert.deepEqual(tags.b.crop,[1,2,3,4]);assert.equal(cfg.reference_sprite,undefined);assert.notEqual(cfg.active_character,'v2');assert.deepEqual(cfg.scene_placements.room.locations,[1,2]);
context.deleteAnimationCharacter().then(()=>{assert.equal(posts,0,'Cancel must not save anything');console.log('Character discovery, deletion isolation, retained assets/metadata, active fallback and confirmation cancellation passed');}).catch(e=>{console.error(e);process.exitCode=1;});
(async()=>{
 const state={document:{getElementById:id=>({value:'v2',textContent:''})},confirm:()=>true};vm.createContext(state);vm.runInContext(html.slice(html.indexOf('// Character catalogue and management.'),html.indexOf('function refreshSavedAnimations()')),state);
 state.readCharacterData=async route=>route.endsWith('sprite_tags')?{x:{variant:'v2',skeleton:{}}}:{characters:{v2:{},v1:{}},animation_sequences:{},active_character:'v1'};
 let release;const pending=new Promise(r=>release=r);let visible;
 state.applyCharacterCatalogue=(cfg,tags)=>{visible=Array.from(state.animationCharacterIds(cfg,tags));};state.writeCharacterData=async()=>pending;
 const deletion=state.deleteAnimationCharacter();await new Promise(r=>setImmediate(r));assert(!visible.includes('v2'),'Dropdown removes character while save is pending');release({});await deletion;
 state.writeCharacterData=async()=>{throw new Error('offline');};await state.deleteAnimationCharacter();assert(visible.includes('v2'),'Failed save restores character in dropdown');
 console.log('Immediate deletion refresh and failed-save rollback passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
