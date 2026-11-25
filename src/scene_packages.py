"""Single-scene packages merge content without replacing applications or characters."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import time
import zipfile
from backup_packages import MAX_BYTES, EXTENSIONS, clean, encoded, destination, export_backup


def pack(payload, files):
    files = dict(files, **{'scene.json': encoded(clean(payload))})
    manifest = dict(format='deskpal-scene', version=1,
        files={n:hashlib.sha256(b).hexdigest() for n,b in files.items()})
    output = io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',encoded(manifest))
        for name,body in files.items():archive.writestr(name,body)
    return output.getvalue()


def read_package(data):
    if len(data)>MAX_BYTES:raise ValueError('Scene archive exceeds 512 MB')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos=archive.infolist()
        if len(infos)>20000 or sum(i.file_size for i in infos)>MAX_BYTES:raise ValueError('Scene archive exceeds content limit')
        files={}
        for info in infos:
            name=info.filename;path=PurePosixPath(name)
            if name in files or info.is_dir() or '\\' in name or ':' in name or path.is_absolute() or '..' in path.parts or str(path)!=name:
                raise ValueError('Unsafe or duplicate scene package path')
            if info.flag_bits&1 or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Encrypted entries and links are unsupported')
            if name not in ('manifest.json','scene.json') and not (name.startswith('assets/') and path.suffix.lower() in EXTENSIONS):raise ValueError('Unsupported scene package file')
            files[name]=archive.read(info)
    manifest=json.loads(files.pop('manifest.json'))
    if manifest.get('format')!='deskpal-scene' or manifest.get('version')!=1:raise ValueError('Unsupported scene package version')
    if set(files)!=set(manifest.get('files',{})):raise ValueError('Scene contents differ from manifest')
    for name,body in files.items():
        if hashlib.sha256(body).hexdigest()!=manifest['files'][name]:raise ValueError('Damaged scene package: '+name)
    payload=json.loads(files.pop('scene.json'))
    if not isinstance(payload.get('scene'),dict) or not isinstance(payload.get('prop_animations',{}),dict):raise ValueError('Invalid scene metadata')
    # Only scene content is imported; unexpected application/configuration keys are rejected.
    if set(payload)-{'id','scene','placements','source_character','prop_animations'}:raise ValueError('Package contains unrelated settings')
    return payload,files


def export_scene(cfg, scene_id, assets):
    if scene_id not in cfg['scenes']:raise ValueError('Unknown scene')
    scene=copy.deepcopy(cfg['scenes'][scene_id]);library=cfg.get('prop_animations',{})
    ids={i for prop in scene.get('props',[]) for i in [prop.get('animation_id')]+prop.get('animation_ids',[]) if i}
    if ids-set(library):raise ValueError('Scene refers to missing prop animations')
    payload=dict(id=scene_id,scene=scene,placements=copy.deepcopy(cfg.get('scene_placements',{}).get(scene_id,{})),
        source_character=cfg.get('active_character'),prop_animations={i:library[i] for i in ids})
    root=Path(assets).resolve();files={};theme=root/'themes'/scene.get('theme',scene_id)
    if not theme.resolve().is_relative_to(root):raise ValueError('Invalid theme path')
    for path in theme.rglob('*'):
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in EXTENSIONS:files['assets/'+path.relative_to(root).as_posix()]=path.read_bytes()
    def visit(value):
        if isinstance(value,dict):
            for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
        elif isinstance(value,str) and value.startswith('/assets/'):
            from urllib.parse import unquote
            name=unquote(value[1:].split('?',1)[0]);path=destination(name,root,root)
            if not path.is_file():raise ValueError('Missing scene asset: '+name)
            if name.startswith('assets/characters/'):return # Character art remains a dependency, not part of the scene.
            files[name]=path.read_bytes()
    visit(payload)
    if sum(map(len,files.values()))>MAX_BYTES:raise ValueError('Scene exceeds content limit')
    return pack(payload,files)


def prepare_scene(data,current,target_id=None):
    payload,files=read_package(data);target=target_id or payload.get('id')
    if not isinstance(target,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',target):raise ValueError('Use a scene ID containing lowercase letters, numbers, hyphens or underscores')
    scene=copy.deepcopy(payload['scene']);theme=scene.get('theme',payload['id']);new_theme='imported_'+target
    asset_map={}
    for name in files:
        if name.startswith('assets/themes/'+theme+'/'):
            asset_map[name]='assets/themes/'+new_theme+'/'+name.split('assets/themes/'+theme+'/',1)[1]
        else:
            asset_map[name]='assets/props/imported_scenes/'+target+'/'+name[len('assets/'):]
    def rewrite(value):
        if isinstance(value,dict):return {k:rewrite(v) for k,v in value.items()}
        if isinstance(value,list):return [rewrite(v) for v in value]
        if isinstance(value,str) and value.startswith('/assets/'):
            from urllib.parse import unquote
            name=unquote(value[1:].split('?',1)[0])
            if name in asset_map:return '/'+asset_map[name]
        return value
    scene=rewrite(scene);scene['theme']=new_theme
    placements=rewrite(payload.get('placements',{}))
    source_character=payload.get('source_character');character=current.get('active_character')
    # Placement guides and playback overrides apply to the selected destination character.
    for spots in (scene.get('interaction_spots',[]),placements.get('interaction_spots',[])):
        for spot in spots:
            for key in ('vector_offsets','playback_overrides'):
                if source_character in spot.get(key,{}) and character!=source_character:
                    spot[key][character]=spot[key].pop(source_character)
    prop_ids={old:'scene_'+target+'__'+old for old in payload.get('prop_animations',{})}
    library={prop_ids[k]:rewrite(v) for k,v in payload.get('prop_animations',{}).items()}
    for prop in scene.get('props',[]):
        if prop.get('animation_id') in prop_ids:prop['animation_id']=prop_ids[prop['animation_id']]
        if 'animation_ids' in prop:prop['animation_ids']=[prop_ids.get(k,k) for k in prop['animation_ids']]
    merged=copy.deepcopy(current);merged.setdefault('scenes',{})[target]=scene
    merged.setdefault('scene_placements',{})[target]=placements or {k:copy.deepcopy(scene.get(k,{} if k=='pose_rules' else [])) for k in ('interaction_spots','pose_rules')}
    merged.setdefault('prop_animations',{}).update(library)
    old_links=merged.get('scene_links',[]);portals={p['id'] for p in scene.get('portals',[])}
    merged['scene_links']=[link for link in old_links if all(end.get('scene')!=target or end.get('portal') in portals for end in (link['a'],link['b']))]
    if merged.get('active_scene')==target:
        from scene_world import activate_scene
        activate_scene(merged,target)
    roles={r for spot in scene.get('interaction_spots',[]) for r in [spot.get('animation')]+spot.get('animations',[]) if r}
    bindings=merged.get('characters',{}).get(character,{}).get('animations',{})
    missing=['Character animation: '+r for r in sorted(roles) if bindings.get('idle_side' if r=='idle' else r) not in merged.get('animation_sequences',{})]
    for other_id,other_scene in current.get('scenes',{}).items():
        if other_id==target:continue
        if other_scene.get('theme')==new_theme:missing.append('Asset namespace is used by another scene: '+other_id)
        for prop in other_scene.get('props',[]):
            if set([prop.get('animation_id')]+prop.get('animation_ids',[])) & set(library):
                missing.append('Prop namespace is used by another scene: '+other_id)
    new_files={asset_map[n]:body for n,body in files.items()}
    def check_assets(value):
        if isinstance(value,dict):
            for child in value.values():check_assets(child)
        elif isinstance(value,list):
            for child in value:check_assets(child)
        elif isinstance(value,str) and value.startswith('/assets/'):
            if value[1:].split('?',1)[0] not in new_files:missing.append('Unbundled scene asset: '+value)
    check_assets(scene);check_assets(library)
    new_files={asset_map[n]:body for n,body in files.items()}
    background='assets/themes/'+new_theme+'/'+scene.get('background','background.jpg')
    if background not in new_files:missing.append('Scene background: '+background)
    spots={s['id'] for s in scene.get('interaction_spots',[])}
    for app in current.get('apps',[]):
        for action in app.get('actions',[]):
            if (action.get('scene') or action.get('target_scene'))==target and action.get('spot_id') and action['spot_id'] not in spots:
                missing.append('Existing mapping '+app['id']+'/'+action['id']+' uses a removed placement: '+action['spot_id'])
    return payload,merged,new_files,missing,len(old_links)-len(merged['scene_links']),target


def preview_scene(data,current,assets,config_dir,target_id=None):
    payload,merged,files,missing,removed_links,target=prepare_scene(data,current,target_id)
    changes={'added':[],'replaced':[],'unchanged':[]};state={'settings':hashlib.sha256(encoded(clean(current))).hexdigest()}
    for name,body in files.items():
        path=destination(name,assets,config_dir);old=path.read_bytes() if path.is_file() else None
        state[name]=hashlib.sha256(old).hexdigest() if old is not None else None
        changes['added' if old is None else 'unchanged' if old==body else 'replaced'].append(name)
    return dict(digest=hashlib.sha256(data).hexdigest(),state_digest=hashlib.sha256(encoded(state)).hexdigest(),
        target_scene=target,scene_name=merged['scenes'][target].get('name',target),mode='replace' if target in current.get('scenes',{}) else 'add',
        changes=changes,missing=missing,removed_connections=removed_links,
        animation_roles=sorted({r for spot in merged['scenes'][target].get('interaction_spots',[]) for r in [spot.get('animation')]+spot.get('animations',[]) if r}),
        notes=['Application mappings and character libraries are unchanged.',
               'Scene artwork and prop animation IDs are isolated under this scene ID.',
               'New entry/exit points can be connected in Scene Map; external connections are not imported.'])


def import_scene(data,current,assets,config_dir,apply_config,digest,state,target_id=None):
    review=preview_scene(data,current,assets,config_dir,target_id)
    if review['digest']!=digest or review['state_digest']!=state or review['missing']:raise ValueError('Preview changed or dependencies are missing; preview again')
    _,merged,files,_,_,_=prepare_scene(data,current,target_id)
    recovery_dir=Path(config_dir)/'backups';recovery_dir.mkdir(parents=True,exist_ok=True)
    recovery=recovery_dir/('before-restore-'+str(time.time_ns())+'.zip');recovery.write_bytes(export_backup(current,assets,config_dir))
    original={}
    def write(path,body):
        path.parent.mkdir(parents=True,exist_ok=True);fd,temp=tempfile.mkstemp(dir=path.parent,prefix='.deskpal-scene-')
        try:
            with os.fdopen(fd,'wb') as output:output.write(body)
            os.replace(temp,path)
        finally:
            if os.path.exists(temp):os.unlink(temp)
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
    return dict(status='ok',scene=review['target_scene'],recovery_backup=recovery.name)
