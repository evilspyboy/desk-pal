"""
Voice Command Dispatcher for Desk-Pal with 3-tier cascade:
1. Core commands & App-configured voice triggers (Instant <5ms)
2. Remote PC Ollama (OpenAI-compatible /chat/completions)
3. On-Device Qwen 2.5 0.5B fallback (Offline on Pi)
"""
import datetime
import json
import logging
import os
import re
import subprocess
import threading
import time
import urllib.request

logger = logging.getLogger("deskpal.voice_router")

# Fallback default trigger phrases for known built-in apps
DEFAULT_APP_TRIGGERS = {
    "fuel_tracker": ["fuel", "petrol", "gas prices", "cheapest fuel", "fuel price", "gas price", "whats the fuel", "what's the fuel"],
    "store_monitor": ["store", "order", "orders", "sales", "how's the store", "new orders", "paid order", "any order", "any orders", "store orders", "shop"],
    "bmcbf": ["pop culture", "movies", "games", "bmcbf", "promotions", "emails", "comic", "comics", "pop culture update"],
    "travel_radar": ["travel", "flights", "flight deals", "cheap flights", "airfare", "vacation", "trip", "trips"],
    "deskpal_weather": ["weather", "forecast", "temperature", "rain", "how's the weather", "watch the weather", "what's the weather", "whats the weather"],
    "wellness_check": ["wellness", "hydration", "water", "stretch", "posture", "drink water", "health check", "stretch break"]
}

def sanitize_for_speech(text):
    """Clean up abbreviations, symbols, and formatting for natural TTS speaking."""
    if not text:
        return ""
    s = str(text)
    # Currency and fuel pricing
    s = re.sub(r'¢/L|Â¢/L|c/L', ' cents per litre', s, flags=re.I)
    s = re.sub(r'¢|Â¢', ' cents', s)
    s = re.sub(r'\$(\d+(?:\.\d{1,2})?)', r'\1 dollars', s)
    # Weather ranges & units
    s = re.sub(r'(\d+(?:\.\d+)?)\s*[–\-]\s*(\d+(?:\.\d+)?)\s*°C', r'\1 to \2 degrees Celsius', s)
    s = re.sub(r'(\d+(?:\.\d+)?)\s*°C', r'\1 degrees Celsius', s)
    s = re.sub(r'(\d+(?:\.\d+)?)\s*km/h', r'\1 kilometres per hour', s, flags=re.I)
    s = re.sub(r'(\d+(?:\.\d+)?)\s*mm\b', r'\1 millimetres', s, flags=re.I)
    s = re.sub(r'(\d+)\s*%', r'\1 percent', s)
    s = s.replace('·', ',')
    # Units
    s = re.sub(r'(\d+)\s*km\b', r'\1 kilometres', s, flags=re.I)
    s = re.sub(r'(\d+)\s*min\b', r'\1 minutes', s, flags=re.I)
    s = re.sub(r'(\d+)\s*h\b', r'\1 hours', s, flags=re.I)
    # Fuel types
    s = re.sub(r'\bU98\b', 'Unleaded 98', s)
    s = re.sub(r'\bU95\b', 'Unleaded 95', s)
    s = re.sub(r'\bU91\b', 'Unleaded 91', s)
    # Date expansions
    s = re.sub(r'\bMon\b', 'Monday', s)
    s = re.sub(r'\bTue\b', 'Tuesday', s)
    s = re.sub(r'\bWed\b', 'Wednesday', s)
    s = re.sub(r'\bThu\b', 'Thursday', s)
    s = re.sub(r'\bFri\b', 'Friday', s)
    s = re.sub(r'\bSat\b', 'Saturday', s)
    s = re.sub(r'\bSun\b', 'Sunday', s)
    s = re.sub(r'\bJan\b', 'January', s)
    s = re.sub(r'\bFeb\b', 'February', s)
    s = re.sub(r'\bMar\b', 'March', s)
    s = re.sub(r'\bApr\b', 'April', s)
    s = re.sub(r'\bJun\b', 'June', s)
    s = re.sub(r'\bJul\b', 'July', s)
    s = re.sub(r'\bAug\b', 'August', s)
    s = re.sub(r'\bSep\b', 'September', s)
    s = re.sub(r'\bOct\b', 'October', s)
    s = re.sub(r'\bNov\b', 'November', s)
    s = re.sub(r'\bDec\b', 'December', s)
    # Clean markdown
    s = re.sub(r'\*\*([^*]+)\*\*', r'\1', s)
    s = re.sub(r'\*([^*]+)\*', r'\1', s)
    s = re.sub(r'#+\s*', '', s)
    s = re.sub(r'`([^`]+)`', r'\1', s)
    # Clean extra whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def _get_app_triggers(app_cfg):
    """Retrieve list of trigger phrases for an application configuration."""
    triggers = app_cfg.get("voice_triggers")
    if triggers is None:
        triggers = DEFAULT_APP_TRIGGERS.get(app_cfg.get("id"), [])
    if isinstance(triggers, str):
        return [t.strip().lower() for t in triggers.split(",") if t.strip()]
    elif isinstance(triggers, list):
        return [str(t).strip().lower() for t in triggers if str(t).strip()]
    return []

INVESTIGATIVE_APPS = {
    "deskpal_weather": {
        "intro": "Let me check the weather outside!",
        "title": "WEATHER",
        "color": (120, 190, 240),
        "spot_keywords": ["window", "ocean_outlook", "outlook", "balcony", "ponder", "inspect"],
        "default_anim": "window_look",
        "default_facing": "right"
    },
    "fuel_tracker": {
        "intro": "Let me check the fuel prices!",
        "title": "FUEL TRACKER",
        "color": (106, 190, 48),
        "spot_keywords": ["globe", "noticeboard", "tv_cabinent", "counter", "inspect"],
        "default_anim": "inspect",
        "default_facing": "left"
    },
    "store_monitor": {
        "intro": "Let me check recent store orders!",
        "title": "STORE MONITOR",
        "color": (100, 110, 130),
        "spot_keywords": ["computer_desk", "notebook_write", "desk", "computer", "typing", "inspect"],
        "default_anim": "typing",
        "default_facing": "left"
    },
    "travel_radar": {
        "intro": "Let me check the flight radar!",
        "title": "FLIGHT RADAR",
        "color": (75, 105, 204),
        "spot_keywords": ["noticeboard", "tiki_bar", "window", "inspect"],
        "default_anim": "inspect",
        "default_facing": "right"
    },
    "bmcbf": {
        "intro": "Let me check pop culture updates!",
        "title": "POP CULTURE",
        "color": (217, 160, 102),
        "spot_keywords": ["mailbox", "collectibles_inspect", "top_shelf_planet", "inspect"],
        "default_anim": "mailbox_interact",
        "default_facing": "right"
    }
}

def _find_investigative_spot(app, app_id):
    """Find the best interaction spot in the current scene for the investigative check."""
    active_scene = app.cfg.get("active_scene", "cozy_study")
    scenes_dict = app.cfg.get("scenes", {})
    scene_cfg = scenes_dict.get(active_scene, {})
    spots = scene_cfg.get("interaction_spots", [])
    if not spots:
        spots = getattr(app, "interaction_spots", []) or app.cfg.get("interaction_spots", [])

    info = INVESTIGATIVE_APPS.get(app_id, {})
    keywords = info.get("spot_keywords", ["inspect", "desk", "window"])

    for kw in keywords:
        for s in spots:
            sid = (s.get("id") or "").lower()
            sanim = (s.get("animation") or "").lower()
            sanims = [str(a).lower() for a in s.get("animations", [])]
            sname = (s.get("name") or "").lower()
            if kw in sid or kw in sanim or kw in sname or any(kw in a for a in sanims):
                return s

    apps_list = getattr(app, "apps", []) or app.cfg.get("apps", [])
    a_cfg = next((a for a in apps_list if a.get("id") == app_id), None)
    if a_cfg:
        for act in a_cfg.get("actions", []):
            sp_id = act.get("spot_id")
            if sp_id:
                s = next((s for s in spots if s.get("id") == sp_id), None)
                if s:
                    return s

    return spots[0] if spots else None

def trigger_investigative_check(app, app_id, app_name, raw_summary, tele):
    """
    Executes an investigative voice query:
    1. Sprite stands up and faces user.
    2. Speaks immediate short acknowledgment ("Let me check the weather outside!").
    3. Physically walks to the inspection prop in the current room.
    4. Upon arrival, displays modal card and speaks the detailed findings.
    """
    if hasattr(app, "stand_and_face_user"):
        app.stand_and_face_user()

    info = INVESTIGATIVE_APPS.get(app_id, {
        "intro": f"Let me check {app_name}!",
        "title": app_name.upper(),
        "color": (120, 190, 240),
        "default_anim": "inspect",
        "default_facing": "right"
    })

    intro_phrase = info["intro"]
    title = info["title"]
    col = info["color"]
    ticker = tele.get("ticker", [])
    clean_findings = sanitize_for_speech(raw_summary)
    arrival_speech = f"{title.title()}: {clean_findings}"

    modal_data = {
        'title': title,
        'summary': raw_summary,
        'ticker': ticker,
        'color': col,
        'timestamp': time.strftime('%I:%M %p'),
        'expires_at': time.monotonic() + 25.0
    }

    spot = _find_investigative_spot(app, app_id)

    if spot:
        tx = spot.get("x", getattr(app, "char_x", 0))
        ty = spot.get("y", getattr(app, "char_y", 0))
        facing_val = spot.get("facing", info.get("default_facing", "right"))
        facing_left = (str(facing_val).lower() == "left")
        anim = spot.get("animation", info.get("default_anim", "inspect"))
        spot_id = spot.get("id")

        char_x = getattr(app, "char_x", tx)
        char_y = getattr(app, "char_y", ty)
        if not isinstance(char_x, (int, float)) or isinstance(char_x, bool):
            char_x = 0.0
        if not isinstance(char_y, (int, float)) or isinstance(char_y, bool):
            char_y = 0.0
        if not isinstance(tx, (int, float)) or isinstance(tx, bool):
            tx = 0.0
        if not isinstance(ty, (int, float)) or isinstance(ty, bool):
            ty = 0.0
        dist = float(((tx - char_x)**2 + (ty - char_y)**2)**0.5)

        if dist > 14.0:
            # Sprite physically walks over to the prop
            app.pending_popup_modal = modal_data
            app.active_popup_modal = None
            app.pending_arrival_speech = arrival_speech
            app.target_x, app.target_y = tx, ty
            app._route_goal = None
            app.target_animation = anim
            app.target_spot_id = spot_id
            app.target_facing_left = facing_left
            app.current_anim = "walk"
            app.idle_waiting = False
            app.is_inspecting = False
            app.status_msg = f"Checking {spot.get('name', app_name)}..."
            return True, intro_phrase, app_id

    # If already at the spot (or no spot exists in room)
    app.active_popup_modal = modal_data
    app.pending_popup_modal = None
    if spot:
        app.target_animation = spot.get("animation", info.get("default_anim", "inspect"))
        app.current_anim = app.target_animation
        app.facing_left = (str(spot.get("facing", "right")).lower() == "left")
        app.is_inspecting = (app.current_anim == "inspect")
    return True, f"{intro_phrase} {arrival_speech}", app_id

def _display_app_feedback(app, app_id, app_name, raw_summary, tele):
    """Trigger application switch, queued action, or active popup modal card."""
    apps_list = getattr(app, "apps", []) or app.cfg.get("apps", [])
    a = next((item for item in apps_list if item.get("id") == app_id), None)
    
    if a and a.get("switch_id") and hasattr(app, "on_switch_press"):
        try:
            app.on_switch_press(a.get("switch_id"))
            return
        except Exception as e:
            logger.debug(f"Failed to trigger switch {a.get('switch_id')}: {e}")
            
    if a and hasattr(app, "queue_action"):
        actions = a.get("actions", [])
        act = next((act for act in actions if act.get("is_primary") or act.get("id") == "status_check"), actions[0] if actions else None)
        if act and act.get("display_mode") != "none":
            col = tuple(a.get("color", [0, 229, 255]))
            ticker = tele.get("ticker", [])
            app.queue_action(act, app_name, col, raw_summary, ticker, source_event='voice', priority=True)
            return

    if getattr(app, 'is_sleeping', False) or getattr(app, 'active_rest_role', None):
        if hasattr(app, 'wake_from_standby'):
            app.wake_from_standby(source='voice')

    col = tuple(a.get("color", [120, 190, 240])) if a else (120, 190, 240)
    ticker = tele.get("ticker", [])
    title = app_name.upper()
    if app_id == "deskpal_weather":
        title = "WEATHER"
    setattr(app, 'active_popup_modal', {
        'title': title,
        'summary': raw_summary,
        'ticker': ticker,
        'color': col,
        'timestamp': time.strftime('%I:%M %p'),
        'expires_at': time.monotonic() + 15.0
    })

def match_core_and_app_command(clean_text, app):
    """
    Tier 1: Check instant core actions and app-configured voice phrases.
    Returns (matched: bool, reply_speech: str or None, action_name: str or None)
    """
    # 1. Sleep
    if any(p in clean_text for p in ("go to sleep", "good night", "goodnight", "turn off screen", "sleep now", "standby")):
        if hasattr(app, "enter_standby"):
            app.enter_standby()
        return True, "Going to sleep now. Goodnight!", "sleep"

    # 2. Wake
    if any(p in clean_text for p in ("wake up", "rise and shine", "are you awake", "wake now")):
        if hasattr(app, "wake_from_standby"):
            app.wake_from_standby()
        return True, "I'm awake and ready!", "wake"

    # 3. Time
    if any(p in clean_text for p in ("what time is it", "what's the time", "tell me the time", "current time", "clock")):
        now_str = datetime.datetime.now().strftime("%I:%M %p").lstrip("0")
        return True, f"It's {now_str}.", "time"

    # 4. Sit / Chair
    if any(p in clean_text for p in ("sit down", "take a seat", "sit on the chair", "sit on chair", "relax on the chair", "sit on the couch", "take a rest")):
        spots = getattr(app, "interaction_spots", [])
        spot = next((s for s in spots if any(k in (s.get("id") or "").lower() for k in ("chair", "rug", "hearth"))), None)
        if spot and hasattr(app, "target_spot_id"):
            app.target_spot_id = spot.get("id")
            app.target_animation = "resting_stretch" if "rug" in spot.get("id", "") else "idle"
            app.target_x, app.target_y = spot.get("x", app.char_x), spot.get("y", app.char_y)
            app.idle_waiting = True
        return True, "Taking a rest on the chair!", "sit"

    # 5. Stand / Wander
    if any(p in clean_text for p in ("stand up", "walk around", "start wandering", "wander around", "explore")):
        if hasattr(app, "idle_waiting"):
            app.idle_waiting = False
            app.target_animation = None
            app.target_spot_id = None
        if hasattr(app, "wander_timer"):
            app.wander_timer = 0
        return True, "On my feet!", "stand"

    # 6. Replay / Repeat last speech
    if any(p in clean_text for p in (
        "repeat that", "what did you say", "say that again", "replay that",
        "replay last speech", "repeat last speech", "say again", "pardon",
        "what was that", "can you repeat that", "repeat", "replay", "what you said"
    )):
        from speech_output import output_for
        out = output_for(app)
        last = out.get_last_spoken(max_age_seconds=300)
        if last:
            return True, f"I said: {last['text']}", "replay"
        else:
            return True, "I haven't said anything in the last five minutes.", "replay"

    # 7. App-configured triggers
    apps_list = getattr(app, "apps", []) or app.cfg.get("apps", [])
    known_apps = list(apps_list)
    existing_ids = set(a.get("id") for a in apps_list)
    for def_id, triggers in DEFAULT_APP_TRIGGERS.items():
        if def_id not in existing_ids:
            name = def_id.replace("deskpal_", "").replace("_", " ").title()
            known_apps.append({"id": def_id, "name": name, "voice_triggers": triggers})

    all_triggers = []
    for a in known_apps:
        app_id = a.get("id")
        app_name = a.get("name", app_id)
        for t in _get_app_triggers(a):
            all_triggers.append((t, a, app_id, app_name))
    all_triggers.sort(key=lambda x: len(x[0]), reverse=True)

    for trig, a, app_id, app_name in all_triggers:
        if trig in clean_text:
            tele = getattr(app, "app_telemetry", {}).get(app_id, {})
            from integration_state import summary_for
            raw_summary = tele.get("summary") or summary_for(tele, app_name)
            if app_id in INVESTIGATIVE_APPS:
                return trigger_investigative_check(app, app_id, app_name, raw_summary, tele)
            _display_app_feedback(app, app_id, app_name, raw_summary, tele)
            speech_body = sanitize_for_speech(raw_summary)
            return True, f"{app_name}: {speech_body}", app_id

    return False, None, None

def _get_ai_settings(app):
    """Load local AI settings from ai_settings.json across standard locations."""
    paths_to_check = [
        os.path.join(os.path.dirname(getattr(app, 'config_path', 'config/room_config.json')), 'ai_settings.json'),
        os.path.expanduser('~/desk-pal/config/ai_settings.json'),
        os.path.expanduser('~/config/ai_settings.json'),
        os.path.expanduser('~/ai_settings.json'),
        'config/ai_settings.json',
        'ai_settings.json'
    ]
    for p in paths_to_check:
        try:
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
    return {}

def _parse_llm_action_and_reply(content, app):
    """Extract optional [ACTION: <name>] tag and clean spoken dialogue."""
    action = "none"
    reply = content.strip()
    match = re.search(r'\[ACTION:\s*([a-zA-Z0-9_-]+)\]', reply, flags=re.I)
    if match:
        action = match.group(1).lower()
    reply = re.sub(r'\[ACTION:[^\]]*\]', '', reply, flags=re.I).strip()
    reply = re.sub(r'\[.*?\]', '', reply).strip()
    if 'loading model' in reply.lower():
        lines = [l for l in reply.splitlines() if not any(l.strip().lower().startswith(p) for p in (
            'loading model', 'build :', 'model :', 'ftype :', 'modalities :', 'available commands:', 'main:'
        ))]
        reply = '\n'.join(lines).strip()
    
    # Execute action if supported
    if action == 'sleep' and hasattr(app, 'enter_standby'):
        app.enter_standby()
    elif action == 'wake' and hasattr(app, 'wake_from_standby'):
        app.wake_from_standby()
    elif action == 'sit':
        spots = getattr(app, "interaction_spots", [])
        spot = next((s for s in spots if any(k in (s.get("id") or "").lower() for k in ("chair", "rug", "hearth"))), None)
        if spot and hasattr(app, "target_spot_id"):
            app.target_spot_id = spot.get("id")
            app.target_animation = "resting_stretch" if "rug" in spot.get("id", "") else "idle"
            app.target_x, app.target_y = spot.get("x", app.char_x), spot.get("y", app.char_y)
            app.idle_waiting = True

    return True, sanitize_for_speech(reply), action

def query_network_llm(clean_text, app, provider_name="local"):
    """Tier 3: Query configured network LLM provider (local, openai, gemini, claude) using its OpenAI-compatible endpoint."""
    settings = _get_ai_settings(app)
    prov_cfg = settings.get('providers', {}).get(provider_name, {})
    if not prov_cfg.get('endpoint'):
        if provider_name == 'local':
            logger.debug(f"[VoiceRouter] No endpoint configured for provider '{provider_name}' in settings.")
            return False, None, None
        prov_cfg = settings.get('providers', {}).get('local', {})

    endpoint = prov_cfg.get('endpoint', '').strip()
    if not endpoint:
        logger.debug(f"[VoiceRouter] No endpoint configured for provider '{provider_name}' in settings.")
        return False, None, None

    model = prov_cfg.get('model', '').strip()
    if not model:
        logger.debug(f"[VoiceRouter] No model configured for provider '{provider_name}' in settings.")
        return False, None, None

    ep = endpoint.rstrip('/')
    base_ep = ep[:-3] if ep.endswith('/v1') else ep
    url = f"{base_ep}/v1/chat/completions"
    is_ollama = ':11434' in base_ep
    sys_prompt = (
        "You are Desk-Pal, a cheeky desk companion (like Wheatley from Portal). "
        "Reply in 1 or 2 short, spoken sentences. Never mention being an AI or language model."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": clean_text}
        ],
        "temperature": 0.7,
        "max_tokens": 50
    }
    if is_ollama:
        payload["keep_alive"] = -1
    elif provider_name == "local":
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        content = data['choices'][0]['message']['content']
        if provider_name == "local" and not is_ollama and prov_cfg.get("unload_after_call", True):
            def _unload_model(unload_base, model_id):
                try:
                    u_req = urllib.request.Request(
                        f"{unload_base}/models/unload",
                        data=json.dumps({"model": model_id}).encode('utf-8'),
                        headers={'Content-Type': 'application/json'}
                    )
                    urllib.request.urlopen(u_req, timeout=3.0).close()
                except Exception:
                    pass
            threading.Thread(target=_unload_model, args=(base_ep, model), daemon=True).start()
        return _parse_llm_action_and_reply(content, app)
    except Exception as e:
        logger.debug(f"Network LLM ({provider_name}) query failed: {e}")
        return False, None, None

def query_pc_ollama(clean_text, app):
    """Backwards-compatible alias for querying the Local LLM (PC Ollama)."""
    return query_network_llm(clean_text, app, provider_name="local")

def query_chat_fallback_tier(tier_provider, clean_text, app):
    """Query a specific fallback tier provider ('local', 'on_device', 'openai', 'gemini', 'claude')."""
    if not tier_provider or tier_provider in ("none", "disabled"):
        return False, None, None
    if tier_provider in ("on_device", "local_gguf"):
        return query_on_device_qwen(clean_text, app)
    else:
        prov_name = "local" if tier_provider in ("local", "local_llm", "external") else tier_provider
        return query_network_llm(clean_text, app, provider_name=prov_name)

def query_on_device_qwen(clean_text, app):
    """Tier 3: Query on-device Qwen 2.5 0.5B fallback on Raspberry Pi."""
    settings = _get_ai_settings(app)
    on_dev_cfg = settings.get('providers', {}).get('on_device', {})
    model_path = on_dev_cfg.get('model', '').strip() or "/home/admin/test_llm/qwen2.5-0.5b-instruct-q4_k_m.gguf"
    llama_bin = on_dev_cfg.get('endpoint', '').strip() or "/home/admin/test_llm/llama-b11706/llama-cli"
    if not (os.path.exists(model_path) and os.path.exists(llama_bin)):
        return False, None, None

    prompt = (
        f"<|im_start|>system\n"
        f"You are Desk-Pal, a cheeky desk companion. Keep reply to 1 short sentence. "
        f"Available actions: sleep, sit, wake, wander, none. "
        f"Prefix with [ACTION: <action>].<|im_end|>\n"
        f"<|im_start|>user\n{clean_text}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    env = dict(os.environ)
    bin_dir = os.path.dirname(llama_bin)
    if bin_dir:
        env['LD_LIBRARY_PATH'] = bin_dir + ':' + env.get('LD_LIBRARY_PATH', '')
    cmd = [
        llama_bin,
        "-m", model_path,
        "-p", prompt,
        "-n", "35",
        "-t", "4",
        "--single-turn",
        "--no-warmup"
    ]
    try:
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=25)
        raw_out = res.stdout or ''
        if '<|im_start|>assistant' in raw_out:
            raw_out = raw_out.split('<|im_start|>assistant', 1)[1]
        for stop_tok in ('<|im_end|>', 'Exiting...', '\n> '):
            if stop_tok in raw_out:
                raw_out = raw_out.split(stop_tok, 1)[0]
        lines = [l for l in raw_out.splitlines() if not any(l.strip().lower().startswith(p) for p in (
            'loading model', 'build :', 'model :', 'ftype :', 'modalities :', 'available commands:', 'main:'
        ))]
        cleaned_out = '\n'.join(lines).strip()
        return _parse_llm_action_and_reply(cleaned_out, app)
    except Exception as e:
        logger.debug(f"On-device Qwen inference failed: {e}")
        return False, None, None

_NEEDLE_ENGINE = None
_NEEDLE_ATTEMPTED = False

def _get_needle_engine():
    """Lazily load and cache the Cactus Needle tool calling engine with Desk-Pal tool schemas."""
    global _NEEDLE_ENGINE, _NEEDLE_ATTEMPTED
    if _NEEDLE_ENGINE is not None:
        return _NEEDLE_ENGINE
    if _NEEDLE_ATTEMPTED:
        return None
    _NEEDLE_ATTEMPTED = True

    # Ensure venv site-packages is in sys.path on Raspberry Pi if needed
    import glob, sys
    venv_sites = glob.glob(os.path.expanduser('~/.venv-deskpal-tts/lib/python*/site-packages'))
    for vs in venv_sites:
        if vs not in sys.path:
            sys.path.insert(0, vs)

    try:
        import needle
    except Exception as e:
        logger.debug(f"[VoiceRouter] Cactus needle not available: {e}")
        return None

    try:
        @needle.tool(triggers=["beach", "cozy", "garden", "switch scene", "change room", "go to scene", "travel to", "room", "scene", "patio", "deck"])
        def switch_scene(scene_name: str):
            """Switch or travel to a specific room or scene environment.

            Args:
                scene_name: Target scene name (e.g. beach, cozy, garden, deck).
            """
            return scene_name

        @needle.tool(triggers=["fuel", "petrol", "diesel", "gas", "fuel price", "petrol price", "cheapest fuel", "cheapest petrol", "gas price"])
        def check_fuel_price(fuel_type: str = "petrol"):
            """Check current fuel prices or petrol costs.

            Args:
                fuel_type: Type of fuel, such as petrol, diesel, unleaded, e10.
            """
            return fuel_type

        @needle.tool(triggers=["weather", "rain", "temperature", "forecast", "degrees", "sunny", "hot outside", "cold outside", "umbrella", "raining"])
        def check_weather():
            """Check the current weather forecast, outdoor conditions, temperature, or rain."""
            return "weather"

        @needle.tool(triggers=["flight", "flights", "travel", "plane", "trip", "holiday", "cheap flights", "vacation", "airline"])
        def check_flight_deals(destination: str = "any"):
            """Check the travel radar for cheap flights, travel deals, or holiday trips.

            Args:
                destination: Desired destination or city, or 'any'.
            """
            return destination

        @needle.tool(triggers=["store", "sales", "orders", "revenue", "shop", "ecommerce", "purchases", "new orders"])
        def check_store_sales():
            """Check store monitor sales, recent customer orders, or store activity."""
            return "store"

        @needle.tool(triggers=["pop culture", "movies", "games", "bmcbf", "promotions", "emails", "deal", "deals"])
        def check_bmcbf_updates():
            """Check pop culture updates, movies, games, promotions, and deals."""
            return "bmcbf"

        @needle.tool(triggers=["sleep", "go to sleep", "bedtime", "turn off screen", "standby", "good night", "rest screen"])
        def go_to_sleep():
            """Put Desk-Pal to sleep, enter standby mode, or turn off the screen display."""
            return "sleep"

        @needle.tool(triggers=["wake", "wake up", "rise and shine", "turn on screen", "awake"])
        def wake_up():
            """Wake Desk-Pal up from sleep or turn the screen back on."""
            return "wake"

        @needle.tool(triggers=["sit", "sit down", "take a seat", "chair", "couch", "rug", "relax"])
        def sit_down():
            """Direct Desk-Pal to walk over to the chair, couch, or rug and sit down."""
            return "sit"

        @needle.tool(triggers=["stand", "stand up", "walk", "wander", "explore", "on your feet"])
        def wander_around():
            """Direct Desk-Pal to stand up from resting and wander around the room freely."""
            return "wander"

        @needle.tool(triggers=["what time is it", "clock", "current time", "tell time"])
        def tell_current_time():
            """Speak the current time."""
            return "time"

        @needle.tool(triggers=["repeat that", "say again", "replay that", "what did you say", "pardon"])
        def repeat_last_phrase():
            """Repeat the last phrase spoken by Desk-Pal."""
            return "repeat"

        @needle.tool(triggers=["tv", "television", "turn on tv", "watch tv", "open tv", "tv viewer", "watch television"])
        def open_tv_viewer():
            """Open or turn on the interactive television viewer prop."""
            return "tv"

        tools = [
            switch_scene, check_fuel_price, check_weather, check_flight_deals,
            check_store_sales, check_bmcbf_updates, go_to_sleep, wake_up,
            sit_down, wander_around, tell_current_time, repeat_last_phrase, open_tv_viewer
        ]
        t0 = time.monotonic()
        engine = needle.Needle(tools=tools, stateless=True)
        logger.info(f"[VoiceRouter] Cactus Needle initialized in {time.monotonic() - t0:.2f}s with {len(tools)} tools.")
        _NEEDLE_ENGINE = engine
        return _NEEDLE_ENGINE
    except Exception as e:
        logger.warning(f"[VoiceRouter] Failed to initialize Cactus Needle: {e}")
        return None

def _execute_needle_tool(tool_name, args, app):
    """Execute on-device tool action determined by Cactus Needle."""
    args = args or {}
    logger.info(f"[VoiceRouter] Executing Needle tool: {tool_name}({args})")

    if tool_name == "switch_scene":
        scenes = app.cfg.get('scenes', {})
        target = (args.get("scene_name") or "").lower().strip()
        matched_sid = None
        for sid, sdata in scenes.items():
            sname = sdata.get('name', sid).lower()
            if target and (target in sname or target in sid.lower() or sid.lower() in target):
                matched_sid = sid
                break
        if matched_sid:
            app.pending_scene_destination = matched_sid
            scene_label = scenes[matched_sid].get('name', matched_sid)
            return True, f"Travelling to the {scene_label} scene!", f"scene:{matched_sid}"
        else:
            available = ", ".join(s.get('name', k) for k, s in scenes.items() if s.get('enabled', True) is not False)
            return True, f"I couldn't find a scene called '{target}'. Available scenes are: {available}.", "scene_not_found"

    elif tool_name == "check_fuel_price":
        tele = getattr(app, "app_telemetry", {}).get("fuel_tracker", {})
        from integration_state import summary_for
        raw_summary = tele.get("summary") or summary_for(tele, "Fuel Tracker")
        return trigger_investigative_check(app, "fuel_tracker", "Fuel Tracker", raw_summary, tele)

    elif tool_name == "check_weather":
        tele = getattr(app, "app_telemetry", {}).get("deskpal_weather", {})
        from integration_state import summary_for
        raw_summary = tele.get("summary") or summary_for(tele, "Weather")
        return trigger_investigative_check(app, "deskpal_weather", "Weather", raw_summary, tele)

    elif tool_name == "check_flight_deals":
        tele = getattr(app, "app_telemetry", {}).get("travel_radar", {})
        from integration_state import summary_for
        raw_summary = tele.get("summary") or summary_for(tele, "Travel Radar")
        return trigger_investigative_check(app, "travel_radar", "Travel Radar", raw_summary, tele)

    elif tool_name == "check_store_sales":
        tele = getattr(app, "app_telemetry", {}).get("store_monitor", {})
        from integration_state import summary_for
        raw_summary = tele.get("summary") or summary_for(tele, "Store Monitor")
        return trigger_investigative_check(app, "store_monitor", "Store Monitor", raw_summary, tele)

    elif tool_name == "check_bmcbf_updates":
        tele = getattr(app, "app_telemetry", {}).get("bmcbf", {})
        from integration_state import summary_for
        raw_summary = tele.get("summary") or summary_for(tele, "Pop Culture")
        return trigger_investigative_check(app, "bmcbf", "Pop Culture", raw_summary, tele)

    elif tool_name == "go_to_sleep":
        if hasattr(app, "enter_standby"):
            app.enter_standby()
        return True, "Going to sleep now. Goodnight!", "sleep"

    elif tool_name == "wake_up":
        if hasattr(app, "wake_from_standby"):
            app.wake_from_standby()
        return True, "I'm awake and ready!", "wake"

    elif tool_name == "sit_down":
        spots = getattr(app, "interaction_spots", [])
        spot = next((s for s in spots if any(k in (s.get("id") or "").lower() for k in ("chair", "rug", "hearth"))), None)
        if spot and hasattr(app, "target_spot_id"):
            app.target_spot_id = spot.get("id")
            app.target_animation = "resting_stretch" if "rug" in spot.get("id", "") else "idle"
            app.target_x, app.target_y = spot.get("x", app.char_x), spot.get("y", app.char_y)
            app.idle_waiting = True
        return True, "Taking a rest on the chair!", "sit"

    elif tool_name == "wander_around":
        if hasattr(app, "idle_waiting"):
            app.idle_waiting = False
            app.target_animation = None
            app.target_spot_id = None
        return True, "On my feet and exploring!", "stand"

    elif tool_name == "tell_current_time":
        now_str = datetime.datetime.now().strftime("%I:%M %p").lstrip("0")
        return True, f"It's {now_str}.", "time"

    elif tool_name == "repeat_last_phrase":
        from speech_output import output_for
        out = output_for(app)
        last = out.get_last_spoken(max_age_seconds=300)
        if last:
            return True, f"I said: {last['text']}", "replay"
        else:
            return True, "I haven't said anything in the last five minutes.", "replay"

    elif tool_name == "open_tv_viewer":
        active_sid = app.cfg.get('active_scene')
        scene_props = app.cfg.get('scenes', {}).get(active_sid, {}).get('props', [])
        tv_prop = next((p for p in scene_props if p.get('interaction') in ('tv', 'overlay_popup') or 'tv' in p.get('id', '').lower()), None)
        if tv_prop:
            try:
                from interactive_props import open_tv
                open_tv(app, tv_prop)
                return True, "Turning on the TV!", "tv"
            except Exception as e:
                logger.warning(f"Failed to open TV: {e}")
                return True, "The TV doesn't have any playable channels right now.", "tv"
        else:
            return True, "There isn't a television in this room.", "tv"

    return False, None, None

def query_cactus_needle(clean_text, app):
    """
    Tier 2: On-device Cactus Needle tool calling engine.
    Resolves natural language commands directly to structured Desk-Pal tool calls.
    Returns (matched: bool, reply: str or None, action: str or None).
    """
    settings = _get_ai_settings(app)
    if settings.get("intent_engine", "cactus_needle") != "cactus_needle":
        return False, None, None

    engine = _get_needle_engine()
    if engine is None:
        return False, None, None

    try:
        t0 = time.monotonic()
        res = engine.complete(clean_text)
        dt = time.monotonic() - t0
        calls = res.get("function_calls", [])
        conf = float(res.get("confidence", 0.0) or 0.0)
        logger.info(f"[VoiceRouter] Cactus Needle completed in {dt*1000:.0f}ms (conf: {conf:.2f}, calls: {len(calls)})")

        # Confidence gate: reject ambiguous or low-confidence hallucinated calls
        if conf < 0.35 or not calls:
            return False, None, None

        first_call = calls[0]
        tool_name = first_call.get("name")
        args = first_call.get("arguments", {})
        return _execute_needle_tool(tool_name, args, app)
    except Exception as e:
        logger.warning(f"[VoiceRouter] Cactus Needle inference failed: {e}")
        return False, None, None

def dispatch_voice_command(raw_text, app):
    """
    Main dispatch entry point:
    1. Tier 1: Check instant direct commands and app-configured voice triggers (<1ms).
    2. Tier 2: Check Cactus Needle On-Device Tool Caller (~2-3s on Pi 4 CPU, ~111MB RAM).
    3. Tier 3: Conversational fallback chain (configurable: External Ollama and/or On-Device Qwen).
    4. Friendly conversational fallback.
    """
    if not raw_text or not raw_text.strip():
        return None, "none"
        
    clean_text = raw_text.lower().strip()
    
    # Strip wake word if present
    for wake in ("hey deskpal", "hey desk-pal", "deskpal", "desk pal"):
        if clean_text.startswith(wake):
            clean_text = clean_text[len(wake):].strip(" ,.!?")
            break
            
    if not clean_text:
        return "I'm listening!", "none"

    logger.info(f"[VoiceRouter] Processing: '{clean_text}'")

    def _maybe_wake():
        if action != 'sleep':
            if hasattr(app, 'stand_and_face_user'):
                app.stand_and_face_user()
            elif getattr(app, 'is_sleeping', False) or getattr(app, 'active_rest_role', None):
                if hasattr(app, 'wake_from_standby'):
                    app.wake_from_standby(source='voice')

    # Tier 1: Instant Matcher
    matched, reply, action = match_core_and_app_command(clean_text, app)
    if matched:
        _maybe_wake()
        logger.info(f"[VoiceRouter] Tier 1 match (action: {action}): '{reply}'")
        return reply, action

    # Tier 2: Cactus Needle On-Device Tool Caller
    matched, reply, action = query_cactus_needle(clean_text, app)
    if matched:
        _maybe_wake()
        logger.info(f"[VoiceRouter] Tier 2 Cactus Needle response (action: {action}): '{reply}'")
        return reply, action

    # Tier 3: Conversational Fallback Chain (Split into Primary & Secondary fallbacks)
    settings = _get_ai_settings(app)
    primary = settings.get("chat_fallback_primary")
    secondary = settings.get("chat_fallback_secondary")
    if not primary and not secondary:
        chain = settings.get("chat_fallback_chain", ["local", "on_device"])
        if isinstance(chain, str):
            chain = [chain]
        primary = chain[0] if len(chain) > 0 else "local"
        secondary = chain[1] if len(chain) > 1 else "on_device"

    tiers_to_try = [p for p in (primary, secondary) if p and p not in ("none", "disabled")]
    for tier_prov in tiers_to_try:
        matched, reply, action = query_chat_fallback_tier(tier_prov, clean_text, app)
        if matched:
            _maybe_wake()
            logger.info(f"[VoiceRouter] Tier 3 Fallback ({tier_prov}) response: '{reply}'")
            return reply, action

    # Friendly conversational fallback
    _maybe_wake()
    fallback_reply = f"Right! I heard you say '{raw_text}', but I'm not quite sure what you'd like me to do with that!"
    logger.info(f"[VoiceRouter] Fallback: '{fallback_reply}'")
    return fallback_reply, "none"
