const fs=require('fs'),vm=require('vm'),assert=require('assert'),html=fs.readFileSync('src/web_studio.html','utf8');const c={spriteTags:{old:{variant:'original'}}};vm.createContext(c);
vm.runInContext(html.slice(html.indexOf('function characterReference('),html.indexOf('function refreshReferenceTemplates(')),c);
const cfg={reference_sprite:{url:'old'},characters:{fresh:{reference_sprite:{url:'new'}}}};
assert.equal(c.characterReference(cfg,'fresh').url,'new');assert.equal(c.characterReference(cfg,'original').url,'old');assert.equal(c.characterReference(cfg,'unrelated'),null);
assert(html.includes('usingTemplates?s.character:char'));assert(html.includes('referenceSequences(cfg,cfg.active_character)'));
console.log('Per-character references isolated; legacy reference only used by its tagged character.');
