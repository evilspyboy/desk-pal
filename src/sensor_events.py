"""Edge-triggered optional sensors. Never poll hardware or move the character here."""
import math

SOURCE_ID = 'deskpal_sensors'
EVENTS = [(f'tilt_{direction}{suffix}', f'{label}{strength}')
          for direction, label in [('left','Tilt left'),('right','Tilt right'),('forward','Tilt toward you'),('back','Tilt away')]
          for suffix, strength in [('', ' · mild'),('_strong',' · strong')]] + [('shake','Shake'),('person_returned','Person returned')]

def ensure_sensor_source(cfg):
    apps = cfg.setdefault('apps', [])
    source = next((a for a in apps if a.get('id') == SOURCE_ID), None)
    if source is None:
        source = dict(id=SOURCE_ID, name='Sensors', built_in='sensors', color=[135,205,240],
                      monitor_health=False, source_enabled=False, heartbeat_action_id='', switch_id=0,
                      actions=[], integration_events=[dict(name=n,label=l) for n,l in EVENTS],
                      sensor_settings=dict(enabled=False, mild_degrees=12, strong_degrees=28,
                        cooldown_seconds=.5, shake_g=.45, presence_enabled=False, absence_seconds=60))
        apps.append(source)
    return source

class SensorEvents:
    def __init__(self):
        self.motion_at = None
        self.filtered = None
        self.tilt_state = None
        self.candidate = None
        self.candidate_since = 0
        self.last_emit = {}
        self.shake_at = None
        self.last_seen = None
        self.presence_since = None
        self.present = False
        self.absence_since = None
        self.enabled_at = None

    def tick(self, options, mount, imu, radar, now, calibration=False):
        if not options.get('enabled') or calibration:
            self.motion_at = self.filtered = self.tilt_state = self.candidate = None
            self.last_seen = self.presence_since = self.enabled_at = None
            self.present = False
            self.absence_since = None
            return []
        if self.enabled_at is None: self.enabled_at = now
        events = []
        cooldown = max(.5, min(120, float(options.get('cooldown_seconds',.5))))
        def emit(name, **values):
            if now-self.last_emit.get(name,-1e9) >= cooldown:
                self.last_emit[name] = now
                events.append(dict(event=name, **values))
        if imu.get('state') == 'live' and now-imu.get('at',0) < 1 and imu.get('at') != self.motion_at:
            previous_at = self.motion_at
            self.motion_at = imu['at']
            vector = ([sum(v*a for v,a in zip(row,imu['accel_g'])) for row in mount['rotation']] if mount.get('rotation') else [imu['accel_g'][axis]*mount['signs'][i] for i,axis in enumerate(mount['axes'])])
            tilt = [math.atan2(vector[1],vector[2]), math.atan2(-vector[0],math.hypot(vector[1],vector[2]))]
            desired = [math.degrees(math.atan2(math.sin(v-n),math.cos(v-n))) for v,n in zip(tilt,mount['neutral'])]
            dt = max(0, min(.5,self.motion_at-previous_at)) if previous_at is not None else 0
            alpha = 1-math.exp(-dt/.18)
            self.filtered = desired if self.filtered is None else [a+alpha*(b-a) for a,b in zip(self.filtered,desired)]
            # Calibrated display X is toward/away; Y is left/right.
            forward, side = self.filtered
            value = side if abs(side)>abs(forward) else forward
            direction = ('right' if side>0 else 'left') if abs(side)>abs(forward) else ('forward' if forward>0 else 'back')
            mild = max(3,min(60,float(options.get('mild_degrees',12))))
            strong = max(mild+2,min(85,float(options.get('strong_degrees',28))))
            state = None if abs(value)<mild-3 else self.tilt_state if abs(value)<mild else 'tilt_'+direction+('_strong' if abs(value)>=strong else '')
            if state != self.candidate: self.candidate,self.candidate_since=state,now
            if now-self.candidate_since >= .25 and state != self.tilt_state:
                self.tilt_state=state
                if state: emit(state,degrees=round(abs(value),1))
            magnitude=math.sqrt(sum(a*a for a in vector))
            if abs(magnitude-1)>=max(.15,min(3,float(options.get('shake_g',.45)))):
                if self.shake_at is not None and .05<=now-self.shake_at<=.8:
                    emit('shake',acceleration_g=round(magnitude,2));self.shake_at=None
                else: self.shake_at=now
        else:
            if imu.get('state')!='live' or now-imu.get('at',0)>=1:
                self.filtered=self.motion_at=self.tilt_state=self.candidate=None
        if options.get('presence_enabled') and radar.get('state')=='receiving' and now-radar.get('_monotonic_at',-1e9)<1:
            if radar.get('targets'):
                if self.presence_since is None: self.presence_since=now
                if now-self.presence_since>=1:
                    absence=now-self.absence_since if self.absence_since is not None else 0
                    if not self.present and absence>=max(5,float(options.get('absence_seconds',60))): emit('person_returned')
                    self.present=True;self.last_seen=now;self.absence_since=None
            else:
                self.presence_since=None;self.present=False
                if self.absence_since is None: self.absence_since=now
        else:
            self.presence_since=None;self.present=False
            self.absence_since=None
        return events
