const fs=require('fs'),vm=require('vm'),assert=require('assert');const html=fs.readFileSync('src/web_studio.html','utf8');
const p={id:'pc',screen_quad:[[100,100],[160,100],[160,150],[100,150]]},c={config:{props:[p]},Math,Number,zoom:1,render(){},pointInObstacle:(x,y)=>x>=100&&x<=160&&y>=100&&y<=150};vm.createContext(c);
vm.runInContext(html.slice(html.indexOf('// Screen effects use'),html.indexOf('function drawTypingScreenPreview')),c);vm.runInContext("screenEffectId='pc';screenEffectEditing=true",c);
assert(c.validScreenQuad(p.screen_quad));assert(!c.validScreenQuad([[0,0],[50,50],[50,0],[0,50]]));
assert(c.screenEffectPointerDown(100,100));c.moveScreenEffect(90,90);assert.deepEqual(Array.from(p.screen_quad[0]),[90,90]);
const before=JSON.stringify(p.screen_quad);c.moveScreenEffect(180,170);assert.equal(JSON.stringify(p.screen_quad),before,'Crossing corners cannot invert the screen');
vm.runInContext('screenEffectDrag=null',c);assert(c.screenEffectPointerDown(125,125));c.moveScreenEffect(-1000,-1000);assert.equal(Math.min(...p.screen_quad.map(a=>a[0])),0);assert.equal(Math.min(...p.screen_quad.map(a=>a[1])),0);assert(c.validScreenQuad(p.screen_quad));
console.log('Screen corner editing, invalid-corner rejection and bounded whole-screen dragging passed.');
