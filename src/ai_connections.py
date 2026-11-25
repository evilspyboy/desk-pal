"""Private connection profiles; no model calls or microphone capture."""
import copy
import json
import threading
import urllib.parse
from pathlib import Path

DEFAULTS = {'providers':{
                'openai': {'endpoint':'','model':''},
                'gemini': {'endpoint':'','model':''},
                'claude': {'endpoint':'','model':''},
                'local': {'endpoint':'','model':''},
                'on_device': {'endpoint':'/home/admin/test_llm/llama-b11706/llama-cli','model':'/home/admin/test_llm/qwen2.5-0.5b-instruct-q4_k_m.gguf'}
            },
            'chat_provider':'local','intent_engine':'cactus_needle',
            'chat_fallback_primary':'local','chat_fallback_secondary':'on_device',
            'chat_fallback_chain':['local','on_device'],
            'tts_provider':'local','stt_provider':'local',
            'tts':{'enabled':False,'model':'piper','voice':'en_US-lessac-low','speed':1.0,'keep_loaded':False},
            'stt':{'enabled':False,'model':'tiny.en','keep_loaded':True,'trigger_mode':'poke_sprite','wake_word':'hey deskpal','silence_seconds':2.0,'max_record_seconds':15.0,'speak_response':True},
            'attention_voice':{'enabled':True,'radar_required':True,'timeout_seconds':90.0,'no_radar_timeout_seconds':45.0,
                               'stale_age_seconds':900.0,'phase2_delay_seconds':24.0,'phase3_delay_seconds':52.0,
                               'cold_load_offset_seconds':14.0,
                               'phase1_template':'Hey, I have a {app} update!','phase2_phrase':"Hey, it's me, your pal!",
                               'phase3_phrase':'Hello? Over here!'}}
LOCK = threading.RLock()

def validate(value):
    result=copy.deepcopy(DEFAULTS)
    if not isinstance(value,dict): raise ValueError('AI settings must be an object')
    for key in ('chat_provider','tts_provider','stt_provider'):
        choice=value.get(key,result[key])
        if key == 'chat_provider':
            if choice in ('on_device', 'local', 'openai', 'gemini', 'claude'):
                result[key] = choice
            else:
                raise ValueError('Unknown provider')
        elif key in ('tts_provider', 'stt_provider'):
            if choice in ('local', 'openai', 'gemini', 'claude'):
                result[key] = choice
            else:
                raise ValueError('Unknown provider')
        elif choice not in result['providers']:
            raise ValueError('Unknown provider')
        else:
            result[key]=choice
    if 'intent_engine' in value:
        engine = value['intent_engine']
        if engine in ('cactus_needle', 'regex_only'):
            result['intent_engine'] = engine

    valid_fallbacks = ('local', 'local_llm', 'on_device', 'openai', 'gemini', 'claude', 'none')
    if 'chat_fallback_primary' in value:
        p = value['chat_fallback_primary']
        if p in valid_fallbacks:
            result['chat_fallback_primary'] = 'local' if p == 'local_llm' else p
    if 'chat_fallback_secondary' in value:
        s = value['chat_fallback_secondary']
        if s in valid_fallbacks:
            result['chat_fallback_secondary'] = 'local' if s == 'local_llm' else s

    chain = []
    if result['chat_fallback_primary'] not in ('none', None):
        chain.append(result['chat_fallback_primary'])
    if result['chat_fallback_secondary'] not in ('none', None) and result['chat_fallback_secondary'] not in chain:
        chain.append(result['chat_fallback_secondary'])
    result['chat_fallback_chain'] = chain or ['local', 'on_device']
    profiles=value.get('providers',{})
    tts=value.get('tts',{})
    if not isinstance(tts,dict): raise ValueError('TTS settings must be an object')
    result['tts'].update({k:v for k,v in tts.items() if k in result['tts']})
    if type(result['tts']['enabled']) is not bool: raise ValueError('TTS enabled must be true or false')
    if type(result['tts']['keep_loaded']) is not bool: raise ValueError('Keep loaded must be true or false')
    if result['tts']['model'] in ('kitten2','nano'):
        result['tts']['model']='piper';result['tts']['voice']='en_US-lessac-low'
    if result['tts']['model'] != 'piper': raise ValueError('Choose Piper')
    from piper_voices import voice_id
    voice_id(result['tts']['voice'])
    speed=result['tts']['speed']
    if type(speed) not in (int,float) or not .5 <= speed <= 2: raise ValueError('Speech speed must be between 0.5 and 2')
    stt=value.get('stt',{})
    if isinstance(stt,dict):
        result['stt'].update({k:v for k,v in stt.items() if k in result['stt']})
    if type(result['stt']['enabled']) is not bool: raise ValueError('STT enabled must be true or false')
    if type(result['stt']['keep_loaded']) is not bool: raise ValueError('STT keep_loaded must be true or false')
    if result['stt']['model'] not in ('tiny.en','base.en','small.en','whistle'): result['stt']['model']='tiny.en'
    if result['stt']['trigger_mode'] not in ('poke_sprite','wake_word','both'): result['stt']['trigger_mode']='poke_sprite'
    silence=result['stt']['silence_seconds']
    if not isinstance(silence,(int,float)) or not 0.5<=silence<=10.0: result['stt']['silence_seconds']=2.0
    attn=value.get('attention_voice',{})
    if not isinstance(attn,dict): raise ValueError('Attention voice settings must be an object')
    result['attention_voice'].update({k:v for k,v in attn.items() if k in result['attention_voice']})
    if type(result['attention_voice']['enabled']) is not bool: raise ValueError('Attention voice enabled must be true or false')
    if type(result['attention_voice']['radar_required']) is not bool: raise ValueError('Radar required must be true or false')
    for num_key,min_val,max_val in (('timeout_seconds',10,600),('no_radar_timeout_seconds',5,300),('stale_age_seconds',30,86400),('phase2_delay_seconds',5,120),('phase3_delay_seconds',10,300),('cold_load_offset_seconds',0,60)):
        v=result['attention_voice'][num_key]
        if type(v) not in (int,float) or not min_val<=v<=max_val: raise ValueError(f'{num_key} must be between {min_val} and {max_val}')
    for str_key in ('phase1_template','phase2_phrase','phase3_phrase'):
        s=result['attention_voice'][str_key]
        if not isinstance(s,str) or len(s)>200: raise ValueError(f'{str_key} must be text up to 200 characters')
    if not isinstance(profiles,dict): raise ValueError('Provider profiles must be an object')
    for name,profile in profiles.items():
        if name not in result['providers'] or not isinstance(profile,dict): raise ValueError('Unknown provider profile')
        for key in ('endpoint','model'):
            text=profile.get(key,'')
            if not isinstance(text,str) or len(text)>500: raise ValueError('Endpoint/model must be short text')
            result['providers'][name][key]=text.strip()
        url=result['providers'][name]['endpoint']
        if url:
            if name == 'on_device':
                pass
            else:
                parsed=urllib.parse.urlsplit(url)
                if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                    raise ValueError('Endpoint must be an HTTP(S) URL without credentials or query parameters')
    return result

def read(path):
    with LOCK:
        target=Path(path)
        if not target.exists(): return copy.deepcopy(DEFAULTS)
        return validate(json.loads(target.read_text(encoding='utf-8')))

def save(path,value):
    validate(value)
    with LOCK:
        current=read(path)
        for key in ('chat_provider','intent_engine','chat_fallback_primary','chat_fallback_secondary','chat_fallback_chain','tts_provider','stt_provider'):
            if key in value:current[key]=value[key]
        for name,profile in value.get('providers',{}).items():
            if name not in current['providers']:
                current['providers'][name] = {}
            current['providers'][name].update(profile)
        current['tts'].update(value.get('tts',{}))
        current['stt'].update(value.get('stt',{}))
        current['attention_voice'].update(value.get('attention_voice',{}))
        result=validate(current)
        target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
        temp=target.with_suffix('.tmp');temp.write_text(json.dumps(result,indent=2),encoding='utf-8');temp.replace(target)
    return result
