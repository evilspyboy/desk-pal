const fs=require('fs'),vm=require('vm'),assert=require('assert');
const nodes=[];function node(tag){const n={tag,children:[],dataset:{},style:{},append(...children){this.children.push(...children)},replaceChildren(){this.children=[]},querySelectorAll(){return this.children.flatMap(c=>c.children||[]).filter(c=>c.tag==='input')}};nodes.push(n);return n;}
const panel=node('div');panel.id='animUsagePanel';
const char=node('input');char.id='animCharacterTag';char.value='hero';
const role=node('select');role.id='animRole';role.value='rest';
const live=()=>{const found=[panel,char,role];const walk=n=>{for(const c of n.children||[]){found.push(c);walk(c)}};walk(panel);return found;};
const document={createElement:node,createTextNode:text=>({text}),getElementById:id=>live().find(n=>n.id===id),querySelectorAll:()=>live().filter(n=>n.tag==='input'&&n.dataset.scene&&n.checked)};
const cfg={scenes:{study:{name:'Study'},beach:{name:'Beach',enabled:false}},characters:{hero:{animations:{rest:'rest',sit:'sit',up:'up',foreign:'other'}}},animation_sequences:{rest:{character:'hero',frames:[{}]},sit:{character:'hero',frames:[{}]},up:{character:'hero',frames:[{}]},other:{character:'other',frames:[{}]}}};
const ctx={document,config:cfg};vm.createContext(ctx);vm.runInContext(fs.readFileSync('src/animation_usage.js','utf8'),ctx);
assert.deepEqual(Array.from(ctx.animationTransitionChoices(cfg,'hero','rest','missing'),x=>x[0]),['','sit','up','missing']);
ctx.renderAnimationUsage({allowed_scenes:['beach','deleted'],entry_transition:'sit',exit_transition:'up',standby_eligible:true},'rest');
let result=JSON.parse(JSON.stringify(ctx.readAnimationUsage()));assert.deepEqual(result.allowed_scenes,['beach','deleted']);assert.equal(result.entry_transition,'sit');assert.equal(result.exit_transition,'up');assert.equal(result.standby_eligible,true);
for(const n of live().filter(n=>n.dataset?.scene))n.checked=false;
assert.throws(()=>ctx.readAnimationUsage(),/at least one scene/);
document.getElementById('animAllScenes').checked=true;assert.deepEqual(Array.from(ctx.readAnimationUsage().allowed_scenes),[]);
document.getElementById('animUsage_entry_transition').value='rest';assert.throws(()=>ctx.readAnimationUsage(),/itself/);
document.getElementById('animUsage_entry_transition').value='sit';document.getElementById('animUsage_transition_only').checked=true;assert.throws(()=>ctx.readAnimationUsage(),/own transitions/);
document.getElementById('animUsage_entry_transition').value='';document.getElementById('animUsage_exit_transition').value='';result=ctx.readAnimationUsage();assert.equal(result.idle_eligible,false);assert.equal(result.standby_eligible,false);
console.log('Scene restrictions and transition bindings restore/save; missing scenes retained; foreign/self transitions excluded; invalid empty restrictions and nested transitions rejected.');
