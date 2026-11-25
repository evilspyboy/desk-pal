const fs=require('fs'),assert=require('assert');
const source=fs.readFileSync(require('path').join(__dirname,'../src/hardware_studio.html'),'utf8');
const fn=source.slice(source.indexOf('function neutralQualityError('),source.indexOf('function updateImuWizard('));
const infer=new Function(fn+';return inferImuCalibration;')();
const permutations=[[0,1,2],[0,2,1],[1,0,2],[1,2,0],[2,0,1],[2,1,0]];
let checked=0;
for(const axes of permutations)for(const sx of [-1,1])for(const sy of [-1,1])for(const sz of [-1,1]){
 const signs=[sx,sy,sz],inversions=axes.reduce((s,a,i)=>s+axes.slice(i+1).filter(b=>a>b).length,0);
 if((inversions%2?-1:1)*sx*sy*sz!==1)continue;
 const raw=v=>{const r=[0,0,0];axes.forEach((a,i)=>r[a]=v[i]*signs[i]);return r;};
 const bias=[.5,-.3,.2],results={neutral:{samples:27,duration:2,accel_spread:.01,gyro:bias,accel:raw([0,0,1])}};
 for(const [phase,vector] of Object.entries({forward:[30,0,0],back:[-30,0,0],right:[0,30,0],left:[0,-30,0],turn_left:[0,0,-30],turn_right:[0,0,30]})){
  results[phase]={duration:4,integral:raw(vector).map((v,i)=>v+bias[i]*4)};
 }
 const proposal=infer(results);for(let i=0;i<3;i++)for(let j=0;j<3;j++)assert(Math.abs(proposal.rotation[i][j]-(j===axes[i]?signs[i]:0))<1e-8);assert.deepStrictEqual(proposal.gyro_bias,bias);checked++;
 for(const gravity of [[0,0,-1],[.8,0,.6]]){const mounted=JSON.parse(JSON.stringify(results));mounted.neutral.accel=raw(gravity);assert.doesNotThrow(()=>infer(mounted));}
 const weak=JSON.parse(JSON.stringify(results));weak.right.integral=bias.map(v=>v*4);assert.throws(()=>infer(weak),/Unclear/);
 const moving=JSON.parse(JSON.stringify(results));moving.neutral.accel_spread=.3;assert.throws(()=>infer(moving),/moved during/);
}
const measured=JSON.parse(fs.readFileSync(require('path').join(__dirname,'fixtures/imu_directions_20261009.json'),'utf8'));
const measuredProposal=infer(measured);
assert(measuredProposal.rotation[0][1]>.9);
assert(measuredProposal.rotation[1][0]<-.9);
assert(measuredProposal.neutral.every(v=>Math.abs(v)<.3));
const mirrored=JSON.parse(JSON.stringify(measured));
[mirrored.turn_left,mirrored.turn_right]=[mirrored.turn_right,mirrored.turn_left];
assert.throws(()=>infer(mirrored),/Turning disagrees/);
const neutralSource=source.slice(source.indexOf('function isImuAtNeutral('),source.indexOf('function observeImuNeutral('));
const atNeutral=new Function(neutralSource+';return isImuAtNeutral;')();
const baseline={accel:[.6,0,.8],gyro:[.2,-.1,.3]};
assert(atNeutral({state:'live',accel_g:[.6,0,.8],gyro_dps:baseline.gyro},baseline));
assert(!atNeutral({state:'live',accel_g:[0,.8,.6],gyro_dps:baseline.gyro},baseline));
assert(!atNeutral({state:'live',accel_g:baseline.accel,gyro_dps:[10,0,0]},baseline));
assert(!atNeutral({state:'unavailable'},baseline));
console.log('Validated '+checked+' mounting rotations, tilted/inverted neutral, return detection, gyro bias and ambiguous-motion rejection.');


// A fixed sensor mounted 45 degrees around Y splits side tilt across X/Z.
const angle=Math.PI/4,c=Math.cos(angle),sn=Math.sin(angle),basis=[[c,0,sn],[0,1,0],[-sn,0,c]];
const raw=v=>basis[0].map((_,j)=>basis.reduce((sum,row,i)=>sum+row[j]*v[i],0));
const tilted={neutral:{samples:30,duration:2,accel_spread:.01,gyro:[0,0,0],accel:raw([0,0,1])}};
for(const [phase,v] of Object.entries({forward:[30,0,0],back:[-30,0,0],right:[0,30,0],left:[0,-30,0],turn_left:[0,0,-30],turn_right:[0,0,30]}))tilted[phase]={duration:4,integral:raw(v)};
const result=infer(tilted);for(let i=0;i<3;i++)for(let j=0;j<3;j++)assert(Math.abs(result.rotation[i][j]-basis[i][j])<1e-8);
console.log('Arbitrary 45-degree mounting learned correctly.');
