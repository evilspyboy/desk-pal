// Animation scene restrictions and transition bindings, saved with the sequence.
function animationTransitionChoices(cfg,character,role,current){
 const choices=[['','None']];
 for(const [key,id] of Object.entries(cfg.characters?.[character]?.animations||{})){
  const seq=cfg.animation_sequences?.[id];
  if(key!==role&&id!==cfg.characters?.[character]?.animations?.[role]&&seq?.character===character&&seq.frames?.length)choices.push([key,seq.name||key]);
 }
 if(current&&!choices.some(([key])=>key===current))choices.push([current,current+' (missing binding)']);
 return choices;
}
function renderAnimationUsage(sequence={},role=document.getElementById('animRole').value){
 const panel=document.getElementById('animUsagePanel');panel.replaceChildren();
 const add=(tag,text,parent=panel)=>{const node=document.createElement(tag);if(text)node.textContent=text;parent.append(node);return node;};
 add('h3','Where and how this animation is used');
 const allLabel=add('label'),all=add('input',null,allLabel);all.type='checkbox';all.id='animAllScenes';all.checked=!sequence.allowed_scenes?.length;allLabel.append(document.createTextNode(' Available in all scenes'));
 const scenes=add('div');scenes.style.cssText='display:flex;gap:12px;flex-wrap:wrap;margin:10px 0';
 const ids=[...new Set([...Object.keys(config.scenes||{}),...(sequence.allowed_scenes||[])])];
 for(const id of ids){const scene=config.scenes?.[id],label=add('label',null,scenes);label.style.cssText='width:140px;display:flex;flex-direction:column;gap:5px';if(scene){const image=add('img',null,label);image.src='/assets/themes/'+encodeURIComponent(scene.theme||id)+'/'+(scene.background||'background.jpg');image.alt=scene.name||id;image.style.cssText='width:140px;height:80px;object-fit:cover';}const check=add('input',null,label);check.type='checkbox';check.dataset.scene=id;check.checked=(sequence.allowed_scenes||[]).includes(id);check.disabled=all.checked;label.append(document.createTextNode((scene?.name||id)+(scene?.enabled===false?' (disabled)':!scene?' (missing scene)':'')));}
 all.onchange=()=>scenes.querySelectorAll('input').forEach(input=>input.disabled=all.checked);
 const character=document.getElementById('animCharacterTag').value.trim();
 for(const [field,labelText] of [['entry_transition','Before: sit/lie down'],['exit_transition','After: get up']]){const label=add('label',labelText+' '),select=add('select',null,label);select.id='animUsage_'+field;for(const [value,text]of animationTransitionChoices(config,character,role,sequence[field])){const option=add('option',text,select);option.value=value;}select.value=sequence[field]||'';label.style.marginRight='15px';}
 for(const [key,text]of [['transition_only','Transition only (hide from ordinary pose choices)'],['standby_eligible','May be used for the sleep button']]){const label=add('label'),check=add('input',null,label);check.type='checkbox';check.id='animUsage_'+key;check.checked=sequence[key]??(key==='standby_eligible'&&['sleeping','sitting_rest','seated_back','deck_chair_rest'].includes(role));label.append(document.createTextNode(text));label.style.cssText='display:block;margin:8px 0';}
 add('small','Use Save animation to save frames and settings to the connected installation. Scene restrictions do not delete placements. Transitions play one cycle before/after the resting pose. Both are needed for idle/sleep resting animations.');
}
function readAnimationUsage(){
 if(!document.getElementById('animAllScenes'))return {};
 const allowed=document.getElementById('animAllScenes').checked?[]:[...document.querySelectorAll('#animUsagePanel input[data-scene]:checked')].map(input=>input.dataset.scene);
 if(!document.getElementById('animAllScenes').checked&&!allowed.length)throw Error('Select at least one scene, or Available in all scenes.');
 const entry=document.getElementById('animUsage_entry_transition').value||null,exit=document.getElementById('animUsage_exit_transition').value||null;
 const role=document.getElementById('animRole').value;
 if(entry===role||exit===role)throw Error('An animation cannot use itself as a transition.');
 const transition=document.getElementById('animUsage_transition_only').checked;
 if(transition&&(entry||exit))throw Error('Transition-only animations cannot have their own transitions.');
 return {allowed_scenes:allowed,entry_transition:entry,exit_transition:exit,transition_only:transition,standby_eligible:!transition&&document.getElementById('animUsage_standby_eligible').checked,...(transition?{idle_eligible:false}:{})};
}
