const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('src/web_studio.html','utf8');
class Element{
 constructor(tag){this.tag=tag;this.attrs={};this.style={};this.children=[];this.hidden=false;}
 setAttribute(k,v){this.attrs[k]=v;} append(...els){this.children.push(...els);} replaceChildren(...els){this.children=els;}
 createSVGPoint(){return {x:0,y:0,matrixTransform(){return {x:this.x,y:this.y};}};}
 getScreenCTM(){return {inverse(){return {};}};} setPointerCapture(){this.captured=true;} hasPointerCapture(){return this.captured;} releasePointerCapture(){this.captured=false;}
 focus(){}
}
const elements={},config={scenes:{a:{name:'A',portals:[{id:'door',x:1280,y:360}]},b:{name:'B',portals:[{id:'entry',x:0,y:360},{id:'back',x:100,y:600}]},c:{name:'C',portals:[]}},scene_links:[]};
const c={Math,Map,JSON,config,currentSceneId:()=> 'a',scenePortLabel:e=>e.scene+'/'+e.portal,document:{getElementById:id=>elements[id] ||=new Element(id),createElementNS:(ns,tag)=>new Element(tag)}};
vm.createContext(c);vm.runInContext(html.slice(html.indexOf('// Visual scene connections.'),html.indexOf('function removeScenePortal')),c);
const a={scene:'a',portal:'door'},b={scene:'b',portal:'entry'};
// Removing one endpoint must remove only its incident connections, after confirmation.
c.confirm=()=>true;c.openSceneMap=()=>{};c.refreshPortalInspector=()=>{};c.render=()=>{};c.selectedPortalId='';
config.scene_links=[{a,b},{a:{scene:'b',portal:'back'},b:{scene:'c',portal:'keep'}}];
vm.runInContext("sceneMapStart={scene:'b',portal:'entry'}",c);
c.confirm=()=>false;c.removeSelectedSceneMapPoint();assert.equal(config.scenes.b.portals.length,2);
c.confirm=()=>true;c.removeSelectedSceneMapPoint();assert.equal(config.scenes.b.portals.length,1);assert.equal(config.scene_links.length,1);assert.equal(config.scene_links[0].a.portal,'back');
config.scenes.b.portals.unshift({id:'entry',x:0,y:360});config.scene_links=[];
assert(!c.connectSceneMapNodes(a,a));assert(!c.connectSceneMapNodes(a,{scene:'b',portal:'missing'}));
assert(c.connectSceneMapNodes(a,b));assert(!c.connectSceneMapNodes(b,a));assert.equal(config.scene_links.length,1);
config.scene_links=[];const entries=Object.entries(config.scenes);c.drawSceneMap(entries);
const svg=elements.sceneMapGraph;assert.equal(svg.children.filter(e=>e.tag==='image').length,3);assert.equal(svg.attrs.viewBox,'0 0 900 640');
const layout=c.sceneMapLayout(entries),nodes=layout.nodes;assert.equal(nodes[0].x,420);assert.equal(nodes[1].x,480);
const circles=()=>svg.children.filter(e=>e.tag==='circle');
const event=n=>({button:0,pointerId:1,clientX:n.x,clientY:n.y,preventDefault(){},stopPropagation(){}});
circles()[0].onpointerdown(event(nodes[0]));svg.onpointermove(event(nodes[1]));svg.onpointerup(event(nodes[1]));assert.equal(config.scene_links.length,1,'Drag connects actual endpoints');
circles()[0].onpointerdown(event(nodes[0]));svg.onpointermove(event(nodes[1]));svg.onpointercancel();svg.onpointerup(event(nodes[1]));assert.equal(config.scene_links.length,1,'Cancelled drag does not change links');
const line=svg.children.find(e=>e.tag==='path'&&e.attrs.role==='button');line.onclick();assert(!elements.removeSceneMapLink.hidden);c.removeSelectedSceneMapLink();assert.equal(config.scene_links.length,0);
circles()[0].onpointerdown(event(nodes[0]));svg.onpointerup(event(nodes[0]));circles()[1].onpointerdown(event(nodes[1]));svg.onpointerup(event(nodes[1]));assert.equal(config.scene_links.length,1,'Two-click connection fallback');
config.scene_links=[];c.drawSceneMap(entries);circles()[0].onkeydown({key:'Enter',preventDefault(){}});circles()[1].onkeydown({key:'Enter',preventDefault(){}});assert.equal(config.scene_links.length,1,'Keyboard connection');
console.log('Thumbnail layout, node drag, cancellation, click/keyboard connections, duplicates and removal passed.');
