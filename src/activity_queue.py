"""Main-loop FIFO for visual actions; incoming telemetry never moves the sprite."""
from collections import deque
import copy
import math
import threading
import time


class ActivityQueue:
    def __init__(self):
        self.items = deque()
        self.lock = threading.RLock()
        self.active = None
        self.arrived = None
        self.started = None
        self.dwell = None
        self.last_error = ''
        self.paused_at = None
        self.completed = 0
        self.popup_dismissed = False
        self.pause_reason = None
        self.sleeping = False

    def snapshot(self):
        with self.lock:
            now = time.monotonic()
            received_now = time.time()
            describe = lambda args: {'app': args[1], 'action': args[0].get('label') or args[0].get('id') or args[0].get('animation'), 'event': args[0].get('source_event'), 'scene': args[0].get('scene') or args[0].get('target_scene'), 'button': bool(args[0].get('_button_action')), 'received_age_seconds': max(0, round(received_now-args[0]['_received_at'])) if args[0].get('_received_at') is not None else None}
            state = 'idle'
            if self.active:
                state = 'waiting_for_dismissal' if self.active[0].get('_hold_popup_until_dismissed') and not self.popup_dismissed and self.arrived is not None else 'playing' if self.arrived is not None else 'travelling'
                if self.active[0].get('_attention_waiting') and not self.active[0].get('_attention_acknowledged') and self.arrived is not None:
                    state = 'waiting_for_interaction'
                elif state == 'playing' and self.dwell is not None and math.isinf(self.dwell) and not self.items:
                    state = 'waiting_for_event'
            clock = self.paused_at if self.paused_at is not None else now
            return {'active': describe(self.active) if self.active else None, 'pending': [describe(args) for args in self.items], 'completed': self.completed, 'last_error': self.last_error, 'paused': self.paused_at is not None, 'pause_reason': self.pause_reason, 'state': state,
                    'turn_seconds': max(0, round(clock-self.started, 1)) if self.active and self.started is not None else None,
                    'playback_seconds': max(0, round(clock-self.arrived, 1)) if self.active and self.arrived is not None else None}

    def enqueue(self, args, app=None):
        with self.lock:
            self.items.append(copy.deepcopy(args))
            if self.sleeping:
                self.compact_sleep_queue(app)

    def compact_sleep_queue(self, app=None, waking=False, now=None):
        """Retain alerts and the newest routine occurrence per application/event."""
        now = time.time() if now is None else now
        with self.lock:
            retained = deque()
            seen = set()
            for args in reversed(self.items):
                action = args[0]
                important = action.get('_important') or action.get('attention_needed') or action.get('_button_action')
                key = (action.get('_source_app_id') or args[1], action.get('source_event') or action.get('event') or action.get('id'))
                reason = None
                if not important:
                    age_limit = float(action.get('_sleep_max_age_seconds', 900))
                    if waking and age_limit > 0 and now-action.get('_received_at', now) > age_limit:
                        reason = 'stale_after_sleep'
                    elif key in seen:
                        reason = 'superseded_during_sleep'
                    seen.add(key)
                if reason:
                    audit = getattr(app, 'audit_activity', None)
                    if audit:
                        audit('discarded', activity_id=action.get('_activity_id'), app=args[1], source_event=key[1], reason=reason)
                else:
                    retained.appendleft(args)
            self.items = retained

    def resume_from_standby(self, app):
        with self.lock:
            self.compact_sleep_queue(app, waking=True)
            self.sleeping = False

    def record(self, app, event, **fields):
        audit = getattr(app, 'audit_activity', None)
        if audit:
            action = self.active[0] if self.active else {}
            audit(event, activity_id=action.get('_activity_id'), app=self.active[1] if self.active else None,
                  action=action.get('id'), source_event=action.get('source_event'), **fields)

    def defer_for_standby(self, app):
        with self.lock:
            self.sleeping = True
            if self.active:
                self.record(app, 'deferred', reason='standby')
                self.items.appendleft(self.active)
                self.active = None
                self.arrived = self.started = self.dwell = None
            self.compact_sleep_queue(app)

    def enqueue_priority(self, app, args):
        with self.lock:
            if self.active:
                self.record(app, 'interrupted', reason='physical_button')
                if not self.active[0].get('_button_action') and not self.active[0].get('_attention_acknowledged'):
                    self.items.appendleft(self.active)
            self.active = None
            self.arrived = self.started = self.dwell = None
            self.items.appendleft(copy.deepcopy(args))
        app.scene_journey = []
        app.journey_arriving = False
        app.pending_post_travel_action = None
        app.target_x, app.target_y = app.char_x, app.char_y
        app._route_goal = None
        app.target_animation = 'idle'
        app.active_popup_modal = app.pending_popup_modal = None
        if getattr(app, 'active_rest_role', None) and not getattr(app, 'rest_transition', None):
            app.begin_rest_transition(app.active_rest_role, 'exit')

    def dismiss_popup(self, app):
        if self.active and self.active[0].get('_hold_popup_until_dismissed'):
            self.popup_dismissed = True
            self.record(app, 'popup_dismissed')

    def acknowledge_attention(self, app, app_id=None):
        """Show the original alert, rather than replacing it with a fresh status summary."""
        if not self.active:
            return False
        action, name, color, summary, ticker, badge = self.active
        if not action.get('_attention_waiting') or action.get('_attention_acknowledged'):
            return False
        if app_id is not None and app_id != action.get('_source_app_id'):
            return False
        action.update(_attention_acknowledged=True, _hold_popup_until_dismissed=True)
        self.popup_dismissed = False
        self.record(app, 'attention_acknowledged', via='button' if app_id is not None else 'touch')
        source_id = action.get('_source_app_id')
        getattr(app, 'integration_attention', {}).pop(source_id, None)
        if source_id:
            if not hasattr(app, 'attention_seen'):
                app.attention_seen = {}
            app.attention_seen[source_id] = 'acknowledged'
            if source_id == 'deskpal_connectivity':
                app._system_health_acknowledged = True
            self.purge_app_alerts(app, source_id)
            mgr_v = getattr(app, 'attention_voice_manager', None)
            if mgr_v:
                mgr_v.purge_deferred_alerts(source_id)
        mgr = getattr(app, 'attention_voice_manager', None)
        if mgr:
            mgr.acknowledge(app)
        app.scene_journey = []
        app.journey_arriving = False
        app.pending_post_travel_action = None
        app.target_x, app.target_y = app.char_x, app.char_y
        app.target_animation = app.current_anim = 'idle'
        app._route_goal = None
        app.pending_popup_modal = None
        app.speech_until = 0
        app.active_popup_modal = action.get('_attention_modal_data') or dict(
            title=name, summary=summary, ticker=ticker or [],
            color=color, badge=badge, timestamp=time.strftime('%I:%M %p'),
            layout=action.get('layout'), slider=action.get('slider'), wellness=action.get('wellness')
        )
        return True

    def purge_app_alerts(self, app, app_id):
        """Immediately purge pending, active, or lingering attention/outage alerts for an app."""
        with self.lock:
            retained = deque()
            for args in self.items:
                act = args[0]
                source_id = act.get('_source_app_id') or args[1]
                if source_id == app_id and (act.get('_attention_waiting') or act.get('attention_needed') or act.get('attention_until_interaction') or act.get('_system_health_incident')):
                    continue
                retained.append(args)
            self.items = retained

            if self.active:
                act = self.active[0]
                source_id = act.get('_source_app_id') or self.active[1]
                if source_id == app_id and act.get('_attention_waiting') and not act.get('_attention_acknowledged'):
                    self.active = None
                    self.arrived = self.started = self.dwell = None
                    app.wander_timer = 0
                    app.target_animation = app.current_anim = 'idle'
                    app.active_popup_modal = None
                    app.pending_popup_modal = None
                    mgr = getattr(app, 'attention_voice_manager', None)
                    if mgr:
                        mgr.acknowledge(app)

    def remove_suppressed(self, app):
        def suppressed(args):
            action = args[0]
            if (action.get('_expires_at') is not None and time.time() >= action['_expires_at']
                    and not (args is self.active and self.arrived is not None)):
                return True
            incident=action.get('_system_health_incident')
            if incident and incident!=getattr(app,'system_health_alert_incident',None):
                return True
            if action.get('_button_action'):
                return False
            health_seen = action.get('_health_seen')
            if health_seen is not None and getattr(app, 'app_telemetry', {}).get(action.get('_source_app_id'), {}).get('last_seen', 0) > health_seen:
                return True
            source = next((a for a in getattr(app, 'apps', []) if
                a.get('id') == action.get('_source_app_id') or a.get('name') == args[1] or a.get('id') == args[1]), {})
            return source.get('suppressed_events', {}).get(action.get('source_event') or action.get('event')) is True
        with self.lock:
            retained = deque()
            for args in self.items:
                if suppressed(args):
                    audit = getattr(app, 'audit_activity', None)
                    if audit:
                        audit('discarded', activity_id=args[0].get('_activity_id'), app=args[1],
                              source_event=args[0].get('source_event'), reason='event_suppressed')
                else:
                    retained.append(args)
            self.items = retained
            if self.active and suppressed(self.active):
                self.record(app, 'discarded', reason='event_suppressed')
                self.active = None
                self.arrived = self.started = self.dwell = None
                app.scene_journey = []
                app.journey_arriving = False
                app.pending_post_travel_action = None
                app.target_x, app.target_y = app.char_x, app.char_y
                app._route_goal = None
                app.target_animation = 'idle'
                app.active_popup_modal = app.pending_popup_modal = None
                app.speech_until = 0
                app.wander_timer = 0

    def tick(self, app, now=None):
        now = time.monotonic() if now is None else now
        self.remove_suppressed(app)
        if app.is_sleeping or app.edit_mode:
            self.pause_reason = 'sleep' if app.is_sleeping else 'editing'
            if self.paused_at is None:
                self.paused_at = now
                self.record(app, 'paused', reason='sleep' if app.is_sleeping else 'editing')
            return
        if self.paused_at is not None:
            self.pause_reason = None
            delay = now-self.paused_at
            if self.started is not None: self.started += delay
            if self.arrived is not None: self.arrived += delay
            self.paused_at = None
            self.record(app, 'resumed', paused_seconds=round(delay, 3))
        if not self.active and (getattr(app, 'scene_journey', None) or getattr(app, 'journey_arriving', False) or getattr(app, 'rest_transition', None)):
            return  # A manual scene journey must finish before consuming the next event.
        if self.active:
            travelling = bool(getattr(app, 'scene_journey', None) or getattr(app, 'journey_arriving', False))
            settled = not travelling and app.current_anim != 'walk' and not getattr(app, 'rest_transition', None) and math.hypot(app.char_x-app.target_x, app.char_y-app.target_y) <= 1
            if settled:
                if self.arrived is None:
                    self.arrived = now
                    if self.active[0].get('display_mode') == 'thought_bubble':
                        app.speech_until = now + 8
                    sequence = app.action_sequence(app.target_animation or app.current_anim)
                    limit = app.sequence_tick_limit(sequence) if sequence else 0
                    override = float(self.active[0].get('duration_seconds', 0) or 0)
                    self.dwell = max(1, min(120, override)) if override > 0 else math.inf
                    if sequence and limit is not None and math.isfinite(limit):
                        self.dwell = max(1, limit/sequence['fps'])
                    elif sequence and override <= 0:
                        # Events are milestones, not ongoing producer state. Play
                        # one cycle by default; idle and attention hold elsewhere.
                        ticks = len(sequence.get('frames', []))
                        if sequence.get('playback_mode') == 'ping_pong':
                            ticks = max(1, 2*ticks-2)
                        self.dwell = max(.01, ticks/max(1, sequence.get('fps', 8)))
                    elif not sequence:
                        self.dwell = 8  # Static legacy poses have no playback cycle.
                    # Visual queue burst compression: if 2+ events are waiting, pace routine animations briskly
                    with self.lock:
                        burst_depth = len(self.items)
                    if burst_depth >= 2 and not self.active[0].get('_important') and not self.active[0].get('_button_action'):
                        self.dwell = min(self.dwell, 2.5 if burst_depth >= 3 else 3.5)
                    self.record(app, 'arrived', animation=app.target_animation or app.current_anim,
                                spot_id=getattr(app, 'target_spot_id', None),
                                playback_mode=sequence.get('playback_mode') if sequence else None,
                                duration_seconds=self.dwell if math.isfinite(self.dwell) else None)
                if self.active[0].get('_hold_popup_until_dismissed'):
                    if not self.popup_dismissed:
                        app.wander_timer = 5.0
                        return
                    self.dwell = 0
                if self.active[0].get('_attention_waiting') and not self.active[0].get('_attention_acknowledged'):
                    mgr = getattr(app, 'attention_voice_manager', None)
                    if mgr and self.arrived is not None:
                        if not mgr.active_session or mgr.active_session['action'] is not self.active[0]:
                            mgr.start_session(app, self.active, now=now)
                        mgr.tick(app, now)
                    if self.active is not None and self.active[0].get('_attention_waiting'):
                        app.wander_timer = 5.0
                        return
                if not self.active or self.dwell is None or self.arrived is None:
                    return
                if math.isinf(self.dwell):
                    # An unrestricted loop yields at a cycle boundary when work arrives.
                    sequence = app.action_sequence(app.target_animation or app.current_anim)
                    cycle = len(sequence.get('frames', [])) / max(1, sequence.get('fps', 8))
                    if sequence.get('playback_mode') == 'ping_pong':
                        cycle = max(1, 2*len(sequence.get('frames', []))-2) / max(1, sequence.get('fps', 8))
                    with self.lock:
                        waiting = bool(self.items)
                    elapsed = now-self.arrived
                    if waiting and elapsed >= cycle:
                        self.dwell = math.ceil(elapsed/max(cycle, .01))*max(cycle, .01)
                if now-self.arrived >= self.dwell:
                    self.record(app, 'completed', playback_seconds=round(now-self.arrived, 3),
                                turn_seconds=round(now-self.started, 3))
                    self.completed += 1
                    self.active = None
                    app.active_popup_modal = None
                    app.pending_popup_modal = None
                    app.target_animation = 'idle'
                    app.wander_timer = 0
            if self.active and not settled and now-self.started > 180:
                self.last_error = 'An application action could not finish its route.'
                self.record(app, 'failed', error=self.last_error)
                self.active = None
                app.wander_timer = 0
            if self.active:
                app.wander_timer = 5.0
                return
        with self.lock:
            while self.items and self.items[0][0].get('_sensor_event') and time.time()-self.items[0][0].get('_received_at',time.time())>5:
                expired = self.items.popleft()
                audit = getattr(app, 'audit_activity', None)
                if audit:
                    audit('discarded', activity_id=expired[0].get('_activity_id'), reason='stale_sensor_reaction')
            if not self.items:
                return
            if getattr(app, 'active_rest_role', None) and not getattr(app, 'rest_transition', None):
                if app.begin_rest_transition(app.active_rest_role, 'exit'):
                    return
            args = self.items.popleft()
        self.active = args
        self.started = now
        self.arrived = None
        self.dwell = None
        self.popup_dismissed = False
        self.record(app, 'started', requested_scene=args[0].get('scene') or args[0].get('target_scene'),
                    requested_animation=args[0].get('animation'), requested_spot=args[0].get('spot_id'))
        try:
            app.trigger_action(*args)
            app.wander_timer = 5.0
        except Exception as error:
            self.last_error = str(error)
            self.record(app, 'failed', error=self.last_error)
            self.active = None
            app.wander_timer = 0
