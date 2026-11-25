"""
Voice Sentry coordinator for continuous microphone capture, wake keyword detection, and STT.
Unified single-stream ALSA capture: prevents device lock contention.
"""
import array
import collections
import json
import logging
import math
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path
from stt_engine import STTEngine

try:
    from voice_command_router import dispatch_voice_command
except ImportError:
    dispatch_voice_command = None

logger = logging.getLogger("deskpal.voice_sentry")

class VoiceSentry:
    def __init__(self, stt_engine=None):
        self.lock = threading.RLock()
        self.stt_engine = stt_engine or STTEngine()
        self._app_ref = None
        self.state = "idle"  # idle, listening, transcribing
        self.capture_proc = None
        self.capture_thread = None
        self.capture_running = False
        
        self.audio_frames = []
        self.speech_detected = False
        self.start_time = 0.0
        self.last_speech_time = 0.0
        self.test_capturing = False
        self.test_frames = []
        self.live_peak = 0
        self.live_rms_dbfs = -70.0
        self.live_ambient_floor = 0.0
        self.live_updated_at = 0.0
        
        self.config = {
            "enabled": True,
            "model": "tiny.en",
            "keep_loaded": True,
            "trigger_mode": "both",  # poke_sprite, wake_word, both
            "wake_word": "hey pal",
            "wake_peak_threshold": 8500,
            "silence_seconds": 2.0,
            "max_record_seconds": 15.0,
            "speak_response": True
        }
        self.latest_transcription = ""

    def is_enabled(self):
        with self.lock:
            return bool(self.config.get("enabled", False))

    def configure(self, stt_cfg):
        with self.lock:
            self.config.update(stt_cfg)
            self.stt_engine.configure(self.config)

    def snapshot(self):
        with self.lock:
            engine_snap = self.stt_engine.snapshot()
            return {
                "state": self.state,
                "enabled": self.config["enabled"],
                "model": self.config["model"],
                "keep_loaded": self.config["keep_loaded"],
                "trigger_mode": self.config["trigger_mode"],
                "wake_word": self.config["wake_word"],
                "silence_seconds": self.config["silence_seconds"],
                "latest_transcription": self.latest_transcription,
                "engine": engine_snap
            }

    def tick(self, app, now):
        """Called by DeskPalApp on each frame to maintain single-stream microphone capture."""
        with self.lock:
            if not self.config.get("enabled", False):
                if self.capture_running:
                    self.stop_capture()
                return

            if not self.capture_running or self.capture_thread is None or not self.capture_thread.is_alive():
                self.capture_running = True
                self.capture_thread = threading.Thread(
                    target=self._capture_worker,
                    args=(app,),
                    daemon=True
                )
                self.capture_thread.start()

    def stop_capture(self):
        with self.lock:
            self.capture_running = False
            if self.capture_proc is not None:
                try:
                    self.capture_proc.terminate()
                    self.capture_proc.wait(timeout=0.5)
                except Exception:
                    try: self.capture_proc.kill()
                    except Exception: pass
                self.capture_proc = None

    def trigger_poke(self, app):
        """Called when user taps the character sprite (push-to-talk)."""
        with self.lock:
            if not self.config.get("enabled", False):
                return False
            if app and (getattr(app, 'is_sleeping', False) or getattr(app, 'standby_choice', None)):
                return False

            if self.state == "listening":
                # Manual finish tap -> trigger transcription
                logger.info("[VoiceSentry] Sprite tapped while listening -> manual finish.")
                self.state = "transcribing"
                threading.Thread(target=self._process_transcription_and_reply, args=(app,), daemon=True).start()
                return True

            if self.state == "idle":
                logger.info("[VoiceSentry] Sprite tapped -> starting listening mode.")
                self.start_listening(app)
                return True

            return False

    def start_listening(self, app):
        """Transitions state to actively recording user speech for command."""
        with self.lock:
            if app:
                self._app_ref = app
            self.state = "listening"
            self.audio_frames = []
            self.speech_detected = False
            self.start_time = time.monotonic()
            self.last_speech_time = time.monotonic()

            if app:
                setattr(app, 'voice_listening', True)
                setattr(app, 'wake_word_active', True)
                setattr(app, 'voice_thought_bubble', {
                    'text': 'Listening... (tap or pause to finish)',
                    'timestamp': time.monotonic(),
                    'expires_at': time.monotonic() + self.config.get("max_record_seconds", 15.0) + 2.0
                })

            if not self.capture_running or self.capture_thread is None or not self.capture_thread.is_alive():
                self.capture_running = True
                self.capture_thread = threading.Thread(
                    target=self._capture_worker,
                    args=(app,),
                    daemon=True
                )
                self.capture_thread.start()

            return True

    def stop_listening_and_transcribe(self, app=None):
        """Called when user manually requests stop listening and transcribes speech."""
        with self.lock:
            target_app = app or getattr(self, '_app_ref', None)
            if self.state == "listening":
                logger.info("[VoiceSentry] stop_listening_and_transcribe called.")
                self.state = "transcribing"
                threading.Thread(target=self._process_transcription_and_reply, args=(target_app,), daemon=True).start()
                return True
            return False

    def _capture_worker(self, app):
        """Single-stream capture loop: manages wake-detection, recording, and silence cutoff."""
        logger.info("[VoiceSentry] Starting unified ALSA capture stream...")
        mic_dev = "plughw:Device,0"
        chunk_size = 3200  # 0.1s at 16kHz S16_LE mono

        while self.capture_running:
            rec_cmd = ['arecord', '-q', '-D', mic_dev, '-t', 'raw', '-f', 'S16_LE', '-r', '16000', '-c', '1']
            proc = None
            try:
                proc = subprocess.Popen(rec_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            except Exception:
                try:
                    rec_cmd[3] = 'default'
                    proc = subprocess.Popen(rec_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                except Exception as e:
                    logger.error(f"[VoiceSentry] Failed starting arecord: {e}")
                    time.sleep(2.0)
                    continue

            with self.lock:
                self.capture_proc = proc

            pre_buffer = collections.deque(maxlen=8)
            ambient_floor = 1200.0
            last_wake_miss_time = 0.0
            consecutive_misses = 0
            wake_miss_cooldown = 2.5
            last_quiet_time = time.monotonic()

            try:
                while self.capture_running:
                    try:
                        raw = proc.stdout.read(chunk_size)
                    except Exception:
                        break
                    if not raw or len(raw) < chunk_size:
                        break

                    samples = array.array('h', raw)
                    peak = max(map(abs, samples)) if samples else 0
                    now = time.monotonic()
                    if samples:
                        rms = math.sqrt(sum(v * v for v in samples) / len(samples))
                        self.live_rms_dbfs = round(20 * math.log10(max(rms, 1.0) / 32768.0), 1)
                    else:
                        self.live_rms_dbfs = -70.0
                    self.live_peak = peak
                    self.live_ambient_floor = round(ambient_floor, 1)
                    self.live_updated_at = now

                    if self.test_capturing:
                        self.test_frames.append(raw)

                    # STATE 1: IDLE - Listen for wake word if enabled
                    if self.state == "idle":
                        speech_out = getattr(app, 'speech_output', None)
                        is_speaking = False
                        if speech_out:
                            so_state = getattr(speech_out, 'status', {}).get('state')
                            last_ended = getattr(speech_out, 'last_playback_ended', 0.0)
                            if so_state in ('generating', 'playing') or (time.time() - last_ended < 0.8):
                                is_speaking = True

                        if is_speaking:
                            # Desk-Pal is actively speaking/generating; ignore mic audio to prevent self-interruption/feedback
                            pre_buffer.clear()
                            continue

                        # Exponential moving average of ambient room noise floor
                        if peak > 0:
                            ambient_floor = (ambient_floor * 0.95) + (peak * 0.05)

                        trigger_mode = self.config.get("trigger_mode", "both")
                        base_threshold = int(self.config.get("wake_peak_threshold", 8500))
                        # Effective threshold requires clear acoustic separation above background room noise
                        effective_threshold = max(base_threshold, int(ambient_floor + 2500))

                        # Reset consecutive miss counter if room has been quiet for >= 6 seconds
                        if peak < base_threshold:
                            if now - last_quiet_time > 6.0:
                                consecutive_misses = 0
                                wake_miss_cooldown = 2.5
                        else:
                            last_quiet_time = now

                        # Cooldown after non-matching ambient audio snippet to prevent continuous CPU spinning
                        if now < last_wake_miss_time + wake_miss_cooldown:
                            pre_buffer.clear()
                            continue

                        user_at_desk = True
                        if hasattr(app, 'hardware_monitor') and app.hardware_monitor:
                            try:
                                with app.hardware_monitor.lock:
                                    if app.hardware_monitor.config.get('radar', {}).get('enabled'):
                                        user_at_desk = bool(getattr(app, 'radar_nearby_present', False))
                            except Exception:
                                pass

                        if not user_at_desk:
                            pre_buffer.clear()
                            continue

                        if trigger_mode in ("wake_word", "both") and peak > effective_threshold:
                            # Speech detected! Immediate visual feedback
                            setattr(app, 'voice_hearing', True)

                            # Accumulate potential wake phrase (min 1.1s, max 2.8s, 500ms silence cutoff)
                            wake_frames = list(pre_buffer) + [raw]
                            silence_count = 0
                            snippet_start = time.monotonic()

                            while self.state == "idle":
                                try:
                                    chunk = proc.stdout.read(chunk_size)
                                except Exception:
                                    break
                                if not chunk:
                                    break
                                wake_frames.append(chunk)
                                ch_samples = array.array('h', chunk)
                                ch_peak = max(map(abs, ch_samples)) if ch_samples else 0
                                elapsed = time.monotonic() - snippet_start

                                if elapsed > 1.1 and ch_peak < 950:
                                    silence_count += 1
                                elif ch_peak >= 950:
                                    silence_count = 0

                                if elapsed >= 2.8 or (elapsed > 1.1 and silence_count >= 5):
                                    break

                            # Transcribe snippet for wake keyword
                            fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="deskpal_wake_")
                            os.close(fd)
                            transcribed = ""
                            try:
                                with wave.open(wav_path, 'wb') as wf:
                                    wf.setnchannels(1)
                                    wf.setsampwidth(2)
                                    wf.setframerate(16000)
                                    wf.writeframes(b''.join(wake_frames))
                                res = self.stt_engine.transcribe_file(wav_path, model_name=self.config.get("model", "tiny.en"), threads=1)
                                transcribed = (res.get("text") or "").strip().lower()
                            except Exception as e:
                                logger.warning(f"[VoiceSentry] Wake transcribe error: {e}")
                            finally:
                                if os.path.exists(wav_path):
                                    try: os.unlink(wav_path)
                                    except Exception: pass
                                setattr(app, 'voice_hearing', False)

                            wake_target = self.config.get("wake_word", "hey pal").lower().strip()
                            clean_t = re.sub(r'[^\w\s]', '', transcribed)

                            # Strict wake phrase variants: require at least 2 words (e.g. "hey pal", "hey deskpal")
                            # NEVER match single words like "paul", "pal", "pile" which trigger constantly on TV dialogue!
                            wake_variants = [wake_target]
                            if "pal" in wake_target:
                                wake_variants.extend(["hey pal", "hey deskpal", "hey desk pal", "okay pal", "ok pal"])
                            elif "deskpal" in wake_target:
                                wake_variants.extend(["hey deskpal", "hey desk pal", "hey pal"])

                            wake_variants = sorted(list(set(v for v in wake_variants if v and (len(v.split()) >= 2 or v == 'deskpal'))), key=len, reverse=True)

                            matched_variant = None
                            matched_span = None
                            if clean_t:
                                for v in wake_variants:
                                    pat = r'\b' + re.escape(v) + r'\b'
                                    m = re.search(pat, clean_t)
                                    if m:
                                        matched_variant = v
                                        matched_span = m.span()
                                        break

                            is_wake = bool(matched_variant)
                            logger.info(f"[VoiceSentry] Wake audio check (peak {peak}, floor {int(ambient_floor)}): transcribed='{transcribed}' matched={is_wake}")

                            if is_wake:
                                consecutive_misses = 0
                                wake_miss_cooldown = 2.5
                                logger.info(f"[VoiceSentry] Wake word '{matched_variant}' matched in: '{transcribed}'!")
                                setattr(app, 'wake_word_active', True)
                                setattr(app, 'voice_listening', True)
                                if hasattr(app, 'stand_and_face_user'):
                                    app.stand_and_face_user()
                                trailing = clean_t[matched_span[1]:].strip()
                                if len(trailing) <= 3:
                                    trailing = ""

                                if trailing:
                                    # Inline command spoken in same breath!
                                    logger.info(f"[VoiceSentry] Inline command from wake: '{trailing}'")
                                    setattr(app, 'voice_thought_bubble', {
                                        'text': f'Hey pal! "{trailing}"',
                                        'timestamp': time.monotonic(),
                                        'expires_at': time.monotonic() + 6.0
                                    })
                                    self._dispatch_command_async(trailing, app)
                                else:
                                    # Only wake word said -> enter command listening mode seamlessly!
                                    logger.info("[VoiceSentry] Wake word heard without command -> entering listening mode.")
                                    with self.lock:
                                        self.state = "listening"
                                        self.audio_frames = []
                                        self.speech_detected = False
                                        self.start_time = time.monotonic()
                                        self.last_speech_time = time.monotonic()
                                    setattr(app, 'voice_thought_bubble', {
                                        'text': "Hey pal! I'm listening...",
                                        'timestamp': time.monotonic(),
                                        'expires_at': time.monotonic() + 6.0
                                    })
                            else:
                                consecutive_misses += 1
                                # Progressive backoff: 2.5s -> 3.5s -> 5.0s -> 7.0s up to 12.0s
                                wake_miss_cooldown = min(12.0, 2.5 * (1.4 ** min(consecutive_misses - 1, 4)))
                                last_wake_miss_time = time.monotonic()
                        else:
                            pre_buffer.append(raw)

                    # STATE 2: LISTENING - Accumulate command audio until silence cutoff
                    elif self.state == "listening":
                        self.audio_frames.append(raw)
                        if peak > 1400:
                            self.speech_detected = True
                            self.last_speech_time = now

                        silence_thresh = float(self.config.get("silence_seconds", 2.0))
                        max_dur = float(self.config.get("max_record_seconds", 15.0))

                        # Auto-stop after 2.0s of silence following speech
                        if (self.speech_detected and (now - self.last_speech_time >= silence_thresh)) or (now - self.start_time >= max_dur):
                            logger.info(f"[VoiceSentry] Command audio complete (silence: {now - self.last_speech_time:.1f}s). Transcribing...")
                            with self.lock:
                                self.state = "transcribing"
                            threading.Thread(target=self._process_transcription_and_reply, args=(app,), daemon=True).start()

                    # STATE 3: TRANSCRIBING - Audio stream continues reading to prevent pipe buffer overrun
                    elif self.state == "transcribing":
                        time.sleep(0.05)

            finally:
                if proc is not None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=0.5)
                    except Exception:
                        try: proc.kill()
                        except Exception: pass
            time.sleep(0.2)

    def _dispatch_command_async(self, text, app):
        """Asynchronously dispatches text to router, updates bubble, and plays TTS response."""
        def worker():
            if hasattr(app, 'stand_and_face_user'):
                app.stand_and_face_user()
            reply_text = None
            action = None
            if dispatch_voice_command:
                try:
                    reply_text, action = dispatch_voice_command(text, app)
                except Exception as e:
                    logger.error(f"[VoiceSentry] Voice command error: {e}")
                    reply_text = f"I heard: {text}"
            else:
                reply_text = f"I heard: {text}"

            if reply_text:
                reply_text = reply_text[:450].strip()
                bubble_dur = max(5.0, min(15.0, len(reply_text) * 0.08 + 2.0))
                setattr(app, 'voice_thought_bubble', {
                    'text': reply_text,
                    'timestamp': time.monotonic(),
                    'expires_at': time.monotonic() + bubble_dur
                })

                speech_out = getattr(app, 'speech_output', None)
                if not speech_out:
                    try:
                        from speech_output import output_for
                        speech_out = output_for(app)
                    except Exception as err:
                        logger.debug(f"[VoiceSentry] Could not init speech_output: {err}")

                if speech_out and self.config.get("speak_response", True):
                    cfg_path = os.path.join(os.path.dirname(getattr(app, 'config_path', 'config/room_config.json')), 'ai_settings.json')
                    if not os.path.exists(cfg_path):
                        for alt in ['/home/admin/config/ai_settings.json', 'config/ai_settings.json']:
                            if os.path.exists(alt):
                                cfg_path = alt
                                break
                    hw_spk = getattr(app, 'hardware_monitor', None)
                    spk_cfg = hw_spk.config.get('speaker', {}) if hw_spk else {'enabled': True}
                    try:
                        clean_speech = re.sub(r'^[a-zA-Z0-9_\s]+:\s*', '', reply_text)
                        from voice_command_router import sanitize_for_speech
                        clean_speech = sanitize_for_speech(clean_speech)
                        speech_out.speak(clean_speech, cfg_path, spk_cfg, source='voice_response')
                    except Exception as err:
                        logger.warning(f"[VoiceSentry] Speech reply error: {err}")

            time.sleep(2.0)
            setattr(app, 'wake_word_active', False)
            setattr(app, 'voice_listening', False)

        threading.Thread(target=worker, daemon=True).start()

    def _process_transcription_and_reply(self, app):
        """Transcribes accumulated command audio and dispatches reply."""
        setattr(app, 'voice_thought_bubble', {
            'text': 'Thinking...',
            'timestamp': time.monotonic(),
            'expires_at': time.monotonic() + 10.0
        })

        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="deskpal_cmd_")
        os.close(fd)
        text = ""
        try:
            with wave.open(wav_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b''.join(self.audio_frames))

            res = self.stt_engine.transcribe_file(wav_path, model_name=self.config.get("model", "tiny.en"))
            text = (res.get("text") or "").strip()
            logger.info(f"[VoiceSentry] Command transcribed: '{text}'")
            with self.lock:
                self.latest_transcription = text
        except Exception as e:
            logger.error(f"[VoiceSentry] Transcription error: {e}")
        finally:
            if os.path.exists(wav_path):
                try: os.unlink(wav_path)
                except Exception: pass

        if text:
            # Strip leading wake word if present
            wake_target = self.config.get("wake_word", "hey pal").lower().strip()
            clean_cmd = text
            if clean_cmd.lower().startswith(wake_target):
                clean_cmd = clean_cmd[len(wake_target):].strip(" ,.!?")

            setattr(app, 'voice_thought_bubble', {
                'text': f'"{text}"',
                'timestamp': time.monotonic(),
                'expires_at': time.monotonic() + 6.0
            })
            self._dispatch_command_async(clean_cmd or text, app)
        else:
            setattr(app, 'voice_thought_bubble', {
                'text': "Couldn't hear anything...",
                'timestamp': time.monotonic(),
                'expires_at': time.monotonic() + 3.0
            })
            setattr(app, 'wake_word_active', False)
            setattr(app, 'voice_listening', False)

        with self.lock:
            self.state = "idle"

    def test_record_and_transcribe(self, duration_s=5.0):
        """Web studio test recognition endpoint."""
        return self.test_capture(duration_s=duration_s)

    def test_capture(self, duration_s=5.0):
        """Test recognition endpoint recording directly from unified audio stream."""
        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="deskpal_test_")
        os.close(fd)
        try:
            # Ensure capture worker is running
            app = getattr(self, '_app_ref', None)
            if not self.capture_running or self.capture_thread is None or not self.capture_thread.is_alive():
                self.capture_running = True
                self.capture_thread = threading.Thread(
                    target=self._capture_worker,
                    args=(app,),
                    daemon=True
                )
                self.capture_thread.start()
                time.sleep(0.2)

            with self.lock:
                self.test_frames = []
                self.test_capturing = True

            target_frames = max(10, int(duration_s * 10))
            t_start = time.monotonic()
            while time.monotonic() - t_start < (duration_s + 1.5):
                if len(self.test_frames) >= target_frames:
                    break
                time.sleep(0.05)

            with self.lock:
                self.test_capturing = False
                frames_to_save = list(self.test_frames)
                self.test_frames = []

            if not frames_to_save:
                return {'success': False, 'error': 'No audio frames captured from microphone stream'}

            with wave.open(wav_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b''.join(frames_to_save))

            model_name = self.config.get('model', 'tiny.en')
            result = self.stt_engine.transcribe(wav_path, model=model_name)
            return {
                'success': True,
                'text': result.get('text', ''),
                'is_silence': result.get('is_silence', False),
                'latency_s': result.get('inference_seconds', 0.0),
                'inference_seconds': result.get('inference_seconds', 0.0),
                'peak': result.get('peak', 0.0),
                'rss_mb': result.get('memory_mb', 0.0),
                'memory_mb': result.get('memory_mb', 0.0),
                'model': model_name
            }
        except Exception as err:
            logger.error(f"[VoiceSentry] Test capture error: {err}")
            return {'success': False, 'error': str(err)}
        finally:
            self.test_capturing = False
            if os.path.exists(wav_path):
                try: os.unlink(wav_path)
                except Exception: pass

_sentry_lock = threading.Lock()

def sentry_for(app):
    with _sentry_lock:
        if not hasattr(app, 'voice_sentry'):
            app.voice_sentry = VoiceSentry()
            try:
                from ai_connections import read
                cfg_path = getattr(app, 'config_path', 'config/room_config.json')
                ai_cfg_path = os.path.join(os.path.dirname(cfg_path), 'ai_settings.json')
                if os.path.exists(ai_cfg_path):
                    saved = read(ai_cfg_path)
                    if 'stt' in saved:
                        app.voice_sentry.configure(saved['stt'])
            except Exception:
                pass
        if app and hasattr(app, 'voice_sentry'):
            app.voice_sentry._app_ref = app
        return app.voice_sentry
