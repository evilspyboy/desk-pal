"""Optional Open-Meteo application; network work runs off the display thread."""
import copy
import json
import math
import queue
import threading
import time
import urllib.parse
import urllib.request


def ensure_weather_source(cfg):
    # Install once; deleting the application should remain effective.
    if cfg.get('weather_application_added'): return
    cfg['weather_application_added'] = True
    cfg.setdefault('apps', []).append(dict(id='deskpal_weather', name='Weather', built_in='weather',
        adapter='weather', weather_enabled=True, poll_seconds=3600, source_enabled=False,
        monitor_health=False, heartbeat_action_id='', switch_id=0, color=[120,190,240],
        actions=[], integration_events=[dict(name='forecast_updated',label="Today's forecast changed")],
        suppressed_events={'heartbeat':True}, suppress_duplicate_events={'forecast_updated':True}))


def validate_weather(cfg):
    for source in cfg.get('apps',[]):
        if source.get('built_in') != 'weather': continue
        if type(source.get('weather_enabled',True)) is not bool: raise ValueError('Weather enabled must be true or false')
        interval = source.get('poll_seconds',3600)
        if type(interval) not in (int,float) or not math.isfinite(interval) or not 900 <= interval <= 86400:
            raise ValueError('Weather refresh must be between 900 and 86400 seconds')


from collections import Counter


def classify_codes(codes, is_night=False):
    if not codes:
        return ('clear_night', 'Clear Night', 'weather_moon') if is_night else ('sunny', 'Sunny', 'weather_sun')
    storm_codes = [c for c in codes if c in (95, 96, 99)]
    rain_codes = [c for c in codes if c in (51, 53, 55, 61, 63, 65, 80, 81, 82)]
    if storm_codes:
        return ('storm', 'Thunderstorm', 'weather_storm')
    if len(rain_codes) >= 2:
        return ('rain', 'Rain & Showers', 'weather_rain')

    counts = Counter(codes)
    most_common_code = counts.most_common(1)[0][0]
    if most_common_code == 0:
        return ('clear_night', 'Clear Night', 'weather_moon') if is_night else ('sunny', 'Sunny', 'weather_sun')
    elif most_common_code in (1, 2):
        return ('partly_cloudy_night', 'Partly Cloudy', 'weather_partly_cloudy_night') if is_night else ('partly_cloudy', 'Partly Cloudy', 'weather_partly_cloudy')
    elif most_common_code in (3, 45, 48):
        return ('overcast', 'Overcast' if most_common_code == 3 else 'Foggy', 'weather_cloudy')
    elif rain_codes:
        return ('rain', 'Light Showers', 'weather_rain')
    return ('cloudy', 'Cloudy', 'weather_cloudy')


def build_progression(payload, daily_data):
    hourly = payload.get('hourly', {})
    times = hourly.get('time', [])
    is_days = hourly.get('is_day', [])
    temps = hourly.get('temperature_2m', [])
    hums = hourly.get('relative_humidity_2m', [])
    codes = hourly.get('weather_code', [])

    day_indices = [i for i in range(min(24, len(is_days))) if is_days[i] == 1]
    if not day_indices:
        day_indices = list(range(6, min(18, len(times))))

    sunset_idx = max(day_indices) + 1 if day_indices else 18
    night_indices = [i for i in range(sunset_idx, min(sunset_idx + 12, len(times))) if is_days[i] == 0]
    if not night_indices:
        night_indices = list(range(sunset_idx, min(sunset_idx + 8, len(times))))

    day_temps = [temps[i] for i in day_indices if i < len(temps)] or [daily_data.get('temperature_2m_max', 24)]
    night_temps = [temps[i] for i in night_indices if i < len(temps)] or [daily_data.get('temperature_2m_min', 18)]
    day_hums = [hums[i] for i in day_indices if i < len(hums)] or [65]
    night_hums = [hums[i] for i in night_indices if i < len(hums)] or [80]

    day_cond, day_lbl, day_icon = classify_codes([codes[i] for i in day_indices if i < len(codes)], is_night=False)
    night_cond, night_lbl, night_icon = classify_codes([codes[i] for i in night_indices if i < len(codes)], is_night=True)

    is_steady = (day_cond == night_cond) or (day_cond in ('rain', 'storm') and night_cond in ('rain', 'storm'))

    return {
        'is_steady': is_steady,
        'day': {
            'condition': day_cond,
            'label': day_lbl,
            'temp': round(max(day_temps)),
            'humidity': round(sum(day_hums) / len(day_hums)),
            'icon': day_icon
        },
        'night': {
            'condition': night_cond,
            'label': night_lbl,
            'temp': round(min(night_temps)),
            'humidity': round(sum(night_hums) / len(night_hums)),
            'icon': night_icon
        },
        'steady': {
            'condition': day_cond,
            'label': day_lbl,
            'sub': 'All Day & Night',
            'temp_min': round(min(night_temps)),
            'temp_max': round(max(day_temps)),
            'humidity': round((sum(day_hums) / len(day_hums) + sum(night_hums) / len(night_hums)) / 2),
            'icon': day_icon
        }
    }


def forecast(payload):
    daily = payload['daily']
    def value(key):
        values = daily.get(key, [])
        return values[0] if values else None
    data = {key: value(key) for key in ('time', 'temperature_2m_min', 'temperature_2m_max',
        'precipitation_probability_max', 'precipitation_sum', 'wind_speed_10m_max', 'uv_index_max', 'weather_code')}
    if data['temperature_2m_min'] is None or data['temperature_2m_max'] is None:
        raise ValueError('Weather response has no daily temperatures')

    progression = build_progression(payload, data)
    data['progression'] = progression
    data['day_temp'] = progression['day']['temp']
    data['night_temp'] = progression['night']['temp']
    data['day_condition'] = progression['day']['condition']
    data['night_condition'] = progression['night']['condition']
    data['day_icon'] = progression['day']['icon']
    data['night_icon'] = progression['night']['icon']
    data['humidity'] = progression['day']['humidity']

    text = f"Today {data['temperature_2m_min']:g}–{data['temperature_2m_max']:g}°C"
    if data['precipitation_probability_max'] is not None: text += f" · Rain {data['precipitation_probability_max']:g}%"
    if data['wind_speed_10m_max'] is not None: text += f"\nWind up to {data['wind_speed_10m_max']:g} km/h"
    if data['uv_index_max'] is not None: text += f" · UV {data['uv_index_max']:g}"
    return data, text


def fetch(lighting):
    query = urllib.parse.urlencode(dict(
        latitude=lighting.get('latitude', -27.47),
        longitude=lighting.get('longitude', 153.03),
        timezone=lighting.get('timezone') or 'auto',
        forecast_days=2,
        daily='temperature_2m_min,temperature_2m_max,precipitation_probability_max,precipitation_sum,wind_speed_10m_max,uv_index_max,weather_code',
        hourly='temperature_2m,relative_humidity_2m,weather_code,is_day'
    ))
    request = urllib.request.Request('https://api.open-meteo.com/v1/forecast?' + query,
        headers={'User-Agent': 'Desk-Pal personal weather integration'})
    with urllib.request.urlopen(request, timeout=15) as response:
        return forecast(json.load(response))


class WeatherSource:
    def __init__(self):
        self.results = queue.Queue()
        self.busy = False
        self.next_poll = 0
        self.signature = None

    def tick(self, app):
        source = next((a for a in app.apps if a.get('built_in')=='weather'),None)
        lighting = copy.deepcopy(app.cfg.get('lighting',{}))
        signature = (source.get('id'), bool(source.get('weather_enabled',True)),
                     json.dumps(lighting,sort_keys=True)) if source else None
        if signature != self.signature:
            self.signature = signature; self.next_poll = 0
        while not self.results.empty():
            result_signature, result = self.results.get_nowait()
            self.busy = False
            if result_signature != signature or not source or not source.get('weather_enabled',True): continue
            interval = source.get('poll_seconds',3600)
            self.next_poll = time.monotonic() + (300 if 'error' in result else interval)
            if 'error' in result:
                previous = app.app_telemetry.get(source['id'],{}).get('summary','Weather unavailable')
                cached = app.app_telemetry.get(source['id'],{}).get('received_events',{}).get('heartbeat',{}).get('data',{})
                app.receive_heartbeat(dict(cached,app_id=source['id'],status='warning',summary=previous,
                    refresh_error=result['error'],ttl_seconds=interval*2))
            else:
                data, summary = result['forecast']
                previous = app.app_telemetry.get(source['id'],{}).get('received_events',{}).get('forecast_updated',{}).get('data',{})
                changed = any(previous.get(k)!=v for k,v in data.items())
                app.receive_heartbeat(dict(data,app_id=source['id'],summary=summary,status='healthy',cached_at=time.time(),ttl_seconds=interval*2))
                if changed:
                    app.receive_telemetry_event(dict(data,app_id=source['id'],event='forecast_updated',summary=summary,status='healthy'))
        if not source or not source.get('weather_enabled',True) or self.busy or time.monotonic()<self.next_poll: return
        self.busy = True
        def worker():
            try: result = {'forecast':fetch(lighting)}
            except Exception as error: result = {'error':str(error)[:200]}
            self.results.put((signature,result))
        threading.Thread(target=worker,name='deskpal-weather',daemon=True).start()
