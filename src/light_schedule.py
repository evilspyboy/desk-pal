"""Solar evening window suppresses lux sleep; manual sleep remains separate."""
from datetime import timedelta
from scene_lighting import local_now,lighting_state

def bedtime_window(options, lighting, now=None):
    """Night runs from the shared bedtime to sunrise (06:00 fallback)."""
    now = local_now(lighting, now)
    hour = now.hour + now.minute/60 + now.second/3600
    h, m = map(int, options.get('bedtime', '22:00').split(':'))
    bed = h + m/60
    sunrise = lighting_state(lighting, now)['sunrise']
    sunrise = 6 if sunrise is None else sunrise
    return bed <= hour < sunrise if bed < sunrise else hour >= bed or hour < sunrise

def evening_awake(options,lighting,now=None):
    if not options.get('evening_awake_enabled'):return False
    now=local_now(lighting,now);hour=now.hour+now.minute/60+now.second/3600
    h,m=map(int,options.get('bedtime','22:00').split(':'));bed=h+m/60
    sunset=lighting_state(lighting,now)['sunset']
    if sunset is not None and sunset<=hour and (bed>sunset and hour<bed or bed<=sunset):return True
    if hour<bed:
        yesterday=lighting_state(lighting,now-timedelta(days=1))['sunset']
        return yesterday is not None and bed<=yesterday
    return False
