const fs=require('fs'),assert=require('assert'),path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../src/hardware_studio.html'),'utf8');
const fn=new Function(source.slice(source.indexOf('function stabiliseRadarTarget('),source.indexOf('function interpretRadar('))+';return stabiliseRadarTarget;')();
const p=(x,y)=>({slot:1,x_mm:x,y_mm:y});let state={};
fn(p(0,1000),state,0);assert.strictEqual(fn(p(0,3300),state,100).y_mm,1000);
assert.match(state.quality,/Uncertain/);
assert.strictEqual(fn(p(0,1005),state,200).y_mm,1005);
fn(p(0,3300),state,300);
assert.strictEqual(fn(p(0,3320),state,799).y_mm,1005);
assert.strictEqual(fn(p(0,3320),state,800).y_mm,3320);
assert.match(state.quality,/Reacquired/);
let held=0,reacquired=0;
if(process.argv[2]){const data=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));state={};for(const f of data.frames){const target=f.targets.find(t=>t.slot===1);if(!target)continue;const result=fn(target,state,f.at*1000);if(result.quality.startsWith('Uncertain'))held++;if(result.quality.startsWith('Reacquired'))reacquired++;}console.log('Replay: held',held,'uncertain frames; reacquired',reacquired,'times. A stable reflection may still be accepted.');}
console.log('Passed transient rejection, legitimate small movements and sustained relocation reacquisition.');
