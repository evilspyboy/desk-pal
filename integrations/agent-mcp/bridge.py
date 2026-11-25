"""Small, model-independent event producer for Desk-Pal. No MCP dependency."""
import hashlib
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

EVENTS = ('started', 'researching', 'coding', 'completed', 'needs_attention', 'failed')


class AgentBridge:
    def __init__(self, endpoint, app_id, name, state_path):
        url = urllib.parse.urlsplit(endpoint)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
            raise ValueError('Use a Desk-Pal HTTP(S) origin, without credentials or a path')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', app_id):
            raise ValueError('Use a 1–64 character application ID')
        self.endpoint, self.app_id = endpoint.rstrip('/'), app_id
        self.name = self.text(name, 'Agent name', 80)
        self.state_path = Path(state_path)
        self.lock = threading.RLock()
        # An adapter instance belongs to one application and endpoint.
        self.identity = hashlib.sha256((self.endpoint + ':' + app_id).encode()).hexdigest()
        self.state = self.load()
        self.opener = urllib.request.build_opener(NoRedirect())

    @staticmethod
    def text(value, label, maximum):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError(f'{label} must contain 1–{maximum} characters')
        return value.strip()

    def load(self):
        try:
            state = json.loads(self.state_path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {'identity': self.identity, 'delivered': {}, 'last_activity': None}
        if not isinstance(state, dict) or state.get('identity') != self.identity or not isinstance(state.get('delivered'), dict):
            raise ValueError('State belongs to another agent/endpoint; use a different state file')
        return state

    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.state, ensure_ascii=False), encoding='utf-8')
        temporary.replace(self.state_path)

    def request(self, path, payload=None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        request = urllib.request.Request(self.endpoint + path, data=body,
                                        headers={'Content-Type': 'application/json'}, method='GET' if body is None else 'POST')
        with self.opener.open(request, timeout=5) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError('Desk-Pal response exceeded 64 KB')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError('Desk-Pal returned an invalid response')
            return result

    def report(self, activity, task_id, message, occurrence_id):
        if activity not in EVENTS:
            raise ValueError('Choose one of: ' + ', '.join(EVENTS))
        task_id = self.text(task_id, 'Task ID', 120)
        occurrence_id = self.text(occurrence_id, 'Occurrence ID', 160)
        message = self.text(message, 'Message', 500)
        event = 'task_' + activity if activity in ('started', 'completed', 'failed') else activity
        payload = dict(app_id=self.app_id, app_name=self.name, event=event, task_id=task_id,
                       activity=activity, summary=message, event_id=occurrence_id,
                       attention_needed=activity in ('needs_attention', 'failed'), status='healthy', ttl_seconds=900)
        key = hashlib.sha256(occurrence_id.encode()).hexdigest()
        signature = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.lock:
            previous = self.state['delivered'].get(key)
            if previous:
                if previous != signature:
                    raise ValueError('Occurrence ID was already used for a different update')
                return {'delivery': 'already_delivered', 'event': event, 'occurrence_id': occurrence_id}
            try:
                response = self.request('/api/v1/event', payload)
                if response.get('status') != 'received':
                    raise ValueError('Desk-Pal did not acknowledge the event')
            except (OSError, ValueError, urllib.error.URLError):
                # Do not retry automatically: a lost response may follow a successful POST.
                return {'delivery': 'unconfirmed', 'event': event, 'occurrence_id': occurrence_id,
                        'message': 'Desk-Pal did not confirm delivery. Check its activity history before retrying.'}
            self.state['delivered'][key] = signature
            self.state['delivered'] = dict(list(self.state['delivered'].items())[-1000:])
            self.state['last_activity'] = {'task_id': task_id, 'activity': activity, 'summary': message}
            result = {'delivery': 'received', 'event': event, 'occurrence_id': occurrence_id,
                      'message': 'Received by Desk-Pal; playback depends on your mappings, suppression and queue.'}
            try:
                self.save()
            except OSError:
                result['warning'] = 'Received, but local deduplication state could not be saved. Do not resend after restarting.'
            try:
                heartbeat = self.request('/api/v1/heartbeat', dict(app_id=self.app_id, app_name=self.name,
                    status='healthy', activity=activity, summary=message, button_summary=message,
                    task_id=task_id, ttl_seconds=900))
                if heartbeat.get('status') != 'ok':
                    raise ValueError('Status update not acknowledged')
            except (OSError, ValueError, urllib.error.URLError):
                result['status_warning'] = 'Event received, but the cached button/status update was not confirmed.'
            return result

    def status(self):
        with self.lock:
            result = {'app_id': self.app_id, 'agent_name': self.name,
                      'last_reported_activity': self.state.get('last_activity')}
            try:
                queue = self.request('/api/activity_queue')
                result.update(reachable=True, display_state=queue.get('state'),
                              pending_count=len(queue.get('pending', [])))
            except (OSError, ValueError, urllib.error.URLError):
                result['reachable'] = False
            return result

    def get_capabilities(self):
        """Fetch Desk-Pal device profile, purpose, world state, rules, and endpoints."""
        try:
            return self.request('/api/v1/agent/capabilities')
        except (OSError, ValueError, urllib.error.URLError) as e:
            return {'status': 'error', 'message': f'Cannot reach Desk-Pal at {self.endpoint}: {e}'}

    def get_world(self):
        """Fetch the living world state: scenes, spots, character pos, animations, presence."""
        try:
            return self.request('/api/v1/world')
        except (OSError, ValueError, urllib.error.URLError) as e:
            return {'status': 'error', 'message': f'Cannot reach Desk-Pal at {self.endpoint}: {e}'}

    def puppeteer(self, scene=None, spot_id=None, x=None, y=None, animation=None, facing=None, speech=None, thought=None, duration_seconds=6.0, priority=True):
        """Directly pilot the character sprite across scenes, spots, or coordinates."""
        payload = {
            'animation': animation or 'idle',
            'duration_seconds': float(duration_seconds),
            'priority': bool(priority)
        }
        if scene:
            payload['scene'] = scene
        if spot_id:
            payload['spot_id'] = spot_id
        if x is not None and y is not None:
            payload['x'] = float(x)
            payload['y'] = float(y)
        if facing:
            payload['facing'] = facing
        if speech:
            payload['speech'] = speech
        if thought:
            payload['speech'] = thought
            payload['display_mode'] = 'thought_bubble'
        try:
            return self.request('/api/v1/action', payload)
        except (OSError, ValueError, urllib.error.URLError) as e:
            return {'status': 'error', 'message': f'Pilot command failed: {e}'}

    def notify(self, title, message, layout=None, attention=True, speech=None, slider=None):
        """Show a rich notification card or popup modal with optional touch slider."""
        payload = {
            'title': title,
            'summary': message,
            'attention': bool(attention),
            'voice_escalation': bool(speech is not None)
        }
        if layout:
            payload['layout'] = layout
        if speech:
            payload['speech'] = speech
        if slider:
            payload['slider'] = slider
        try:
            return self.request('/api/v1/notify', payload)
        except (OSError, ValueError, urllib.error.URLError) as e:
            return {'status': 'error', 'message': f'Notify command failed: {e}'}

    def speak(self, text):
        """Speak a phrase aloud on Desk-Pal's speaker using Piper TTS."""
        try:
            return self.request('/api/v1/say', {'text': text})
        except (OSError, ValueError, urllib.error.URLError) as e:
            return {'status': 'error', 'message': f'Speak command failed: {e}'}

    def get_presence(self):
        """Query the mmWave radar sensor to check if the human is sitting at their desk."""
        try:
            return self.request('/api/v1/presence')
        except (OSError, ValueError, urllib.error.URLError) as e:
            return {'status': 'error', 'message': f'Presence check failed: {e}'}

    def get_sensors(self):
        """Query real-time environmental sensors and display sleep status (LUX light sensor, mmWave radar, bedtime and sleep policy)."""
        try:
            return self.request('/api/v1/sensors')
        except (OSError, ValueError, urllib.error.URLError) as e:
            return {'status': 'error', 'message': f'Sensors check failed: {e}'}

    def control_display(self, action='wake'):
        """Put the physical touchscreen display into standby ('sleep') or wake it up ('wake')."""
        try:
            return self.request('/api/v1/display', {'action': action})
        except (OSError, ValueError, urllib.error.URLError) as e:
            return {'status': 'error', 'message': f'Display control failed: {e}'}

    def travel_scene(self, scene):
        """Trigger an animated walking journey to another room/scene."""
        try:
            return self.request('/api/scenes/travel', {'scene': scene})
        except (OSError, ValueError, urllib.error.URLError) as e:
            return {'status': 'error', 'message': f'Scene travel failed: {e}'}

    def dismiss_modal(self):
        """Programmatically dismiss any active on-screen modal card or popup notification."""
        try:
            return self.request('/api/v1/modal/dismiss', {})
        except (OSError, ValueError, urllib.error.URLError) as e:
            return {'status': 'error', 'message': f'Dismiss modal failed: {e}'}

    def get_preview_frame(self, as_base64=True):
        """Fetch the latest rendered frame from Desk-Pal as JPEG bytes or base64."""
        import base64
        import time
        try:
            req = urllib.request.Request(self.endpoint + '/api/preview/frame')
            with self.opener.open(req, timeout=5) as res:
                frame = res.read()
            if len(frame) < 1000:
                time.sleep(0.15)
                req = urllib.request.Request(self.endpoint + '/api/preview/frame')
                with self.opener.open(req, timeout=5) as res:
                    frame = res.read()
            if as_base64:
                return {
                    'status': 'ok',
                    'format': 'jpeg',
                    'width': 1280,
                    'height': 720,
                    'size_bytes': len(frame),
                    'base64': base64.b64encode(frame).decode('ascii')
                }
            return frame
        except (OSError, ValueError, urllib.error.URLError) as e:
            return {'status': 'error', 'message': f'Could not capture preview frame: {e}'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
