"""Optional Piper worker with explicit retention, cancellation and bounded requests."""
import atexit
import json
import os
import select
import signal
import subprocess
import tempfile
import threading
import datetime
import time
import uuid
import shutil
from pathlib import Path
from ai_connections import read

CACHE_AUDIO_PATH = Path.home() / '.cache' / 'deskpal' / 'last_speech.wav'
PREBAKE_AUDIO_PATH = Path('/tmp/deskpal_prebake_morning.wav') if os.name != 'nt' else Path.home() / '.cache' / 'deskpal' / 'prebake_morning.wav'
PREBAKE_META_PATH = Path('/tmp/deskpal_prebake_morning.json') if os.name != 'nt' else Path.home() / '.cache' / 'deskpal' / 'prebake_morning.json'

_output_lock=threading.Lock()

class SpeechOutput:
    def __init__(self):
        self.lock=threading.RLock()
        self.synth_io_lock=threading.Lock()
        self.process=None
        self._synth=None
        self.synth_trace=[]
        self.cancelled=False;self.keep_loaded=False
        self.synth_voice=None;self.selected_voice=None
        self.status={'state':'idle','error':''}
        self.last_playback_ended = 0.0
        self.history = []
        self.last_spoken = None
        self._load_history()
        self._load_settings()
        atexit.register(self.stop)

    @property
    def synth(self):
        return self._synth

    @synth.setter
    def synth(self, val):
        import traceback
        frames = traceback.extract_stack(limit=4)
        caller = frames[-2] if len(frames) >= 2 else None
        loc = f"{caller.name}:{caller.lineno} in {os.path.basename(caller.filename)}" if caller else "unknown"
        msg = f"synth set to {bool(val)} by {loc}"
        if not hasattr(self, 'synth_trace'): self.synth_trace = []
        self.synth_trace.append(msg)
        if len(self.synth_trace) > 20: self.synth_trace = self.synth_trace[-20:]
        print(f"[SynthTrace] {msg}")
        self._synth = val

    def _load_settings(self):
        for p in ['/home/admin/config/ai_settings.json', 'config/ai_settings.json']:
            if os.path.exists(p):
                try:
                    data = read(p)
                    tts = data.get('tts', {})
                    if tts:
                        self.configure(tts)
                    print(f"[Speech] Loaded settings from {p}: enabled={tts.get('enabled')} keep_loaded={tts.get('keep_loaded')} voice={tts.get('voice')}")
                    break
                except Exception as e:
                    print(f"[Speech] _load_settings error on {p}: {e}")

    def _history_path(self):
        for p in ['/home/admin/config/speech_history.json', 'config/speech_history.json']:
            if os.path.exists(os.path.dirname(p)):
                return p
        return 'config/speech_history.json'

    def _load_history(self):
        path = self._history_path()
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.history = data[:50]
                        if self.history:
                            self.last_spoken = self.history[0]
        except Exception:
            self.history = []

    def _save_history(self):
        path = self._history_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.history[:50], f, indent=2)
        except Exception:
            pass

    def get_history(self, limit=30):
        with self.lock:
            now = time.time()
            res = []
            for item in self.history[:limit]:
                copy_item = dict(item)
                copy_item['age_seconds'] = max(0, int(now - item.get('timestamp', now)))
                res.append(copy_item)
            return res

    def get_last_spoken(self, max_age_seconds=None):
        with self.lock:
            if not self.last_spoken:
                return None
            if max_age_seconds is not None:
                if time.time() - self.last_spoken.get('timestamp', 0) > max_age_seconds:
                    return None
            return dict(self.last_spoken)

    def replay(self, item_id=None, max_age_seconds=None, prefix=""):
        with self.lock:
            target = None
            if item_id:
                target = next((item for item in self.history if item.get('id') == item_id), None)
            else:
                target = self.get_last_spoken(max_age_seconds)
            if not target:
                return False, "No speech found to replay."
            text = target['text']
            settings_path = target.get('settings_path')
            speaker = target.get('speaker', {'enabled': True, 'volume': 0.25, 'output': 'default'})

        spoken_text = (prefix + text) if prefix else text
        self.speak(spoken_text, settings_path, speaker, source='replay')
        return True, text

    def snapshot(self):
        with self.lock:return dict(self.status,loaded=bool(self.synth and self.synth.poll() is None),synth_trace=list(getattr(self,'synth_trace',[])))

    @staticmethod
    def _terminate(process):
        if process is None:return
        if process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait()
        for stream in (process.stdin,process.stdout,process.stderr):
            if stream:stream.close()

    def configure(self,tts):
        with self.lock:
            self.keep_loaded=tts.get('keep_loaded', False)
            self.selected_voice=tts.get('voice')
            if not tts.get('enabled'):self.stop(hard=True)
            elif (not self.keep_loaded or self.synth_voice != self.selected_voice) and self.status['state'] not in ('generating','playing'):
                self._terminate(self.synth);self.synth=None
        if tts.get('enabled') and self.keep_loaded:
            self.warmup()

    def warmup(self):
        """Warm up Piper synth in the background so model is preloaded into RAM."""
        def _warm():
            print(f"[Speech] Warmup thread started for voice={self.selected_voice} keep_loaded={self.keep_loaded}")
            with self.synth_io_lock:
                with self.lock:
                    if not self.keep_loaded or not self.selected_voice:
                        print("[Speech] Warmup aborted: not keep_loaded or no selected_voice")
                        return
                    if self.synth is not None and self.synth.poll() is None and self.synth_voice == self.selected_voice:
                        print("[Speech] Warmup: synth already resident")
                        return
                    python=Path.home()/'.venv-deskpal-tts'/'bin'/'python'
                    if not python.exists():
                        print(f"[Speech] Warmup error: python binary not found at {python}")
                        return
                    try:
                        self._terminate(self.synth)
                        self.synth=subprocess.Popen([str(python),str(Path(__file__).with_name('piper_synth.py'))],
                            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,
                            env=dict(os.environ,OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4'),start_new_session=True)
                        self.synth_voice=self.selected_voice
                        self.synth.stdin.write(json.dumps({'action':'preload','voice':self.selected_voice})+'\n')
                        self.synth.stdin.flush()
                        print(f"[Speech] Warmup spawned synth process PID {self.synth.pid}")
                    except Exception as err:
                        print(f"[Speech] Warmup spawn error: {err}")
                        self._terminate(self.synth);self.synth=None
                        return
                    synth=self.synth
                try:
                    if select.select([synth.stdout],[],[],60)[0]:
                        line = synth.stdout.readline()
                        print(f"[Speech] Warmup response: {line.strip()}")
                except Exception as err:
                    print(f"[Speech] Warmup readline error: {err}")
        threading.Thread(target=_warm,name='deskpal-tts-warmup',daemon=True).start()

    def stop_playback(self):
        """Interrupt active playback without unloading resident model."""
        with self.lock:
            self.cancelled=True
            self._terminate(self.process);self.process=None
            if not self.keep_loaded:
                self._terminate(self.synth);self.synth=None
            self.status={'state':'idle','error':''}

    def stop(self, hard=False):
        import traceback
        frames = traceback.extract_stack()
        callers = " -> ".join([f"{f.name}:{f.lineno} in {os.path.basename(f.filename)}" for f in frames[-4:-1]])
        if not hasattr(self, 'synth_trace'): self.synth_trace = []
        self.synth_trace.append(f"stop(hard={hard}) called by: {callers}")
        print(f"[SynthTrace] stop(hard={hard}) called by: {callers}")
        with self.lock:
            self.cancelled=True
            self._terminate(self.process);self.process=None
            if hard or not self.keep_loaded:
                self._terminate(self.synth);self.synth=None
            self.status={'state':'idle','error':''}

    def prebake(self, text, settings_path=None, speaker=None, source='morning_greeting'):
        """Pre-synthesize audio in the background and cache to disk for instant zero-latency playback."""
        if not isinstance(text, str) or not text.strip() or len(text) > 500:
            return False
        if not settings_path or not os.path.exists(settings_path):
            for alt in ['/home/admin/config/ai_settings.json', 'config/ai_settings.json']:
                if os.path.exists(alt):
                    settings_path = alt
                    break
        try:
            tts = read(settings_path).get('tts', {})
        except Exception:
            return False
        if not tts.get('enabled') or not tts.get('voice'):
            return False
        if speaker is None:
            speaker = {'enabled': True, 'volume': 0.25, 'output': 'default'}
        elif not speaker.get('enabled'):
            return False

        python = Path.home() / '.venv-deskpal-tts' / 'bin' / 'python'
        from piper_voices import resolve
        try:
            model = resolve(tts['voice'])
        except Exception:
            return False
        if not python.exists() or not model.exists():
            return False

        voice = tts['voice']
        speed = tts.get('speed', 1.0)
        volume = speaker.get('volume', 0.25)

        # Check if existing prebaked cache already matches this exact text, voice, speed, volume
        if PREBAKE_AUDIO_PATH.exists() and PREBAKE_META_PATH.exists():
            try:
                meta = json.loads(PREBAKE_META_PATH.read_text(encoding='utf-8'))
                if (meta.get('text') == text and meta.get('voice') == voice 
                    and meta.get('speed') == speed and abs(meta.get('volume', 0) - volume) < 0.01):
                    return True  # Already cached!
            except Exception:
                pass

        with self.lock:
            if getattr(self, '_prebaking', False):
                return False
            self._prebaking = True

        def _do_prebake():
            try:
                with tempfile.TemporaryDirectory(prefix='deskpal-prebake-') as directory:
                    path = Path(directory) / 'speech.wav'
                    with self.synth_io_lock:
                        with self.lock:
                            if self.synth is None or self.synth.poll() is not None or self.synth_voice != voice:
                                self._terminate(self.synth)
                                self.synth = subprocess.Popen(
                                    [str(python), str(Path(__file__).with_name('piper_synth.py'))],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                    env=dict(os.environ, OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4'), start_new_session=True
                                )
                                self.synth_voice = voice
                            synth = self.synth
                            synth.stdin.write(json.dumps(dict(text=text, voice=voice, speed=speed, path=str(path), volume=volume)) + '\n')
                            synth.stdin.flush()
                        if not select.select([synth.stdout], [], [], 60)[0]:
                            return
                        raw_line = synth.stdout.readline()
                        if not raw_line or not raw_line.strip():
                            return
                        metrics = json.loads(raw_line)
                        if metrics.get('error'):
                            return

                    out_48k = Path(directory) / 'speech_48k.wav'
                    conv_cmd = ['ffmpeg', '-y', '-v', 'error', '-i', str(path), '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(out_48k)]
                    play_path = out_48k if (subprocess.run(conv_cmd).returncode == 0 and out_48k.exists()) else path

                    PREBAKE_AUDIO_PATH.parent.mkdir(parents=True, exist_ok=True)
                    tmp_out = PREBAKE_AUDIO_PATH.with_suffix('.tmp')
                    shutil.copyfile(str(play_path), str(tmp_out))
                    tmp_out.replace(PREBAKE_AUDIO_PATH)

                    meta = {
                        'text': text,
                        'voice': voice,
                        'speed': speed,
                        'volume': volume,
                        'timestamp': time.time(),
                        'metrics': metrics
                    }
                    PREBAKE_META_PATH.write_text(json.dumps(meta), encoding='utf-8')
                    print(f"[Speech] Prebake successfully ready for: '{text[:35]}...' ({len(text)} chars)")
            except Exception as e:
                print(f"[Speech] Prebake error: {e}")
            finally:
                with self.lock:
                    self._prebaking = False

        threading.Thread(target=_do_prebake, name='deskpal-tts-prebake', daemon=True).start()
        return True

    def speak(self,text,settings_path=None,speaker=None,source='speech'):
        if not isinstance(text,str) or not text.strip() or len(text)>500:raise ValueError('Enter 1–500 characters')
        if not settings_path or not os.path.exists(settings_path):
            for alt in ['/home/admin/config/ai_settings.json', 'config/ai_settings.json']:
                if os.path.exists(alt):
                    settings_path = alt
                    break
        tts=read(settings_path)['tts']
        if not tts['enabled']:raise ValueError('Enable and save Piper first')
        if speaker is None:
            speaker = {'enabled': True, 'volume': 0.25, 'output': 'default'}
        elif not speaker.get('enabled'):raise ValueError('Enable the speaker on Hardware first')
        python=Path.home()/'.venv-deskpal-tts'/'bin'/'python'
        from piper_voices import resolve
        model=resolve(tts['voice'])
        if not python.exists() or not model.exists():raise ValueError('Piper environment or voice is not installed on this device')
        entry = {
            'id': uuid.uuid4().hex[:8],
            'text': text,
            'timestamp': time.time(),
            'time_str': datetime.datetime.now().strftime('%H:%M:%S'),
            'date_str': datetime.datetime.now().strftime('%Y-%m-%d'),
            'source': source,
            'settings_path': str(settings_path),
            'speaker': dict(speaker) if isinstance(speaker, dict) else {}
        }
        with self.lock:
            if source != 'replay':
                self.last_spoken = entry
            self.history.insert(0, entry)
            if len(self.history) > 50:
                self.history = self.history[:50]
            self._save_history()
        with self.lock:
            if self.status['state'] in ('generating', 'playing'):
                self.cancelled = True
                self._terminate(self.process)
                self.process = None
                if not self.keep_loaded or self.synth_voice != tts['voice'] or self.status['state'] == 'generating':
                    self._terminate(self.synth)
                    self.synth = None
                self.status = {'state': 'idle', 'error': ''}
            self.cancelled = False
            self.keep_loaded = tts['keep_loaded']
            self.selected_voice = tts['voice']
            self.status = {'state': 'generating', 'error': ''}

        # Check if prebaked audio matches for zero-latency instant playback!
        use_prebaked = False
        prebake_metrics = {}
        if PREBAKE_AUDIO_PATH.exists() and PREBAKE_META_PATH.exists():
            try:
                meta = json.loads(PREBAKE_META_PATH.read_text(encoding='utf-8'))
                if (meta.get('text') == text and meta.get('voice') == tts['voice']
                    and meta.get('speed') == tts.get('speed', 1.0)
                    and abs(meta.get('volume', 0) - speaker.get('volume', 0.25)) < 0.01):
                    use_prebaked = True
                    prebake_metrics = meta.get('metrics', {})
            except Exception:
                pass

        def worker():
            try:
                with tempfile.TemporaryDirectory(prefix='deskpal-speech-') as directory:
                    path=Path(directory)/'speech.wav'
                    metrics = prebake_metrics
                    if use_prebaked:
                        play_path = Path(directory) / 'prebaked_48k.wav'
                        shutil.copyfile(str(PREBAKE_AUDIO_PATH), str(play_path))
                        print(f"[Speech] INSTANT PLAYBACK using prebaked audio ({len(text)} chars)")
                    else:
                        with self.synth_io_lock:
                            with self.lock:
                                if self.cancelled:return
                                if self.synth is None or self.synth.poll() is not None or self.synth_voice != tts['voice']:
                                    self._terminate(self.synth)
                                    self.synth=subprocess.Popen([str(python),str(Path(__file__).with_name('piper_synth.py'))],
                                        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,
                                        env=dict(os.environ,OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4'),start_new_session=True)
                                    self.synth_voice=tts['voice']
                                synth=self.synth
                                synth.stdin.write(json.dumps(dict(text=text,voice=tts['voice'],speed=tts['speed'],path=str(path),volume=speaker.get('volume',.25)))+'\n')
                                synth.stdin.flush()
                            if not select.select([synth.stdout],[],[],60)[0]:raise ValueError('Piper generation timed out')
                            raw_line = synth.stdout.readline()
                            if not raw_line or not raw_line.strip():
                                err_out = synth.stderr.read() if synth.stderr else ""
                                raise ValueError(f"Piper synthesis returned no data (model may still be loading). {err_out[:100]}")
                            metrics=json.loads(raw_line)
                            if metrics.get('error'):raise ValueError(metrics['error'])

                        # Resample to 48kHz Stereo so hardware USB DACs and ALSA play cleanly without static
                        out_48k = Path(directory) / 'speech_48k.wav'
                        conv_cmd = ['ffmpeg', '-y', '-v', 'error', '-i', str(path), '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(out_48k)]
                        play_path = out_48k if (subprocess.run(conv_cmd).returncode == 0 and out_48k.exists()) else path

                    # Cache for web audio replay in browser
                    try:
                        CACHE_AUDIO_PATH.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(str(play_path), str(CACHE_AUDIO_PATH))
                    except Exception:
                        pass

                    from audio_output import playback_command
                    command=playback_command(speaker.get('output','default'),play_path)
                    with self.lock:
                        if self.cancelled:return
                        if not self.keep_loaded:self._terminate(self.synth);self.synth=None
                        self.status={'state':'playing','error':'',**metrics}
                        self.process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,start_new_session=True)
                        process=self.process
                    _,err=process.communicate(timeout=120)
                    if process.returncode and not self.cancelled:raise ValueError(err[-300:] or 'Speaker playback failed')
            except Exception as error:
                with self.lock:
                    self._terminate(self.synth);self.synth=None
                    self._terminate(self.process);self.process=None
                    self.status={'state':'error','error':str(error)[:400]}
            finally:
                with self.lock:
                    self._terminate(self.process);self.process=None
                    self.last_playback_ended = time.time()
                    if (not self.keep_loaded) or (self.synth_voice != self.selected_voice):
                        self._terminate(self.synth);self.synth=None
                    if self.cancelled:self.status={'state':'idle','error':''}
                    elif self.status['state'] != 'error':self.status={'state':'idle','error':'',**metrics}
        threading.Thread(target=worker,name='deskpal-speech',daemon=True).start()

def output_for(app):
    with _output_lock:
        if not hasattr(app,'speech_output'):app.speech_output=SpeechOutput()
        return app.speech_output
