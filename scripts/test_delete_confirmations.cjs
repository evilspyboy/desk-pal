const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('src/web_studio.html','utf8');
const context={selectedActionId:'one',selectedAppId:'app',renderActionPane(){},renderAppStudio(){},render(){},confirm:()=>false};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('src/integration_studio.js','utf8'),context);
for(const name of ['deleteCurrentAction','deleteCurrentApp','removePosePlacement']){
 const match=html.match(new RegExp('window\\.'+name+' = function\\([^]*?\\n};'));
 assert(match,name+' found');vm.runInContext(match[0],context);
}
const one={id:'one',label:'Saved mapping',conditions:[{field:'price'}],scene:'study'},two={id:'two'};
const app={id:'app',name:'App',actions:[one,two]};context.config={apps:[app]};
const before=JSON.stringify(context.config);
context.removeIntegrationMapping(app,one);context.deleteCurrentAction();context.deleteCurrentApp();
let placementTouched=false;context.setStagedLocationAllowed=()=>{placementTouched=true};context.removePosePlacement('desk');
assert.equal(JSON.stringify(context.config),before);assert.equal(placementTouched,false);
context.confirm=()=>true;context.removeIntegrationMapping(app,one);
assert.deepEqual(app.actions,[two]);assert.equal(context.selectedActionId,'');
context.selectedActionId='two';context.deleteCurrentAction();assert.equal(app.actions.length,0);
context.deleteCurrentApp();assert.equal(context.config.apps.length,0);
const primary={id:'primary',is_primary:true};app.actions=[primary];context.removeIntegrationMapping(app,primary);assert.equal(app.actions.length,1);
assert(html.includes("controls.append(remove)"));
assert(!fs.readFileSync('src/integration_studio.js','utf8').includes("row.append(integrationButton('Remove mapping'"));
console.log('Cancel preserves mapping/application/placement settings; confirmed deletion affects the selected item; primary mapping protected; delete sits beside edit.');
