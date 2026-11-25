"""Shared solar lighting. No network calls or geometry/asset edits."""
from datetime import datetime
from functools import lru_cache
from calendar import isleap
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@lru_cache(maxsize=32)
def solar_hours(date, latitude, longitude, offset):
    # Fractional-year approximation for equation of time and solar declination.
    # https://gml.noaa.gov/grad/solcalc/solareqns.PDF
    gamma = 2*math.pi/(366 if isleap(date.year) else 365)*(date.timetuple().tm_yday-1)
    equation = 229.18*(.000075+.001868*math.cos(gamma)-.032077*math.sin(gamma)
                       -.014615*math.cos(2*gamma)-.040849*math.sin(2*gamma))
    declination = (.006918-.399912*math.cos(gamma)+.070257*math.sin(gamma)
                   -.006758*math.cos(2*gamma)+.000907*math.sin(2*gamma)
                   -.002697*math.cos(3*gamma)+.00148*math.sin(3*gamma))
    lat = math.radians(latitude)
    cosine = (math.cos(math.radians(90.833))/(math.cos(lat)*math.cos(declination))
              -math.tan(lat)*math.tan(declination))
    if cosine > 1:
        return None, None, 'night'
    if cosine < -1:
        return None, None, 'day'
    angle = math.degrees(math.acos(cosine))
    noon = (720-4*longitude-equation)/60+offset
    return noon-angle/15, noon+angle/15, None


def validate_lighting(settings):
    if not isinstance(settings, dict):
        raise ValueError('Day/night settings must be an object')
    for name, default, low, high in [('latitude', -27.47, -90, 90), ('longitude', 153.03, -180, 180)]:
        value = settings.get(name, default)
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(name.capitalize() + ' must be a number') from None
        if isinstance(value, bool) or not math.isfinite(number) or not low <= number <= high:
            raise ValueError(name.capitalize() + f' must be between {low} and {high}')
    timezone = settings.get('timezone', '')
    if not isinstance(timezone, str):
        raise ValueError('Timezone must be an IANA name, such as Australia/Brisbane')
    if timezone:
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Unknown timezone. Use an IANA name, such as Australia/Brisbane') from None


def local_now(settings, now=None):
    now = datetime.now().astimezone() if now is None else now.astimezone() if now.tzinfo is None else now
    return now.astimezone(ZoneInfo(settings['timezone'])) if settings.get('timezone') else now


def lighting_details(settings=None, now=None):
    settings = settings or {}
    validate_lighting(settings)
    now = local_now(settings, now)
    return dict(lighting_state(settings, now), local_time=now.isoformat(),
                timezone=settings.get('timezone') or now.tzname(),
                latitude=float(settings.get('latitude', -27.47)), longitude=float(settings.get('longitude', 153.03)))


def lighting_state(settings=None, now=None):
    settings = settings or {}
    now = local_now(settings, now)
    offset = now.utcoffset().total_seconds()/3600
    rise, setting, polar = solar_hours(now.date(), float(settings.get('latitude',-27.47)),
                                      float(settings.get('longitude',153.03)), offset)
    hour = now.hour+now.minute/60+now.second/3600
    if polar:
        return dict(night=1.0 if polar=='night' else 0.0, twilight=0.0, sunrise=None, sunset=None)
    span = .5  # One hour blend centred on each solar event.
    dawn = max(0.0,min(1.0,(hour-(rise-span))/(2*span)))
    dusk = max(0.0,min(1.0,(hour-(setting-span))/(2*span)))
    night = 1-dawn+dusk
    twilight = max(0,1-abs(hour-rise)/span,1-abs(hour-setting)/span)
    return dict(night=max(0,min(1,night)),twilight=twilight,sunrise=rise,sunset=setting)
