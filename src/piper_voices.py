"""Private Piper voice library; bounded uploads and optional official downloader."""
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

MAX_MODEL=256*1024*1024
MAX_CONFIG=1024*1024

def voice_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',value):
        raise ValueError('Voice name must use letters, numbers, underscores or hyphens')
    return value

def root_path():return Path.home()/'.cache/deskpal/piper'

def resolve(value,root=None):
    value=voice_id(value);root=Path(root or root_path()).resolve()
    for path in (root/(value+'.onnx'),root/value/(value+'.onnx')):
        if path.is_file() and Path(str(path)+'.json').is_file() and path.resolve().is_relative_to(root):return path
    raise ValueError('Selected Piper voice is not installed; add it first')

def configuration(path):
    if path.stat().st_size>MAX_CONFIG:raise ValueError('Voice configuration exceeds 1 MB')
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict):raise ValueError('Piper configuration must be an object')
    rate=data.get('audio',{}).get('sample_rate')
    if type(rate) is not int or not 8000<=rate<=96000:raise ValueError('Invalid Piper sample rate')
    if not isinstance(data.get('phoneme_id_map'),dict) or not data['phoneme_id_map']:raise ValueError('Missing Piper phoneme map')
    return data

class VoiceLibrary:
    def __init__(self,root=None,python=None):
        self.root=Path(root or root_path()).resolve()
        self.python=Path(python or Path.home()/'.venv-deskpal-tts/bin/python')
        self.lock=threading.RLock();self.task={'state':'idle','error':''}

    def snapshot(self):
        voices=[]
        paths=list(self.root.glob('*.onnx'))+list(self.root.glob('*/*.onnx'))
        for path in paths:
            if path.parent.name.startswith('.'):continue
            try:
                name=voice_id(path.stem);resolve(name,self.root)
                config=configuration(Path(str(path)+'.json'))
                voices.append(dict(id=name,label=name.replace('_',' ').replace('-',' · '),
                    sample_rate=config['audio']['sample_rate'],speakers=config.get('num_speakers',1)))
            except (OSError,ValueError,TypeError,AttributeError):continue
        with self.lock:return dict(voices=sorted(voices,key=lambda v:v['id']),install=dict(self.task))

    def _available(self,name):
        voice_id(name)
        try:resolve(name,self.root)
        except ValueError:pass
        else:raise ValueError('That voice is already installed; choose a different name')
        if self.task['state'] in ('downloading','validating'):raise ValueError('A voice installation is already in progress')
        if not self.python.exists():raise ValueError('Install the optional Piper environment first')
        self.root.mkdir(parents=True,exist_ok=True)

    def _commit(self,stage,name):
        model=stage/(name+'.onnx');config=Path(str(model)+'.json')
        if not 0<model.stat().st_size<=MAX_MODEL:raise ValueError('Voice model must be between 1 byte and 256 MB')
        configuration(config)
        # Check both the ONNX graph and its Piper configuration in an isolated process.
        code="""import json,sys,wave,tempfile
from pathlib import Path
import onnxruntime as ort
from piper import PiperVoice
from piper.config import PiperConfig
p=Path(sys.argv[1]);opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
v=PiperVoice(session=ort.InferenceSession(str(p),opts,providers=['CPUExecutionProvider']),config=PiperConfig.from_dict(json.loads(Path(str(p)+'.json').read_text())))
with tempfile.TemporaryFile() as f:
 with wave.open(f,'wb') as wav:v.synthesize_wav('Hello.',wav)
"""
        result=subprocess.run([str(self.python),'-c',code,str(model)],capture_output=True,text=True,timeout=60,
            env=dict(os.environ,OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2'))
        if result.returncode:raise ValueError('Piper could not load this model/config pair: '+result.stderr[-250:])
        target=self.root/name
        if target.exists():raise ValueError('That voice directory already exists')
        stage.rename(target)

    def upload(self,name,kind,stream,length):
        name=voice_id(name)
        if kind not in ('model','config'):raise ValueError('Upload a model or configuration')
        limit=MAX_MODEL if kind=='model' else MAX_CONFIG
        if not 0<length<=limit:raise ValueError('Voice file exceeds its upload limit')
        with self.lock:
            self._available(name)
            stage=self.root/('.upload-'+name)
            if kind=='model':
                if stage.exists():shutil.rmtree(stage)
                stage.mkdir()
            elif not (stage/(name+'.onnx')).is_file():raise ValueError('Upload the ONNX model first')
            file=stage/(name+'.onnx'+('.json' if kind=='config' else ''))
            try:
                with file.open('wb') as output:
                    remaining=length
                    while remaining:
                        chunk=stream.read(min(1024*1024,remaining))
                        if not chunk:raise ValueError('Voice upload was interrupted')
                        output.write(chunk);remaining-=len(chunk)
                if kind=='config':
                    self.task=dict(state='validating',voice=name,error='')
                    self._commit(stage,name)
                    self.task=dict(state='ready',voice=name,error='')
                return dict(state='ready' if kind=='config' else 'model_uploaded',voice=name)
            except Exception as error:
                if stage.exists():shutil.rmtree(stage)
                self.task=dict(state='error',voice=name,error=str(error)[:400])
                raise

    def download(self,name):
        name=voice_id(name)
        with self.lock:
            self._available(name);self.task=dict(state='downloading',voice=name,error='')
        def worker():
            stage=Path(tempfile.mkdtemp(prefix='.download-',dir=self.root))
            try:
                result=subprocess.run([str(self.python),'-m','piper.download_voices','--download-dir',str(stage),name],
                    capture_output=True,text=True,timeout=300)
                if result.returncode:raise ValueError('Voice download failed: '+result.stderr[-300:])
                with self.lock:self.task=dict(state='validating',voice=name,error='')
                self._commit(stage,name)
                with self.lock:self.task=dict(state='ready',voice=name,error='')
            except Exception as error:
                with self.lock:self.task=dict(state='error',voice=name,error=str(error)[:400])
            finally:
                if stage.exists():shutil.rmtree(stage)
        threading.Thread(target=worker,name='deskpal-voice-install',daemon=True).start()
        return dict(self.task)

_lock=threading.Lock()
def library_for(app):
    with _lock:
        if not hasattr(app,'piper_voices'):app.piper_voices=VoiceLibrary()
        return app.piper_voices
