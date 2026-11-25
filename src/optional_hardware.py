"""Optional bench hardware, isolated from scenes, integrations and playback."""
import array
import json
import math
import os
import struct
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

DEFAULTS = {'radar': {'enabled': False, 'model': 'rd03d', 'port': '/dev/serial0', 'presence_range_m': 2.0,
                      'dropout_hold_seconds': 2.5, 'jump_threshold_mm': 600, 'jump_confirm_seconds': 0.5},
            'speaker': {'enabled': False, 'output': 'headphones', 'volume': .25},
            'microphone': {'enabled': False, 'wake_peak_threshold': 4500},
            'buttons': {'enabled': True, 'pins': None},
            'light': {'enabled': False, 'idle_threshold_enabled': False, 'sleep_below_lux': 5,
                      'wake_margin_lux': 2, 'delay_seconds': 5, 'manual_wake_seconds': 120, 'evening_awake_enabled': False, 'bedtime': '22:00', 'presence_awake_enabled': False, 'presence_absence_seconds': 30,
                      'mode': 'high_res_2', 'mtreg': 254}, 'imu': {'enabled': False,
                'rotation': None, 'axes': [0, 1, 2], 'signs': [1, 1, 1], 'neutral': [0, 0], 'gyro_bias': [0, 0, 0]}}


def decode_frame(frame):
    if len(frame) != 30 or frame[:4] != b'\xaa\xff\x03\x00' or frame[-2:] != b'\x55\xcc':
        raise ValueError('Invalid radar frame')
    signed = lambda v: (v & 32767) if v & 32768 else -v
    targets = []
    for i in range(3):
        raw = frame[4+i*8:12+i*8]
        if not any(raw):
            continue
        x, y, speed, resolution = struct.unpack('<HHHH', raw)
        x, y = signed(x), signed(y)
        targets.append({'slot': i+1, 'x_mm': x, 'y_mm': y, 'speed_cm_s': signed(speed),
                        'distance_mm': round(math.hypot(x, y)),
                        'angle_deg': round(math.degrees(math.atan2(x, y)), 1),
                        'resolution_mm': resolution})
    return targets


class HardwareMonitor:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self._control_lock = threading.Lock()
        self.config = json.loads(json.dumps(DEFAULTS))
        self.settings_error = ''
        try:
            if self.path.exists():
                self.config = self.validate(json.loads(self.path.read_text()))
        except (OSError, ValueError, TypeError) as error:
            self.settings_error = str(error)
        self.stop = threading.Event()
        self.radar_thread = None
        from radar_tracker import RadarTracker
        radar_cfg = self.config.get('radar', {})
        self.tracker = RadarTracker(
            jump_threshold_mm=radar_cfg.get('jump_threshold_mm', 600),
            jump_confirm_seconds=radar_cfg.get('jump_confirm_seconds', 0.5),
            hold_dropout_seconds=radar_cfg.get('dropout_hold_seconds', 2.5)
        )
        self.radar = dict(state='disabled', error='', frames=0, malformed=0, targets=[], raw_targets=[], last_frame=None)
        self.microphone = dict(state='ready', error='', rms_dbfs=None, peak=0)
        self.speaker = dict(state='ready', error='')
        self.devices = {'playback': '', 'capture': '', 'error': ''}
        self.devices_at = 0
        self.i2c_at = 0
        self.i2c = {'light': {'state': 'disabled'}, 'imu': {'state': 'disabled'}}
        self.imu_capture = {'state': 'ready'}
        self.radar_capture = {'state': 'ready'}
        self.radar_capture_frames = []
        self.imu_bus_lock = threading.Lock()
        if self.config['radar']['enabled']:
            self.start_radar()
        threading.Thread(target=self._poll_i2c, daemon=True).start()

    @staticmethod
    def validate(value):
        if not isinstance(value, dict) or set(value) - set(DEFAULTS):
            raise ValueError('Unknown hardware setting')
        result = json.loads(json.dumps(DEFAULTS))
        for kind, options in value.items():
            if not isinstance(options, dict) or set(options) - set(DEFAULTS[kind]):
                raise ValueError('Unknown device setting')
            result[kind].update(options)
            if type(result[kind]['enabled']) is not bool:
                raise ValueError('Enabled must be true or false')
        if result['radar']['model'] != 'rd03d':
            raise ValueError('Only RD-03D is supported by this bench reader')
        radius = result['radar']['presence_range_m']
        if type(radius) not in (int,float) or not math.isfinite(radius) or not .1 <= radius <= 8:
            raise ValueError('Radar presence range must be between 0.1 and 8 metres')
        hold = result['radar'].get('dropout_hold_seconds', 2.5)
        if type(hold) not in (int, float) or not math.isfinite(hold) or not 0 <= hold <= 30:
            raise ValueError('Dropout hold must be between 0 and 30 seconds')
        jump = result['radar'].get('jump_threshold_mm', 600)
        if type(jump) not in (int, float) or not math.isfinite(jump) or not 100 <= jump <= 5000:
            raise ValueError('Jump threshold must be between 100 and 5000 mm')
        confirm = result['radar'].get('jump_confirm_seconds', 0.5)
        if type(confirm) not in (int, float) or not math.isfinite(confirm) or not 0.1 <= confirm <= 5.0:
            raise ValueError('Jump confirmation must be between 0.1 and 5.0 seconds')
        from gpio_hardware import validate_buttons
        result['buttons'] = validate_buttons(result['buttons'])
        reserved = ({2,3} if result['light']['enabled'] or result['imu']['enabled'] else set()) | ({14,15} if result['radar']['enabled'] else set())
        if result['buttons']['enabled'] and any(p['bcm'] in reserved for p in result['buttons']['pins'] or []):raise ValueError('A button GPIO conflicts with an enabled I2C/UART sensor')
        if result['speaker']['output'] not in ('headphones','usb','default'):raise ValueError('Choose a supported audio output')
        volume = result['speaker']['volume']
        if type(volume) not in (int, float) or not math.isfinite(volume) or not 0 <= volume <= 1:
            raise ValueError('Speaker volume must be between 0 and 1')
        mic_thresh = result['microphone'].get('wake_peak_threshold', 4500)
        if type(mic_thresh) not in (int, float) or not math.isfinite(mic_thresh) or not 300 <= mic_thresh <= 30000:
            raise ValueError('Microphone wake threshold must be between 300 and 30000')
        result['microphone']['wake_peak_threshold'] = int(round(mic_thresh))
        import re
        if type(result['light']['evening_awake_enabled']) is not bool or not isinstance(result['light']['bedtime'],str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',result['light']['bedtime']):raise ValueError('Choose a valid evening setting and bedtime HH:MM')
        imu = result['imu']
        rotation = imu['rotation']
        if rotation is not None:
            if not isinstance(rotation,list) or len(rotation)!=3 or any(not isinstance(row,list) or len(row)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in row) for row in rotation):
                raise ValueError('Invalid IMU mounting rotation')
            dot=lambda a,b:sum(x*y for x,y in zip(a,b))
            if any(abs(dot(rotation[i],rotation[j])-(1 if i==j else 0))>.02 for i in range(3) for j in range(3)):
                raise ValueError('IMU mounting rotation must be orthonormal')
            a,b,c=rotation
            det=a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
            if det<.98:raise ValueError('IMU mounting rotation must preserve handedness')
        light = result['light']
        if type(light['presence_awake_enabled']) is not bool:
            raise ValueError('Presence stay-awake must be true or false')
        absence = light['presence_absence_seconds']
        if type(absence) not in (int, float) or not math.isfinite(absence) or not 1 <= absence <= 3600:
            raise ValueError('Presence absence delay must be 1–3600 seconds')
        if type(light['idle_threshold_enabled']) is not bool:
            raise ValueError('Light threshold enabled must be true or false')
        for key, low, high in [('sleep_below_lux', .1, 65535), ('wake_margin_lux', .1, 65535), ('delay_seconds', 1, 300), ('manual_wake_seconds', 10, 3600)]:
            v = light[key]
            if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
                raise ValueError('Invalid light '+key)
        mtreg = light.get('mtreg', 254)
        if type(mtreg) not in (int, float) or not math.isfinite(mtreg) or not 31 <= mtreg <= 254:
            raise ValueError('BH1750 measurement time (MTreg) must be between 31 and 254')
        mode = light.get('mode', 'high_res_2')
        if mode not in ('high_res_2', 'high_res_1'):
            raise ValueError('Light mode must be high_res_2 or high_res_1')
        if not isinstance(imu['gyro_bias'], list) or len(imu['gyro_bias']) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 20 for v in imu['gyro_bias']):
            raise ValueError('Invalid stationary gyro bias')
        if not isinstance(imu['axes'], list) or len(imu['axes']) != 3 or any(type(v) is not int for v in imu['axes']) or sorted(imu['axes']) != [0, 1, 2]:
            raise ValueError('Each IMU source axis must be used exactly once')
        if not isinstance(imu['signs'], list) or len(imu['signs']) != 3 or any(type(v) is not int or v not in (-1, 1) for v in imu['signs']):
            raise ValueError('IMU axis direction must be +1 or -1')
        if not isinstance(imu['neutral'], list) or len(imu['neutral']) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > math.pi for v in imu['neutral']):
            raise ValueError('Invalid IMU neutral tilt')
        if result['radar']['port'] not in ('/dev/serial0', '/dev/ttyS0', '/dev/ttyAMA0'):
            raise ValueError('Choose a supported Pi UART port')
        return result

    def configure(self, value):
        # Serialize reconfiguration; the reader uses a separate state lock.
        with self.control_lock:
            self.validate(value)
            settings = self.validate({kind: {**self.config[kind], **value.get(kind, {})} for kind in DEFAULTS})
            restart = settings['radar'] != self.config['radar'] or self.radar['state'] == 'unavailable'
            if restart:
                self.stop.set()
            if restart and self.radar_thread:
                self.radar_thread.join(timeout=2)
                if self.radar_thread.is_alive():
                    raise ValueError('Radar reader is still stopping; retry shortly')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(settings, indent=2))
            os.replace(temp, self.path)
            with self.lock:
                self.config = settings
                self.settings_error = ''
                if restart:
                    if hasattr(self, 'tracker'):
                        self.tracker.reset()
                    self.radar = dict(state='disabled', error='', frames=0, malformed=0, targets=[], raw_targets=[], last_frame=None)
                elif hasattr(self, 'tracker'):
                    radar_cfg = settings.get('radar', {})
                    self.tracker.jump_threshold_mm = radar_cfg.get('jump_threshold_mm', 600)
                    self.tracker.jump_confirm_seconds = radar_cfg.get('jump_confirm_seconds', 0.5)
                    self.tracker.hold_dropout_seconds = radar_cfg.get('dropout_hold_seconds', 2.5)
            if restart and settings['radar']['enabled']:
                self.start_radar()

    @property
    def control_lock(self):
        return self._control_lock

    def start_radar(self):
        self.stop = threading.Event()
        self.radar_thread = threading.Thread(target=self.read_radar, daemon=True)
        self.radar_thread.start()

    def read_radar(self):
        with self.lock:
            self.radar.update(state='connecting', error='')
        try:
            import serial
            buffer = bytearray()
            with serial.Serial(self.config['radar']['port'], 256000, timeout=.2, exclusive=True) as port:
                while not self.stop.is_set():
                    buffer.extend(port.read(300))
                    while len(buffer) >= 30:
                        start = buffer.find(b'\xaa\xff\x03\x00')
                        if start < 0:
                            buffer = buffer[-3:]
                            break
                        del buffer[:start]
                        if len(buffer) < 30:
                            break
                        if buffer[28:30] != b'\x55\xcc':
                            del buffer[0]
                            with self.lock:
                                self.radar['malformed'] += 1
                            continue
                        targets = decode_frame(bytes(buffer[:30]))
                        raw_hex = bytes(buffer[:30]).hex()
                        del buffer[:30]
                        now = time.time()
                        stabilized = self.tracker.update(targets, now) if hasattr(self, 'tracker') else targets
                        with self.lock:
                            self.radar.update(state='receiving', last_frame=now, targets=stabilized, raw_targets=targets)
                            self.radar['frames'] += 1
                            if self.radar_capture['state'] == 'recording' and len(self.radar_capture_frames) < 12000:
                                self.radar_capture_frames.append(dict(at=now, phase=self.radar_capture['phase'], raw_hex=raw_hex, targets=targets))
        except Exception as error:
            with self.lock:
                self.radar.update(state='unavailable', error=str(error), targets=[], raw_targets=[])

    def _live_voice_sentry(self):
        app = getattr(self, '_app_ref', None)
        sentry = getattr(app, 'voice_sentry', None) if app else None
        if sentry and getattr(sentry, 'capture_running', False):
            if time.monotonic() - getattr(sentry, 'live_updated_at', 0.0) < 3.0:
                return sentry
        return None

    def snapshot(self):
        with self.lock:
            # Cache device inventory so live polling cannot spawn unbounded commands.
            if time.monotonic() - self.devices_at > 10:
                self.devices_at = time.monotonic()
                for name, command in [('playback', 'aplay'), ('capture', 'arecord')]:
                    try:
                        result = subprocess.run([command, '-l'], capture_output=True, text=True, timeout=2)
                        self.devices[name] = result.stdout or result.stderr
                    except (OSError, subprocess.TimeoutExpired) as error:
                        self.devices[name] = str(error)
            data = json.loads(json.dumps(dict(settings=self.config, radar=self.radar,
                                             microphone=self.microphone, speaker=self.speaker,
                                             devices=self.devices, i2c=self.i2c, imu_capture=self.imu_capture, radar_capture=self.radar_capture, settings_error=self.settings_error)))
        sentry = self._live_voice_sentry()
        if sentry:
            mic_state = 'testing' if data['microphone'].get('state') == 'testing' else 'active'
            data['microphone'].update(
                state=mic_state,
                error='',
                rms_dbfs=getattr(sentry, 'live_rms_dbfs', -70.0),
                peak=getattr(sentry, 'live_peak', 0),
                ambient_floor=getattr(sentry, 'live_ambient_floor', 0.0),
                stream_source='voice_sentry',
            )
        last = data['radar']['last_frame']
        data['radar']['age_seconds'] = None if last is None else max(0, time.time()-last)
        if data['radar']['state'] == 'receiving' and data['radar']['age_seconds'] > 1:
            data['radar']['state'] = 'stale'
            data['radar']['targets'] = []
            data['radar']['raw_targets'] = []
        return data

    def capture_radar(self, value):
        with self.lock:
            if value.get('action') == 'cancel':
                if self.radar_capture['state'] in ('preparing', 'recording'):
                    self.radar_capture['state'] = 'cancelled'
                    self.radar_capture['instruction'] = 'Capture cancelled. Start again when ready.'
                return
            if value.get('action') != 'start':
                raise ValueError('Choose start or cancel')
            if self.radar_capture['state'] in ('preparing', 'recording'):
                raise ValueError('Radar capture is already running')
            if self.radar['state'] != 'receiving' or time.time()-(self.radar['last_frame'] or 0) > 1:
                raise ValueError('Enable radar and wait for fresh readings first')
            self.radar_capture_frames = []
            run_id = time.time()
            self.radar_capture = dict(state='preparing', id=run_id, phase='prepare', instruction='Stand in front of the sensor. Keep the sensor fixed.', seconds_left=10)
        threading.Thread(target=self._capture_radar, args=(run_id,), daemon=True).start()

    def _capture_radar(self, run_id):
        steps = [('prepare', 'Stand in front of the sensor. Keep the sensor fixed.', 10),
                 ('near_center', 'Stand still at your starting position.', 6),
                 ('near_left', 'Take ONE step to YOUR LEFT, then hold.', 8),
                 ('near_return', 'Return to your starting position, then hold.', 8),
                 ('near_right', 'Take ONE step to YOUR RIGHT, then hold.', 8),
                 ('near_return_2', 'Return to your starting position, then hold.', 8),
                 ('far_center', 'Take ONE step BACK away from the sensor, then hold.', 8),
                 ('far_left', 'From here, take ONE step to YOUR LEFT, then hold.', 8),
                 ('far_return', 'Return to the farther centre position, then hold.', 8),
                 ('far_right', 'Take ONE step to YOUR RIGHT, then hold.', 8),
                 ('far_return_2', 'Return to the farther centre position, then hold.', 8)]
        try:
            for index, (phase, instruction, duration) in enumerate(steps):
                deadline = time.monotonic()+duration
                while time.monotonic() < deadline:
                    with self.lock:
                        if self.radar_capture.get('id') != run_id or self.radar_capture['state'] == 'cancelled':
                            return
                        self.radar_capture.update(state='preparing' if index == 0 else 'recording', phase=phase, instruction=instruction, step=index, total_steps=len(steps)-1, seconds_left=round(max(0, deadline-time.monotonic()), 1), frames=len(self.radar_capture_frames))
                    time.sleep(.1)
            with self.lock:
                if self.radar_capture.get('id') != run_id or self.radar_capture['state'] == 'cancelled':
                    return
                frames = list(self.radar_capture_frames)
                settings = dict(self.config['radar'])
            if not frames:
                raise ValueError('No radar frames received during capture')
            report = dict(version=1, started_at=run_id, finished_at=time.time(), settings=settings,
                          note='Diagnostic capture only. No sensor reset, calibration command or coordinate correction was applied. Slots are not person identities.',
                          steps=[dict(phase=p, instruction=i, seconds=d) for p, i, d in steps], frames=frames)
            target = self.path.parent/'radar_capture_latest.json'
            temp = target.with_suffix('.tmp')
            temp.write_text(json.dumps(report), encoding='utf-8')
            os.replace(temp, target)
            with self.lock:
                if self.radar_capture.get('id') == run_id and self.radar_capture['state'] != 'cancelled':
                    self.radar_capture.update(state='complete', instruction='Capture saved. Download it for review.', frames=len(frames), seconds_left=0)
        except Exception as error:
            with self.lock:
                if self.radar_capture.get('id') == run_id and self.radar_capture['state'] != 'cancelled':
                    self.radar_capture.update(state='error', error=str(error))

    def radar_capture_report(self):
        return (self.path.parent/'radar_capture_latest.json').read_bytes()

    def _poll_i2c(self):
        while True:
            with self.lock:
                self.read_i2c()
            time.sleep(.1)

    def read_i2c(self):
        for kind in ('light', 'imu'):
            if not self.config[kind]['enabled']:
                self.i2c[kind] = {'state': 'disabled'}
                continue
            if kind == 'light' and time.monotonic()-self.i2c[kind].get('at', 0) < 1:
                continue
            try:
                if kind == 'imu' and self.imu_capture['state'] == 'recording':
                    continue
                from smbus2 import SMBus, i2c_msg
                with SMBus(1) as bus:
                    if kind == 'light':
                        mode_str = self.config['light'].get('mode', 'high_res_2')
                        mtreg = int(self.config['light'].get('mtreg', 254))
                        cfg_key = (mode_str, mtreg)
                        if getattr(self, '_light_cfg_key', None) != cfg_key:
                            bus.write_byte(0x23, 0x01)
                            time.sleep(0.01)
                            bus.write_byte(0x23, 0x40 | (mtreg >> 5))
                            time.sleep(0.01)
                            bus.write_byte(0x23, 0x60 | (mtreg & 0x1F))
                            time.sleep(0.01)
                            mode_byte = 0x11 if mode_str == 'high_res_2' else 0x10
                            bus.write_byte(0x23, mode_byte)
                            meas_delay = (0.12 if mode_str == 'high_res_2' else 0.12) * (mtreg / 69.0) * 1.2
                            time.sleep(min(0.6, max(0.18, meas_delay)))
                            self._light_cfg_key = cfg_key
                        message = i2c_msg.read(0x23, 2)
                        bus.i2c_rdwr(message)
                        raw = list(message)
                        count = raw[0]*256 + raw[1]
                        factor = 2.4 if mode_str == 'high_res_2' else 1.2
                        lux = round((count / factor) * (69.0 / mtreg), 2)
                        self.i2c[kind] = {'state': 'live', 'lux': lux, 'at': time.monotonic()}
                    else:
                        identity = bus.read_byte_data(0x68, 0x75)
                        if identity != 0x68:
                            raise ValueError('Unexpected MPU6050 identity')
                        bus.write_byte_data(0x68, 0x6b, 0)
                        bus.write_byte_data(0x68, 0x1b, 0)
                        bus.write_byte_data(0x68, 0x1c, 0)
                        time.sleep(.01)
                        values = struct.unpack('>7h', bytes(bus.read_i2c_block_data(0x68, 0x3b, 14)))
                        self.i2c[kind] = {'state': 'live', 'at': time.monotonic(),
                            'accel_g': [round(v/16384, 3) for v in values[:3]],
                            'gyro_dps': [round(v/131, 2) for v in values[4:]],
                            'temperature_c': round(values[3]/340+36.53, 1)}
            except Exception as error:
                if kind == 'light':
                    self._light_cfg_key = None
                self.i2c[kind] = {'state': 'unavailable', 'error': str(error)}

    def capture_imu(self, value):
        phase = value.get('phase')
        bias = value.get('gyro_bias', [0, 0, 0])
        if not isinstance(bias, list) or len(bias) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 20 for v in bias):
            raise ValueError('Invalid calibration gyro bias')
        if phase not in ('neutral', 'left', 'right', 'forward', 'back', 'turn_left', 'turn_right'):
            raise ValueError('Choose a calibration movement')
        with self.lock:
            if not self.config['imu']['enabled']:
                raise ValueError('Enable IMU readings first')
            if self.imu_capture['state'] == 'recording':
                raise ValueError('A calibration recording is already running')
            self.imu_capture = {'state': 'recording', 'phase': phase, 'id': time.time(), 'seconds_left': 4}
        threading.Thread(target=self._capture_imu, args=(phase, bias), daemon=True).start()

    def _capture_imu(self, phase, bias):
        samples = []
        try:
            from smbus2 import SMBus
            with self.imu_bus_lock, SMBus(1) as bus:
                if bus.read_byte_data(0x68, 0x75) != 0x68:
                    raise ValueError('Unexpected MPU6050 identity')
                for register in (0x6b, 0x1b, 0x1c):
                    bus.write_byte_data(0x68, register, 0)
                time.sleep(.05)
                started = time.monotonic()
                motion_started = None
                while time.monotonic()-started < 30:
                    values = struct.unpack('>7h', bytes(bus.read_i2c_block_data(0x68, 0x3b, 14)))
                    elapsed = time.monotonic()-started
                    sample = ([v/16384 for v in values[:3]], [v/131 for v in values[4:]])
                    if phase != 'neutral' and motion_started is None and math.hypot(*(sample[1][i]-bias[i] for i in range(3))) > 5:
                        motion_started = elapsed
                    samples.append((elapsed, *sample))
                    with self.lock:
                        if not self.config['imu']['enabled']:
                            raise ValueError('IMU was disabled; recording cancelled')
                        self.imu_capture['motion_started'] = phase == 'neutral' or motion_started is not None
                        self.imu_capture['seconds_left'] = round(max(0, (2-elapsed) if phase == 'neutral' else (4-(elapsed-motion_started)) if motion_started is not None else (30-elapsed)), 1)
                        self.i2c['imu'].update(state='live', at=time.monotonic(), accel_g=sample[0], gyro_dps=sample[1])
                    if phase == 'neutral' and elapsed >= 2:
                        break
                    if phase != 'neutral' and motion_started is not None and elapsed-motion_started >= 4:
                        break
                    if phase != 'neutral' and elapsed >= .75:
                        integral_now = [sum((samples[j][0]-samples[j-1][0])*((samples[j][2][i]+samples[j-1][2][i])/2-bias[i]) for j in range(1,len(samples))) for i in range(3)]
                        ordered = sorted(map(abs, integral_now), reverse=True)
                        if ordered[0] >= 18 and ordered[0] >= 2*math.hypot(*ordered[1:]):
                            break
                    time.sleep(.05)
                if phase != 'neutral' and motion_started is None:
                    raise ValueError('No movement detected. Return to the starting position and retry.')
            count = len(samples)
            accel = [sum(s[1][i] for s in samples)/count for i in range(3)]
            gyro = [sum(s[2][i] for s in samples)/count for i in range(3)]
            integral = [sum((samples[j][0]-samples[j-1][0])*(samples[j][2][i]+samples[j-1][2][i])/2 for j in range(1,count)) for i in range(3)]
            spread = max(math.sqrt(sum((s[1][i]-accel[i])**2 for i in range(3))) for s in samples)
            with self.lock:
                self.imu_capture.update(state='complete', samples=count, duration=samples[-1][0]-samples[0][0], accel=accel, gyro=gyro, integral=integral, accel_spread=spread)
                self._retain_imu_capture(phase, bias, samples)
        except Exception as error:
            with self.lock:
                self.imu_capture.update(state='error', error=str(error))
                try:
                    self._retain_imu_capture(phase, bias, samples)
                except OSError as storage_error:
                    self.imu_capture['error'] += '; could not save capture: '+str(storage_error)

    def _retain_imu_capture(self, phase, bias, samples):
        """Retain step summaries and raw readings independently of browser lifetime."""
        target = self.path.parent/'imu_capture_latest.json'
        report = dict(version=1, started_at=self.imu_capture['id'], steps={}, attempts=[])
        if phase != 'neutral' and target.exists():
            try:
                report = json.loads(target.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                pass
        entry = dict(self.imu_capture)
        entry['gyro_bias_used'] = list(bias)
        entry['raw_samples'] = [dict(seconds=t, accel_g=a, gyro_dps=g) for t, a, g in samples]
        report['steps'][phase] = entry
        report['attempts'] = (report['attempts']+[entry])[-24:]
        report['updated_at'] = time.time()
        report['complete'] = all(report['steps'].get(p, {}).get('state') == 'complete' for p in ('neutral', 'left', 'right', 'forward', 'back', 'turn_left', 'turn_right'))
        report['note'] = 'Diagnostic measurements only; calibration is not applied automatically. Neutral starts a new recording; download before another run.'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(report), encoding='utf-8')
        os.replace(temp, target)

    def imu_capture_report(self):
        return (self.path.parent/'imu_capture_latest.json').read_bytes()

    def test(self, kind, level=.25):
        if kind not in ('speaker', 'microphone'):
            raise ValueError('Unknown hardware test')
        if not isinstance(level, (int, float)) or not math.isfinite(level) or not 0 <= level <= 1:
            raise ValueError('Tone level must be between 0 and 1')
        with self.lock:
            if not self.config[kind]['enabled']:
                raise ValueError('Enable this device first')
            state = getattr(self, kind)
            if state['state'] == 'testing':
                raise ValueError('Test already running')
            state.update(state='testing', error='')
        threading.Thread(target=self.audio_test, args=(kind, level), daemon=True).start()

    def audio_test(self, kind, level):
        try:
            if kind == 'speaker':
                with tempfile.TemporaryDirectory(prefix='deskpal-tone-') as directory:
                    path = Path(directory)/'tone.wav'
                    data = bytearray()
                    for i in range(44100):
                        t = i/44100
                        envelope = max(0, min(1, (t-.15)/.02, (.8-t)/.02))
                        v = int(32767*level*envelope*math.sin(2*math.pi*660*t))
                        data.extend(struct.pack('<hh', v, v))
                    with wave.open(str(path), 'wb') as output:
                        output.setparams((2, 2, 44100, 0, 'NONE', 'not compressed'))
                        output.writeframes(data)
                    from audio_output import playback_command
                    subprocess.run(playback_command(self.config['speaker']['output'], path),
                                   capture_output=True, check=True, timeout=5)
            else:
                sentry = self._live_voice_sentry()
                if sentry:
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline and self.config['microphone']['enabled']:
                        if not self._live_voice_sentry():
                            break
                        with self.lock:
                            self.microphone.update(
                                rms_dbfs=getattr(sentry, 'live_rms_dbfs', -70.0),
                                peak=getattr(sentry, 'live_peak', 0),
                                ambient_floor=getattr(sentry, 'live_ambient_floor', 0.0),
                                stream_source='voice_sentry',
                            )
                        time.sleep(0.1)
                else:
                    process = subprocess.Popen(['arecord', '-q', '-D', 'plughw:Device,0', '-t', 'raw',
                                                '-f', 'S16_LE', '-r', '48000', '-c', '1', '-d', '15'],
                                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                    try:
                        deadline = time.monotonic()+17
                        while time.monotonic() < deadline and self.config['microphone']['enabled']:
                            data = process.stdout.read(9600)
                            if not data:
                                break
                            values = array.array('h', data)
                            rms = math.sqrt(sum(v*v for v in values)/max(1, len(values)))
                            with self.lock:
                                self.microphone.update(rms_dbfs=round(20*math.log10(max(rms, 1)/32768), 1),
                                                       peak=max(map(abs, values), default=0))
                        if process.poll() not in (None, 0):
                            raise ValueError('Microphone capture failed; check USB device availability')
                    finally:
                        if process.poll() is None:
                            process.terminate()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        process.stdout.close()
            with self.lock:
                getattr(self, kind).update(state='ready', error='')
        except Exception as error:
            with self.lock:
                getattr(self, kind).update(state='unavailable', error=str(error))


class LightSleepPolicy:
    """Debounced automatic sleep; manual sleep/wake always takes precedence."""
    def __init__(self):
        self.auto_sleep = False
        self.manual_awake = False
        self.awake_until = 0
        self.pending = None
        self.since = None
        self.last_options = None

    def manual(self, now):
        self.auto_sleep = False
        self.manual_awake = True
        self.awake_until = now+(self.last_options or {}).get('manual_wake_seconds', 120)
        self.pending = self.since = None

    def tick(self, options, reading, sleeping, now, blocked=False, keep_awake=False):
        if options != self.last_options:
            self.pending = self.since = None
            self.last_options = dict(options)
        enabled = options.get('enabled') and options.get('idle_threshold_enabled')
        if not enabled:
            self.pending = self.since = None
            self.manual_awake = False
            if self.auto_sleep and sleeping:
                self.auto_sleep = False
                return 'wake'
            self.auto_sleep = False
            return None
        if keep_awake:
            self.pending = self.since = None
            if sleeping and self.auto_sleep:
                self.auto_sleep = False
                return 'wake'
            return None
        if reading.get('state') != 'live' or now-reading.get('at', 0) > 5:
            self.pending = self.since = None
            return None
        lux = reading['lux']
        threshold = options['sleep_below_lux']
        bright = lux >= threshold+options['wake_margin_lux']
        if self.manual_awake and now >= self.awake_until:
            self.manual_awake = False
        if sleeping and not bright:
            self.auto_sleep = True
            self.manual_awake = False
        action = 'wake' if sleeping and self.auto_sleep and bright else 'sleep' if not sleeping and not self.manual_awake and not blocked and lux < threshold else None
        if action != self.pending:
            self.pending, self.since = action, now if action else None
        if action and now-self.since >= options['delay_seconds']:
            self.pending = self.since = None
            self.auto_sleep = action == 'sleep'
            return action
        return None


_factory_lock = threading.Lock()


def monitor_for(app, path):
    with _factory_lock:
        if not hasattr(app, 'hardware_monitor'):
            app.hardware_monitor = HardwareMonitor(path)
        app.hardware_monitor._app_ref = app
        return app.hardware_monitor
