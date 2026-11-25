"""STT Engine manager for isolated faster-whisper worker process."""
import atexit
import json
import logging
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger("deskpal.stt")

class STTEngine:
    def __init__(self):
        self.lock = threading.RLock()
        self.process = None
        self.keep_loaded = False
        self.loaded_model = None
        self.selected_model = "tiny.en"
        self.status = {'state': 'idle', 'error': '', 'loaded': False, 'memory_mb': 0}
        atexit.register(self.stop)

    def snapshot(self):
        with self.lock:
            is_alive = bool(self.process and self.process.poll() is None)
            res = dict(self.status)
            res['loaded'] = is_alive and bool(self.loaded_model)
            return res

    @staticmethod
    def _terminate(process):
        if process is None:
            return
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except Exception:
                try:
                    process.terminate()
                except Exception:
                    pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
                try:
                    process.wait(timeout=1)
                except Exception:
                    pass
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream:
                try:
                    stream.close()
                except Exception:
                    pass

    def configure(self, stt_cfg):
        with self.lock:
            self.keep_loaded = bool(stt_cfg.get('keep_loaded', False))
            self.selected_model = stt_cfg.get('model', 'tiny.en')
            if not stt_cfg.get('enabled', False):
                self.stop()
            elif (not self.keep_loaded or self.loaded_model != self.selected_model) and self.status['state'] not in ('transcribing',):
                self._terminate(self.process)
                self.process = None
                self.loaded_model = None
                self.status['loaded'] = False

    def stop(self):
        with self.lock:
            self._terminate(self.process)
            self.process = None
            self.loaded_model = None
            self.status = {'state': 'idle', 'error': '', 'loaded': False, 'memory_mb': 0}

    def _get_python_path(self):
        venv_py = Path.home() / '.venv-deskpal-tts' / 'bin' / 'python3'
        if venv_py.exists():
            return str(venv_py)
        venv_py2 = Path.home() / '.venv-deskpal-tts' / 'bin' / 'python'
        if venv_py2.exists():
            return str(venv_py2)
        return 'python3'

    def _ensure_worker(self, model_name):
        if self.process is not None and self.process.poll() is None and self.loaded_model == model_name:
            return self.process
            
        self._terminate(self.process)
        self.process = None
        self.loaded_model = None
        
        worker_script = str(Path(__file__).parent / 'stt_worker.py')
        python_bin = self._get_python_path()
        
        kwargs = {
            'stdin': subprocess.PIPE,
            'stdout': subprocess.PIPE,
            'stderr': subprocess.PIPE,
            'text': True,
            'bufsize': 1
        }
        if os.name != 'nt':
            kwargs['preexec_fn'] = os.setsid
            
        self.process = subprocess.Popen([python_bin, worker_script], **kwargs)
        self.loaded_model = model_name
        return self.process

    def transcribe_file(self, audio_path, model_name=None, threads=2):
        with self.lock:
            model_to_use = model_name or self.selected_model or "tiny.en"
            self.status['state'] = 'transcribing'
            self.status['error'] = ''
            
            try:
                proc = self._ensure_worker(model_to_use)
                req = {
                    "cmd": "transcribe",
                    "model": model_to_use,
                    "path": str(audio_path),
                    "threads": threads
                }
                proc.stdin.write(json.dumps(req) + "\n")
                proc.stdin.flush()
                
                resp_line = proc.stdout.readline()
                if not resp_line:
                  err_out = proc.stderr.read() if proc.stderr else ""
                  raise RuntimeError(f"STT worker exited unexpectedly. Stderr: {err_out[:200]}")
                  
                data = json.loads(resp_line)
                if 'error' in data:
                    raise RuntimeError(data['error'])
                    
                self.status['memory_mb'] = data.get('memory_mb', 0)
                self.status['state'] = 'ready'
                self.status['loaded'] = True
                
                if not self.keep_loaded:
                    self.stop()
                    
                return data
            except Exception as err:
                self.status['state'] = 'error'
                self.status['error'] = str(err)[:200]
                self._terminate(self.process)
                self.process = None
                self.loaded_model = None
                raise

    def transcribe(self, audio_path, model_name=None, model=None, threads=2):
        return self.transcribe_file(audio_path, model_name=model_name or model, threads=threads)
