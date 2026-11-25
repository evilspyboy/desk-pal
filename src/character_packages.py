"""Portable character content, merged without changing scene or application settings."""
import copy,hashlib,io,json,math,os,re,tempfile,time,zipfile
from pathlib import Path,PurePosixPath
from urllib.parse import unquote
from backup_packages import MAX_BYTES,encoded,clean,destination,export_backup

GUIDES=('skeleton_annotations.json','skeleton_frame_sources.json')
def load_json(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}

def pack(payload,files):
    files=dict(files);files['character.json']=encoded(clean(payload))
    manifest={'format':'deskpal-character','version':1,'files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()}}
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',encoded(manifest))
        for n,b in files.items():z.writestr(n,b)
    return output.getvalue()

def read_package(data):
    if len(data)>MAX_BYTES:raise ValueError('Character archive exceeds 512 MB')
    files={}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        entries=z.infolist()
        if len(entries)>20000 or sum(e.file_size for e in entries)>MAX_BYTES:raise ValueError('Expanded character archive is too large')
        for e in entries:
            n=e.filename;p=PurePosixPath(n)
            if n in files or e.is_dir() or '\\' in n or ':' in n or p.is_absolute() or '..' in p.parts or str(p)!=n:raise ValueError('Unsafe or duplicate package path')
            if e.flag_bits&1 or (e.external_attr>>16)&0o170000==0o120000:raise ValueError('Links and encrypted entries are unsupported')
            if n not in ('manifest.json','character.json') and not (n.startswith('assets/characters/adventurer/') and p.suffix.lower() in ('.png','.jpg','.jpeg','.gif','.webp')):raise ValueError('Unsupported character package file')
            files[n]=z.read(e)
    manifest=json.loads(files.pop('manifest.json'))
    if manifest.get('format')!='deskpal-character' or manifest.get('version')!=1:raise ValueError('Unsupported character package version')
    if set(files)!=set(manifest.get('files',{})):raise ValueError('Contents differ from manifest')
    for n,b in files.items():
        if hashlib.sha256(b).hexdigest()!=manifest['files'][n]:raise ValueError('Damaged character package: '+n)
    payload=json.loads(files.pop('character.json'))
    if set(payload)-{'id','character','sequences','tags','guides'}:raise ValueError('Package contains unrelated settings')
    for key in ('character','sequences','tags','guides'):
        if not isinstance(payload.get(key,{}),dict):raise ValueError('Invalid character metadata')
    return payload,files

def export_character(cfg,character_id,assets,config_dir):
    tags=load_json(Path(config_dir)/'sprite_tags.json')
    character=copy.deepcopy(cfg.get('characters',{}).get(character_id,{'animations':{}}))
    own_tags={url:tag for url,tag in tags.items() if tag.get('variant')==character_id}
    if character_id not in cfg.get('characters',{}) and not own_tags:raise ValueError('Unknown character')
    if not character.get('reference_sprite') and cfg.get('reference_sprite',{}).get('url') in own_tags:character['reference_sprite']=copy.deepcopy(cfg['reference_sprite'])
    sequences={k:copy.deepcopy(s) for k,s in cfg.get('animation_sequences',{}).items() if s.get('character')==character_id}
    if set(character.get('animations',{}).values())-set(sequences):raise ValueError('Character has missing or foreign animation bindings')
    files={}
    def collect(value):
        if isinstance(value,dict):
            for child in value.values():collect(child)
        elif isinstance(value,list):
            for child in value:collect(child)
        elif isinstance(value,str) and value.startswith('/assets/'):
            name=unquote(value[1:].split('?',1)[0])
            if not name.startswith('assets/characters/adventurer/'):raise ValueError('Unsupported character asset: '+name)
            path=destination(name,assets,config_dir)
            if not path.is_file():raise ValueError('Missing character asset: '+name)
            files[name]=path.read_bytes()
    collect(character);collect(sequences)
    for url in own_tags:collect(url)
    # Include tags for all referenced frames; every frame must belong to this character.
    for name in files:
        url='/'+name
        if tags.get(url,{}).get('variant')!=character_id:raise ValueError('Referenced sprite is not tagged for this character: '+url)
        own_tags[url]=tags[url]
    guides={n:{k:v for k,v in load_json(Path(config_dir)/n).items() if k in own_tags} for n in GUIDES}
    if sum(map(len,files.values()))>MAX_BYTES:raise ValueError('Character exceeds content limit')
    return pack(dict(id=character_id,character=character,sequences=sequences,tags=own_tags,guides=guides),files)

def prepare(data,current,assets,config_dir,target_id=None):
    payload,files=read_package(data);target=target_id or payload.get('id')
    if not isinstance(target,str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}',target) or target in ('__proto__','prototype','constructor','custom'):raise ValueError('Use a character ID of 1-64 letters, numbers, underscores or hyphens')
    urls={'/'+n:'/assets/characters/adventurer/imported/'+target+'/'+n[len('assets/characters/adventurer/'):] for n in files}
    def rewrite(value):
        if isinstance(value,dict):return {urls.get(k,k):rewrite(v) for k,v in value.items()}
        if isinstance(value,list):return [rewrite(v) for v in value]
        if isinstance(value,str):
            if value.startswith('/assets/'):return urls.get('/'+unquote(value[1:].split('?',1)[0]),value)
            if '/'+value in urls:return urls['/'+value][1:]
        return value
    character=rewrite(payload['character']);sequences={};ids={k:target+':package_'+hashlib.sha256(k.encode()).hexdigest()[:16] for k in payload.get('sequences',{})}
    missing=[]
    for key,sequence in payload.get('sequences',{}).items():
        if sequence.get('character')!=payload.get('id'):raise ValueError('Foreign sequence in character package')
        fps=sequence.get('fps',8)
        if not isinstance(fps,(int,float)) or not math.isfinite(fps) or not 1<=fps<=60:raise ValueError('Animation FPS must be between 1 and 60')
        if sequence.get('playback_mode','loop') not in ('once','repeat','loop','ping_pong'):raise ValueError('Invalid animation playback mode')
        sequences[ids[key]]=rewrite(sequence);sequences[ids[key]]['character']=target
        if not sequence.get('frames'):missing.append('Empty sequence: '+key)
        for frame in sequence.get('frames',[]):
            url=frame.get('url','')
            if url not in urls or payload.get('tags',{}).get(url,{}).get('variant')!=payload.get('id'):missing.append('Missing or incorrectly tagged frame: '+url)
            crop=frame.get('crop')
            if crop is not None and (not isinstance(crop,list) or len(crop)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in crop) or min(crop[:2])<0 or min(crop[2:])<=0):raise ValueError('Invalid frame crop')
    bindings=character.get('animations',{})
    for role,key in list(bindings.items()):
        if key not in ids:missing.append('Missing bound sequence: '+str(key))
        else:bindings[role]=ids[key]
    tags=rewrite(payload.get('tags',{}))
    for url,tag in tags.items():
        if url not in urls.values():missing.append('Unbundled tagged sprite: '+url)
        if tag.get('variant')!=payload.get('id'):raise ValueError('Foreign sprite tag in character package')
        tag['variant']=target
    def check(value):
        if isinstance(value,dict):
            for v in value.values():check(v)
        elif isinstance(value,list):
            for v in value:check(v)
        elif isinstance(value,str) and value.startswith('/assets/') and value not in urls.values():missing.append('Unbundled character asset: '+value)
    check(character);check(sequences)
    if current.get('active_character')==target and not (bindings.get('walk_side') or bindings.get('walk')):missing.append('Active character needs a walking sequence')
    old_roles=set(current.get('characters',{}).get(target,{}).get('animations',{}));lost=sorted(old_roles-set(bindings))
    if lost:missing.append('Replacement removes existing animation roles: '+', '.join(lost))
    for key in sequences:
        old=current.get('animation_sequences',{}).get(key)
        if old and old.get('character')!=target:missing.append('Sequence ID belongs to another character: '+key)
    merged=copy.deepcopy(current);merged.setdefault('characters',{})[target]=character;merged.setdefault('animation_sequences',{}).update(sequences)
    output={urls['/'+n][1:]:b for n,b in files.items()}
    existing_tags=load_json(Path(config_dir)/'sprite_tags.json')
    for url,tag in tags.items():
        if url in existing_tags and existing_tags[url].get('variant') not in (None,target):missing.append('Sprite belongs to another character: '+url)
    existing_tags.update(tags);output['config/sprite_tags.json']=encoded(existing_tags)
    for name,entries in payload.get('guides',{}).items():
        if name not in GUIDES:raise ValueError('Unsupported skeleton guide file')
        if not isinstance(entries,dict) or set(entries)-set(payload['tags']):raise ValueError('Unrelated skeleton guide entries')
        existing=load_json(Path(config_dir)/name);existing.update(rewrite(entries));output['config/'+name]=encoded(existing)
    warnings=sorted({sid for seq in sequences.values() for sid in seq.get('allowed_scenes',[]) if sid not in current.get('scenes',{})})
    return merged,output,sorted(set(missing)),target,warnings,len(sequences),len(tags)

def preview_character(data,current,assets,config_dir,target_id=None):
    merged,files,missing,target,warnings,count,sprites=prepare(data,current,assets,config_dir,target_id)
    changes={'added':[],'replaced':[],'unchanged':[]};state={'settings':hashlib.sha256(encoded(clean(current))).hexdigest()}
    for name,body in files.items():
        path=destination(name,assets,config_dir);old=path.read_bytes() if path.is_file() else None
        state[name]=hashlib.sha256(old).hexdigest() if old is not None else None
        changes['added' if old is None else 'unchanged' if old==body else 'replaced'].append(name)
    return dict(digest=hashlib.sha256(data).hexdigest(),state_digest=hashlib.sha256(encoded(state)).hexdigest(),target_character=target,
        mode='replace' if target in current.get('characters',{}) else 'add',changes=changes,missing=missing,sequences=count,sprites=sprites,
        notes=['Scenes, placement vectors, application mappings and the selected character remain unchanged.',
        'Sprite paths and imported sequence IDs are isolated under the destination character.',
        'Scene restrictions are retained; unavailable scene IDs: '+(', '.join(warnings) or 'none')])

def import_character(data,current,assets,config_dir,apply_config,digest,state,target_id=None):
    review=preview_character(data,current,assets,config_dir,target_id)
    if review['digest']!=digest or review['state_digest']!=state or review['missing']:raise ValueError('Preview changed or dependencies are missing; preview again')
    merged,files,*_=prepare(data,current,assets,config_dir,target_id)
    recovery_dir=Path(config_dir)/'backups';recovery_dir.mkdir(parents=True,exist_ok=True)
    recovery=recovery_dir/('before-restore-'+str(time.time_ns())+'.zip');recovery.write_bytes(export_backup(current,assets,config_dir))
    original={}
    def write(path,body):
        path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.deskpal-character-')
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(body)
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    try:
        for name in review['changes']['added']+review['changes']['replaced']:
            path=destination(name,assets,config_dir);original[path]=path.read_bytes() if path.is_file() else None;write(path,files[name])
        apply_config(merged)
    except Exception:
        for path,body in original.items():
            if body is None:path.unlink(missing_ok=True)
            else:write(path,body)
        apply_config(current)
        raise
    return dict(status='ok',character=review['target_character'],recovery_backup=recovery.name)
