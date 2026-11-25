const fs=require('fs'),vm=require('vm'),assert=require('assert');const c={Map,Math,Number,performance:{now:()=>0}};vm.createContext(c);vm.runInContext(fs.readFileSync('src/prop_editor.js','utf8'),c);
let a={frames:['a','b','c'],fps:1,playback_mode:'ping_pong'};assert.deepEqual([0,1,2,3,4,5].map(t=>c.propFrameIndex(a,t)),[0,1,2,1,0,1]);a.playback_mode='repeat';a.repeat_count=2;assert.equal(c.propFrameIndex(a,3),0);assert.equal(c.propFrameIndex(a,6),2);
c.config={props:[{id:'p',x:100,y:100,width:100,rotation:0}]};c.refreshImageProps=()=>{};c.render=()=>{};
vm.runInContext("selectedImageProp='p';propDrag={mode:'move',x:100,y:100,px:100,py:100}",c);c.moveImageProp(200,250);assert.equal(c.config.props[0].x,200);assert.equal(c.config.props[0].y,250);
vm.runInContext("propDrag={mode:'scale',width:100,distance:100}",c);c.moveImageProp(400,250);assert.equal(c.config.props[0].width,200);
vm.runInContext("propDrag={mode:'rotate'}",c);c.moveImageProp(300,250);assert.equal(c.config.props[0].rotation,90);
console.log('Prop playback, move, scale and rotation passed.');
