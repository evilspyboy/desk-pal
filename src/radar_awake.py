"""Fresh radar presence can veto light-triggered sleep; no sensor commands."""
import math

def presence_reading(radar, range_m=2.0):
    """Filter presence inputs only; raw diagnostics and captures stay intact."""
    targets=[]
    for target in radar.get('targets', []):
        distance=target.get('distance_mm')
        if type(distance) in (int,float) and math.isfinite(distance) and 0 < distance < range_m*1000:
            targets.append(target)
    return dict(radar, targets=targets)

class RadarAwakePolicy:
    def __init__(self):
        self.since = self.last_present = self.frame = None
        self.absent_since = None
        self.sleep_ready = False

    def tick(self, enabled, radar, now, absence_seconds=30, calibrating=False):
        fresh = radar.get('state') == 'receiving' and 0 <= now-radar.get('_monotonic_at', -1e9) < 1
        self.sleep_ready = False
        if not enabled or calibrating or not fresh:
            self.since = self.last_present = self.frame = None
            self.absent_since = None
            return False
        frame = radar.get('last_frame')
        if frame is None: return False
        if frame != self.frame:
            self.frame = frame
            if radar.get('targets'):
                self.absent_since = None
                if self.since is None: self.since = now
                if now-self.since >= 1: self.last_present = now
            else:
                self.since = None
                if self.absent_since is None: self.absent_since = now
        self.sleep_ready = self.absent_since is not None and now-self.absent_since >= absence_seconds
        return self.last_present is not None and now-self.last_present < absence_seconds

def sleep_inputs(options, reading, policy, presence_awake, now, night=True, bedtime_priority=False, sleeping=False):
    """Use lux when configured; otherwise use confirmed radar presence/absence."""
    if not options.get('presence_awake_enabled') or (options.get('enabled') and options.get('idle_threshold_enabled')):
        return options, reading
    options = dict(options, enabled=True, idle_threshold_enabled=True,
                   sleep_below_lux=1, wake_margin_lux=1, delay_seconds=0)
    if night and sleeping:
        return options, dict(state='live', at=now, lux=0)
    if bedtime_priority and night:
        return options, dict(state='live', at=now, lux=0)
    if presence_awake or not night or policy.sleep_ready:
        return options, dict(state='live', at=now, lux=2 if presence_awake or not night else 0)
    return options, dict(state='unavailable')

def presence_keeps_awake(presence_awake, night=False, sleeping=False):
    """Presence keeps an awake Desk-Pal awake even past bedtime; once asleep at night, presence does not wake it."""
    if not presence_awake:
        return False
    if sleeping and night:
        return False
    return True
