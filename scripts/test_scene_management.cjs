const fs=require('fs'),vm=require('vm'),assert=require('assert'),html=fs.readFileSync('src/web_studio.html','utf8');
const c={};vm.createContext(c);vm.runInContext(html.slice(html.indexOf('function newSceneData('),html.indexOf('async function createEditorScene')),c);
const a=c.newSceneData('Workshop',{theme:'custom_workshop',background:'new.png'}),b=c.newSceneData('Garden',{theme:'garden',background:'b.png'});
a.obstacles.push({id:'box'});assert.equal(b.obstacles.length,0);assert.equal(a.portals.length,0);assert.equal(a.enabled,true);assert.equal(a.walkable_trapezoid.points.length,4);assert.equal(a.background,'new.png');console.log('New scenes have independent geometry and empty placements.');
