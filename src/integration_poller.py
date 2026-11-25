"""
Direct native integration poller for Desk-Pal.
Queries application HTTP endpoints directly from Desk-Pal.
"""
import copy
import json
import logging
import queue
import threading
import time
import urllib.parse
import urllib.request
from integration_state import value_at


def fetch_json(url, timeout=15, headers=None, retries=1, retry_delay=3.0):
    if not url.startswith(('http://', 'https://')):
        raise ValueError('Source URL must use HTTP or HTTPS')
    req_headers = {'User-Agent': 'Desk-Pal Native Poller'}
    if headers and isinstance(headers, dict):
        req_headers.update(headers)
    last_err = None
    for attempt in range(max(1, int(retries) + 1)):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.load(response)
        except Exception as err:
            last_err = err
            if attempt < retries:
                time.sleep(retry_delay)
    raise last_err


class IntegrationPoller:
    def __init__(self):
        self.results = queue.Queue()
        self.next_poll = {}
        self.active_threads = set()
        self.lock = threading.Lock()
        self.seen_tasks = {}
        self.initialized_apps = set()
        self.failure_counts = {}
        self.started_at = time.monotonic()

    def _map_task_to_event(self, text, actions):
        t = str(text).lower()
        for a in actions:
            ev = a.get('event')
            if ev and ev != '*' and ev.lower() in t:
                return ev
        for keywords, ev in [
            (('email', 'mail', 'inbox'), 'email_check'),
            (('comic',), 'comic_pull'),
            (('calendar', 'sweep', 'dedup'), 'calendar_sweep'),
            (('social', 'promot', 'post', 'blog', 'article'), 'social_promo'),
            (('movie', 'radar', 'cinema', 'film', 'vhs'), 'movie_radar'),
            (('game', 'release', 'gaming'), 'game_release'),
            (('fuel drop', 'price drop', 'fuel fell', 'cheaper fuel'), 'fuel_drop'),
            (('fuel', 'price', 'timesfm', 'stations', 'inference', 'poll'), 'fuel_update'),
            (('anomaly', 'flight deal', 'cheap flight', 'flight dislocation'), 'flight_anomaly'),
        ]:
            if any(k in t for k in keywords):
                return ev
        return 'task_active'

    def _dispatch_app_events(self, app, source, app_id, data, payload):
        actions = source.get('actions', [])
        if app_id not in self.seen_tasks:
            self.seen_tasks[app_id] = set()

        # 1. Process recent completed tasks (e.g. BMCBF & FuelTracker recent_events)
        recent = data.get('recent_events') or []
        if isinstance(recent, list) and recent:
            new_events = []
            for item in recent:
                if not isinstance(item, dict):
                    continue
                ev_label = item.get('event') or item.get('task')
                ev_time = item.get('timestamp') or ''
                if not ev_label:
                    continue
                task_sig = f"{ev_label}_{ev_time}"
                if task_sig not in self.seen_tasks[app_id]:
                    self.seen_tasks[app_id].add(task_sig)
                    new_events.append((ev_label, ev_time))

            # Only dispatch if app was already baseline-initialized
            if app_id in self.initialized_apps:
                for ev_label, ev_time in new_events:
                    matched_event = self._map_task_to_event(ev_label, actions)
                    ev_payload = dict(payload, event=matched_event, activity=ev_label,
                                      summary=f"{source.get('name', app_id)}: {ev_label}")
                    logging.info(f"[Poller] Dispatched native event '{matched_event}' for {app_id}: {ev_label}")
                    app.receive_telemetry_event(ev_payload)
            else:
                self.initialized_apps.add(app_id)

        # 2. Check current active task
        cur_task = data.get('current_task')
        if cur_task and data.get('is_busy'):
            cur_sig = f"current_{cur_task}"
            if cur_sig not in self.seen_tasks[app_id]:
                self.seen_tasks[app_id].add(cur_sig)
                matched = self._map_task_to_event(cur_task, actions)
                app.receive_telemetry_event(dict(payload, event=matched, activity=cur_task,
                                                 summary=f"{source.get('name', app_id)}: {cur_task}"))

        # 3. Check travel opportunities (e.g. Travel Radar flight_anomaly)
        opps = data.get('opportunities')
        if isinstance(opps, list) and opps:
            top = opps[0]
            deal_id = str(top.get('id') or top.get('whyNow') or top.get('hotelNeighborhood') or 'top_deal')
            if deal_id not in self.seen_tasks[app_id]:
                self.seen_tasks[app_id].add(deal_id)
                if app_id in self.initialized_apps:
                    is_anomaly = bool(top.get('isNewLow') or (top.get('flightSavingsPercent', 0) >= 40))
                    ev = 'flight_anomaly' if is_anomaly else 'status_check'
                    title = top.get('whyNow') or top.get('hotelNeighborhood') or f"{top.get('origin', 'BNE')} Flight Deal"
                    ev_payload = dict(payload, event=ev, activity=title, summary=f"Flight Deal: {title}")
                    logging.info(f"[Poller] Dispatched flight deal event '{ev}' for {app_id}: {title}")
                    app.receive_telemetry_event(ev_payload)
                else:
                    self.initialized_apps.add(app_id)

        # 4. Check fuel price drops and updates (Fuel Tracker)
        if source.get('adapter') == 'fuel_tracker':
            cur_price = data.get('price')
            cur_station = data.get('station')
            fuel_type_label = str(data.get('fuel_type') or 'fuel').upper()
            if isinstance(cur_price, (int, float)):
                last_price_key = f"last_price_{app_id}"
                last_station_key = f"last_station_{app_id}"
                prev_price = getattr(self, last_price_key, None)
                prev_station = getattr(self, last_station_key, None)
                setattr(self, last_price_key, cur_price)
                setattr(self, last_station_key, cur_station)

                if app_id in self.initialized_apps and prev_price is not None:
                    if cur_price < prev_price - 2.0:
                        drop = round(prev_price - cur_price, 1)
                        drop_msg = f"Cheapest nearby {fuel_type_label} fell {drop} cents to {cur_price:.1f}¢/L at {cur_station or 'cheapest station'}"
                        logging.info(f"[Poller] Dispatched fuel_drop alert for {app_id}: {drop_msg}")
                        app.receive_telemetry_event(dict(payload, event='fuel_drop', summary=drop_msg,
                                                         activity=drop_msg, attention_needed=True, voice_escalation=True))
                    elif cur_price != prev_price or cur_station != prev_station:
                        upd_msg = data.get('summary') or f"Nearby {fuel_type_label} updated to {cur_price:.1f}¢/L at {cur_station}"
                        logging.info(f"[Poller] Dispatched fuel_update for {app_id}: {upd_msg}")
                        app.receive_telemetry_event(dict(payload, event='fuel_update', summary=upd_msg,
                                                         activity=upd_msg, attention_needed=False))
                else:
                    self.initialized_apps.add(app_id)

    def tick(self, app):
        # 1. Ingest any completed background poll results
        while not self.results.empty():
            try:
                app_id, result = self.results.get_nowait()
            except queue.Empty:
                break
            with self.lock:
                self.active_threads.discard(app_id)

            source = next((a for a in getattr(app, 'apps', []) if a.get('id') == app_id), None)
            if not source:
                continue

            interval = max(5, int(source.get('poll_seconds', 30)))
            if 'error' in result:
                self.failure_counts[app_id] = self.failure_counts.get(app_id, 0) + 1
                cached = app.app_telemetry.get(app_id, {}).get('received_events', {}).get('heartbeat', {}).get('data', {})
                existing_summary = cached.get('summary') if cached else None
                err_str = str(result['error'])
                # Require 5+ consecutive failed polls (each with retry, past 45s startup grace) before escalating to offline outage
                past_grace = (time.monotonic() - getattr(self, 'started_at', 0)) >= 45.0
                if past_grace and self.failure_counts[app_id] >= 5:
                    summary_text = f"{source.get('name', app_id)} is unreachable ({err_str})"
                    status = 'offline'
                else:
                    summary_text = f"{source.get('name', app_id)} connection warning ({err_str})"
                    status = 'warning'
                app.receive_heartbeat(dict(cached or {}, app_id=app_id, status=status,
                                           summary=summary_text,
                                           refresh_error=err_str, ttl_seconds=interval * 3))
            else:
                self.failure_counts[app_id] = 0
                data = result['data']
                summary = result['summary']
                previous = app.app_telemetry.get(app_id, {}).get('received_events', {}).get('heartbeat', {}).get('data', {})
                # Check for significant state changes
                changed = any(previous.get(k) != v for k, v in data.items() if k not in ('cached_at', 'timestamp', 'last_seen'))
                payload = dict(data, app_id=app_id, summary=summary, status=data.get('status', 'healthy'),
                               cached_at=time.time(), ttl_seconds=interval * 3)
                app.receive_heartbeat(payload)

                # Natively dispatch specific task events (email checks, comic pulls, etc.)
                self._dispatch_app_events(app, source, app_id, data, payload)

                # Only auto-dispatch integration_events for generic JSON endpoints that do not have dedicated monitors
                if changed and source.get('integration_events') and source.get('adapter') not in ('wellness_check', 'fuel_tracker', 'travel_radar', 'bmcbf') and app_id != 'wellness_check':
                    ev_name = source['integration_events'][0].get('name', 'status_check')
                    app.receive_telemetry_event(dict(payload, event=ev_name))

        # 2. Check which configured apps are due for polling
        now = time.monotonic()
        apps = getattr(app, 'apps', []) or app.cfg.get('apps', [])
        for a in apps:
            app_id = a.get('id')
            url = a.get('source_url', '').strip()
            # If source_enabled is False, or no url configured, skip polling
            if not url or a.get('source_enabled') is False:
                continue
            # Weather has its own Open-Meteo poller
            if a.get('built_in') in ('weather', 'sensors'):
                continue

            interval = max(5, int(a.get('poll_seconds', 30)))
            if now < self.next_poll.get(app_id, 0):
                continue

            with self.lock:
                if app_id in self.active_threads:
                    continue
                self.active_threads.add(app_id)

            self.next_poll[app_id] = now + interval
            self._spawn_worker(app_id, copy.deepcopy(a), url)

    def _spawn_worker(self, app_id, app_cfg, url):
        def worker():
            try:
                adapter = app_cfg.get('adapter', 'json')
                if adapter == 'fuel_tracker':
                    st = app_cfg.get('settings', {})
                    postcode = str(st.get('postcode', '0000'))
                    fuel_type = str(st.get('fuel_type', 'u98')).lower().strip()
                    radius_km = float(st.get('radius_km', 5.0))

                    parsed = urllib.parse.urlparse(url)
                    base_url = f"{parsed.scheme}://{parsed.netloc}"
                    query_url = f"{base_url}/api/v1/query?postcode={postcode}&fuel_type={fuel_type}&radius_km={radius_km}"
                    status_url = f"{base_url}/api/v1/status?fuel_type={fuel_type}&postcode={postcode}&radius_km={radius_km}"

                    try:
                        raw_data = fetch_json(query_url, timeout=15)
                    except Exception:
                        raw_data = fetch_json(status_url, timeout=15)

                    if not isinstance(raw_data, dict):
                        raise ValueError('Fuel Tracker did not return a valid object')

                    cheapest = raw_data.get('cheapest_station') or {}
                    price = cheapest.get('price_cents') if isinstance(cheapest, dict) else raw_data.get('price')
                    station_name = cheapest.get('name') if isinstance(cheapest, dict) else raw_data.get('station')
                    summary = raw_data.get('summary')
                    if not summary and price:
                        summary = f"Cheapest {fuel_type.upper()}: {price:.1f}¢ at {station_name} ({postcode})"
                    elif not summary:
                        summary = f"Fuel Tracker ({fuel_type.upper()}): {postcode}"

                    forecast = raw_data.get('forecast') or {}
                    cluster = raw_data.get('cluster_stats') or {}
                    recommendation = raw_data.get('recommendation') or 'BUY NOW'

                    data = dict(raw_data)
                    data['summary'] = summary
                    data['button_summary'] = summary
                    data['price'] = price
                    data['station'] = station_name
                    data['fuel_type'] = fuel_type
                    data['postcode'] = postcode
                    data['radius_km'] = radius_km
                    data['badge'] = f"{price:.1f}¢" if price is not None else None
                    avg_c = cluster.get('average_price_cents')
                    trend = str(forecast.get('trend') or 'Steady').title()
                    data['dashboard'] = {
                        'hero_value': f"{price:.1f}¢/L" if price is not None else None,
                        'hero_subhead': station_name,
                        'badge': recommendation,
                        'tiles': [
                            {'label': 'Avg', 'value': f"{avg_c:.1f}¢" if isinstance(avg_c, (int, float)) else str(avg_c or 'N/A')},
                            {'label': 'Trend', 'value': trend}
                        ]
                    }
                    self.results.put((app_id, {'data': data, 'summary': str(summary)}))
                    return

                req_headers = {}
                auth_tok = app_cfg.get('auth_token') or app_cfg.get('settings', {}).get('auth_token')
                if auth_tok:
                    req_headers['Authorization'] = f"Bearer {auth_tok.strip()}"
                api_k = app_cfg.get('api_key') or app_cfg.get('settings', {}).get('api_key')
                if api_k:
                    req_headers['X-API-Key'] = api_k.strip()
                raw_data = fetch_json(url, timeout=10, headers=req_headers)
                if not isinstance(raw_data, dict):
                    raise ValueError('Endpoint did not return a JSON object')

                # Support standard summary field lookup or specific adapter data formats
                sum_field = app_cfg.get('summary_field', 'summary')
                summary = (value_at(raw_data, sum_field)
                           or raw_data.get('summary'))

                # Smart fallback for opportunities (e.g. Travel Radar / travel-track)
                if not summary and isinstance(raw_data.get('opportunities'), list) and raw_data['opportunities']:
                    top = raw_data['opportunities'][0]
                    title = top.get('whyNow') or top.get('hotelNeighborhood') or f"{top.get('origin', 'BNE')} to {top.get('destination', 'Flight Deal')}"
                    price = top.get('flightDeal') or top.get('price')
                    savings = top.get('flightSavingsPercent') or top.get('savings_pct')
                    if price and savings:
                        summary = f"{title} (${int(price)}, {savings}% off)"
                    elif price:
                        summary = f"{title} (${int(price)})"
                    else:
                        summary = str(title)

                # Smart fallback for ticker data if activity is idle
                if not summary:
                    act = raw_data.get('activity')
                    ticker = raw_data.get('ticker')
                    if ticker and isinstance(ticker, list) and ticker:
                        first_ticker = str(ticker[0])
                        if act and 'idle' not in str(act).lower():
                            summary = f"{act} - {first_ticker}"
                        else:
                            summary = first_ticker
                    elif act:
                        summary = str(act)
                    else:
                        summary = raw_data.get('message') or f"{app_cfg.get('name', app_id)} online"

                # If dashboard layout elements are available, pass them cleanly
                data = dict(raw_data)
                self.results.put((app_id, {'data': data, 'summary': str(summary)}))
            except Exception as e:
                self.results.put((app_id, {'error': str(e)[:200]}))

        threading.Thread(target=worker, name=f'deskpal-poller-{app_id}', daemon=True).start()
