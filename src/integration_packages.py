"""Data-only integration definitions with optional portable reaction mappings."""
import copy,hashlib,json,math,re,time
from pathlib import Path
from backup_packages import clean,encoded,export_backup,SECRETS

MAX_BYTES=1024*1024
APP_FIELDS={'id','name','adapter','poll_seconds','summary_field','stale_after_seconds','sleep_max_age_seconds','heartbeat_action_id','suppress_duplicate_events','suppressed_events','color'}
ACTION_FIELDS={'id','label','event','is_primary','scene','target_scene','animation','spot_id','target_mode','x','y','facing','duration_seconds','display_mode','message_label_mode','attention_needed','attention_until_interaction','voice_escalation','voice_phrase','conditions'}
PRIVATE=re.compile(r'https?://\S+|[A-Za-z]:[\\/][^\s]*|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}')
def public_text(value):
    if isinstance(value,dict):return {k:public_text(v) for k,v in clean(value).items()}
    if isinstance(value,list):return [public_text(v) for v in value]
    return PRIVATE.sub('[removed]',value) if isinstance(value,str) else value

def example_shape(value):
    if isinstance(value,dict):return {k:example_shape(v) for k,v in clean(value).items()}
    if isinstance(value,list):return []
    if isinstance(value,bool):return False
    if isinstance(value,(int,float)):return 0
    return 'example' if value is not None else None

def export_integration(cfg,app_id):
    app=next((a for a in cfg.get('apps',[]) if a.get('id')==app_id),None)
    if app is None:raise ValueError('Unknown application')
    application=public_text({k:v for k,v in app.items() if k in APP_FIELDS})
    application['source_enabled']=False
    events={e['name']:dict(name=e['name'],label=public_text(e.get('label',e['name'])),example=example_shape(e.get('example',{}))) for e in app.get('integration_events',[])}
    for action in app.get('actions',[]):
        event=action.get('event')
        if event and not action.get('is_primary'):events.setdefault(event,dict(name=event,label=public_text(action.get('label',event))))
    events.setdefault('heartbeat',dict(name='heartbeat',label='Heartbeat'))
    actions=[public_text({k:v for k,v in a.items() if k in ACTION_FIELDS}) for a in app.get('actions',[])]
    for action in actions:
        for condition in action.get('conditions',[]):
            if set(str(condition.get('field','')).lower().split('.')) & SECRETS:
                condition['value']='[configure locally]'
    return encoded(dict(format='deskpal-integration',schema_version=1,application=application,events=list(events.values()),mappings=actions,
        excludes=['connection URLs','credentials','private adapter settings','hardware assignments','received payloads','custom speech templates']))

def read_package(data):
    if len(data)>MAX_BYTES:raise ValueError('Choose an integration JSON file smaller than 1 MB')
    value=json.loads(data)
    if not isinstance(value,dict) or value.get('schema_version')!=1 or value.get('format','deskpal-integration')!='deskpal-integration':raise ValueError('Use a version 1 Desk-Pal integration definition or package')
    if not isinstance(value.get('application'),dict) or not isinstance(value.get('events'),list) or len(value['events'])>100:raise ValueError('Invalid application or event definitions')
    if set(value)-{'format','schema_version','application','events','mappings','excludes'}:raise ValueError('Package contains unrelated settings')
    events=[];seen=set()
    for e in value['events']:
        if not isinstance(e,dict) or not isinstance(e.get('name'),str) or not 1<=len(e['name'].strip())<=80 or e['name'] in seen:raise ValueError('Event names must be unique and contain 1–80 characters')
        seen.add(e['name']);events.append(dict(name=e['name'],label=str(e.get('label',e['name'])),example=clean(e.get('example',{}))))
    mappings=value.get('mappings',[])
    if not isinstance(mappings,list) or len(mappings)>200:raise ValueError('Use at most 200 mappings')
    value['events']=events
    return value

def prepare(data,current,target_id=None,include_mappings=False):
    package=read_package(data);source=package['application'];target=target_id or source.get('id')
    if not isinstance(target,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',target) or target in ('__proto__','prototype','constructor'):raise ValueError('Use a 1–64 character application ID with letters, numbers, underscores or hyphens')
    old=next((a for a in current.get('apps',[]) if a.get('id')==target),None)
    # Only an explicit whitelist crosses the boundary. Connection and button fields remain local.
    app=copy.deepcopy(old) if old else dict(id=target,adapter='json',source_url='',source_enabled=False,monitor_health=False,switch_id=0,settings={},actions=[])
    for k,v in source.items():
        if k in APP_FIELDS and k!='id' and not (old and k=='adapter'):app[k]=copy.deepcopy(v)
    app['id']=target;app.setdefault('name',target);app['integration_events']=package['events']
    if app.get('adapter','json') not in ('json','bmcbf','fuel_tracker','travel_radar','wellness_check'):raise ValueError('Unknown relay adapter; choose a supported adapter')
    for key,default,minimum in (('poll_seconds',30,5),('stale_after_seconds',300,60),('sleep_max_age_seconds',900,0)):
        n=app.get(key,default)
        if not isinstance(n,(int,float)) or not math.isfinite(n) or n<minimum:raise ValueError('Invalid '+key)
    for key in ('suppressed_events','suppress_duplicate_events'):
        settings=app.get(key,{})
        if not isinstance(settings,dict) or any(not isinstance(k,str) or not isinstance(v,bool) for k,v in settings.items()):raise ValueError('Invalid event suppression preferences')
    missing=[];actions=[];ids=set()
    if include_mappings:
        for entry in package.get('mappings',[]):
            if not isinstance(entry,dict):raise ValueError('Invalid mapping')
            action={k:copy.deepcopy(v) for k,v in entry.items() if k in ACTION_FIELDS};aid=action.get('id')
            if not isinstance(aid,str) or not aid or aid in ids:raise ValueError('Mapping IDs must be unique')
            ids.add(aid);action['speech']='{summary}'
            if action.get('target_mode','any') not in ('any','gesture','location','specific','current'):raise ValueError('Invalid location mode')
            if action.get('display_mode','none') not in ('none','thought_bubble','popup_modal'):raise ValueError('Invalid display mode')
            for key in ('x','y','duration_seconds'):
                v=action.get(key,0)
                if not isinstance(v,(int,float)) or not math.isfinite(v) or (key=='duration_seconds' and v<0):raise ValueError('Invalid mapping '+key)
            for condition in action.get('conditions',[]):
                if not isinstance(condition,dict) or not isinstance(condition.get('field'),str) or condition.get('op','eq') not in ('eq','neq','lt','lte','gt','gte','contains') or 'value' not in condition:raise ValueError('Invalid value condition')
                if isinstance(condition['value'],str) and ('[removed]' in condition['value'] or condition['value']=='[configure locally]'):missing.append(aid+': redacted condition needs local configuration')
            scene=action.get('scene') or action.get('target_scene');room=current.get('scenes',{}).get(scene)
            if scene and room is None:missing.append(aid+': missing scene '+scene)
            if room and room.get('enabled') is False:missing.append(aid+': scene is disabled '+scene)
            if room and action.get('spot_id') and action['spot_id'] not in {s.get('id') for s in room.get('interaction_spots',[])}:missing.append(aid+': missing location '+action['spot_id'])
            role=action.get('animation');bindings=current.get('characters',{}).get(current.get('active_character'),{}).get('animations',{})
            if room and action.get('spot_id') and action.get('target_mode')=='specific':
                spot=next((s for s in room.get('interaction_spots',[]) if s.get('id')==action['spot_id']),None)
                if spot and role not in [spot.get('animation')]+spot.get('animations',[]):missing.append(aid+': animation is not placed at '+action['spot_id'])
            if role and action.get('target_mode') not in ('any','location') and bindings.get('idle_side' if role=='idle' else role) not in current.get('animation_sequences',{}):missing.append(aid+': missing character animation '+role)
            actions.append(action)
        app['actions']=actions
    if not app.get('actions'):
        app['actions']=[dict(id='status_check',label='Status / button response',event='status_check',is_primary=True,scene=current.get('active_scene'),animation='idle_side',target_mode='any',duration_seconds=0,speech='{summary}',display_mode='popup_modal')]
    if include_mappings and old:
        # A hardware assignment remains useful only with a primary response.
        if old.get('switch_id') and not any(a.get('is_primary') or a.get('id')=='status_check' for a in app['actions']):missing.append('Replacement must include a button/status response for the assigned hardware button')
    if not include_mappings:
        # Exported action IDs do not exist when only event definitions are being imported.
        if old:app['heartbeat_action_id']=old.get('heartbeat_action_id','__primary__')
        else:app['heartbeat_action_id']='__primary__'
    elif app.get('heartbeat_action_id','__primary__') not in ('','__primary__') and not any(a['id']==app['heartbeat_action_id'] for a in app['actions']):missing.append('Heartbeat reaction refers to a missing mapping')
    merged=copy.deepcopy(current);merged['apps']=[app if a.get('id')==target else a for a in merged.get('apps',[])]
    if old is None:merged['apps'].append(app)
    return merged,app,sorted(set(missing)),old,package

def preview_integration(data,current,target_id=None,include_mappings=False):
    merged,app,missing,old,package=prepare(data,current,target_id,include_mappings)
    return dict(digest=hashlib.sha256(data).hexdigest(),state_digest=hashlib.sha256(encoded(current)).hexdigest(),target_application=app['id'],name=app['name'],mode='replace' if old else 'add',missing=missing,
        events=[dict(name=e['name'],label=e['label']) for e in app['integration_events']],include_mappings=include_mappings,
        preferences={k:app.get(k) for k in APP_FIELDS if k not in ('id','name','color')},
        mappings=[{k:a.get(k) for k in ACTION_FIELDS} for a in app['actions']],
        notes=['Connection URLs, credentials, adapter, private adapter settings and hardware assignments are preserved locally on replacement; new applications start unconnected.',
        'Scenes, character animations and other applications remain unchanged.',
        'Custom speech templates are excluded; included mappings display the incoming summary.',
        'Mappings are '+('included; replacing an application replaces its action list.' if include_mappings else 'excluded; existing action mappings are retained.'),
        'Event examples are examples, never received updates. Review labels and conditions before sharing.'])

def import_integration(data,current,assets,config_dir,apply_config,digest,state,target_id=None,include_mappings=False):
    review=preview_integration(data,current,target_id,include_mappings)
    if review['digest']!=digest or review['state_digest']!=state or review['missing']:raise ValueError('Preview changed or dependencies are missing; preview again')
    merged,*_=prepare(data,current,target_id,include_mappings)
    directory=Path(config_dir)/'backups';directory.mkdir(parents=True,exist_ok=True);recovery=directory/('before-restore-'+str(time.time_ns())+'.zip');recovery.write_bytes(export_backup(current,assets,config_dir))
    try:apply_config(merged)
    except Exception:
        apply_config(current);raise
    return dict(status='ok',application=review['target_application'],recovery_backup=recovery.name)
