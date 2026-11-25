"""Interactive voice attention ladder with presence gating and progressive escalation."""
import os
import time
import threading
from collections import deque
from pathlib import Path


DEFAULT_CONFIG = {
    'enabled': True,
    'radar_required': True,
    'timeout_seconds': 90.0,
    'no_radar_timeout_seconds': 45.0,
    'stale_age_seconds': 900.0,
    'phase1_delay_seconds': 12.0,
    'phase2_delay_seconds': 28.0,
    'phase3_delay_seconds': 56.0,
    'cold_load_offset_seconds': 14.0,
    'phase1_template': "Hey, I have a {app} update!",
    'phase2_phrase': "Hey, it's me, your pal!",
    'phase3_phrase': "Hello? Over here!",
}


class AttentionVoiceManager:
    def __init__(self, config_dir=None):
        self.config_dir = config_dir
        self.active_session = None
        self.deferred_alerts = deque()
        self.lock = threading.RLock()

    def get_config_dir(self):
        if self.config_dir:
            return self.config_dir
        try:
            from config_paths import get_active_config_path
            return os.path.dirname(get_active_config_path())
        except Exception:
            return 'config'

    def get_settings(self):
        try:
            from ai_connections import read, DEFAULTS
            path = os.path.join(self.get_config_dir(), 'ai_settings.json')
            data = read(path)
            return dict(DEFAULT_CONFIG, **data.get('attention_voice', {}))
        except Exception:
            return dict(DEFAULT_CONFIG)

    def is_tts_keep_loaded(self, app=None):
        speech = getattr(app, 'speech_output', None) if app else None
        if speech and hasattr(speech, 'keep_loaded'):
            return bool(speech.keep_loaded)
        try:
            from ai_connections import read
            path = os.path.join(self.get_config_dir(), 'ai_settings.json')
            data = read(path)
            return bool(data.get('tts', {}).get('keep_loaded', False))
        except Exception:
            return False

    def get_cold_load_offset(self, app=None, settings=None):
        settings = settings or self.get_settings()
        if self.is_tts_keep_loaded(app):
            return 0.0
        return float(settings.get('cold_load_offset_seconds', 14.0))

    def is_radar_available(self, app):
        monitor = getattr(app, 'hardware_monitor', None)
        if monitor:
            with monitor.lock:
                return bool(monitor.config.get('radar', {}).get('enabled'))
        try:
            from optional_hardware import monitor_for
            h_path = os.path.join(self.get_config_dir(), 'hardware_settings.json')
            m = monitor_for(app, h_path)
            with m.lock:
                return bool(m.config.get('radar', {}).get('enabled'))
        except Exception:
            return False

    def is_user_present(self, app):
        if getattr(app, 'radar_nearby_present', False):
            return True
        last_nearby = getattr(app, 'last_radar_nearby', None)
        if last_nearby and last_nearby.get('targets'):
            return True
        return False

    def should_defer_for_absence(self, app, action):
        settings = self.get_settings()
        if not settings.get('enabled', True):
            return False
        if not settings.get('radar_required', True):
            return False
        if not self.is_radar_available(app):
            return False
        return not self.is_user_present(app)

    def defer_alert(self, app, item):
        with self.lock:
            action = item[0]
            source_id = action.get('_source_app_id') or item[1]
            # Avoid stockpiling multiple alerts for the same service
            for existing in self.deferred_alerts:
                if (existing[0].get('_source_app_id') or existing[1]) == source_id:
                    return
            if '_received_at' not in action:
                action['_received_at'] = time.time()
            action['_deferred_for_presence'] = True
            self.deferred_alerts.append(item)
            audit = getattr(app, 'audit_activity', None)
            if audit:
                audit('attention_deferred_for_presence', app=item[1],
                      action=action.get('id'), source_event=action.get('source_event'))

    def start_session(self, app, item, now=None):
        action, app_name, color, summary, ticker, badge = item
        now = time.monotonic() if now is None else now
        settings = self.get_settings()
        voice_enabled = settings.get('enabled', True) and action.get('voice_escalation', True)
        self.active_session = {
            'action': action,
            'app_name': app_name,
            'summary': summary,
            'started_at': now,
            'last_spoken_at': None,
            'last_speech_finished_at': now,
            'phase': 0,
            'voice_enabled': voice_enabled,
            'custom_phrase': action.get('voice_phrase')
        }
        audit = getattr(app, 'audit_activity', None)
        if audit:
            audit('attention_session_started', app=app_name, silent_waving=True)

    def is_speech_busy(self, app):
        speech = getattr(app, 'speech_output', None)
        if speech:
            state = speech.snapshot().get('state')
            if state in ('generating', 'playing'):
                return True
        return False

    def tick(self, app, now=None):
        now = time.monotonic() if now is None else now
        user_present = self.is_user_present(app)
        radar_avail = self.is_radar_available(app)
        settings = self.get_settings()
        queue = getattr(app, 'activity_queue', None)

        # 1. Process deferred alerts
        with self.lock:
            if self.deferred_alerts:
                current_time = time.time()
                stale_limit = float(settings.get('stale_age_seconds', 900.0))
                retained = deque()
                while self.deferred_alerts:
                    alert = self.deferred_alerts.popleft()
                    age = current_time - alert[0].get('_received_at', current_time)
                    is_wellness = (alert[0].get('layout') == 'wellness' or alert[0].get('wellness') is not None or 'stretch' in str(alert[0].get('speech', '')).lower())
                    limit = 300.0 if is_wellness else stale_limit
                    if age > limit:
                        audit = getattr(app, 'audit_activity', None)
                        if audit:
                            audit('attention_deferred_expired', app=alert[1],
                                  action=alert[0].get('id'), age_seconds=round(age, 1))
                    else:
                        retained.append(alert)
                self.deferred_alerts = retained

                if (user_present or not radar_avail) and self.deferred_alerts and queue:
                    ready_item = self.deferred_alerts.popleft()
                    ready_item[0]['_deferred_for_presence'] = False
                    audit = getattr(app, 'audit_activity', None)
                    if audit:
                        audit('attention_deferred_resumed', app=ready_item[1],
                              action=ready_item[0].get('id'))
                    queue.enqueue(ready_item, app)

        # 2. Process active attention session
        if not self.active_session:
            return

        if not queue or not queue.active or queue.active[0] is not self.active_session['action']:
            self.active_session = None
            return

        action = self.active_session['action']
        if action.get('_attention_acknowledged') or not action.get('_attention_waiting'):
            self.active_session = None
            return

        speech_busy = self.is_speech_busy(app)
        if not speech_busy:
            # When speech is not busy, set speech finished timestamp if it was cleared
            if self.active_session.get('last_speech_finished_at') is None:
                self.active_session['last_speech_finished_at'] = now
        else:
            # While speech is actively generating or playing, clear finished stamp so we measure gap after completion
            self.active_session['last_speech_finished_at'] = None

        cold_offset = self.get_cold_load_offset(app, settings)
        elapsed = now - self.active_session['started_at']
        base_timeout = float(settings.get('timeout_seconds', 90.0) if radar_avail else settings.get('no_radar_timeout_seconds', 45.0))
        timeout = base_timeout + (cold_offset * 2.0)

        if elapsed >= timeout and not speech_busy:
            action['_attention_waiting'] = False
            action['_attention_timed_out'] = True
            action['_hold_popup_until_dismissed'] = False
            queue.active = None
            queue.arrived = queue.started = queue.dwell = None
            app.wander_timer = 0
            app.target_animation = app.current_anim = 'idle'
            app.active_popup_modal = None
            app.pending_popup_modal = None
            audit = getattr(app, 'audit_activity', None)
            if audit:
                audit('attention_timed_out', app=self.active_session['app_name'],
                      action=action.get('id'), elapsed=round(elapsed, 1))
            self.active_session = None
            return

        if self.active_session['voice_enabled']:
            if settings.get('radar_required', True) and radar_avail and not user_present:
                # User stepped away; do not escalate voice into an empty room
                return

            if speech_busy:
                # Wait for ongoing voice synthesis and audio playback to finish completely
                return

            phase = self.active_session['phase']
            phase1_delay = float(settings.get('phase1_delay_seconds', 12.0)) + cold_offset
            phase2_delay = float(settings.get('phase2_delay_seconds', 28.0)) + cold_offset
            phase3_delay = float(settings.get('phase3_delay_seconds', 56.0)) + (cold_offset * 2.0)
            silence_after_speech = now - self.active_session.get('last_speech_finished_at', now)

            if phase == 0 and elapsed >= phase1_delay:
                phrase = None
                action = self.active_session['action']
                app_name = self.active_session['app_name']
                summary = self.active_session['summary']
                if action.get('voice_phrase'):
                    try:
                        phrase = action['voice_phrase'].format(app=app_name, summary=summary)
                    except Exception:
                        phrase = action['voice_phrase']
                else:
                    tmpl = settings.get('phase1_template', "Hey, I have a {app} update!")
                    try:
                        phrase = tmpl.format(app=app_name, summary=summary)
                    except Exception:
                        phrase = f"Hey, I have a {app_name} update!"
                self.speak(app, phrase)
                self.active_session['phase'] = 1
                self.active_session['last_spoken_at'] = now
                self.active_session['last_speech_finished_at'] = None
                audit = getattr(app, 'audit_activity', None)
                if audit:
                    audit('attention_voice_spoken', app=app_name, phrase=phrase, phase=1)

            elif phase == 1 and elapsed >= phase2_delay and silence_after_speech >= 10.0:
                phrase = settings.get('phase2_phrase', "Hey, it's me, your pal!")
                self.speak(app, phrase)
                self.active_session['phase'] = 2
                self.active_session['last_spoken_at'] = now
                self.active_session['last_speech_finished_at'] = None
                audit = getattr(app, 'audit_activity', None)
                if audit:
                    audit('attention_voice_spoken', app=self.active_session['app_name'], phrase=phrase, phase=2)

            elif phase == 2 and elapsed >= phase3_delay and silence_after_speech >= 10.0:
                phrase = settings.get('phase3_phrase', "Hello? Over here!")
                self.speak(app, phrase)
                self.active_session['phase'] = 3
                self.active_session['last_spoken_at'] = now
                self.active_session['last_speech_finished_at'] = None
                audit = getattr(app, 'audit_activity', None)
                if audit:
                    audit('attention_voice_spoken', app=self.active_session['app_name'], phrase=phrase, phase=3)

    def acknowledge(self, app):
        if self.active_session:
            self.stop_speech(app)
            self.active_session = None

    def purge_deferred_alerts(self, app_id):
        with self.lock:
            self.deferred_alerts = deque(a for a in self.deferred_alerts if (a[0].get('_source_app_id') or a[1]) != app_id)
            if self.active_session and (self.active_session.get('action', {}).get('_source_app_id') == app_id or self.active_session.get('app_name') == app_id):
                self.active_session = None

    def speak(self, app, phrase):
        try:
            from speech_output import output_for
            output = output_for(app)
            settings_path = os.path.join(self.get_config_dir(), 'ai_settings.json')
            speaker = {'enabled': True, 'output': 'default', 'volume': 0.5}
            monitor = getattr(app, 'hardware_monitor', None)
            if monitor:
                with monitor.lock:
                    speaker = dict(monitor.config.get('speaker', speaker))
            else:
                try:
                    from optional_hardware import monitor_for
                    h_path = os.path.join(self.get_config_dir(), 'hardware_settings.json')
                    m = monitor_for(app, h_path)
                    with m.lock:
                        speaker = dict(m.config.get('speaker', speaker))
                except Exception:
                    pass
            output.speak(phrase, settings_path, speaker, source='attention_alert')
        except Exception as error:
            print('[AttentionVoice] Speech output skipped:', error)

    def stop_speech(self, app):
        try:
            from speech_output import output_for
            output_for(app).stop()
        except Exception:
            pass
