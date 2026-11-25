"""Once-per-local-morning radar greeting; uses cached data, never polls producers."""
import json
import math
import os
import re
import time
from pathlib import Path
from scene_lighting import local_now


def settings(value=None):
    result = dict(enabled=False, start='06:00', end='21:30', fuel_app_id='')
    result.update(value or {})
    if type(result['enabled']) is not bool:
        raise ValueError('Morning greeting enabled must be true or false')
    for key in ('start', 'end'):
        if not isinstance(result[key], str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', result[key]):
            raise ValueError('Morning greeting times must use HH:MM')
    if result['start'] >= result['end']:
        raise ValueError('Morning greeting start must be before its cutoff')
    if 'sections' in result:
        if not isinstance(result['sections'], list) or len(result['sections']) > 32:
            raise ValueError('Morning greeting sections must be a list of at most 32 applications')
        for section in result['sections']:
            if not isinstance(section,dict) or not isinstance(section.get('app_id'),str) or not isinstance(section.get('event','heartbeat'),str):
                raise ValueError('Each greeting section needs an application and event')
            if not isinstance(section.get('field','summary'),str) or len(section.get('field','summary')) > 100:
                raise ValueError('Greeting field must be a JSON dot path')
    return result


class MorningGreeting:
    def __init__(self, path):
        self.path = Path(path)
        try:
            self.state = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(self.state, dict): self.state = {}
        except (OSError, ValueError):
            self.state = {}
        self.present_since = None
        self.frame = None

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.state), encoding='utf-8')
        temp.replace(self.path)

    def slept(self, now):
        self.state['slept_at'] = now.timestamp()
        self.present_since = self.frame = None
        self.save()

    def ready(self, options, now, radar, monotonic, blocked=False):
        options = settings(options)
        current = now.strftime('%H:%M')
        age = now.timestamp()-self.state.get('slept_at', 0)
        eligible = (options['enabled'] and options['start'] <= current < options['end']
                    and 0 <= age <= 36*3600 and self.state.get('greeted_date') != now.date().isoformat())
        fresh = radar.get('state') == 'receiving' and 0 <= monotonic-radar.get('_monotonic_at', -1e9) < 1
        if not eligible or blocked or not fresh or not radar.get('targets'):
            self.present_since = self.frame = None
            return False
        frame = radar.get('last_frame')
        if frame is None or frame == self.frame: return False
        self.frame = frame
        if self.present_since is None: self.present_since = monotonic
        return monotonic-self.present_since >= 1

    def greeted(self, now):
        self.state.update(greeted_date=now.date().isoformat(), slept_at=0)
        self.save()


def fuel_message(app, options, now):
    greeting = 'Good morning!\n'+now.strftime('%a %d %b')
    source = next((a for a in app.apps if a.get('id') == options.get('fuel_app_id')), None) if options.get('fuel_app_id') else next((a for a in app.apps if a.get('adapter') == 'fuel_tracker'), None)
    if not source: return greeting+'\nFuel: no integration selected.'
    telemetry = app.app_telemetry.get(source['id'], {})
    receipt = telemetry.get('received_events', {}).get('heartbeat', {})
    data = receipt.get('data', {})
    price = data.get('price')
    if type(price) not in (int, float) or not math.isfinite(price): return greeting+'\nFuel: awaiting a price.'
    fuel = str(data.get('fuel_type') or 'fuel').upper()
    station = str(data.get('station') or 'nearest reported station')
    text = f'\n{fuel}: {price:.1f}¢/L\n{station}'
    # Price refresh time is distinct from the heartbeat receipt time.
    cached = data.get('cached_at')
    if isinstance(cached, (int, float)) and math.isfinite(cached):
        age = max(0, int((now.timestamp()-cached)/60))
        text += f'\nPrice cache: {age} min ago'
    else: text += '\nCached price; refresh time unavailable'
    if data.get('status') in ('offline', 'error', 'warning') or data.get('refresh_error'):
        text += '\nFuel update delayed'
    return greeting+text


def message(app, options, now):
    if 'sections' not in options: return fuel_message(app,options,now)
    parts = ['Good morning!', now.strftime('%a %d %b')]
    for section in options['sections']:
        source = next((a for a in app.apps if a.get('id') == section['app_id']),None)
        if not source: continue
        if source.get('adapter') == 'fuel_tracker' and section.get('field','summary') == 'summary':
            parts.append(fuel_message(app,dict(options,fuel_app_id=source['id']),now).split('\n',2)[-1]); continue
        telemetry = app.app_telemetry.get(source['id'],{})
        req_event = section.get('event')
        receipt = telemetry.get('received_events',{}).get(req_event, {}) if req_event else {}
        if not receipt:
            receipt = telemetry.get('received_events',{}).get('forecast_updated',{}) or telemetry.get('received_events',{}).get('heartbeat',{})
        data = receipt.get('data') or telemetry.get('data',{})
        value = data
        for key in section.get('field','summary').split('.'):
            value = value.get(key) if isinstance(value,dict) else None
        label = section.get('label') or source.get('name') or source['id']
        text = str(value)[:350] if value is not None and not isinstance(value,(dict,list)) else (telemetry.get('summary') or 'Awaiting data')
        if source.get('adapter') == 'weather':
            weather_time = data.get('time') or telemetry.get('data', {}).get('time')
            if weather_time and weather_time != now.date().isoformat():
                text = 'Forecast for today unavailable'
            elif telemetry.get('summary'):
                text = telemetry.get('summary')
        if telemetry.get('status') in ('warning','offline','error'): text += ' (update delayed)'
        cached = data.get('cached_at',receipt.get('last_seen'))
        if isinstance(cached,(int,float)) and now.timestamp()-cached > data.get('ttl_seconds',telemetry.get('ttl_seconds',3600)):
            text += ' (cached; awaiting refresh)'
        parts.append(label+': '+text)
    return '\n'.join(parts)


def policy_for(app):
    if not hasattr(app, 'morning_greeting'):
        app.morning_greeting = MorningGreeting(app._morning_state_path())
    return app.morning_greeting


def build_spoken_commentary(app, now):
    """
    Build concise, complimentary spoken commentary (15-20 words max):
    - Good morning / afternoon / evening / day depending on time of day
    - Weather: "The weather is a top of X with rain" / "and sunny" / "and overcast"
    - Fuel: "Fuel is at Y per litre"
    - Calendar: "You have nothing on" / "You have X events today" / "No events until tomorrow" / "X events left this week"
    - Final item prefixed with "And" for smooth conversational sentence flow
    """
    hr = now.hour
    if 5 <= hr < 12:
        greeting = "Good morning!"
    elif 12 <= hr < 17:
        greeting = "Good afternoon!"
    elif 17 <= hr < 21:
        greeting = "Good evening!"
    else:
        greeting = "Good day!"
        
    items = []
    
    # Weather: Extreme / summary only
    weather_tele = app.app_telemetry.get('deskpal_weather', {})
    if weather_tele:
        w_data = weather_tele.get('data') or weather_tele.get('received_events', {}).get('forecast_updated', {}).get('data', {})
        if w_data:
            max_temp = w_data.get('temperature_2m_max') or w_data.get('day_temp')
            if max_temp is not None:
                top_str = f"The weather is a top of {round(float(max_temp))}"
                precip_prob = w_data.get('precipitation_probability_max', 0)
                cond = str(w_data.get('day_condition') or w_data.get('progression', {}).get('day', {}).get('condition') or '').lower()
                lbl = str(w_data.get('progression', {}).get('day', {}).get('label') or '').lower()
                
                if precip_prob >= 40 or any(k in cond or k in lbl for k in ['rain', 'shower', 'storm', 'drizzle', 'thunder']):
                    cond_str = "with rain"
                elif any(k in cond or k in lbl for k in ['sun', 'clear']):
                    cond_str = "and sunny"
                elif any(k in cond or k in lbl for k in ['cloud', 'overcast']):
                    cond_str = "and overcast"
                else:
                    cond_str = "with rain" if precip_prob >= 30 else "and partly cloudy"
                    
                items.append(f"{top_str} {cond_str}.")
                
    # Fuel: "Fuel is at Y per litre"
    fuel_tele = app.app_telemetry.get('fuel_tracker', {})
    if fuel_tele:
        f_data = fuel_tele.get('data') or fuel_tele.get('received_events', {}).get('heartbeat', {}).get('data', {})
        if f_data:
            price = f_data.get('price')
            if price is None and isinstance(f_data.get('cheapest_station'), dict):
                price = f_data['cheapest_station'].get('price_cents')
            if price is not None and isinstance(price, (int, float)):
                p_str = f"{price:.1f}" if price % 1 != 0 else f"{int(price)}"
                items.append(f"Fuel is at {p_str} cents per litre.")
                
    # Calendar: "You have nothing on" / "You have X events today" / "No events until tomorrow" / "X events left this week"
    cal_tele = app.app_telemetry.get('calendar', {})
    cal_data = cal_tele.get('data') or cal_tele.get('received_events', {}).get('heartbeat', {}).get('data', {})
    if cal_data and cal_data.get('configured'):
        events_today = cal_data.get('events_today', [])
        count = len(events_today)
        if count > 0:
            items.append(f"You have {count} event{'s' if count != 1 else ''} today.")
        else:
            next_ev = cal_data.get('next_event')
            days_ahead = next_ev.get('days_ahead') if next_ev else None
            if days_ahead == 1:
                items.append("No events until tomorrow.")
            else:
                upcoming = cal_data.get('upcoming_events', [])
                today_weekday = now.weekday()
                days_left = 6 - today_weekday
                this_week = [ev for ev in upcoming if ev.get('days_ahead', 99) <= days_left]
                if not this_week:
                    items.append("You have nothing on.")
                else:
                    items.append(f"{len(this_week)} event{'s' if len(this_week) != 1 else ''} left this week.")
                    
    # Flow smoothly as a conversational sentence by prepending 'And' to the last item
    if len(items) >= 2:
        last = items[-1]
        items[-1] = f"And {last[0].lower() + last[1:]}"

    assembled = f"{greeting} {' '.join(items)}".strip()
    try:
        from voice_command_router import sanitize_for_speech
        return sanitize_for_speech(assembled)
    except Exception:
        return assembled


def prebake_morning_commentary(app, now):
    """Pre-synthesize morning greeting speech in background so it plays with zero delay upon radar arrival."""
    try:
        from speech_output import output_for
        speech_out = output_for(app)
        if not speech_out: return
        cfg_path = os.path.join(os.path.dirname(getattr(app, 'config_path', 'config/room_config.json')), 'ai_settings.json')
        if not os.path.exists(cfg_path):
            for alt in ['/home/admin/config/ai_settings.json', 'config/ai_settings.json']:
                if os.path.exists(alt):
                    cfg_path = alt
                    break
        hw_spk = getattr(app, 'hardware_monitor', None)
        spk_cfg = hw_spk.config.get('speaker', {}) if hw_spk else {'enabled': True}
        spoken_commentary = build_spoken_commentary(app, now)
        if spoken_commentary:
            speech_out.prebake(spoken_commentary, cfg_path, spk_cfg, source='morning_greeting')
    except Exception:
        pass


def update(app, radar, calibrating=False):
    options = settings(app.cfg.get('morning_greeting'))
    now = local_now(app.cfg.get('lighting', {}))
    policy = policy_for(app)
    blocked = bool(calibrating or app.edit_mode or getattr(app, 'local_preview', False)
                   or app.active_popup_modal or app.pending_popup_modal
                   or getattr(app, 'show_shutdown_modal', False) or getattr(app, 'tv_viewer', None) or getattr(app, 'active_game_overlay', None))

    # Pre-bake voice commentary on morning wake / light trigger!
    current = now.strftime('%H:%M')
    age = now.timestamp() - policy.state.get('slept_at', 0)
    eligible = (options['enabled'] and options['start'] <= current < options['end']
                and 0 <= age <= 36*3600 and policy.state.get('greeted_date') != now.date().isoformat())
    
    if eligible and not blocked:
        sleep_status = getattr(app, 'sleep_policy_status', {})
        if not sleep_status.get('bedtime_active'):
            hw = getattr(app, 'hardware_monitor', None)
            is_dark = False
            if hw and hasattr(hw, 'i2c') and hasattr(hw, 'config'):
                lux = getattr(hw, 'i2c', {}).get('light', {}).get('lux')
                thresh = getattr(hw, 'config', {}).get('light', {}).get('sleep_below_lux', 0.1)
                wake_margin = getattr(hw, 'config', {}).get('light', {}).get('wake_margin_lux', 0.2)
                if lux is not None and lux < (thresh + wake_margin):
                    is_dark = True
            if not is_dark:
                prebake_morning_commentary(app, now)

    if not policy.ready(options, now, radar, time.monotonic(), blocked): return False

    # Never wake or trigger greeting during bedtime
    sleep_status = getattr(app, 'sleep_policy_status', {})
    if sleep_status.get('bedtime_active'):
        return False

    # Never wake or trigger greeting if room is dark (lights off)
    hw = getattr(app, 'hardware_monitor', None)
    if hw and hasattr(hw, 'i2c') and hasattr(hw, 'config'):
        lux = getattr(hw, 'i2c', {}).get('light', {}).get('lux')
        thresh = getattr(hw, 'config', {}).get('light', {}).get('sleep_below_lux', 0.1)
        wake_margin = getattr(hw, 'config', {}).get('light', {}).get('wake_margin_lux', 0.2)
        if lux is not None and lux < (thresh + wake_margin):
            return False

    # If device is sleeping due to darkness, do not wake for greeting
    if getattr(app, 'is_sleeping', False):
        if sleep_status.get('sleeping'):
            return False
        app.wake_from_standby(source='morning')
        if app.is_sleeping: return False
    if hasattr(app, 'light_sleep_policy'): app.light_sleep_policy.manual(time.monotonic())
    summary = message(app, options, now)
    cutoff = now.replace(hour=int(options['end'][:2]), minute=int(options['end'][3:]), second=0, microsecond=0).timestamp()
    hello_role = 'wave_hello' if 'wave_hello' in getattr(app, 'character_sequences', {}) else 'idle'
    weather_tele = app.app_telemetry.get('deskpal_weather', {})
    progression = weather_tele.get('data', {}).get('progression')
    action = dict(id='morning_greeting', animation=hello_role, target_mode='current',
                  display_mode='popup_modal', layout='morning', speech='{summary}', duration_seconds=180,
                  hide_label=True, _hold_popup_until_dismissed=True, _expires_at=cutoff,
                  progression=progression)

    hr = now.hour
    if 5 <= hr < 12:
        title_greeting = "Good morning"
    elif 12 <= hr < 17:
        title_greeting = "Good afternoon"
    elif 17 <= hr < 21:
        title_greeting = "Good evening"
    else:
        title_greeting = "Good day"

    modal_data = {
        "title": title_greeting.upper(),
        "summary": summary,
        "layout": "morning",
        "color": (255, 175, 40),
        "progression": progression,
        "date_str": now.strftime("%A, %d %b"),
        "timestamp": time.strftime("%I:%M %p"),
        "expires_at": time.monotonic() + 180,
        "hold_until_dismissed": True
    }
    app.active_popup_modal = modal_data
    app.pending_popup_modal = None
    app.wander_timer = 180.0

    if getattr(app, 'active_rest_role', None) and not getattr(app, 'rest_transition', None):
        app.begin_rest_transition(app.active_rest_role, 'exit')
        app.target_animation = hello_role
    elif not getattr(app, 'rest_transition', None):
        app.current_anim = hello_role
        app.target_animation = hello_role

    queue = getattr(app, 'activity_queue', None)
    if queue:
        with queue.lock:
            if queue.active and not queue.active[0].get('_button_action'):
                queue.active = None
                queue.arrived = queue.started = queue.dwell = None

    # Speak concise complementary commentary via Piper TTS
    try:
        from speech_output import output_for
        speech_out = output_for(app)
        if speech_out:
            cfg_path = os.path.join(os.path.dirname(getattr(app, 'config_path', 'config/room_config.json')), 'ai_settings.json')
            if not os.path.exists(cfg_path):
                for alt in ['/home/admin/config/ai_settings.json', 'config/ai_settings.json']:
                    if os.path.exists(alt):
                        cfg_path = alt
                        break
            hw_spk = getattr(app, 'hardware_monitor', None)
            spk_cfg = hw_spk.config.get('speaker', {}) if hw_spk else {'enabled': True}
            spoken_commentary = build_spoken_commentary(app, now)
            if spoken_commentary:
                speech_out.speak(spoken_commentary, cfg_path, spk_cfg, source='morning_greeting')
    except Exception as e:
        app.audit_activity('morning_greeting_speech_failed', error=str(e)[:100])

    policy.greeted(now)
    app.audit_activity('morning_greeting_displayed', source_event='morning_greeting')
    return True
